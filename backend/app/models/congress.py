import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Legislator(Base):
    __tablename__ = "legislators"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), unique=True, nullable=False)
    state_dst: Mapped[str | None] = mapped_column(String(8), nullable=True)


class CongressTrade(Base):
    """A single buy or sell (transaction type P/S only — "E" exchanges are ambiguous and not
    ingested) from a House Periodic Transaction Report. Bond/CUSIP-identified holdings and other
    non-stock assets are still stored (ticker_id left null) rather than dropped — see
    congress_service for why: the disclosure itself is the signal, not just the ticker match.

    `line_no` (the transaction's position within its filing) is part of the natural key because
    a single PTR can legitimately list the same asset/date/amount twice (seen in real filings —
    an aggregated multi-lot sale reported as repeated identical-looking rows); without it,
    re-ingestion would silently collapse those into one row."""

    __tablename__ = "congress_trades"
    __table_args__ = (UniqueConstraint("doc_id", "line_no", name="uq_congress_trade_doc_line"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    legislator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("legislators.id"), nullable=False, index=True)
    ticker_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tickers.id"), nullable=True, index=True)
    doc_id: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    line_no: Mapped[int] = mapped_column(nullable=False)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    notification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_type: Mapped[str] = mapped_column(String(2), nullable=False)  # P or S
    direction: Mapped[str] = mapped_column(String(4), nullable=False)  # buy or sell
    owner: Mapped[str | None] = mapped_column(String(16), nullable=True)  # spouse/joint/dependent_child/None=self
    asset_description: Mapped[str] = mapped_column(String(512), nullable=False)
    amount_low: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    amount_high: Mapped[float | None] = mapped_column(Numeric(18, 2), nullable=True)
    amount_unbounded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
