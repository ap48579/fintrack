import logging

from app.db.sync import get_sync_db
from app.services import research_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="research.passive_scan")
def run_passive_scan() -> int:
    """Daily, keyless, GDELT-only — flags watchlisted tickers with unusual news activity."""
    with get_sync_db() as db:
        return research_service.run_passive_scan(db)
