import logging

from app.db.sync import get_sync_db
from app.services import whales_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="whales.check_and_update")
def check_and_update_whales(force: bool = False) -> int:
    """Weekly check against EDGAR for new 13F-HR filings from tracked institutions; only
    reparses/diffs when a filing newer than what we have on record is detected."""
    with get_sync_db() as db:
        updated = 0
        for institution in whales_service.list_institutions(db):
            try:
                if whales_service.refresh_institution_holdings(db, institution, force=force):
                    updated += 1
            except Exception:
                logger.exception("Failed to refresh holdings for %s", institution.name)
        return updated
