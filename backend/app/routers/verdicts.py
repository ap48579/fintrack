import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.verdict import VerdictItem
from app.services import agent_verdict_service

router = APIRouter(prefix="/verdicts", tags=["verdicts"])


@router.get("/{ticker}", response_model=VerdictItem | None)
async def get_verdict(ticker: str, db: AsyncSession = Depends(get_db)) -> VerdictItem | None:
    verdict = await agent_verdict_service.get_cached_verdict(db, ticker)
    if not verdict:
        return None
    return VerdictItem.model_validate(verdict)


@router.post("/{ticker}/stream")
async def stream_verdict(ticker: str, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Server-Sent Events: `{"phase": "bull"|"bear", "text": ...}` as each argument completes,
    then `{"phase": "judge", "verdict": {...}}` once the synthesis is persisted."""

    async def event_stream():
        async for event in agent_verdict_service.stream_verdict_generation(db, ticker):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
