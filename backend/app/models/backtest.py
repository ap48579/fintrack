import uuid
from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Hypothesis(Base):
    """A named, parameterized signal-correlation test — e.g. "3+ distinct buyers, 60d horizon"
    or "insider buys by officers only, <=3 day disclosure lag". `params` drives backtest_service's
    event filter so a hypothesis is fully reproducible from this row alone. Re-run periodically
    (see HypothesisRun) as more disclosure data lands, rather than trusted from one run — that's
    the whole point of this table existing instead of a one-off script."""

    __tablename__ = "hypotheses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(16), nullable=False)  # manual | llm_generated
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    active: Mapped[bool] = mapped_column(default=True, nullable=False)  # re-run on each scheduled pass?


class HypothesisRun(Base):
    """One execution of a Hypothesis against whatever disclosure+price data exists at run time.
    Multiple rows per hypothesis over time are the point — a hypothesis is only worth trusting
    once its results are consistent across several runs covering different, non-overlapping data
    windows, not just the first time it happened to look good."""

    __tablename__ = "hypothesis_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(nullable=False, index=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_window_start: Mapped[date] = mapped_column(Date, nullable=False)
    data_window_end: Mapped[date] = mapped_column(Date, nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False)
    results: Mapped[dict] = mapped_column(JSON, nullable=False)  # per-horizon mean/median/win_rate/n
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
