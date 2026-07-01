from uuid import UUID

from pydantic import BaseModel

from app.schemas.stock import QuoteResponse


class WatchlistItem(BaseModel):
    ticker_id: UUID
    symbol: str
    name: str
    sector: str | None
    quote: QuoteResponse | None
