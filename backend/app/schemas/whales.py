from datetime import date

from pydantic import BaseModel


class TickerHolder(BaseModel):
    institution: str
    period: date
    shares: int
    market_value: float


class PortfolioPosition(BaseModel):
    symbol: str
    name: str
    period: date
    shares: int
    market_value: float


class ActivityItem(BaseModel):
    institution: str
    symbol: str
    name: str
    period: date
    change_type: str
    magnitude: float


class InstitutionSummary(BaseModel):
    cik: str
    name: str


class AddInstitutionRequest(BaseModel):
    name: str
    cik: str


class InstitutionOverview(BaseModel):
    cik: str
    name: str
    period: date | None
    total_market_value: float | None
    position_count: int
    value_change_pct: float | None
    new_positions: int
    exited_positions: int
