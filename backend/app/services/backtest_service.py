"""Reusable, parameterized signal-correlation backtest — the generalized version of the one-off
script that ran the first preliminary check. A Hypothesis's `params` dict drives every filter
here, so the same code path runs any variant (buyer-count threshold, insider seniority, max
disclosure lag, sector scope, direction) and every run is reproducible from its stored params.

Deliberately NOT a trading-strategy simulator — see algo_backtest_service for position sizing,
entry/exit rules, and portfolio-level metrics (Sharpe, drawdown). This module only asks "does
this signal correlate with forward returns," which is the prerequisite question.
"""

import logging
import time
from datetime import UTC, date, datetime, timedelta
from typing import Literal, TypedDict

import pandas as pd
import yfinance as yf
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.backtest import Hypothesis, HypothesisRun
from app.models.congress import CongressTrade, Legislator
from app.models.insiders import Insider, InsiderTrade
from app.models.ticker import Ticker
from app.models.whales import HoldingsChange, Institution
from app.utils.tickers import is_real_symbol

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = [7, 30, 60]
_YF_REQUEST_DELAY = 0.1


class HypothesisParams(TypedDict, total=False):
    sources: list[Literal["insider", "congress", "whale"]]  # default: all three
    direction: Literal["buy", "sell", "both"]  # default: "buy"
    min_buyers: int  # min distinct (source, actor) pairs on a ticker, default 1
    sectors: list[str] | None  # restrict to these sectors, default None (all)
    max_lag_days: int | None  # insider/congress only; None = no filter
    officers_only: bool  # insider only: require is_officer
    lookback_days: int  # how far back to pull events from today, default 365
    horizons: list[int]  # forward-return horizons in trading days


def _collect_events(db: Session, params: HypothesisParams) -> list[dict]:
    sources = params.get("sources", ["insider", "congress", "whale"])
    direction = params.get("direction", "buy")
    lookback_days = params.get("lookback_days", 365)
    max_lag_days = params.get("max_lag_days")
    officers_only = params.get("officers_only", False)
    since = date.today() - timedelta(days=lookback_days)

    events: list[dict] = []

    if "insider" in sources:
        q = select(InsiderTrade, Insider, Ticker).join(Insider).join(Ticker).where(InsiderTrade.filed_date >= since)
        if direction != "both":
            q = q.where(InsiderTrade.direction == direction)
        if officers_only:
            q = q.where(InsiderTrade.is_officer.is_(True))
        for trade, insider, ticker in db.execute(q).all():
            if not is_real_symbol(ticker.symbol):
                continue
            lag = (trade.filed_date - trade.transaction_date).days
            if max_lag_days is not None and lag > max_lag_days:
                continue
            events.append(
                {
                    "ticker": ticker.symbol,
                    "sector": ticker.sector,
                    "date": trade.filed_date,
                    "source": "insider",
                    "direction": trade.direction,
                    "actor": insider.name,
                }
            )

    if "congress" in sources:
        q = (
            select(CongressTrade, Legislator, Ticker)
            .join(Legislator)
            .outerjoin(Ticker)
            .where(CongressTrade.filed_date >= since, CongressTrade.ticker_id.isnot(None))
        )
        if direction != "both":
            q = q.where(CongressTrade.direction == direction)
        for trade, legislator, ticker in db.execute(q).all():
            if not ticker or not is_real_symbol(ticker.symbol):
                continue
            lag = (trade.filed_date - trade.transaction_date).days
            if max_lag_days is not None and lag > max_lag_days:
                continue
            events.append(
                {
                    "ticker": ticker.symbol,
                    "sector": ticker.sector,
                    "date": trade.filed_date,
                    "source": "congress",
                    "direction": trade.direction,
                    "actor": legislator.name,
                }
            )

    if "whale" in sources:
        q = select(HoldingsChange, Institution, Ticker).join(Institution).join(Ticker).where(
            HoldingsChange.period >= since
        )
        for change, institution, ticker in db.execute(q).all():
            if not is_real_symbol(ticker.symbol):
                continue
            whale_direction = "buy" if change.change_type in ("new", "increase") else "sell"
            if direction != "both" and whale_direction != direction:
                continue
            events.append(
                {
                    "ticker": ticker.symbol,
                    "sector": ticker.sector,
                    "date": change.period,
                    "source": "whale",
                    "direction": whale_direction,
                    "actor": institution.name,
                }
            )

    sectors = params.get("sectors")
    if sectors:
        events = [e for e in events if e["sector"] in sectors]

    min_buyers = params.get("min_buyers", 1)
    if min_buyers > 1:
        buyer_sets: dict[str, set] = {}
        for e in events:
            buyer_sets.setdefault(e["ticker"], set()).add((e["source"], e["actor"]))
        events = [e for e in events if len(buyer_sets.get(e["ticker"], set())) >= min_buyers]

    return events


def _fetch_price_series(symbols: list[str], start: date, end: date) -> dict[str, pd.Series]:
    data = {}
    for sym in symbols:
        try:
            df = yf.Ticker(sym).history(start=start.isoformat(), end=(end + timedelta(days=1)).isoformat())
            if not df.empty:
                s = df["Close"]
                s.index = s.index.date
                data[sym] = s
        except Exception:
            logger.debug("Price fetch failed for %s", sym)
        time.sleep(_YF_REQUEST_DELAY)
    return data


def _forward_return(series: pd.Series, signal_date: date, horizon: int) -> float | None:
    idx = list(series.index)
    pos = next((i for i, d in enumerate(idx) if d >= signal_date), None)
    if pos is None or pos + horizon >= len(series):
        return None
    p0, p1 = series.iloc[pos], series.iloc[pos + horizon]
    return ((p1 - p0) / p0) * 100 if p0 else None


def run_backtest(db: Session, params: HypothesisParams) -> dict:
    """Runs one parameterized backtest and returns a HypothesisRun.results-shaped dict:
    {"7d": {"n": ..., "mean_excess": ..., "median_excess": ..., "win_rate": ...}, "30d": {...}, ...}
    plus "_meta" with sample_size and the actual data window covered."""
    horizons = params.get("horizons", DEFAULT_HORIZONS)
    events = _collect_events(db, params)
    if not events:
        return {"_meta": {"sample_size": 0, "window_start": None, "window_end": None}}

    tickers = sorted({e["ticker"] for e in events})
    earliest = min(e["date"] for e in events)
    start = earliest - timedelta(days=10)
    end = date.today()

    price_data = _fetch_price_series([*tickers, "SPY"], start, end)
    spy_series = price_data.get("SPY")

    results: dict[str, list[float]] = {f"{h}d": [] for h in horizons}
    usable = 0
    for e in events:
        series = price_data.get(e["ticker"])
        if series is None or spy_series is None:
            continue
        usable += 1
        for h in horizons:
            r = _forward_return(series, e["date"], h)
            spy_r = _forward_return(spy_series, e["date"], h)
            if r is not None and spy_r is not None:
                results[f"{h}d"].append(r - spy_r)

    output = {"_meta": {"sample_size": usable, "window_start": earliest.isoformat(), "window_end": end.isoformat()}}
    for h in horizons:
        vals = pd.Series(results[f"{h}d"]).dropna()
        if len(vals) < 5:
            output[f"{h}d"] = {"n": int(len(vals)), "note": "too few observations"}
        else:
            output[f"{h}d"] = {
                "n": int(len(vals)),
                "mean_excess": round(float(vals.mean()), 3),
                "median_excess": round(float(vals.median()), 3),
                "win_rate": round(float((vals > 0).mean()) * 100, 1),
            }
    return output


PRESET_HYPOTHESES: dict[str, dict] = {
    "buyer_clustering_1": {
        "description": "Baseline: any buy signal, 1+ distinct buyer (no clustering filter).",
        "params": {"direction": "buy", "min_buyers": 1},
    },
    "buyer_clustering_2": {
        "description": "Buy signals where 2+ distinct buyers hit the same ticker.",
        "params": {"direction": "buy", "min_buyers": 2},
    },
    "buyer_clustering_3plus": {
        "description": "Buy signals where 3+ distinct buyers hit the same ticker — the one thread "
        "the preliminary check found mildly promising.",
        "params": {"direction": "buy", "min_buyers": 3},
    },
    "insider_officers_only": {
        "description": "Insider buys restricted to officers (CEO/CFO/etc.) — tests whether seniority "
        "matters more than raw buyer count.",
        "params": {"sources": ["insider"], "direction": "buy", "officers_only": True},
    },
    "insider_all_buy": {
        "description": "All insider buys regardless of role, for comparison against officers_only.",
        "params": {"sources": ["insider"], "direction": "buy"},
    },
    "fast_disclosure": {
        "description": "Buy signals disclosed within 3 days of the transaction — tests whether "
        "disclosure speed correlates with conviction.",
        "params": {"direction": "buy", "max_lag_days": 3},
    },
    "congress_only_buy": {
        "description": "Congressional buys only, isolated from insider/whale.",
        "params": {"sources": ["congress"], "direction": "buy"},
    },
    "whale_only_buy": {
        "description": "13F new/increased positions only, isolated from insider/congress.",
        "params": {"sources": ["whale"], "direction": "buy"},
    },
    "sell_baseline": {
        "description": "All sell signals — robustness check: if sells predict returns as strongly "
        "as buys, the buy-side result is probably not real information content.",
        "params": {"direction": "sell"},
    },
}


def get_or_create_hypothesis(
    db: Session, name: str, description: str, params: HypothesisParams, source: str = "manual"
) -> Hypothesis:
    existing = db.scalar(select(Hypothesis).where(Hypothesis.name == name))
    if existing:
        return existing
    hyp = Hypothesis(name=name, description=description, params=dict(params), source=source, created_at=datetime.now(UTC))
    db.add(hyp)
    db.flush()
    return hyp


def run_and_save(db: Session, hypothesis: Hypothesis) -> HypothesisRun:
    """Runs `hypothesis.params` through run_backtest and persists a new HypothesisRun — call this
    repeatedly over time for the same Hypothesis (e.g. from a scheduled job) rather than trusting
    a single run; get_hypothesis_history below is how you check whether it's held up."""
    results = run_backtest(db, hypothesis.params)
    meta = results.pop("_meta")
    run = HypothesisRun(
        hypothesis_id=hypothesis.id,
        run_at=datetime.now(UTC),
        data_window_start=date.fromisoformat(meta["window_start"]) if meta["window_start"] else date.today(),
        data_window_end=date.fromisoformat(meta["window_end"]) if meta["window_end"] else date.today(),
        sample_size=meta["sample_size"],
        results=results,
    )
    db.add(run)
    db.commit()
    return run


def get_hypothesis_history(db: Session, hypothesis_id) -> list[HypothesisRun]:
    return list(
        db.scalars(
            select(HypothesisRun).where(HypothesisRun.hypothesis_id == hypothesis_id).order_by(HypothesisRun.run_at)
        ).all()
    )
