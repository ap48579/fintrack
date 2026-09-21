"""SEC EDGAR client — XBRL company facts (Pillar 2), submissions/filing history,
Form 13F holdings (Pillar 3), and Form 4 insider transactions.

SEC requires a descriptive User-Agent identifying the requester and rate-limits to roughly
10 requests/second; see https://www.sec.gov/os/webmaster-faq#developers. Every request in this
module goes through `_get`, which enforces both."""

import re
import threading
import time
from datetime import date, datetime
from difflib import SequenceMatcher

import httpx

_HEADERS = {"User-Agent": "FinTrack/0.1 (dev@fintrack.local)"}
_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_INDEX_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
_FILING_DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{doc}"
_FULL_TEXT_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
_DISPLAY_NAME_RE = re.compile(r"^(.*?)\s*\(CIK (\d{10})\)$")

# Keeps every request in this module under SEC's ~10 req/sec guidance, including the bulk
# Form 4 discovery loop which can otherwise fire hundreds of requests back-to-back.
_MIN_REQUEST_INTERVAL = 0.11
_rate_limit_lock = threading.Lock()
_last_request_at = 0.0

# A large backfill runs for hours and makes tens of thousands of requests to SEC's full-text
# search index, which returns the occasional transient 500/503 under sustained load — without a
# retry, one such blip aborts the entire run (this is exactly what killed the first multi-month
# Form 4 backfill, partway through, with no way to resume other than restarting from scratch).
_MAX_RETRIES = 4
_RETRY_BACKOFF_BASE = 1.5


def _get(url: str, **kwargs) -> httpx.Response:
    global _last_request_at

    for attempt in range(_MAX_RETRIES + 1):
        with _rate_limit_lock:
            wait = _last_request_at + _MIN_REQUEST_INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_request_at = time.monotonic()
        kwargs.setdefault("headers", _HEADERS)
        kwargs.setdefault("timeout", 15)
        try:
            resp = httpx.get(url, **kwargs)
        except httpx.TransportError:
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(_RETRY_BACKOFF_BASE**attempt)
            continue

        if resp.status_code >= 500 and attempt < _MAX_RETRIES:
            time.sleep(_RETRY_BACKOFF_BASE**attempt)
            continue
        return resp

    raise AssertionError("unreachable")  # pragma: no cover


_ticker_to_cik_cache: dict[str, str] | None = None
_company_rows_cache: list[dict] | None = None  # [{"ticker": "NVDA", "name": "NVIDIA CORP", "cik": "..."}]


class EdgarNotFound(Exception):
    pass


def _load_company_rows() -> list[dict]:
    global _ticker_to_cik_cache, _company_rows_cache
    if _company_rows_cache is not None:
        return _company_rows_cache

    resp = _get(_TICKERS_URL)
    resp.raise_for_status()
    rows = resp.json().values()  # {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"}, ...}
    _company_rows_cache = [
        {"ticker": row["ticker"].upper(), "name": row["title"], "cik": str(row["cik_str"]).zfill(10)} for row in rows
    ]
    _ticker_to_cik_cache = {row["ticker"]: row["cik"] for row in _company_rows_cache}
    return _company_rows_cache


def _load_ticker_map() -> dict[str, str]:
    global _ticker_to_cik_cache
    if _ticker_to_cik_cache is None:
        _load_company_rows()
    return _ticker_to_cik_cache  # type: ignore[return-value]


def get_cik_for_ticker(symbol: str) -> str:
    mapping = _load_ticker_map()
    cik = mapping.get(symbol.upper())
    if not cik:
        raise EdgarNotFound(f"No CIK found for ticker {symbol.upper()}")
    return cik


def search_companies(query: str, limit: int = 8) -> list[dict]:
    """Typo-tolerant ticker/company-name search over SEC's full ~10k-issuer list (the same
    list `get_cik_for_ticker` uses), so searching "Apple" resolves to AAPL even though the
    `tickers` DB table only has rows for symbols someone has already looked up.

    Scored rather than a plain ILIKE so a prefix match on ticker or name ranks above a
    substring match, which ranks above a fuzzy (typo-tolerant) name match."""
    query = query.strip()
    if not query:
        return []
    q_lower = query.lower()
    q_upper = query.upper()

    scored: list[tuple[float, dict]] = []
    for row in _load_company_rows():
        ticker, name = row["ticker"], row["name"]
        name_lower = name.lower()
        score = 0.0

        if ticker == q_upper:
            score = 100.0
        elif ticker.startswith(q_upper):
            score = 90.0
        elif name_lower.startswith(q_lower):
            score = 80.0
        elif any(word.startswith(q_lower) for word in name_lower.split()):
            score = 70.0
        elif q_upper in ticker:
            score = 55.0
        elif q_lower in name_lower:
            score = 50.0
        else:
            ratio = SequenceMatcher(None, q_lower, name_lower).ratio()
            if ratio > 0.55:
                score = 40.0 * ratio

        if score > 0:
            scored.append((score, row))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [row for _, row in scored[:limit]]


def get_company_facts(cik: str) -> dict:
    resp = _get(_COMPANY_FACTS_URL.format(cik=cik))
    if resp.status_code == 404:
        raise EdgarNotFound(f"No company facts for CIK {cik}")
    resp.raise_for_status()
    return resp.json()


def get_submissions(cik: str) -> dict:
    resp = _get(_SUBMISSIONS_URL.format(cik=cik))
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
    resp = _get(url)
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

    resp = _get(_FILING_DOC_URL.format(cik=int(cik), accession=accession, doc=doc))
    resp.raise_for_status()
    return resp.text


def get_period_of_report(cik: str, accession: str) -> date:
    resp = _get(_FILING_DOC_URL.format(cik=int(cik), accession=accession, doc="primary_doc.xml"))
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
    resp = _get(_FULL_TEXT_SEARCH_URL, params={"q": name, "forms": "13F-HR"})
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


def search_form4_filings(start_date: date, end_date: date, frm: int = 0) -> tuple[list[dict], int]:
    """One page of Form 4 filings filed in [start_date, end_date], via EDGAR's full-text search
    index. This is how new tickers/insiders enter the universe — no pre-known CIK list needed.
    Returns (hits, total_hit_count); page forward by calling again with frm += len(hits)."""
    resp = _get(
        _FULL_TEXT_SEARCH_URL,
        params={
            "forms": "4",
            "dateRange": "custom",
            "startdt": start_date.isoformat(),
            "enddt": end_date.isoformat(),
            "from": frm,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    total = data["hits"]["total"]["value"]

    hits = []
    for hit in data["hits"]["hits"]:
        accession, doc = hit["_id"].split(":", 1)
        source = hit["_source"]
        filed_date_str = source.get("file_date")
        hits.append(
            {
                "accession": accession,
                "doc": doc,
                "ciks": source.get("ciks", []),
                "filed_date": datetime.strptime(filed_date_str, "%Y-%m-%d").date() if filed_date_str else end_date,
            }
        )
    return hits, total


def get_form4_xml(ciks: list[str], accession: str, doc: str) -> str:
    """Fetches a Form 4's ownership XML directly by its known filename (from the search hit's
    `_id`), skipping the filing-index lookup that 13F ingestion needs. EDGAR indexes each filing
    under every CIK named in it (owner and issuer alike), so each candidate CIK is tried in turn
    until one resolves — the search hit doesn't say which one owns the archive path."""
    accession_nodash = accession.replace("-", "")
    last_error: Exception | None = None
    for cik in ciks:
        try:
            resp = _get(_FILING_DOC_URL.format(cik=int(cik), accession=accession_nodash, doc=doc))
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPStatusError as exc:
            last_error = exc
            continue
    raise EdgarNotFound(f"No Form 4 document found for accession {accession} (tried CIKs {ciks})") from last_error
