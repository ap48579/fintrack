import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Institution(Base):
    __tablename__ = "institutions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)


class HoldingsQuarterly(Base):
    __tablename__ = "holdings_quarterly"
    __table_args__ = (
        UniqueConstraint("institution_id", "ticker_id", "period", name="uq_holdings_inst_ticker_period"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    shares: Mapped[int] = mapped_column(nullable=False)
    market_value: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)


class HoldingsChange(Base):
    __tablename__ = "holdings_changes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("institutions.id"), nullable=False, index=True)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)  # new/exit/increase/decrease
    magnitude: Mapped[float] = mapped_column(Numeric(20, 2), nullable=False)
