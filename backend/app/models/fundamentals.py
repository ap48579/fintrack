import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundamentalsQuarterly(Base):
    __tablename__ = "fundamentals_quarterly"
    __table_args__ = (UniqueConstraint("ticker_id", "period", name="uq_fundamentals_ticker_period"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    period: Mapped[date] = mapped_column(Date, nullable=False)
    revenue: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    net_income: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_debt: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)
    total_assets: Mapped[float | None] = mapped_column(Numeric(20, 2), nullable=True)


class Filing(Base):
    __tablename__ = "filings"
    __table_args__ = (UniqueConstraint("ticker_id", "filing_type", "filed_date", "edgar_url", name="uq_filing"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    filing_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False)
    edgar_url: Mapped[str] = mapped_column(String(512), nullable=False)
