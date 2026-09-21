"""Parses SEC Form 13F information tables and maintains the holdings_quarterly /
holdings_changes tables.

Known simplifications (the "fiddly parsing" plan.md calls out):
- 13F-HR/A amendments are ignored — only the original 13F-HR per quarter is parsed. Amendments
  are rare corrections; handling supersession correctly is a v2 concern, not MVP.
- Large institutions often file one combined 13F covering several manager subsidiaries, so the
  same CUSIP can appear as multiple <infoTable> rows (one per sub-manager). These are summed by
  CUSIP into a single position before anything is persisted.
- 13F holdings are reported by CUSIP, not ticker. CUSIPs are resolved to ticker symbols via
  OpenFIGI's free API; unresolvable CUSIPs (rare for US-listed common stock) still get a Ticker
  row, keyed by a synthetic `CUSIP:<cusip>` symbol, so the position isn't silently dropped.
- Only the top `TOP_N_POSITIONS` holdings by market value are kept per institution per quarter.
  Quant managers (Renaissance Technologies' latest 13F: 3,213 distinct positions; Bridgewater:
  993) report thousands of small statistical-arbitrage positions that aren't meaningful "whale
  bets" and would both make OpenFIGI resolution take 20-30+ minutes per refresh (risking the free
  keyless tier's rate limit) and make "full portfolio" an unusable several-thousand-row table.
  Capping to the top holdings by value keeps the feature genuinely useful and the refresh fast.
"""

import logging
import xml.etree.ElementTree as ET
from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.clients import edgar_client, openfigi_client
from app.models.ticker import Ticker
from app.services import alert_engine
from app.models.whales import HoldingsChange, HoldingsQuarterly, Institution

logger = logging.getLogger(__name__)

TOP_N_POSITIONS = 75


def get_institution_by_identifier(db: Session, identifier: str) -> Institution | None:
    """Looks up by CIK (exact) first, falling back to a case-insensitive name match — lets API
    routes accept either a precise CIK or a human-friendly name like "Berkshire Hathaway Inc"."""
    institution = db.scalar(select(Institution).where(Institution.cik == identifier))
    if institution:
        return institution
    return db.scalar(select(Institution).where(Institution.name.ilike(identifier)))


def list_institutions(db: Session) -> list[Institution]:
    return list(db.scalars(select(Institution)).all())


def get_institution_overview(db: Session, institution: Institution) -> dict:
    """Summary stats for the whales list page — total portfolio value, position count, and
    QoQ value change — without needing to drill into the full holdings table first."""
    periods = _existing_periods(db, institution.id)
    base = {"cik": institution.cik, "name": institution.name}
    if not periods:
        return {
            **base,
            "period": None,
            "total_market_value": None,
            "position_count": 0,
            "value_change_pct": None,
            "new_positions": 0,
            "exited_positions": 0,
        }

    latest_period = periods[0]
    latest_rows = db.scalars(
        select(HoldingsQuarterly).where(
            HoldingsQuarterly.institution_id == institution.id, HoldingsQuarterly.period == latest_period
        )
    ).all()
    total_value = sum(float(r.market_value) for r in latest_rows)

    value_change_pct = None
    if len(periods) > 1:
        prior_rows = db.scalars(
            select(HoldingsQuarterly).where(
                HoldingsQuarterly.institution_id == institution.id, HoldingsQuarterly.period == periods[1]
            )
        ).all()
        prior_total = sum(float(r.market_value) for r in prior_rows)
        if prior_total > 0:
            value_change_pct = (total_value - prior_total) / prior_total * 100

    changes = db.scalars(
        select(HoldingsChange).where(
            HoldingsChange.institution_id == institution.id, HoldingsChange.period == latest_period
        )
    ).all()

    return {
        **base,
        "period": latest_period,
        "total_market_value": total_value,
        "position_count": len(latest_rows),
        "value_change_pct": value_change_pct,
        "new_positions": sum(1 for c in changes if c.change_type == "new"),
        "exited_positions": sum(1 for c in changes if c.change_type == "exit"),
    }


def get_institutions_overview(db: Session) -> list[dict]:
    return [get_institution_overview(db, inst) for inst in list_institutions(db)]


def add_institution(db: Session, name: str, cik: str) -> tuple[Institution, bool]:
    """Get-or-create plus an immediate (synchronous) refresh attempt, so a newly added
    institution shows real holdings right away rather than waiting for the weekly Celery task.
    A refresh failure (e.g. the CIK has no 13F-HR on file) doesn't prevent adding the row —
    the institution still appears in the tracked list, just with empty holdings until the next
    successful refresh."""
    institution = db.scalar(select(Institution).where(Institution.cik == cik))
    is_new = institution is None
    if is_new:
        institution = Institution(name=name, cik=cik)
        db.add(institution)
        db.commit()
        db.refresh(institution)

    try:
        refresh_institution_holdings(db, institution, force=True)
    except Exception:
        logger.exception("Initial refresh failed for newly added institution %s (%s)", name, cik)

    return institution, is_new


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def parse_information_table(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    entries = []
    for info_table in root:
        if _local_tag(info_table.tag) != "infoTable":
            continue
        fields = {_local_tag(child.tag): child for child in info_table}
        shares_el = fields.get("shrsOrPrnAmt")
        shares = None
        if shares_el is not None:
            for child in shares_el:
                if _local_tag(child.tag) == "sshPrnamt":
                    shares = int(child.text)
        issuer = fields["nameOfIssuer"].text
        cusip = fields["cusip"].text
        value = float(fields["value"].text)
        if shares is None or issuer is None or cusip is None:
            continue
        entries.append({"issuer": issuer.strip(), "cusip": cusip.strip(), "value": value, "shares": shares})
    return entries


def aggregate_by_cusip(entries: list[dict]) -> dict[str, dict]:
    aggregated: dict[str, dict] = {}
    for e in entries:
        bucket = aggregated.setdefault(e["cusip"], {"issuer": e["issuer"], "value": 0.0, "shares": 0})
        bucket["value"] += e["value"]
        bucket["shares"] += e["shares"]
    return aggregated


def _get_or_create_ticker_by_cusip(db: Session, cusip: str, issuer_name: str, resolved_symbol: str | None) -> Ticker:
    ticker = db.scalar(select(Ticker).where(Ticker.cusip == cusip))
    if ticker:
        return ticker

    symbol = resolved_symbol or f"CUSIP:{cusip}"
    ticker = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker:
        ticker.cusip = cusip
        return ticker

    ticker = Ticker(symbol=symbol, name=issuer_name, cusip=cusip)
    db.add(ticker)
    db.flush()
    return ticker


def _existing_periods(db: Session, institution_id) -> list[date]:
    rows = db.scalars(
        select(HoldingsQuarterly.period).where(HoldingsQuarterly.institution_id == institution_id).distinct()
    ).all()
    return sorted(rows, reverse=True)


def _fetch_and_store_period(db: Session, institution: Institution, cik: str, accession: str, period: date) -> None:
    xml_text = edgar_client.get_information_table_xml(cik, accession)
    aggregated = aggregate_by_cusip(parse_information_table(xml_text))

    top_cusips = sorted(aggregated, key=lambda c: aggregated[c]["value"], reverse=True)[:TOP_N_POSITIONS]
    aggregated = {c: aggregated[c] for c in top_cusips}

    resolved = openfigi_client.resolve_cusips(list(aggregated.keys()))

    for cusip, position in aggregated.items():
        ticker = _get_or_create_ticker_by_cusip(db, cusip, position["issuer"], resolved.get(cusip))
        existing = db.scalar(
            select(HoldingsQuarterly).where(
                HoldingsQuarterly.institution_id == institution.id,
                HoldingsQuarterly.ticker_id == ticker.id,
                HoldingsQuarterly.period == period,
            )
        )
        if existing:
            existing.shares = position["shares"]
            existing.market_value = position["value"]
        else:
            db.add(
                HoldingsQuarterly(
                    institution_id=institution.id,
                    ticker_id=ticker.id,
                    period=period,
                    shares=position["shares"],
                    market_value=position["value"],
                )
            )
    db.flush()


def _diff_periods(
    db: Session, institution: Institution, prior_period: date, current_period: date
) -> list[HoldingsChange]:
    prior_rows = db.execute(
        select(HoldingsQuarterly).where(
            HoldingsQuarterly.institution_id == institution.id, HoldingsQuarterly.period == prior_period
        )
    ).scalars().all()
    current_rows = db.execute(
        select(HoldingsQuarterly).where(
            HoldingsQuarterly.institution_id == institution.id, HoldingsQuarterly.period == current_period
        )
    ).scalars().all()

    prior_by_ticker = {r.ticker_id: r for r in prior_rows}
    current_by_ticker = {r.ticker_id: r for r in current_rows}

    changes: list[HoldingsChange] = []
    for ticker_id, current in current_by_ticker.items():
        prior = prior_by_ticker.get(ticker_id)
        if prior is None:
            change_type, magnitude = "new", float(current.shares)
        elif current.shares > prior.shares:
            change_type, magnitude = "increase", float(current.shares - prior.shares)
        elif current.shares < prior.shares:
            change_type, magnitude = "decrease", float(prior.shares - current.shares)
        else:
            continue
        change = HoldingsChange(
            institution_id=institution.id,
            ticker_id=ticker_id,
            period=current_period,
            change_type=change_type,
            magnitude=magnitude,
        )
        db.add(change)
        changes.append(change)

    for ticker_id, prior in prior_by_ticker.items():
        if ticker_id not in current_by_ticker:
            change = HoldingsChange(
                institution_id=institution.id,
                ticker_id=ticker_id,
                period=current_period,
                change_type="exit",
                magnitude=float(prior.shares),
            )
            db.add(change)
            changes.append(change)

    db.flush()
    return changes


def refresh_institution_holdings(db: Session, institution: Institution, force: bool = False) -> bool:
    """Fetches the latest 13F-HR for this institution. On a fresh institution (no holdings on
    record yet), backfills the two most recent filings so a same-day diff is possible. Returns
    True if any new data was parsed."""
    filings = edgar_client.get_13f_filings(institution.cik, limit=2)
    if not filings:
        return False

    known_periods = _existing_periods(db, institution.id)
    latest_filing = filings[0]
    latest_period = edgar_client.get_period_of_report(institution.cik, latest_filing["accession"])

    if not force and known_periods and latest_period <= known_periods[0]:
        return False  # no new filing since our last check

    is_fresh = not known_periods
    if is_fresh and len(filings) > 1:
        prior_filing = filings[1]
        prior_period = edgar_client.get_period_of_report(institution.cik, prior_filing["accession"])
        _fetch_and_store_period(db, institution, institution.cik, prior_filing["accession"], prior_period)
        known_periods = [prior_period]

    _fetch_and_store_period(db, institution, institution.cik, latest_filing["accession"], latest_period)

    if known_periods and known_periods[0] < latest_period:
        changes = _diff_periods(db, institution, known_periods[0], latest_period)
        for change in changes:
            ticker = db.get(Ticker, change.ticker_id)
            if ticker:
                alert_engine.evaluate_whale_alert(db, change, ticker, institution)

    db.commit()
    return True


def backfill_institution_history(db: Session, institution: Institution, target_quarters: int = 8) -> int:
    """Walks an institution's 13F-HR history back further than refresh_institution_holdings ever
    does (that function only ever keeps 2 quarters' worth of diff-basis). Fetches up to
    `target_quarters` most recent filings, stores any periods not already on record, and diffs
    each consecutive pair that hasn't been diffed yet. Returns the number of new HoldingsChange
    rows created. Safe to re-run — skips periods/diffs already present instead of duplicating."""
    filings = edgar_client.get_13f_filings(institution.cik, limit=target_quarters)
    if not filings:
        return 0

    # Oldest first, so diffs are computed in chronological order.
    filings_with_periods = []
    for filing in filings:
        try:
            period = edgar_client.get_period_of_report(institution.cik, filing["accession"])
        except Exception:
            logger.exception("Could not resolve period for %s accession %s", institution.name, filing["accession"])
            continue
        filings_with_periods.append((period, filing["accession"]))
    filings_with_periods.sort(key=lambda p: p[0])

    known_periods = set(_existing_periods(db, institution.id))
    for period, accession in filings_with_periods:
        if period not in known_periods:
            _fetch_and_store_period(db, institution, institution.cik, accession, period)
            known_periods.add(period)
            db.commit()

    new_changes = 0
    for (prior_period, _), (current_period, _) in zip(filings_with_periods, filings_with_periods[1:]):
        already_diffed = db.scalar(
            select(HoldingsChange.id).where(
                HoldingsChange.institution_id == institution.id, HoldingsChange.period == current_period
            )
        )
        if already_diffed:
            continue
        changes = _diff_periods(db, institution, prior_period, current_period)
        new_changes += len(changes)
        db.commit()

    return new_changes


def get_ticker_holders(db: Session, ticker: Ticker) -> list[dict]:
    """Tracked institutions currently holding this ticker, at each institution's latest period."""
    results = []
    for institution in db.scalars(select(Institution)).all():
        periods = _existing_periods(db, institution.id)
        if not periods:
            continue
        row = db.scalar(
            select(HoldingsQuarterly).where(
                HoldingsQuarterly.institution_id == institution.id,
                HoldingsQuarterly.ticker_id == ticker.id,
                HoldingsQuarterly.period == periods[0],
            )
        )
        if row:
            results.append(
                {
                    "institution": institution.name,
                    "period": periods[0],
                    "shares": row.shares,
                    "market_value": row.market_value,
                }
            )
    return results


def get_institution_portfolio(db: Session, institution: Institution) -> list[dict]:
    periods = _existing_periods(db, institution.id)
    if not periods:
        return []
    rows = db.execute(
        select(HoldingsQuarterly, Ticker)
        .join(Ticker, HoldingsQuarterly.ticker_id == Ticker.id)
        .where(HoldingsQuarterly.institution_id == institution.id, HoldingsQuarterly.period == periods[0])
        .order_by(HoldingsQuarterly.market_value.desc())
    ).all()
    return [
        {
            "symbol": ticker.symbol,
            "name": ticker.name,
            "period": holding.period,
            "shares": holding.shares,
            "market_value": holding.market_value,
        }
        for holding, ticker in rows
    ]


def get_activity_feed(db: Session, limit: int = 50) -> list[dict]:
    rows = db.execute(
        select(HoldingsChange, Institution, Ticker)
        .join(Institution, HoldingsChange.institution_id == Institution.id)
        .join(Ticker, HoldingsChange.ticker_id == Ticker.id)
        .order_by(HoldingsChange.period.desc())
        .limit(limit)
    ).all()
    return [
        {
            "institution": institution.name,
            "symbol": ticker.symbol,
            "name": ticker.name,
            "period": change.period,
            "change_type": change.change_type,
            "magnitude": change.magnitude,
        }
        for change, institution, ticker in rows
    ]


# --- Async variants (for Pillar 4's deep-research context, which runs on an AsyncSession) ---


async def get_ticker_holders_async(db: AsyncSession, ticker_id: UUID) -> list[dict]:
    """Same intent as get_ticker_holders but query-shaped for async use: one pass over all
    holdings_quarterly rows for this ticker, keeping the most recent period per institution."""
    result = await db.execute(
        select(HoldingsQuarterly, Institution)
        .join(Institution, HoldingsQuarterly.institution_id == Institution.id)
        .where(HoldingsQuarterly.ticker_id == ticker_id)
        .order_by(HoldingsQuarterly.period.desc())
    )
    latest_by_institution: dict[UUID, dict] = {}
    for holding, institution in result.all():
        latest_by_institution.setdefault(
            institution.id,
            {
                "institution": institution.name,
                "period": holding.period,
                "shares": holding.shares,
                "market_value": float(holding.market_value),
            },
        )
    return list(latest_by_institution.values())


async def get_recent_activity_for_ticker_async(db: AsyncSession, ticker_id: UUID, limit: int = 5) -> list[dict]:
    result = await db.execute(
        select(HoldingsChange, Institution)
        .join(Institution, HoldingsChange.institution_id == Institution.id)
        .where(HoldingsChange.ticker_id == ticker_id)
        .order_by(HoldingsChange.period.desc())
        .limit(limit)
    )
    return [
        {
            "institution": institution.name,
            "change_type": change.change_type,
            "magnitude": float(change.magnitude),
            "period": change.period,
        }
        for change, institution in result.all()
    ]
