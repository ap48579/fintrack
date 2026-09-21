import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentVerdict(Base):
    """Cached result of a bull/bear/judge debate for one ticker (TradingAgents-style: separate
    passes argue for and against before a synthesis verdict, instead of one pass that tends to
    just agree with whatever framing it started with). Keyed by ticker rather than a history
    table — a verdict goes stale as new disclosures/news land, so callers regenerate past a TTL
    rather than accumulating a run history the way HypothesisRun does."""

    __tablename__ = "agent_verdicts"

    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    bull_case: Mapped[str] = mapped_column(Text, nullable=False)
    bear_case: Mapped[str] = mapped_column(Text, nullable=False)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)  # bullish | bearish | neutral
    confidence: Mapped[float] = mapped_column(Float, nullable=False)  # 0-1
    key_risks: Mapped[str] = mapped_column(Text, nullable=False)
    key_catalysts: Mapped[str] = mapped_column(Text, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
