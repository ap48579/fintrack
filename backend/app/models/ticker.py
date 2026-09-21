import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Ticker(Base):
    __tablename__ = "tickers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Usually a short equity ticker, but 13F holdings can include bonds/notes, where OpenFIGI's
    # resolved "symbol" is a longer descriptive string (e.g. "BRKR 6.375 09/01/28") rather than a
    # true ticker — wide enough to hold those instead of crashing whale-holdings ingestion on them.
    symbol: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Resolved from 13F holdings (Pillar 3) via CUSIP, so whale holdings can FK to a real ticker
    # even when the symbol wasn't already known (e.g. it hasn't been searched/watchlisted yet).
    cusip: Mapped[str | None] = mapped_column(String(9), unique=True, nullable=True)

    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="ticker")


class PriceHistory(Base):
    __tablename__ = "price_history"
    __table_args__ = (UniqueConstraint("ticker_id", "timestamp", name="uq_price_history_ticker_ts"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)

    ticker: Mapped["Ticker"] = relationship(back_populates="price_history")
