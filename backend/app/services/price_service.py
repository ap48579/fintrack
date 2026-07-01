import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.clients import alpha_vantage_client, yfinance_client
from app.clients.yfinance_client import Candle, Quote
from app.models.ticker import PriceHistory, Ticker
from app.schemas.stock import CandlePoint, HistoryResponse, LinePoint, QuoteResponse

logger = logging.getLogger(__name__)

# Intraday ranges don't have enough daily bars for a meaningful 50/200-day MA.
_DAILY_PLUS_RANGES = {"1M", "1Y", "5Y"}


async def get_quote(symbol: str) -> QuoteResponse:
    try:
        quote: Quote = await asyncio.to_thread(yfinance_client.get_quote, symbol)
    except Exception:
        logger.warning("yfinance quote failed for %s, falling back to Alpha Vantage", symbol)
        quote = await alpha_vantage_client.get_quote(symbol)

    return QuoteResponse(
        symbol=quote.symbol,
        price=quote.price,
        change_percent=quote.change_percent,
        volume=quote.volume,
        last_updated=quote.last_updated,
    )


def _moving_average(candles: list[Candle], window: int) -> list[LinePoint]:
    closes = [c.close for c in candles]
    points: list[LinePoint] = []
    for i in range(window - 1, len(closes)):
        avg = sum(closes[i - window + 1 : i + 1]) / window
        points.append(LinePoint(time=int(candles[i].timestamp.timestamp()), value=round(avg, 4)))
    return points


def _trim_to_range(ma_points: list[LinePoint], display_candles: list[Candle]) -> list[LinePoint]:
    if not display_candles:
        return []
    start = int(display_candles[0].timestamp.timestamp())
    return [p for p in ma_points if p.time >= start]


async def get_history(symbol: str, range_key: str) -> HistoryResponse:
    display_candles = await asyncio.to_thread(yfinance_client.get_history, symbol, range_key)

    ma50: list[LinePoint] = []
    ma200: list[LinePoint] = []
    if range_key in _DAILY_PLUS_RANGES:
        lookback_candles = await asyncio.to_thread(
            yfinance_client.get_daily_history_with_ma_lookback, symbol
        )
        ma50 = _trim_to_range(_moving_average(lookback_candles, 50), display_candles)
        ma200 = _trim_to_range(_moving_average(lookback_candles, 200), display_candles)

    return HistoryResponse(
        symbol=symbol.upper(),
        range=range_key,
        candles=[
            CandlePoint(
                time=int(c.timestamp.timestamp()),
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume,
            )
            for c in display_candles
        ],
        ma50=ma50,
        ma200=ma200,
    )


def get_or_create_ticker_sync(db: Session, symbol: str) -> Ticker:
    """Get-or-create a tickers row, fetching name/sector/exchange from yfinance on first sight.
    Used wherever a ticker needs a persisted row (watchlist, alert rules) — pure lookup/history
    endpoints don't need this, they hit yfinance live for any symbol."""
    symbol = symbol.upper()
    ticker = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker:
        return ticker

    info = yfinance_client.get_company_info(symbol)
    ticker = Ticker(symbol=symbol, name=info["name"], sector=info["sector"], exchange=info["exchange"])
    db.add(ticker)
    db.flush()
    return ticker


async def get_or_create_ticker(db: AsyncSession, symbol: str) -> Ticker:
    """Async counterpart of get_or_create_ticker_sync, for use from FastAPI routes."""
    symbol = symbol.upper()
    ticker = await db.scalar(select(Ticker).where(Ticker.symbol == symbol))
    if ticker:
        return ticker

    info = await asyncio.to_thread(yfinance_client.get_company_info, symbol)
    ticker = Ticker(symbol=symbol, name=info["name"], sector=info["sector"], exchange=info["exchange"])
    db.add(ticker)
    await db.flush()
    return ticker


def poll_and_store_price(db: Session, ticker: Ticker) -> tuple[PriceHistory, float]:
    """Called by the 15-min Celery poll task — fetches a live quote and persists a price_history
    row. Also returns change_percent so the caller can feed it straight to the alert engine
    without an extra API call."""
    quote = yfinance_client.get_quote(ticker.symbol)
    row = PriceHistory(
        ticker_id=ticker.id,
        timestamp=quote.last_updated,
        open=quote.price,
        high=quote.price,
        low=quote.price,
        close=quote.price,
        volume=quote.volume,
    )
    db.add(row)
    db.flush()
    return row, quote.change_percent
