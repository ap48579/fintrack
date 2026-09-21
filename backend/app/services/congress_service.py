"""Parses House Periodic Transaction Reports (PTRs) and stores open-market buys and sells.

PTRs are PDFs, but — as of 2026 filings, verified empirically against real filings before
writing this — they are electronically filed, text-based PDFs, not scanned images. pdfplumber
(pure Python, no OCR) extracts them reliably. A PDF that yields no table text at all (e.g. an
old scanned filing) is logged and skipped rather than guessed at — a failed parse must never
silently produce a trade.

Row layout is fiddlier than Form 4's clean XML: the form's "Asset" and "Amount" columns each
wrap across two physical lines, and pdfplumber's linear text flow interleaves those wrapped
halves in a way that doesn't match visual reading order (confirmed against real samples — this
is a PDF layout quirk, not an extraction bug). The parser below scopes each row's text between
consecutive "F/S/D" field-label lines (the form's own row separators) rather than trusting line
order, which fixes the interleaving. A known remaining rough edge: when a row's own "D:"
(description) field spans several lines, a trailing fragment of it can bleed into the *next*
row's asset_description text. This is cosmetic only — it never affects ticker, transaction type,
date, or amount, which is the buy/sell signal this exists to capture.

Only transaction types P (purchase) and S (sale) are stored — "E" (exchange) is neither cleanly
a buy nor a sell and is skipped, matching insider_service's treatment of non-P/S Form 4 codes.
"""

import io
import logging
import re
from datetime import date, datetime

import pdfplumber
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import house_clerk_client
from app.models.congress import CongressTrade, Legislator
from app.models.ticker import Ticker

logger = logging.getLogger(__name__)

_RELEVANT_TYPES = {"P": "buy", "S": "sell"}
_OWNER_CODES = {"SP": "spouse", "JT": "joint", "DC": "dependent_child"}

_TABLE_START_MARKER = "$200?"
_TABLE_END_MARKER = "* For the complete list"

_ANCHOR_RE = re.compile(
    r"(?P<type>[PSE])\s?(?:\(partial\))?\s+"
    r"(?P<txn_date>\d{2}/\d{2}/\d{4})\s+"
    r"(?P<notif_date>\d{2}/\d{2}/\d{4})"
)
_LABEL_LINE_RE = re.compile(r"^[A-Za-z][\x00]{2,}.*$", re.MULTILINE)
_TICKER_PAREN_RE = re.compile(r"\(([A-Z]{1,5}(?:\.[A-Z]{1,2})?)\)")
_TICKER_BRACKET_RE = re.compile(r"\b([A-Z]{2,5})\s*\[[A-Z]{2}\]")
_ASSET_TYPE_BRACKET_RE = re.compile(r"\[[A-Z]{2}\]")
_AMOUNT_RE = re.compile(r"\$[\d,]{4,}(?:\.\d+)?(?!\s*/\s*share)")
_OWNER_PREFIX_RE = re.compile(r"^\s*(SP|JT|DC)\b\s*")


def _extract_table_text(pdf) -> str:
    """Joins just the transactions-table portion of each page — between the repeated column
    header and the asset-type-code footnote — so cover-page and certification text can't
    pollute row scoping or get mistaken for a row."""
    chunks = []
    for page in pdf.pages:
        text = page.extract_text() or ""
        start = text.rfind(_TABLE_START_MARKER)
        if start == -1:
            continue
        start += len(_TABLE_START_MARKER)
        end = text.find(_TABLE_END_MARKER, start)
        chunks.append(text[start : end if end != -1 else len(text)])
    return "\n".join(chunks)


def _find_ticker(text: str) -> str | None:
    m = _TICKER_BRACKET_RE.search(text)
    if m:
        return m.group(1)
    m = _TICKER_PAREN_RE.search(text)
    if m:
        return m.group(1)
    return None


def _clean_description(blob: str) -> tuple[str, str | None]:
    lines = [l.strip() for l in blob.split("\n") if l.strip() and not _LABEL_LINE_RE.match(l.strip())]
    text = " ".join(lines)
    text = _TICKER_PAREN_RE.sub("", text)
    text = _TICKER_BRACKET_RE.sub("", text)
    text = _ASSET_TYPE_BRACKET_RE.sub("", text)
    owner = None
    m = _OWNER_PREFIX_RE.match(text)
    if m:
        owner = _OWNER_CODES[m.group(1)]
        text = text[m.end() :]
    return re.sub(r"\s+", " ", text).strip(" -")[:512], owner


def _to_float(raw: str | None) -> float | None:
    return None if raw is None else float(raw.replace("$", "").replace(",", ""))


def parse_ptr_pdf(pdf_bytes: bytes) -> list[dict]:
    """Returns one dict per open-market buy/sell row found. Returns [] for a filing with no
    extractable table text (scanned image) or no P/S rows (pure exchanges, or a filing type
    that slipped through the FilingType=='P' index filter)."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        text = _extract_table_text(pdf)
    if not text.strip():
        return []

    anchors = list(_ANCHOR_RE.finditer(text))
    label_starts = [m.start() for m in _LABEL_LINE_RE.finditer(text)]

    rows = []
    for i, anchor in enumerate(anchors):
        txn_type = anchor.group("type")
        if txn_type not in _RELEVANT_TYPES:
            continue

        next_label = next((ls for ls in label_starts if ls > anchor.end()), len(text))
        forward_scope = text[anchor.end() : next_label]

        prev_anchor_end = anchors[i - 1].end() if i > 0 else 0
        labels_before = [ls for ls in label_starts if prev_anchor_end <= ls < anchor.start()]
        if labels_before:
            line_end = text.find("\n", labels_before[-1])
            backward_start = line_end + 1 if line_end != -1 else labels_before[-1]
        else:
            backward_start = prev_anchor_end
        backward_scope = text[backward_start : anchor.start()]

        ticker = _find_ticker(forward_scope) or _find_ticker(backward_scope)
        amounts = _AMOUNT_RE.findall(forward_scope)
        if not amounts:
            continue  # no parseable amount — don't guess, skip this row
        description, owner = _clean_description(backward_scope)

        rows.append(
            {
                "line_no": i,
                "transaction_type": txn_type,
                "direction": _RELEVANT_TYPES[txn_type],
                "transaction_date": datetime.strptime(anchor.group("txn_date"), "%m/%d/%Y").date(),
                "notification_date": datetime.strptime(anchor.group("notif_date"), "%m/%d/%Y").date(),
                "amount_low": _to_float(amounts[0]),
                "amount_high": _to_float(amounts[1]) if len(amounts) > 1 else None,
                "amount_unbounded": len(amounts) == 1 and "+" in forward_scope[: forward_scope.find(amounts[0]) + 20],
                "ticker": ticker,
                "owner": owner,
                "description": description or "(description unavailable)",
            }
        )
    return rows


def _get_or_create_legislator(db: Session, name: str, state_dst: str | None) -> Legislator:
    legislator = db.scalar(select(Legislator).where(Legislator.name == name))
    if legislator:
        return legislator
    legislator = Legislator(name=name, state_dst=state_dst)
    db.add(legislator)
    db.flush()
    return legislator


def _get_or_create_ticker_by_symbol(db: Session, symbol: str) -> Ticker:
    ticker = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker:
        return ticker
    ticker = Ticker(symbol=symbol, name=symbol)
    db.add(ticker)
    db.flush()
    return ticker


def _trade_exists(db: Session, doc_id: str, line_no: int) -> bool:
    return (
        db.scalar(
            select(CongressTrade.id).where(CongressTrade.doc_id == doc_id, CongressTrade.line_no == line_no)
        )
        is not None
    )


def ingest_ptr_filing(
    db: Session, doc_id: str, year: int, legislator_name: str, state_dst: str, filed_date: date
) -> list[CongressTrade]:
    """Fetches, parses, and stores one PTR's open-market transactions. Safe to re-run."""
    pdf_bytes = house_clerk_client.get_ptr_pdf_bytes(doc_id, year)
    rows = parse_ptr_pdf(pdf_bytes)
    if not rows:
        return []

    legislator = _get_or_create_legislator(db, legislator_name, state_dst)

    stored: list[CongressTrade] = []
    for row in rows:
        if _trade_exists(db, doc_id, row["line_no"]):
            continue
        ticker = _get_or_create_ticker_by_symbol(db, row["ticker"]) if row["ticker"] else None
        trade = CongressTrade(
            legislator_id=legislator.id,
            ticker_id=ticker.id if ticker else None,
            doc_id=doc_id,
            line_no=row["line_no"],
            filed_date=filed_date,
            transaction_date=row["transaction_date"],
            notification_date=row["notification_date"],
            transaction_type=row["transaction_type"],
            direction=row["direction"],
            owner=row["owner"],
            asset_description=row["description"],
            amount_low=row["amount_low"],
            amount_high=row["amount_high"],
            amount_unbounded=row["amount_unbounded"],
        )
        db.add(trade)
        stored.append(trade)
    db.flush()
    return stored


def ingest_ptr_range(db: Session, start_date: date, end_date: date, max_filings: int | None = None) -> int:
    """Ingests every PTR filed in [start_date, end_date]. The Clerk's index is per calendar
    year, so a range spanning a year boundary pulls each year's index separately."""
    total_stored = 0
    total_seen = 0

    for year in range(start_date.year, end_date.year + 1):
        try:
            filings = house_clerk_client.list_ptr_filings(year)
        except house_clerk_client.HouseClerkNotFound:
            logger.info("No House Clerk disclosure index for year %s", year)
            continue

        in_range = [f for f in filings if start_date <= f["filing_date"] <= end_date]
        for filing in in_range:
            if max_filings is not None and total_seen >= max_filings:
                logger.info("Reached max_filings=%s, stopping early", max_filings)
                return total_stored
            total_seen += 1
            name = f"{filing['first']} {filing['last']}".strip()
            try:
                stored = ingest_ptr_filing(
                    db, filing["doc_id"], filing["year"], name, filing["state_dst"], filing["filing_date"]
                )
                if stored:
                    db.commit()
                    total_stored += len(stored)
            except Exception:
                logger.exception("Failed to ingest PTR doc_id %s (%s)", filing["doc_id"], name)
                db.rollback()

            if total_seen % 25 == 0:
                logger.info("Processed %s/%s PTRs in range (%s trades stored so far)", total_seen, len(in_range), total_stored)

    return total_stored
