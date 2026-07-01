import asyncio
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.deps import get_current_user
from app.models.ticker import Ticker
from app.models.user import Watchlist
from app.schemas.watchlist import WatchlistItem
from app.services import price_service

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItem])
async def list_watchlist(
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[WatchlistItem]:
    rows = await db.execute(
        select(Watchlist, Ticker).join(Ticker, Watchlist.ticker_id == Ticker.id).where(Watchlist.user_id == user_id)
    )
    pairs = rows.all()

    async def build_item(ticker: Ticker) -> WatchlistItem:
        try:
            quote = await price_service.get_quote(ticker.symbol)
        except Exception:
            quote = None
        return WatchlistItem(
            ticker_id=ticker.id, symbol=ticker.symbol, name=ticker.name, sector=ticker.sector, quote=quote
        )

    items = await asyncio.gather(*(build_item(ticker) for _watchlist, ticker in pairs))
    return list(items)


@router.post("/{ticker}", response_model=WatchlistItem, status_code=201)
async def add_to_watchlist(
    ticker: str,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> WatchlistItem:
    ticker_row = await price_service.get_or_create_ticker(db, ticker)

    existing = await db.scalar(
        select(Watchlist).where(Watchlist.user_id == user_id, Watchlist.ticker_id == ticker_row.id)
    )
    if not existing:
        db.add(Watchlist(user_id=user_id, ticker_id=ticker_row.id))
        await db.commit()

    try:
        quote = await price_service.get_quote(ticker_row.symbol)
    except Exception:
        quote = None
    return WatchlistItem(
        ticker_id=ticker_row.id, symbol=ticker_row.symbol, name=ticker_row.name, sector=ticker_row.sector, quote=quote
    )


@router.delete("/{ticker}", status_code=204)
async def remove_from_watchlist(
    ticker: str,
    user_id: UUID = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == ticker.upper()))
    if not ticker_row:
        raise HTTPException(status_code=404, detail=f"Unknown ticker {ticker.upper()}")

    existing = await db.scalar(
        select(Watchlist).where(Watchlist.user_id == user_id, Watchlist.ticker_id == ticker_row.id)
    )
    if existing:
        await db.delete(existing)
        await db.commit()
