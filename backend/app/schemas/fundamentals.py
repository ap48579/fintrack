from datetime import date

from pydantic import BaseModel


class FundamentalsSummary(BaseModel):
    period: date | None
    revenue: float | None
    net_income: float | None
    total_debt: float | None
    total_assets: float | None
    debt_to_equity: float | None
    net_margin: float | None
    revenue_growth_qoq: float | None
    revenue_growth_yoy: float | None


class FundamentalsQuarter(BaseModel):
    period: date
    revenue: float | None
    net_income: float | None
    total_debt: float | None
    total_assets: float | None


class FilingItem(BaseModel):
    filing_type: str
    filed_date: date
    edgar_url: str
