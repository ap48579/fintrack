import asyncio

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.clients import edgar_client
from app.db.sync import get_sync_db
from app.models.ticker import Ticker
from app.schemas.whales import (
    ActivityItem,
    AddInstitutionRequest,
    InstitutionOverview,
    InstitutionSummary,
    PortfolioPosition,
    TickerHolder,
)
from app.services import whales_service

router = APIRouter(prefix="/whales", tags=["whales"])


@router.get("/institutions", response_model=list[InstitutionSummary])
async def list_institutions() -> list[InstitutionSummary]:
    def _run() -> list[InstitutionSummary]:
        with get_sync_db() as db:
            return [InstitutionSummary(cik=i.cik, name=i.name) for i in whales_service.list_institutions(db)]

    return await asyncio.to_thread(_run)


@router.post("/institutions", response_model=InstitutionSummary, status_code=201)
async def add_institution(body: AddInstitutionRequest) -> InstitutionSummary:
    def _run() -> InstitutionSummary:
        with get_sync_db() as db:
            institution, _is_new = whales_service.add_institution(db, body.name, body.cik)
            return InstitutionSummary(cik=institution.cik, name=institution.name)

    return await asyncio.to_thread(_run)


@router.get("/search-institutions", response_model=list[InstitutionSummary])
async def search_institutions(name: str) -> list[InstitutionSummary]:
    """Looks up 13F-HR filers by name via EDGAR full-text search, so the user can pick a CIK
    without needing to already know it — feeds the "add institution" flow on the whales page."""
    results = await asyncio.to_thread(edgar_client.search_institutions_by_name, name)
    return [InstitutionSummary(**r) for r in results]


@router.get("/overview", response_model=list[InstitutionOverview])
async def get_institutions_overview() -> list[InstitutionOverview]:
    def _run() -> list[InstitutionOverview]:
        with get_sync_db() as db:
            return [InstitutionOverview(**o) for o in whales_service.get_institutions_overview(db)]

    return await asyncio.to_thread(_run)


@router.get("/activity", response_model=list[ActivityItem])
async def get_activity(limit: int = 50) -> list[ActivityItem]:
    def _run() -> list[ActivityItem]:
        with get_sync_db() as db:
            return [ActivityItem(**item) for item in whales_service.get_activity_feed(db, limit=limit)]

    return await asyncio.to_thread(_run)


@router.get("/{institution}/holdings", response_model=list[PortfolioPosition])
async def get_institution_holdings(institution: str) -> list[PortfolioPosition]:
    def _run() -> list[PortfolioPosition]:
        with get_sync_db() as db:
            inst = whales_service.get_institution_by_identifier(db, institution)
            if not inst:
                raise HTTPException(status_code=404, detail=f"Unknown tracked institution {institution}")
            return [PortfolioPosition(**p) for p in whales_service.get_institution_portfolio(db, inst)]

    return await asyncio.to_thread(_run)


@router.get("/{ticker}", response_model=list[TickerHolder])
async def get_ticker_holders(ticker: str) -> list[TickerHolder]:
    def _run() -> list[TickerHolder]:
        with get_sync_db() as db:
            ticker_row = db.scalar(select(Ticker).where(Ticker.symbol == ticker.upper()))
            if not ticker_row:
                return []
            return [TickerHolder(**h) for h in whales_service.get_ticker_holders(db, ticker_row)]

    return await asyncio.to_thread(_run)
