from datetime import datetime

from pydantic import BaseModel


class QuoteResponse(BaseModel):
    symbol: str
    price: float
    change_percent: float
    volume: int
    last_updated: datetime


class CandlePoint(BaseModel):
    time: int  # unix seconds, UTC — lightweight-charts UTCTimestamp
    open: float
    high: float
    low: float
    close: float
    volume: int


class LinePoint(BaseModel):
    time: int
    value: float


class HistoryResponse(BaseModel):
    symbol: str
    range: str
    candles: list[CandlePoint]
    ma50: list[LinePoint]
    ma200: list[LinePoint]
