"""Backup data source for Pillar 1 — used when yfinance fails to return data for a symbol.
Free tier: 25 requests/day, so this is a fallback, not the primary path."""

from datetime import datetime

import httpx

from app.clients.yfinance_client import Quote
from app.config import settings

BASE_URL = "https://www.alphavantage.co/query"


class AlphaVantageUnavailable(Exception):
    pass


async def get_quote(symbol: str) -> Quote:
    if not settings.alpha_vantage_api_key:
        raise AlphaVantageUnavailable("No ALPHA_VANTAGE_API_KEY configured")

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            BASE_URL,
            params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": settings.alpha_vantage_api_key},
        )
        resp.raise_for_status()
        data = resp.json().get("Global Quote") or {}

    if not data:
        raise AlphaVantageUnavailable(f"No Alpha Vantage data for {symbol}")

    price = float(data["05. price"])
    change_percent = float(data["10. change percent"].rstrip("%"))
    return Quote(
        symbol=symbol.upper(),
        price=price,
        change_percent=change_percent,
        volume=int(data["06. volume"]),
        last_updated=datetime.now().astimezone(),
    )
