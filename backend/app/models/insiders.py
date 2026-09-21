import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Insider(Base):
    __tablename__ = "insiders"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cik: Mapped[str] = mapped_column(String(10), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(256), nullable=False)


class InsiderTrade(Base):
    """A single open-market buy or sell from a Form 4 (transaction codes P/S only — grants,
    option exercises, tax withholding, and gifts are not ingested; see insider_service)."""

    __tablename__ = "insider_trades"
    __table_args__ = (
        UniqueConstraint(
            "accession_no",
            "insider_id",
            "ticker_id",
            "transaction_date",
            "transaction_code",
            "shares",
            name="uq_insider_trade_natural_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    insider_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("insiders.id"), nullable=False, index=True)
    ticker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tickers.id"), nullable=False, index=True)
    accession_no: Mapped[str] = mapped_column(String(25), index=True, nullable=False)
    filed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_code: Mapped[str] = mapped_column(String(2), nullable=False)  # P or S
    direction: Mapped[str] = mapped_column(String(4), nullable=False)  # buy or sell
    shares: Mapped[float] = mapped_column(Numeric(18, 4), nullable=False)
    price_per_share: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    shares_owned_after: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)
    is_direct: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_director: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_officer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_ten_percent_owner: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    officer_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
