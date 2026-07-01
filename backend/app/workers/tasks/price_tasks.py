import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.db.sync import get_sync_db
from app.models.ticker import Ticker
from app.models.user import Watchlist
from app.services import alert_engine, price_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_MARKET_TZ = ZoneInfo("America/New_York")


def _is_market_hours(now: datetime | None = None) -> bool:
    now = (now or datetime.now(_MARKET_TZ)).astimezone(_MARKET_TZ)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    open_time, close_time = now.replace(hour=9, minute=30, second=0, microsecond=0), now.replace(
        hour=16, minute=0, second=0, microsecond=0
    )
    return open_time <= now <= close_time


@celery_app.task(name="price.poll_watchlisted")
def poll_watchlisted_prices(force: bool = False) -> int:
    """Polls a live quote for every ticker that appears on at least one watchlist.
    `force=True` bypasses the market-hours check (useful for manual/dev triggering)."""
    if not force and not _is_market_hours():
        logger.info("Outside market hours, skipping price poll")
        return 0

    with get_sync_db() as db:
        ticker_ids = db.scalars(select(Watchlist.ticker_id).distinct()).all()
        tickers = db.scalars(select(Ticker).where(Ticker.id.in_(ticker_ids))).all()

        polled = 0
        for ticker in tickers:
            try:
                _, change_percent = price_service.poll_and_store_price(db, ticker)
                alert_engine.evaluate_price_alert(db, ticker, change_percent)
                polled += 1
            except Exception:
                logger.exception("Failed to poll price for %s", ticker.symbol)
        db.commit()
        return polled
