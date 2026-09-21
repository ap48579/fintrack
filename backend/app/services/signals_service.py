"""Normalizes the three disclosure sources (Form 4 insider trades, House PTR congressional
trades, 13F institutional holdings changes) into one common "signal" shape, so the frontend has
a single feed to render instead of three differently-shaped lists. No scoring or correlation
here — see technical-spec.md's "Signal detection" section for why that's a later phase; this is
just a display-layer merge of "any indication of buys and sells" across sources, newest first.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.congress import CongressTrade, Legislator
from app.models.insiders import Insider, InsiderTrade
from app.models.ticker import Ticker
from app.models.whales import HoldingsChange, Institution
from app.utils.tickers import is_real_symbol

_WHALE_DIRECTION_LABEL = {"new": "new position", "exit": "exited", "increase": "increased", "decrease": "decreased"}


def _insider_role(trade: InsiderTrade) -> str | None:
    labels = []
    if trade.is_officer:
        labels.append(trade.officer_title or "Officer")
    if trade.is_director:
        labels.append("Director")
    if trade.is_ten_percent_owner:
        labels.append("10% Owner")
    return ", ".join(labels) or None


def get_insider_signals(
    db: Session, limit: int, offset: int = 0, ticker_id=None, since: date | None = None
) -> list[dict]:
    query = select(InsiderTrade, Insider, Ticker).join(Insider, InsiderTrade.insider_id == Insider.id).join(
        Ticker, InsiderTrade.ticker_id == Ticker.id
    )
    if ticker_id is not None:
        query = query.where(InsiderTrade.ticker_id == ticker_id)
    if since is not None:
        query = query.where(InsiderTrade.filed_date >= since)
    query = query.order_by(InsiderTrade.filed_date.desc(), InsiderTrade.id).offset(offset).limit(limit)

    signals = []
    for trade, insider, ticker in db.execute(query).all():
        price = f" @ ${trade.price_per_share:,.2f}" if trade.price_per_share else ""
        signals.append(
            {
                "source": "insider",
                "ticker": ticker.symbol,
                "direction": trade.direction,
                "actor": insider.name,
                "actor_detail": _insider_role(trade),
                "amount_label": f"{trade.shares:,.0f} sh{price}",
                "detail": None,
                "date": trade.filed_date,
                "transaction_date": trade.transaction_date,
                "lag_days": (trade.filed_date - trade.transaction_date).days,
            }
        )
    return signals


def count_insider_signals(db: Session, ticker_id=None, since: date | None = None) -> int:
    query = select(func.count(InsiderTrade.id))
    if ticker_id is not None:
        query = query.where(InsiderTrade.ticker_id == ticker_id)
    if since is not None:
        query = query.where(InsiderTrade.filed_date >= since)
    return db.scalar(query) or 0


def get_congress_signals(
    db: Session, limit: int, offset: int = 0, ticker_id=None, since: date | None = None
) -> list[dict]:
    query = (
        select(CongressTrade, Legislator, Ticker)
        .join(Legislator, CongressTrade.legislator_id == Legislator.id)
        .outerjoin(Ticker, CongressTrade.ticker_id == Ticker.id)
    )
    if ticker_id is not None:
        query = query.where(CongressTrade.ticker_id == ticker_id)
    if since is not None:
        query = query.where(CongressTrade.filed_date >= since)
    query = query.order_by(CongressTrade.filed_date.desc(), CongressTrade.id).offset(offset).limit(limit)

    signals = []
    for trade, legislator, ticker in db.execute(query).all():
        if trade.amount_unbounded:
            amount = f"${float(trade.amount_low):,.0f}+"
        elif trade.amount_high is not None:
            amount = f"${float(trade.amount_low):,.0f}-${float(trade.amount_high):,.0f}"
        else:
            amount = f"${float(trade.amount_low):,.0f}"
        signals.append(
            {
                "source": "congress",
                "ticker": ticker.symbol if ticker else None,
                "direction": trade.direction,
                "actor": legislator.name,
                "actor_detail": trade.owner,
                "amount_label": amount,
                "detail": trade.asset_description,
                "date": trade.filed_date,
                "transaction_date": trade.transaction_date,
                "lag_days": (trade.filed_date - trade.transaction_date).days,
            }
        )
    return signals


def count_congress_signals(db: Session, ticker_id=None, since: date | None = None) -> int:
    query = select(func.count(CongressTrade.id))
    if ticker_id is not None:
        query = query.where(CongressTrade.ticker_id == ticker_id)
    if since is not None:
        query = query.where(CongressTrade.filed_date >= since)
    return db.scalar(query) or 0


def get_whale_signals(
    db: Session, limit: int, offset: int = 0, ticker_id=None, since: date | None = None
) -> list[dict]:
    query = (
        select(HoldingsChange, Institution, Ticker)
        .join(Institution, HoldingsChange.institution_id == Institution.id)
        .join(Ticker, HoldingsChange.ticker_id == Ticker.id)
    )
    if ticker_id is not None:
        query = query.where(HoldingsChange.ticker_id == ticker_id)
    if since is not None:
        query = query.where(HoldingsChange.period >= since)
    query = query.order_by(HoldingsChange.period.desc(), HoldingsChange.id).offset(offset).limit(limit)

    signals = []
    for change, institution, ticker in db.execute(query).all():
        signals.append(
            {
                "source": "whale",
                "ticker": ticker.symbol,
                "direction": change.change_type,
                "actor": institution.name,
                "actor_detail": None,
                "amount_label": f"{float(change.magnitude):,.0f} sh ({_WHALE_DIRECTION_LABEL[change.change_type]})",
                "detail": None,
                "date": change.period,
                "transaction_date": change.period,
                "lag_days": None,  # 13F is quarterly; only the period-end date is stored, not the filing date
            }
        )
    return signals


def count_whale_signals(db: Session, ticker_id=None, since: date | None = None) -> int:
    query = select(func.count(HoldingsChange.id))
    if ticker_id is not None:
        query = query.where(HoldingsChange.ticker_id == ticker_id)
    if since is not None:
        query = query.where(HoldingsChange.period >= since)
    return db.scalar(query) or 0


SOURCE_SIGNAL_FUNCS = {
    "insider": get_insider_signals,
    "congress": get_congress_signals,
    "whale": get_whale_signals,
}
SOURCE_COUNT_FUNCS = {
    "insider": count_insider_signals,
    "congress": count_congress_signals,
    "whale": count_whale_signals,
}


def _merged_page(
    db: Session, limit: int, offset: int, ticker_id, since: date | None
) -> tuple[list[dict], int]:
    """Paginates the combined feed purely by date across all three sources (page 2, 3, ... reach
    older rows from every source, so a high-volume source can no longer permanently bury a quiet
    one the way a single top-N-by-date cut did — see the "no congress/13F signals" incident this
    replaced). Each source is asked for its own top `offset + limit` (already date-sorted, so
    this is just enough rows to guarantee the merge is correct up to this page) rather than paged
    independently, since the three sources can't share one SQL OFFSET across different tables."""
    total = sum(fn(db, ticker_id=ticker_id, since=since) for fn in SOURCE_COUNT_FUNCS.values())

    fetch_n = offset + limit
    combined = [
        *get_insider_signals(db, fetch_n, ticker_id=ticker_id, since=since),
        *get_congress_signals(db, fetch_n, ticker_id=ticker_id, since=since),
        *get_whale_signals(db, fetch_n, ticker_id=ticker_id, since=since),
    ]
    combined.sort(key=lambda s: s["date"], reverse=True)
    return combined[offset : offset + limit], total


def get_domain_buy_signals(
    db: Session, since: date | None = None, min_weight: int = 1, per_domain_limit: int = 15
) -> list[dict]:
    """Groups the buy side of all three sources — insider Form 4 buys, congressional PTR buys,
    and 13F new/increased positions — by ticker, weighted by count of *distinct buyers* (not raw
    row count, so one insider filing five small buys doesn't outweigh five different people each
    buying once), then by sector so the landing page can show "what's being bought, by domain"
    instead of only a flat chronological feed. `min_weight` filters out single-buyer noise —
    tickers only one person happened to buy aren't a domain signal worth surfacing here."""
    weights: dict = {}

    def _add(ticker_id, source: str, actor: str) -> None:
        if ticker_id is None:
            return
        entry = weights.setdefault(ticker_id, {"buyers": set(), "sources": set()})
        entry["buyers"].add((source, actor))
        entry["sources"].add(source)

    insider_q = select(InsiderTrade.ticker_id, Insider.name).join(Insider).where(InsiderTrade.direction == "buy")
    if since is not None:
        insider_q = insider_q.where(InsiderTrade.filed_date >= since)
    for ticker_id, name in db.execute(insider_q).all():
        _add(ticker_id, "insider", name)

    congress_q = (
        select(CongressTrade.ticker_id, Legislator.name)
        .join(Legislator)
        .where(CongressTrade.direction == "buy", CongressTrade.ticker_id.isnot(None))
    )
    if since is not None:
        congress_q = congress_q.where(CongressTrade.filed_date >= since)
    for ticker_id, name in db.execute(congress_q).all():
        _add(ticker_id, "congress", name)

    whale_q = (
        select(HoldingsChange.ticker_id, Institution.name)
        .join(Institution)
        .where(HoldingsChange.change_type.in_(["new", "increase"]))
    )
    if since is not None:
        whale_q = whale_q.where(HoldingsChange.period >= since)
    for ticker_id, name in db.execute(whale_q).all():
        _add(ticker_id, "whale", name)

    candidate_ids = [tid for tid, entry in weights.items() if len(entry["buyers"]) >= min_weight]
    if not candidate_ids:
        return []

    tickers = db.execute(select(Ticker).where(Ticker.id.in_(candidate_ids))).scalars().all()

    by_sector: dict[str, list[dict]] = {}
    for t in tickers:
        # Not every "ticker" row is a real, look-up-able equity symbol — see utils.tickers for why.
        if not is_real_symbol(t.symbol):
            continue
        entry = weights[t.id]
        sector = t.sector or "Uncategorized"
        by_sector.setdefault(sector, []).append(
            {
                "ticker": t.symbol,
                "name": t.name,
                "weight": len(entry["buyers"]),
                "sources": sorted(entry["sources"]),
            }
        )

    domains = []
    for sector, items in by_sector.items():
        items.sort(key=lambda i: i["weight"], reverse=True)
        domains.append({"sector": sector, "tickers": items[:per_domain_limit]})
    domains.sort(key=lambda d: sum(i["weight"] for i in d["tickers"]), reverse=True)
    return domains


def get_recent_signals(db: Session, limit: int = 50, offset: int = 0, since: date | None = None) -> tuple[list[dict], int]:
    """Combined feed across all three sources, newest-filed first, paginated. Returns (page, total)."""
    return _merged_page(db, limit, offset, ticker_id=None, since=since)


def get_signals_for_ticker(
    db: Session, ticker: Ticker, limit: int = 50, offset: int = 0, since: date | None = None
) -> tuple[list[dict], int]:
    return _merged_page(db, limit, offset, ticker_id=ticker.id, since=since)
