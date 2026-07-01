import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.models.ticker import Ticker
from app.schemas.fundamentals import FilingItem, FundamentalsQuarter, FundamentalsSummary
from app.schemas.research import ResearchReportSummary
from app.schemas.stock import HistoryResponse, QuoteResponse
from app.services import fundamentals_service, price_service, research_service

router = APIRouter(prefix="/stock", tags=["stock"])

RangeKey = Literal["1D", "1W", "1M", "1Y", "5Y"]


@router.get("/{ticker}/quote", response_model=QuoteResponse)
async def get_quote(ticker: str) -> QuoteResponse:
    try:
        return await price_service.get_quote(ticker)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No quote data for {ticker.upper()}") from exc


@router.get("/{ticker}/history", response_model=HistoryResponse)
async def get_history(ticker: str, range: RangeKey = "1M") -> HistoryResponse:
    try:
        return await price_service.get_history(ticker, range)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No history data for {ticker.upper()}") from exc


@router.get("/{ticker}/fundamentals", response_model=FundamentalsSummary)
async def get_fundamentals(ticker: str) -> FundamentalsSummary:
    try:
        summary = await asyncio.to_thread(fundamentals_service.get_fundamentals_summary, ticker)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {ticker.upper()}") from exc
    return FundamentalsSummary(**summary)


@router.get("/{ticker}/fundamentals/history", response_model=list[FundamentalsQuarter])
async def get_fundamentals_history(ticker: str) -> list[FundamentalsQuarter]:
    try:
        history = await asyncio.to_thread(fundamentals_service.get_fundamentals_history, ticker)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No fundamentals data for {ticker.upper()}") from exc
    return [FundamentalsQuarter(**row) for row in history]


@router.get("/{ticker}/filings", response_model=list[FilingItem])
async def get_filings(ticker: str) -> list[FilingItem]:
    try:
        filings = await asyncio.to_thread(fundamentals_service.get_filings, ticker)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"No filings found for {ticker.upper()}") from exc
    return [FilingItem(**f) for f in filings]


@router.get("/{ticker}/research", response_model=list[ResearchReportSummary])
async def get_ticker_research(ticker: str, db: AsyncSession = Depends(get_db)) -> list[ResearchReportSummary]:
    ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == ticker.upper()))
    if not ticker_row:
        return []
    reports = await research_service.get_reports_for_ticker(db, ticker_row)
    return [ResearchReportSummary.model_validate(r) for r in reports]
