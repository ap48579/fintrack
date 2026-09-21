"""House Clerk financial disclosure client — Periodic Transaction Reports (PTRs), the
congressional-trade source (Pillar 3's third leg, alongside Form 4 and 13F).

The Clerk publishes one ZIP per year containing an XML index of every filing (all types —
annual, PTR, extension requests, etc.); PTRs are FilingType "P". Each PTR's PDF is then fetched
by a fixed URL pattern keyed on year + DocID. Both endpoints are unauthenticated and undocumented
but stable — the same approach used by the well-known unofficial congress-trading datasets
(house-stock-watcher and similar). No API key or rate limit is published for this site, but
requests still carry a descriptive User-Agent as a courtesy, matching the EDGAR client."""

import io
import re
import zipfile
from datetime import datetime

import httpx

_HEADERS = {"User-Agent": "FinTrack/0.1 (dev@fintrack.local; research use)"}
_INDEX_ZIP_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
_PTR_PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

_MEMBER_RE = re.compile(r"<Member>(.*?)</Member>", re.S)
_FIELD_RE = re.compile(r"<(\w+)>(.*?)</\1>", re.S)


class HouseClerkNotFound(Exception):
    pass


def _get(url: str, **kwargs) -> httpx.Response:
    kwargs.setdefault("headers", _HEADERS)
    kwargs.setdefault("timeout", 20)
    return httpx.get(url, **kwargs)


def list_ptr_filings(year: int) -> list[dict]:
    """Every Periodic Transaction Report filed in `year`, from the Clerk's annual index. The
    index mixes all disclosure types (annual reports, extensions, terminations, PTRs); only
    FilingType "P" rows are PTRs and are returned here."""
    resp = _get(_INDEX_ZIP_URL.format(year=year))
    if resp.status_code == 404:
        raise HouseClerkNotFound(f"No financial disclosure index for year {year}")
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        xml_name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        xml_text = zf.read(xml_name).decode("utf-8-sig")

    filings = []
    for block in _MEMBER_RE.findall(xml_text):
        fields = dict(_FIELD_RE.findall(block))
        if fields.get("FilingType") != "P":
            continue
        doc_id = fields.get("DocID")
        filing_date_str = fields.get("FilingDate")
        if not doc_id or not filing_date_str:
            continue
        filings.append(
            {
                "doc_id": doc_id,
                "year": year,
                "first": fields.get("First", "").strip(),
                "last": fields.get("Last", "").strip(),
                "state_dst": fields.get("StateDst", "").strip(),
                "filing_date": datetime.strptime(filing_date_str, "%m/%d/%Y").date(),
            }
        )
    return filings


def get_ptr_pdf_bytes(doc_id: str, year: int) -> bytes:
    resp = _get(_PTR_PDF_URL.format(year=year, doc_id=doc_id))
    if resp.status_code == 404:
        raise HouseClerkNotFound(f"No PTR PDF found for doc_id {doc_id} ({year})")
    resp.raise_for_status()
    return resp.content
