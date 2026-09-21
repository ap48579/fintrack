"""Parses SEC Form 4 filings and stores open-market insider buys and sells.

Only transaction codes P (open-market purchase) and S (open-market sale) on the
non-derivative table are kept. Grants, option exercises, tax withholding, and gifts are
real Form 4 line items but aren't a discretionary buy/sell decision — mixing them in would
bury the signal ("any indication of buys and sells") under paperwork noise. Derivative-table
transactions (options, RSUs, OP units, etc.) are skipped for the same reason.

Idempotency mirrors whales_service: rows are keyed on a natural key (accession + insider +
ticker + transaction date/code/shares) and skipped if already present, so re-running a date
range is safe.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date, datetime
from xml.etree.ElementTree import Element

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients import edgar_client
from app.models.insiders import Insider, InsiderTrade
from app.models.ticker import Ticker

logger = logging.getLogger(__name__)

_RELEVANT_CODES = {"P": "buy", "S": "sell"}


def _text(el: Element | None, tag: str) -> str | None:
    if el is None:
        return None
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else None


def _value(el: Element | None, tag: str) -> str | None:
    if el is None:
        return None
    return _text(el.find(tag), "value")


def parse_form4_xml(xml_text: str) -> dict | None:
    """Returns issuer info, reporting owner(s), and any open-market P/S transactions found.
    Returns None for filings with nothing relevant to store (pure grant/derivative filings,
    which are the majority of Form 4s)."""
    root = ET.fromstring(xml_text)

    issuer = root.find("issuer")
    issuer_symbol = _text(issuer, "issuerTradingSymbol")
    if not issuer_symbol:
        return None  # no ticker to attach the trade to (rare, but seen on some filings)

    owners = []
    for owner_el in root.findall("reportingOwner"):
        owner_id = owner_el.find("reportingOwnerId")
        relationship = owner_el.find("reportingOwnerRelationship")
        cik = _text(owner_id, "rptOwnerCik")
        name = _text(owner_id, "rptOwnerName")
        if not cik or not name:
            continue
        owners.append(
            {
                "cik": cik,
                "name": name,
                "is_director": _text(relationship, "isDirector") == "1",
                "is_officer": _text(relationship, "isOfficer") == "1",
                "is_ten_percent_owner": _text(relationship, "isTenPercentOwner") == "1",
                "officer_title": _text(relationship, "officerTitle"),
            }
        )
    if not owners:
        return None

    transactions = []
    non_deriv = root.find("nonDerivativeTable")
    for txn in (non_deriv.findall("nonDerivativeTransaction") if non_deriv is not None else []):
        coding = txn.find("transactionCoding")
        code = _text(coding, "transactionCode")
        if code not in _RELEVANT_CODES:
            continue

        amounts = txn.find("transactionAmounts")
        shares_str = _value(amounts, "transactionShares")
        txn_date_str = _value(txn, "transactionDate")
        if not shares_str or not txn_date_str:
            continue

        price_str = _value(amounts, "transactionPricePerShare")
        owned_after_str = _value(txn.find("postTransactionAmounts"), "sharesOwnedFollowingTransaction")
        direct_or_indirect = _value(txn.find("ownershipNature"), "directOrIndirectOwnership")

        transactions.append(
            {
                "transaction_date": datetime.strptime(txn_date_str, "%Y-%m-%d").date(),
                "transaction_code": code,
                "direction": _RELEVANT_CODES[code],
                "shares": float(shares_str),
                "price_per_share": float(price_str) if price_str else None,
                "shares_owned_after": float(owned_after_str) if owned_after_str else None,
                "is_direct": direct_or_indirect != "I",
            }
        )

    if not transactions:
        return None

    return {
        "issuer_symbol": issuer_symbol.upper(),
        "issuer_name": _text(issuer, "issuerName"),
        "owners": owners,
        "transactions": transactions,
    }


def _get_or_create_insider(db: Session, cik: str, name: str) -> Insider:
    insider = db.scalar(select(Insider).where(Insider.cik == cik))
    if insider:
        return insider
    insider = Insider(cik=cik, name=name)
    db.add(insider)
    db.flush()
    return insider


def _get_or_create_ticker_by_symbol(db: Session, symbol: str, name: str | None) -> Ticker:
    ticker = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker:
        return ticker
    ticker = Ticker(symbol=symbol, name=name or symbol)
    db.add(ticker)
    db.flush()
    return ticker


def _trade_exists(db: Session, accession_no: str, insider_id, ticker_id, txn: dict) -> bool:
    return (
        db.scalar(
            select(InsiderTrade.id).where(
                InsiderTrade.accession_no == accession_no,
                InsiderTrade.insider_id == insider_id,
                InsiderTrade.ticker_id == ticker_id,
                InsiderTrade.transaction_date == txn["transaction_date"],
                InsiderTrade.transaction_code == txn["transaction_code"],
                InsiderTrade.shares == txn["shares"],
            )
        )
        is not None
    )


def ingest_form4_filing(db: Session, accession: str, doc: str, ciks: list[str], filed_date: date) -> list[InsiderTrade]:
    """Fetches, parses, and stores one Form 4 filing's open-market transactions. Safe to
    re-run — existing rows are detected and skipped rather than duplicated."""
    if not ciks:
        return []

    xml_text = edgar_client.get_form4_xml(ciks, accession, doc)
    parsed = parse_form4_xml(xml_text)
    if not parsed:
        return []

    ticker = _get_or_create_ticker_by_symbol(db, parsed["issuer_symbol"], parsed["issuer_name"])

    stored: list[InsiderTrade] = []
    for owner in parsed["owners"]:
        insider = _get_or_create_insider(db, owner["cik"], owner["name"])
        for txn in parsed["transactions"]:
            if _trade_exists(db, accession, insider.id, ticker.id, txn):
                continue
            trade = InsiderTrade(
                insider_id=insider.id,
                ticker_id=ticker.id,
                accession_no=accession,
                filed_date=filed_date,
                transaction_date=txn["transaction_date"],
                transaction_code=txn["transaction_code"],
                direction=txn["direction"],
                shares=txn["shares"],
                price_per_share=txn["price_per_share"],
                shares_owned_after=txn["shares_owned_after"],
                is_direct=txn["is_direct"],
                is_director=owner["is_director"],
                is_officer=owner["is_officer"],
                is_ten_percent_owner=owner["is_ten_percent_owner"],
                officer_title=owner["officer_title"],
            )
            db.add(trade)
            stored.append(trade)
    db.flush()
    return stored


def ingest_form4_range(db: Session, start_date: date, end_date: date, max_filings: int | None = None) -> int:
    """Pages through EDGAR full-text search for every Form 4 filed in [start_date, end_date]
    and ingests each one, committing after each filing so a mid-run failure doesn't lose
    earlier progress. Returns the count of new insider trade rows stored."""
    total_stored = 0
    total_seen = 0
    frm = 0
    while True:
        hits, total = edgar_client.search_form4_filings(start_date, end_date, frm=frm)
        if not hits:
            break

        for hit in hits:
            if max_filings is not None and total_seen >= max_filings:
                logger.info("Reached max_filings=%s, stopping early", max_filings)
                return total_stored
            total_seen += 1
            try:
                stored = ingest_form4_filing(db, hit["accession"], hit["doc"], hit["ciks"], hit["filed_date"])
                if stored:
                    db.commit()
                    total_stored += len(stored)
            except Exception:
                logger.exception("Failed to ingest Form 4 filing %s", hit["accession"])
                db.rollback()

            if total_seen % 50 == 0:
                logger.info("Processed %s/%s Form 4 filings (%s trades stored so far)", total_seen, total, total_stored)

        frm += len(hits)
        if frm >= total:
            break

    return total_stored
