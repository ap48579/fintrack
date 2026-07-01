import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ticker import Ticker


class ResearchCandidate(Base):
    """Lightweight daily 'worth a look' flag from the passive GDELT scan. subject_type/subject mirror
    research_reports so a candidate can be turned directly into a deep-research trigger."""

    __tablename__ = "research_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)  # ticker | theme
    subject: Mapped[str] = mapped_column(String(256), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)


class ResearchReport(Base):
    __tablename__ = "research_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subject_type: Mapped[str] = mapped_column(String(16), nullable=False)  # ticker | theme
    subject: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment_direction: Mapped[str] = mapped_column(String(16), nullable=False)  # bullish/bearish/neutral/mixed
    full_report: Mapped[str] = mapped_column(Text, nullable=False)

    sources: Mapped[list["ResearchSource"]] = relationship(back_populates="report", cascade="all, delete-orphan")
    ticker_links: Mapped[list["ResearchTickerLink"]] = relationship(
        back_populates="report", cascade="all, delete-orphan"
    )


class ResearchSource(Base):
    __tablename__ = "research_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False)  # news/reddit/edgar/web
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)

    report: Mapped["ResearchReport"] = relationship(back_populates="sources")


class ResearchTickerLink(Base):
    __tablename__ = "research_ticker_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("research_reports.id"), nullable=False, index=True)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    exposure_type: Mapped[str] = mapped_column(String(16), nullable=False)  # positive/negative/neutral
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    report: Mapped["ResearchReport"] = relationship(back_populates="ticker_links")
    ticker: Mapped["Ticker"] = relationship()
