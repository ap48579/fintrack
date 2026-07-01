import logging

from sqlalchemy import func, select

from app.clients import edgar_client
from app.db.sync import get_sync_db
from app.models.fundamentals import Filing, FundamentalsQuarterly
from app.models.ticker import Ticker
from app.models.user import Watchlist
from app.services import alert_engine, fundamentals_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="fundamentals.check_and_update")
def check_and_update_fundamentals(force: bool = False) -> int:
    """Daily per-ticker check against EDGAR's submissions feed; only re-parses company facts
    (and persists filings/fundamentals_quarterly rows) when a newer filing than what we already
    have on record is detected. `force=True` always re-parses (useful for manual/dev triggering)."""
    with get_sync_db() as db:
        ticker_ids = db.scalars(select(Watchlist.ticker_id).distinct()).all()
        tickers = db.scalars(select(Ticker).where(Ticker.id.in_(ticker_ids))).all()

        updated = 0
        for ticker in tickers:
            try:
                if _refresh_ticker_fundamentals(db, ticker, force=force):
                    updated += 1
            except Exception:
                logger.exception("Failed to check/update fundamentals for %s", ticker.symbol)
        db.commit()
        return updated


def _refresh_ticker_fundamentals(db, ticker: Ticker, force: bool) -> bool:
    cik = edgar_client.get_cik_for_ticker(ticker.symbol)

    latest_known = db.scalar(select(func.max(Filing.filed_date)).where(Filing.ticker_id == ticker.id))
    latest_remote = edgar_client.get_latest_filing_date(cik)
    if not force and latest_known and latest_remote and latest_remote <= latest_known:
        return False  # no new filing since our last check

    for f in edgar_client.get_recent_filings(cik, limit=10):
        exists = db.scalar(
            select(Filing).where(
                Filing.ticker_id == ticker.id,
                Filing.filing_type == f["filing_type"],
                Filing.filed_date == f["filed_date"],
                Filing.edgar_url == f["edgar_url"],
            )
        )
        if not exists:
            db.add(Filing(ticker_id=ticker.id, **f))

    facts = edgar_client.get_company_facts(cik)
    for row in fundamentals_service.build_quarterly_history(facts, quarters=8):
        existing = db.scalar(
            select(FundamentalsQuarterly).where(
                FundamentalsQuarterly.ticker_id == ticker.id, FundamentalsQuarterly.period == row["period"]
            )
        )
        if existing:
            existing.revenue = row["revenue"]
            existing.net_income = row["net_income"]
            existing.total_debt = row["total_debt"]
            existing.total_assets = row["total_assets"]
        else:
            db.add(FundamentalsQuarterly(ticker_id=ticker.id, **row))

    db.flush()
    alert_engine.evaluate_fundamental_alert(db, ticker, fundamentals_service.build_latest_summary(facts))
    return True
