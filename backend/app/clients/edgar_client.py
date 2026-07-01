"""SEC EDGAR client — XBRL company facts (Pillar 2), submissions/filing history, and
Form 13F holdings (Pillar 3).

SEC requires a descriptive User-Agent identifying the requester; see
https://www.sec.gov/os/webmaster-faq#developers."""

import re
from datetime import date, datetime

import httpx

_HEADERS = {"User-Agent": "FinTrack/0.1 (dev@fintrack.local)"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
_FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_DISPLAY_NAME_RE = re.compile(r"^(.*?)\s*\(CIK (\d{10})\)$")

_ticker_to_cik_cache: dict[str, str] | None = None


class EdgarNotFound(Exception):
    pass


def _load_ticker_map() -> dict[str, str]:
    global _ticker_to_cik_cache
    if _ticker_to_cik_cache is not None:
        return _ticker_to_cik_cache

    resp = httpx.get(_TICKERS_URL, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    rows = resp.json().values()  # {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
    _ticker_to_cik_cache = {row["ticker"].upper(): str(row["cik_str"]).zfill(10) for row in rows}
    return _ticker_to_cik_cache


def get_cik_for_ticker(symbol: str) -> str:
    mapping = _load_ticker_map()
    cik = mapping.get(symbol.upper())
    if not cik:
        raise EdgarNotFound(f"No CIK found for ticker {symbol.upper()}")
    return cik


def get_company_facts(cik: str) -> dict:
    resp = httpx.get(_COMPANY_FACTS_URL.format(cik=cik), headers=_HEADERS, timeout=15)
    if resp.status_code == 404:
        raise EdgarNotFound(f"No company facts for CIK {cik}")
    resp.raise_for_status()
    return resp.json()


def get_submissions(cik: str) -> dict:
    resp = httpx.get(_SUBMISSIONS_URL.format(cik=cik), headers=_HEADERS, timeout=15)
    if resp.status_code == 404:
        raise EdgarNotFound(f"No submissions for CIK {cik}")
    resp.raise_for_status()
    return resp.json()


def get_recent_filings(cik: str, forms: tuple[str, ...] = ("10-K", "10-Q"), limit: int = 10) -> list[dict]:
    submissions = get_submissions(cik)
    recent = submissions["filings"]["recent"]
    filings = []
    for i, form in enumerate(recent["form"]):
        if form not in forms:
            continue
        accession = recent["accessionNumber"][i].replace("-", "")
        primary_doc = recent["primaryDocument"][i]
        filings.append(
            {
                "filing_type": form,
                "filed_date": datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").date(),
                "edgar_url": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}/{primary_doc}",
            }
        )
        if len(filings) >= limit:
            break
    return filings


def get_latest_filing_date(cik: str, forms: tuple[str, ...] = ("10-K", "10-Q")) -> date | None:
    filings = get_recent_filings(cik, forms=forms, limit=1)
    return filings[0]["filed_date"] if filings else None


def get_13f_filings(cik: str, limit: int = 4) -> list[dict]:
    """Most recent 13F-HR filings (excludes /A amendments — see whales_service module docstring
    for why amendments are out of MVP scope). Returns accession numbers with dashes stripped,
    matching the directory-path convention used by the filing index/document URLs."""
    submissions = get_submissions(cik)
    recent = submissions["filings"]["recent"]
    filings = []
    for i, form in enumerate(recent["form"]):
        if form != "13F-HR":
            continue
        filings.append(
            {
                "accession": recent["accessionNumber"][i].replace("-", ""),
                "filed_date": datetime.strptime(recent["filingDate"][i], "%Y-%m-%d").date(),
            }
        )
        if len(filings) >= limit:
            break
    return filings


def _get_filing_documents(cik: str, accession: str) -> list[str]:
    url = _FILING_INDEX_URL.format(cik=int(cik), accession=accession)
    resp = httpx.get(url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return [item["name"] for item in resp.json()["directory"]["item"]]


def get_information_table_xml(cik: str, accession: str) -> str:
    """The 13F 'information table' (the actual holdings list) ships as a second XML document
    alongside primary_doc.xml (the cover page) — filers name it differently (infotable.xml,
    <numeric>.xml, <custom-name>.xml), so it's identified by elimination rather than a fixed name."""
    docs = _get_filing_documents(cik, accession)
    candidates = [d for d in docs if d.lower().endswith(".xml") and d.lower() != "primary_doc.xml"]
    if not candidates:
        raise EdgarNotFound(f"No information table document found for CIK {cik} accession {accession}")
    doc = max(candidates, key=len)  # if ever ambiguous, the longer/custom name is the real table

    resp = httpx.get(_FILING_DOC_URL.format(cik=int(cik), accession=accession, doc=doc), headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def get_period_of_report(cik: str, accession: str) -> date:
    resp = httpx.get(
        _FILING_DOC_URL.format(cik=int(cik), accession=accession, doc="primary_doc.xml"),
        headers=_HEADERS,
        timeout=15,
    )
    resp.raise_for_status()
    match = re.search(r"<periodOfReport>(.*?)</periodOfReport>", resp.text)
    if not match:
        raise EdgarNotFound(f"No periodOfReport found for CIK {cik} accession {accession}")
    return datetime.strptime(match.group(1), "%m-%d-%Y").date()


def search_institutions_by_name(name: str, limit: int = 8) -> list[dict]:
    """Searches EDGAR's full-text search index for 13F-HR filers matching `name`, used so a
    user can add a new tracked institution by name instead of needing to already know its CIK.

    Note: the older `browse-edgar?action=getcompany` company-search endpoint is unreliable for
    this — its ATOM output omits the company name entirely whenever a query matches more than
    one entity (a long-standing EDGAR quirk), so full-text search against actual 13F-HR filings
    (whose cover pages always carry a clean filer name) is used instead."""
    resp = httpx.get(
        _FULL_TEXT_SEARCH_URL, params={"q": name, "forms": "13F-HR"}, headers=_HEADERS, timeout=15
    )
    resp.raise_for_status()
    hits = resp.json().get("hits", {}).get("hits", [])

    seen: dict[str, str] = {}
    for hit in hits:
        for display_name in hit.get("_source", {}).get("display_names", []):
            match = _DISPLAY_NAME_RE.match(display_name)
            if match:
                seen.setdefault(match.group(2), match.group(1).strip())
        if len(seen) >= limit:
            break

    return [{"name": name, "cik": cik} for cik, name in list(seen.items())[:limit]]
