import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.db.sync import get_sync_db
from app.schemas.research import (
    CandidateItem,
    ResearchReportDetail,
    ResearchReportSummary,
    ResearchTriggerRequest,
)
from app.services import research_service

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/candidates", response_model=list[CandidateItem])
async def get_candidates() -> list[CandidateItem]:
    def _run() -> list[CandidateItem]:
        with get_sync_db() as db:
            return [CandidateItem.model_validate(c, from_attributes=True) for c in research_service.get_candidates(db)]

    return await asyncio.to_thread(_run)


@router.get("/history", response_model=list[ResearchReportSummary])
async def get_history(
    subject_type: str, subject: str, db: AsyncSession = Depends(get_db)
) -> list[ResearchReportSummary]:
    reports = await research_service.get_history(db, subject_type, subject)
    return [ResearchReportSummary.model_validate(r) for r in reports]


@router.get("/recent", response_model=list[ResearchReportSummary])
async def get_recent(limit: int = 20, db: AsyncSession = Depends(get_db)) -> list[ResearchReportSummary]:
    reports = await research_service.get_recent_reports(db, limit=limit)
    return [ResearchReportSummary.model_validate(r) for r in reports]


@router.post("/stream")
async def trigger_research_stream(body: ResearchTriggerRequest, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Server-Sent Events: a `{"step": "..."}` line per pipeline phase (the reasoning trace),
    then a final `{"done": true, "report": {...}}` line once the report is persisted."""
    query = body.query or f"What's driving sentiment around {body.subject}?"

    async def event_stream():
        async for event in research_service.trigger_research_stream(db, body.subject_type, body.subject, query):
            if event.get("done"):
                report = await research_service.get_report(db, UUID(event["report_id"]))
                payload = {"done": True, "report": ResearchReportDetail.from_orm_report(report).model_dump(mode="json")}
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("", response_model=ResearchReportDetail, status_code=201)
async def trigger_research(
    body: ResearchTriggerRequest, db: AsyncSession = Depends(get_db)
) -> ResearchReportDetail:
    """Non-streaming variant, kept for simple/programmatic callers that don't need progress events."""
    query = body.query or f"What's driving sentiment around {body.subject}?"
    report = await research_service.trigger_research(db, body.subject_type, body.subject, query)
    if not report:
        raise HTTPException(status_code=502, detail="Research run did not produce a report")
    return ResearchReportDetail.from_orm_report(report)


@router.get("/{report_id}", response_model=ResearchReportDetail)
async def get_report(report_id: UUID, db: AsyncSession = Depends(get_db)) -> ResearchReportDetail:
    report = await research_service.get_report(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Research report not found")
    return ResearchReportDetail.from_orm_report(report)
