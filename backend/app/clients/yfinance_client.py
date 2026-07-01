from dataclasses import dataclass
from datetime import datetime

import pandas as pd
import yfinance as yf

# range -> (yfinance period, yfinance interval). Daily+ ranges get enough lookback for 200-day MA.
_RANGE_CONFIG: dict[str, tuple[str, str]] = {
    "1D": ("1d", "5m"),
    "1W": ("5d", "15m"),
    "1M": ("1mo", "1d"),
    "1Y": ("1y", "1d"),
    "5Y": ("5y", "1wk"),
}
_MA_LOOKBACK_PERIOD = "2y"  # enough daily bars to compute a trailing 200-day MA


@dataclass
class Quote:
    symbol: str
    price: float
    change_percent: float
    volume: int
    last_updated: datetime


@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int


def get_company_info(symbol: str) -> dict:
    info = yf.Ticker(symbol).get_info()
    return {
        "name": info.get("longName") or info.get("shortName") or symbol.upper(),
        "sector": info.get("sector"),
        "exchange": info.get("exchange"),
    }


def get_quote(symbol: str) -> Quote:
    ticker = yf.Ticker(symbol)
    fast_info = ticker.fast_info
    price = float(fast_info["lastPrice"])
    previous_close = float(fast_info["previousClose"])
    change_percent = ((price - previous_close) / previous_close) * 100 if previous_close else 0.0
    return Quote(
        symbol=symbol.upper(),
        price=price,
        change_percent=change_percent,
        volume=int(fast_info.get("lastVolume") or 0),
        last_updated=datetime.now().astimezone(),
    )


def _df_to_candles(df: pd.DataFrame) -> list[Candle]:
    return [
        Candle(
            timestamp=idx.to_pydatetime(),
            open=float(row["Open"]),
            high=float(row["High"]),
            low=float(row["Low"]),
            close=float(row["Close"]),
            volume=int(row["Volume"]),
        )
        for idx, row in df.iterrows()
    ]


def get_history(symbol: str, range_key: str) -> list[Candle]:
    period, interval = _RANGE_CONFIG[range_key]
    df = yf.Ticker(symbol).history(period=period, interval=interval)
    return _df_to_candles(df)


def get_daily_history_with_ma_lookback(symbol: str) -> list[Candle]:
    """Daily bars over a ~2y window — enough trailing data to compute 50/200-day moving averages."""
    df = yf.Ticker(symbol).history(period=_MA_LOOKBACK_PERIOD, interval="1d")
    return _df_to_candles(df)
