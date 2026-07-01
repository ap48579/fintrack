from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class CandidateItem(BaseModel):
    subject_type: str
    subject: str
    date: date
    reason: str
    score: float


class ResearchTriggerRequest(BaseModel):
    subject_type: Literal["ticker", "theme"]
    subject: str
    query: str | None = None


class ResearchSourceItem(BaseModel):
    source_type: str
    url: str
    title: str
    published_at: datetime | None
    excerpt: str

    model_config = {"from_attributes": True}


class ResearchTickerLinkItem(BaseModel):
    exposure_type: str
    confidence: float
    ticker: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_link(cls, link) -> "ResearchTickerLinkItem":
        return cls(exposure_type=link.exposure_type, confidence=link.confidence, ticker=link.ticker.symbol)


class ResearchReportDetail(BaseModel):
    id: UUID
    subject_type: str
    subject: str
    query: str
    created_at: datetime
    summary: str
    sentiment_direction: str
    full_report: str
    sources: list[ResearchSourceItem]
    ticker_links: list[ResearchTickerLinkItem]

    @classmethod
    def from_orm_report(cls, report) -> "ResearchReportDetail":
        return cls(
            id=report.id,
            subject_type=report.subject_type,
            subject=report.subject,
            query=report.query,
            created_at=report.created_at,
            summary=report.summary,
            sentiment_direction=report.sentiment_direction,
            full_report=report.full_report,
            sources=[ResearchSourceItem.model_validate(s) for s in report.sources],
            ticker_links=[ResearchTickerLinkItem.from_orm_link(t) for t in report.ticker_links],
        )


class ResearchReportSummary(BaseModel):
    id: UUID
    subject_type: str
    subject: str
    created_at: datetime
    summary: str
    sentiment_direction: str

    model_config = {"from_attributes": True}
