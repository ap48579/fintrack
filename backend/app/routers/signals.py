import asyncio
from datetime import date, timedelta

from fastapi import APIRouter
from sqlalchemy import select

from app.db.sync import get_sync_db
from app.models.ticker import Ticker
from app.schemas.signals import DomainGroup, SignalItem, SignalPage
from app.services import signals_service

router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("/domains", response_model=list[DomainGroup])
async def get_domain_buy_signals(days: int | None = 180, min_weight: int = 1) -> list[DomainGroup]:
    """Buy-side signals grouped by sector then ticker, weighted by distinct-buyer count — powers
    the landing page's "what's being bought, by domain" overview."""

    def _run() -> list[DomainGroup]:
        with get_sync_db() as db:
            since = _since_from_days(days)
            groups = signals_service.get_domain_buy_signals(db, since=since, min_weight=min_weight)
            return [DomainGroup(**g) for g in groups]

    return await asyncio.to_thread(_run)


def _since_from_days(days: int | None) -> date | None:
    """days=None or 0 means "all time"; otherwise a cutoff `days` back from today."""
    return date.today() - timedelta(days=days) if days else None


@router.get("/recent", response_model=SignalPage)
async def get_recent_signals(
    limit: int = 50, offset: int = 0, days: int | None = 90, source: str | None = None
) -> SignalPage:
    """`source` paginates that source's own rows directly; without it, the three sources are
    merged and paginated purely by date (see signals_service._merged_page) — deep pages reach
    every source's older rows rather than a single top-N cut permanently burying a quiet source
    under a high-volume one."""

    def _run() -> SignalPage:
        with get_sync_db() as db:
            since = _since_from_days(days)
            if source in signals_service.SOURCE_SIGNAL_FUNCS:
                items = signals_service.SOURCE_SIGNAL_FUNCS[source](db, limit, offset=offset, since=since)
                total = signals_service.SOURCE_COUNT_FUNCS[source](db, since=since)
            else:
                items, total = signals_service.get_recent_signals(db, limit=limit, offset=offset, since=since)
            return SignalPage(items=[SignalItem(**s) for s in items], total=total)

    return await asyncio.to_thread(_run)


@router.get("/ticker/{ticker}", response_model=SignalPage)
async def get_signals_for_ticker(
    ticker: str, limit: int = 50, offset: int = 0, days: int | None = 90, source: str | None = None
) -> SignalPage:
    def _run() -> SignalPage:
        with get_sync_db() as db:
            ticker_row = db.scalar(select(Ticker).where(Ticker.symbol == ticker.upper()))
            if not ticker_row:
                return SignalPage(items=[], total=0)
            since = _since_from_days(days)
            if source in signals_service.SOURCE_SIGNAL_FUNCS:
                items = signals_service.SOURCE_SIGNAL_FUNCS[source](
                    db, limit, offset=offset, ticker_id=ticker_row.id, since=since
                )
                total = signals_service.SOURCE_COUNT_FUNCS[source](db, ticker_id=ticker_row.id, since=since)
            else:
                items, total = signals_service.get_signals_for_ticker(
                    db, ticker_row, limit=limit, offset=offset, since=since
                )
            return SignalPage(items=[SignalItem(**s) for s in items], total=total)

    return await asyncio.to_thread(_run)
