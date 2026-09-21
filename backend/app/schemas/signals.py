from datetime import date
from typing import Literal

from pydantic import BaseModel


class SignalItem(BaseModel):
    source: Literal["insider", "congress", "whale"]
    ticker: str | None
    direction: str
    actor: str
    actor_detail: str | None
    amount_label: str
    detail: str | None
    date: date
    transaction_date: date
    lag_days: int | None


class SignalPage(BaseModel):
    items: list[SignalItem]
    total: int


class DomainTickerItem(BaseModel):
    ticker: str
    name: str
    weight: int
    sources: list[Literal["insider", "congress", "whale"]]


class DomainGroup(BaseModel):
    sector: str
    tickers: list[DomainTickerItem]
