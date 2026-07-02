from __future__ import annotations

import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta

import httpx

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "FinTrack/0.1 (dev@fintrack.local)"}
_ARCHIVE_BASE = "https://www.sec.gov/Archives/edgar/data"


def _fetch_form4_transactions(cik: str, months: int = 6) -> list[dict]:
    from app.clients.edgar_client import get_submissions

    submissions = get_submissions(cik)
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    cutoff = (date.today() - timedelta(days=months * 30)).isoformat()
    results = []

    for i, form in enumerate(forms):
        if form != "4":
            continue
        filing_date = dates[i] if i < len(dates) else ""
        if filing_date < cutoff:
            continue

        accession_clean = accessions[i].replace("-", "") if i < len(accessions) else ""
        doc = docs[i] if i < len(docs) else ""
        if not accession_clean or not doc:
            continue

        url = f"{_ARCHIVE_BASE}/{int(cik)}/{accession_clean}/{doc}"
        try:
            resp = httpx.get(url, headers=_HEADERS, timeout=15)
            resp.raise_for_status()
            transactions = _parse_form4_xml(resp.text, filing_date)
            results.extend(transactions)
        except Exception as exc:
            logger.debug("Could not fetch/parse Form 4 at %s: %s", url, exc)

        if len(results) >= 20:
            break

    return results


def _parse_form4_xml(xml_text: str, filing_date: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    ns = {"": ""}

    def find_text(node, path: str) -> str:
        el = node.find(path)
        if el is None:
            return ""
        # Form 4 wraps values in <value> sub-elements
        val_el = el.find("value")
        return (val_el.text or "").strip() if val_el is not None else (el.text or "").strip()

    # Owner name
    owner_name = ""
    owner_el = root.find(".//reportingOwner/reportingOwnerId/rptOwnerName")
    if owner_el is not None:
        owner_name = (owner_el.text or "").strip()

    role = ""
    for tag in ["isDirector", "isOfficer", "isTenPercentOwner"]:
        el = root.find(f".//reportingOwnerRelationship/{tag}")
        if el is not None and (el.text or "").strip() == "1":
            if tag == "isOfficer":
                title_el = root.find(".//reportingOwnerRelationship/officerTitle")
                role = (title_el.text or "Officer").strip() if title_el is not None else "Officer"
            else:
                role = {"isDirector": "Director", "isTenPercentOwner": "10%+ Owner"}.get(tag, tag)
            break

    records = []
    for txn in root.findall(".//nonDerivativeTable/nonDerivativeTransaction"):
        acquired_disposed = find_text(txn, "transactionAmounts/transactionAcquiredDisposedCode")
        shares_str = find_text(txn, "transactionAmounts/transactionShares")
        price_str = find_text(txn, "transactionAmounts/transactionPricePerShare")
        txn_date = find_text(txn, "transactionDate")

        try:
            shares = float(shares_str) if shares_str else 0.0
            price = float(price_str) if price_str else 0.0
        except ValueError:
            continue

        if shares == 0:
            continue

        direction = "buy" if acquired_disposed == "A" else "sell" if acquired_disposed == "D" else "other"
        records.append({
            "owner": owner_name,
            "role": role,
            "direction": direction,
            "shares": shares,
            "price_per_share": price,
            "value_usd": round(shares * price, 2),
            "transaction_date": txn_date or filing_date,
            "filing_date": filing_date,
        })

    return records


class InsiderTradesTool(Tool):
    name = "get_insider_trades"
    description = (
        "Fetch recent insider transactions (Form 4) for a ticker from SEC EDGAR. "
        "Shows executive/director buys and sells with share counts and prices. "
        "Buy signals from insiders using personal money are high-conviction signals. "
        "Args: {\"ticker\": \"NVDA\", \"months\": 6}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        months = int(args.get("months", 6))
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            from app.clients.edgar_client import get_cik_for_ticker

            cik = await asyncio.to_thread(get_cik_for_ticker, ticker)
            transactions = await asyncio.to_thread(_fetch_form4_transactions, cik, months)

            if not transactions:
                return ToolResult(content={"ticker": ticker, "transactions": [], "summary": "No insider transactions found in the last 6 months"})

            buys = [t for t in transactions if t["direction"] == "buy"]
            sells = [t for t in transactions if t["direction"] == "sell"]
            total_buy_value = sum(t["value_usd"] for t in buys)
            total_sell_value = sum(t["value_usd"] for t in sells)

            return ToolResult(
                content={
                    "ticker": ticker,
                    "period_months": months,
                    "summary": {
                        "buy_transactions": len(buys),
                        "sell_transactions": len(sells),
                        "total_buy_value_usd": total_buy_value,
                        "total_sell_value_usd": total_sell_value,
                        "net_signal": "bullish" if total_buy_value > total_sell_value else "bearish" if total_sell_value > total_buy_value else "neutral",
                    },
                    "transactions": transactions[:15],
                },
                tokens=len(str(transactions)) // 4,
            )
        except Exception as exc:
            logger.warning("Insider trades tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
