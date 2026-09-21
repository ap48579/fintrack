"""Pillar 4 — Research. Two independent halves:
  A. Passive candidate scan (this file, ticker-only): a cheap daily GDELT heuristic that flags
     watchlisted tickers with unusual news volume or tone shift — no LLM cost, just a prompt to
     go look closer.
  B. On-demand deep research (added alongside the mock/real agent clients): user-triggered,
     synthesizes a full report from GDELT + Reddit + EDGAR + web context.
"""

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from statistics import mean
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.clients import gdelt_client
from app.clients.reddit import get_reddit_client
from app.clients.research_agent import get_research_agent_client
from app.clients.research_agent._context_sources import build_sources_from_context
from app.clients.research_agent.base import ResearchContext, ResearchSourceRef
from app.db.sync import get_sync_db
from app.models.research import (
    ResearchCandidate,
    ResearchChatContext,
    ResearchChatMessage,
    ResearchReport,
    ResearchSource,
    ResearchTickerLink,
)
from app.models.ticker import Ticker
from app.models.user import Watchlist
from app.services import alert_engine, fundamentals_service, price_service, signals_service, whales_service

logger = logging.getLogger(__name__)

VOLUME_SPIKE_RATIO = 2.0  # today's volume vs trailing-average must be at least 2x to flag
TONE_SHIFT_THRESHOLD = 3.0  # GDELT "Average Tone" points (roughly -10..+10 scale)
TIMELINE_DAYS = 14

# Deep-research news pull: a wider window/count than the passive scan's timeline query, plus an
# OR-expansion so a plain company-name query doesn't just surface generic market-recap noise —
# GDELT indexes broadly enough (240+ languages, tens of thousands of sources) that the gap versus
# a paid news API is mostly about *asking it the right question*, not needing a different source.
NEWS_LOOKBACK_DAYS = 30
NEWS_MAX_ARTICLES = 30
_NEWS_SIGNAL_TERMS = (
    "partnership OR acquisition OR merger OR lawsuit OR settlement OR investigation OR recall "
    'OR "FDA" OR approval OR earnings OR guidance OR layoffs OR contract OR breakthrough OR patent'
)


def _build_news_query(subject_name: str) -> str:
    return f'"{subject_name}" ({_NEWS_SIGNAL_TERMS})'


def _scan_ticker(ticker: Ticker) -> tuple[str, float] | None:
    """Returns (reason, score) if this ticker should be flagged today, else None."""
    volume = gdelt_client.get_volume_timeline(ticker.name, days=TIMELINE_DAYS)
    tone = gdelt_client.get_tone_timeline(ticker.name, days=TIMELINE_DAYS)
    if len(volume) < 2:
        return None

    today_vol = volume[-1]["value"]
    baseline_vol = mean(v["value"] for v in volume[:-1])
    vol_ratio = (today_vol / baseline_vol) if baseline_vol > 0 else 0.0

    today_tone = tone[-1]["value"] if len(tone) >= 2 else None
    baseline_tone = mean(t["value"] for t in tone[:-1]) if len(tone) >= 2 else None
    tone_shift = abs(today_tone - baseline_tone) if today_tone is not None and baseline_tone is not None else 0.0

    reasons = []
    if baseline_vol > 0 and vol_ratio >= VOLUME_SPIKE_RATIO:
        reasons.append(f"News volume +{(vol_ratio - 1) * 100:.0f}% vs {len(volume) - 1}-day average")
    if tone_shift >= TONE_SHIFT_THRESHOLD:
        direction = "negative" if today_tone < baseline_tone else "positive"
        reasons.append(f"Average tone shifted {direction} by {tone_shift:.1f} pts vs recent average")

    if not reasons:
        return None

    score = min(1.0, max(vol_ratio / (VOLUME_SPIKE_RATIO * 2), tone_shift / (TONE_SHIFT_THRESHOLD * 2)))
    return "; ".join(reasons), score


def run_passive_scan(db: Session) -> int:
    """Daily heuristic scan over watchlisted tickers. Upserts one ResearchCandidate per
    flagged ticker per day (re-running the same day refreshes the reason/score, not duplicates)."""
    today = date.today()
    ticker_ids = db.scalars(select(Watchlist.ticker_id).distinct()).all()
    tickers = db.scalars(select(Ticker).where(Ticker.id.in_(ticker_ids))).all()

    flagged_count = 0
    new_candidates: list[ResearchCandidate] = []
    for ticker in tickers:
        try:
            result = _scan_ticker(ticker)
        except Exception:
            logger.exception("Passive scan failed for %s", ticker.symbol)
            continue
        if result is None:
            continue
        reason, score = result

        existing = db.scalar(
            select(ResearchCandidate).where(
                ResearchCandidate.subject_type == "ticker",
                ResearchCandidate.subject == ticker.symbol,
                ResearchCandidate.date == today,
            )
        )
        if existing:
            existing.reason, existing.score = reason, score
            new_candidates.append(existing)
        else:
            candidate = ResearchCandidate(
                subject_type="ticker", subject=ticker.symbol, date=today, reason=reason, score=score
            )
            db.add(candidate)
            new_candidates.append(candidate)
        flagged_count += 1

    db.flush()
    alert_engine.evaluate_candidate_alerts(db, new_candidates)
    db.commit()
    return flagged_count


def get_candidates(db: Session, on_date: date | None = None) -> list[ResearchCandidate]:
    on_date = on_date or date.today()
    return list(
        db.scalars(
            select(ResearchCandidate).where(ResearchCandidate.date == on_date).order_by(ResearchCandidate.score.desc())
        ).all()
    )


# --- B. On-demand deep research -------------------------------------------------------------

_REPORT_LOAD_OPTIONS = (
    selectinload(ResearchReport.sources),
    selectinload(ResearchReport.ticker_links).selectinload(ResearchTickerLink.ticker),
)


async def _build_market_snapshot(db: AsyncSession, ticker_symbol: str) -> dict:
    """Price/volume, capex trend, and blue-whale holdings/activity for one ticker — folded into
    the agent's context up front for subject_type == "ticker" (we know the symbol already), or
    appended to the report afterward for subject_type == "theme" (see trigger_research_stream).
    All dates are pre-serialized to ISO strings so this dict is JSON-safe for SSE streaming."""
    snapshot: dict = {"ticker": ticker_symbol.upper()}

    try:
        quote = await price_service.get_quote(ticker_symbol)
        snapshot["price"] = quote.price
        snapshot["change_percent"] = quote.change_percent
        snapshot["volume"] = quote.volume
    except Exception:
        logger.warning("No live quote for market snapshot on %s", ticker_symbol)

    try:
        capex_trend = await asyncio.to_thread(fundamentals_service.get_capex_trend, ticker_symbol, 4)
        snapshot["capex_trend"] = [{"period": row["period"].isoformat(), "capex": row["capex"]} for row in capex_trend]
    except Exception:
        snapshot["capex_trend"] = []

    ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol.upper()))
    if ticker_row:
        holders = await whales_service.get_ticker_holders_async(db, ticker_row.id)
        activity = await whales_service.get_recent_activity_for_ticker_async(db, ticker_row.id)
        snapshot["whale_holders"] = [{**h, "period": h["period"].isoformat()} for h in holders]
        snapshot["whale_recent_activity"] = [{**a, "period": a["period"].isoformat()} for a in activity]
    else:
        snapshot["whale_holders"] = []
        snapshot["whale_recent_activity"] = []

    disclosed_trades = await asyncio.to_thread(_fetch_disclosed_trades_sync, ticker_symbol)
    snapshot["disclosed_trades"] = [{**t, "date": t["date"].isoformat(), "transaction_date": t["transaction_date"].isoformat()} for t in disclosed_trades]

    return snapshot


def _fetch_disclosed_trades_sync(ticker_symbol: str) -> list[dict]:
    """Recent Form 4 insider and House PTR congressional buys/sells for this ticker — run in a
    thread with its own sync session, matching how whale holdings/activity would be fetched if
    they didn't already have async variants (see whales_service's *_async functions)."""
    with get_sync_db() as sync_db:
        ticker_row = sync_db.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol.upper()))
        if not ticker_row:
            return []
        insider = signals_service.get_insider_signals(sync_db, limit=10, ticker_id=ticker_row.id)
        congress = signals_service.get_congress_signals(sync_db, limit=10, ticker_id=ticker_row.id)
        return sorted(insider + congress, key=lambda s: s["date"], reverse=True)[:10]


def _format_market_snapshots_section(snapshots: list[dict]) -> str:
    lines = ["## Market & Blue Whale Data"]
    for s in snapshots:
        lines.append(f"### {s['ticker']}")
        if "price" in s:
            lines.append(f"- Price: ${s['price']:.2f} ({s['change_percent']:+.2f}%), Volume: {s['volume']:,}")
        if s.get("capex_trend"):
            capex_str = ", ".join(f"{row['period']}: ${row['capex'] / 1e9:.2f}B" for row in s["capex_trend"])
            lines.append(f"- Capex trend: {capex_str}")
        if s.get("whale_holders"):
            holders_str = "; ".join(
                f"{h['institution']} ({h['shares']:,} sh, ${h['market_value'] / 1e9:.2f}B)" for h in s["whale_holders"]
            )
            lines.append(f"- Blue whale holders: {holders_str}")
        else:
            lines.append("- Blue whale holders: none of the tracked institutions currently hold this ticker")
        if s.get("whale_recent_activity"):
            activity_str = "; ".join(
                f"{a['institution']} {a['change_type']} ({a['period']})" for a in s["whale_recent_activity"]
            )
            lines.append(f"- Recent whale activity: {activity_str}")
        if s.get("disclosed_trades"):
            trades_str = "; ".join(
                f"{t['actor']} {t['direction']} ({t['amount_label']}, filed {t['date']})" for t in s["disclosed_trades"]
            )
            lines.append(f"- Disclosed insider/congressional trades: {trades_str}")
    return "\n".join(lines)


async def trigger_research_stream(db: AsyncSession, subject_type: str, subject: str, query: str):
    """Runs the on-demand research loop, yielding a `{"step": "..."}` progress event before each
    phase so the frontend can show a reasoning trace instead of a blank wait, and a final
    `{"done": True, "report_id": ...}` once the report is persisted. `subject` is normalized to
    its ticker symbol for subject_type == "ticker"; left as free text for "theme"."""
    subject = subject.upper() if subject_type == "ticker" else subject.strip()

    news_subject_name = subject
    if subject_type == "ticker":
        ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == subject))
        if ticker_row:
            news_subject_name = ticker_row.name

    yield {"step": f"Searching news for {news_subject_name} (partnerships, regulatory, earnings, and more)…"}
    gdelt_articles = await asyncio.to_thread(
        gdelt_client.get_articles,
        _build_news_query(news_subject_name),
        days=NEWS_LOOKBACK_DAYS,
        max_records=NEWS_MAX_ARTICLES,
    )

    yield {"step": "Checking Reddit for community sentiment…"}
    reddit_posts = await get_reddit_client().search(subject, limit=10)

    filings: list[dict] = []
    market_snapshots: list[dict] = []
    if subject_type == "ticker":
        yield {"step": "Pulling recent SEC filings…"}
        try:
            filings = await asyncio.to_thread(fundamentals_service.get_filings, subject, limit=5)
        except Exception:
            logger.warning("Could not fetch filings for research subject %s", subject)

        yield {"step": f"Pulling price, volume, capex & blue whale data for {subject}…"}
        market_snapshots = [await _build_market_snapshot(db, subject)]

    context = ResearchContext(
        gdelt_articles=gdelt_articles, reddit_posts=reddit_posts, filings=filings, market_snapshots=market_snapshots
    )

    yield {"step": "Synthesizing research report…"}
    result = await get_research_agent_client().run_deep_research(subject_type, subject, query, context)

    if subject_type == "theme" and result.ticker_links:
        yield {"step": "Pulling market & blue whale data for exposed tickers…"}
        snapshots = [await _build_market_snapshot(db, link.ticker) for link in result.ticker_links]
        result.full_report += "\n\n" + _format_market_snapshots_section(snapshots)

    yield {"step": "Saving report…"}
    report = ResearchReport(
        subject_type=subject_type,
        subject=subject,
        query=query,
        created_at=datetime.now(UTC),
        summary=result.summary,
        sentiment_direction=result.sentiment_direction,
        full_report=result.full_report,
    )
    db.add(report)
    await db.flush()

    for src in result.sources:
        db.add(
            ResearchSource(
                report_id=report.id,
                source_type=src.source_type,
                url=src.url,
                title=src.title,
                published_at=src.published_at,
                excerpt=src.excerpt,
            )
        )

    for link in result.ticker_links:
        ticker = await price_service.get_or_create_ticker(db, link.ticker)
        db.add(
            ResearchTickerLink(
                report_id=report.id, ticker_id=ticker.id, exposure_type=link.exposure_type, confidence=link.confidence
            )
        )

    await db.commit()
    yield {"done": True, "report_id": str(report.id)}


async def trigger_research(db: AsyncSession, subject_type: str, subject: str, query: str) -> ResearchReport | None:
    """Non-streaming convenience wrapper — drains the progress stream and returns the persisted
    report. Used by anything that doesn't need the reasoning-trace events (e.g. future automation)."""
    report_id: str | None = None
    async for event in trigger_research_stream(db, subject_type, subject, query):
        if event.get("done"):
            report_id = event["report_id"]
    return await get_report(db, UUID(report_id)) if report_id else None


async def get_report(db: AsyncSession, report_id: UUID) -> ResearchReport | None:
    result = await db.execute(
        select(ResearchReport).options(*_REPORT_LOAD_OPTIONS).where(ResearchReport.id == report_id)
    )
    return result.scalar_one_or_none()


async def get_history(db: AsyncSession, subject_type: str, subject: str, limit: int = 20) -> list[ResearchReport]:
    subject = subject.upper() if subject_type == "ticker" else subject.strip()
    result = await db.execute(
        select(ResearchReport)
        .options(*_REPORT_LOAD_OPTIONS)
        .where(ResearchReport.subject_type == subject_type, ResearchReport.subject == subject)
        .order_by(ResearchReport.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_reports_for_ticker(db: AsyncSession, ticker: Ticker, limit: int = 5) -> list[ResearchReport]:
    """Direct ticker research plus theme reports that flagged this ticker as exposed."""
    direct = await db.execute(
        select(ResearchReport)
        .options(*_REPORT_LOAD_OPTIONS)
        .where(ResearchReport.subject_type == "ticker", ResearchReport.subject == ticker.symbol)
    )
    via_theme = await db.execute(
        select(ResearchReport)
        .options(*_REPORT_LOAD_OPTIONS)
        .join(ResearchTickerLink, ResearchTickerLink.report_id == ResearchReport.id)
        .where(ResearchTickerLink.ticker_id == ticker.id)
    )
    combined = {r.id: r for r in [*direct.scalars().all(), *via_theme.scalars().all()]}
    return sorted(combined.values(), key=lambda r: r.created_at, reverse=True)[:limit]


async def get_recent_reports(db: AsyncSession, limit: int = 20) -> list[ResearchReport]:
    """Catalogue of past research across every subject — the feed shown below the trigger form
    so a user can revisit or re-run something without remembering exactly what they asked."""
    result = await db.execute(
        select(ResearchReport).options(*_REPORT_LOAD_OPTIONS).order_by(ResearchReport.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


# --- C. Inline per-ticker research chat ------------------------------------------------------
# A conversational alternative to the report-per-run flow above: one growing thread per ticker,
# backed by a context bundle that's fetched once and reused across follow-up questions instead
# of re-hitting GDELT/EDGAR/whales on every message.

CHAT_CONTEXT_TTL_HOURS = 6

DEFAULT_CHAT_PROMPT = (
    "Give me a comprehensive research analysis of {ticker}. Cover: recent news (partnerships, "
    "product/regulatory/FDA developments, earnings, legal/contract activity), insider and "
    "congressional trading activity, institutional (13F) holdings changes, and your overall "
    "sentiment with reasoning. If the context is thin on any of these, say so plainly rather "
    "than guessing."
)


async def _fetch_chat_context(db: AsyncSession, ticker_symbol: str) -> tuple[ResearchContext, list[ResearchSourceRef]]:
    """Same ingredients as the ticker branch of trigger_research_stream (wide GDELT pull, Reddit
    sentiment, filings, market/whale/disclosed-trades snapshot), assembled once per ticker."""
    ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol))
    news_subject_name = ticker_row.name if ticker_row else ticker_symbol

    gdelt_articles = await asyncio.to_thread(
        gdelt_client.get_articles,
        _build_news_query(news_subject_name),
        days=NEWS_LOOKBACK_DAYS,
        max_records=NEWS_MAX_ARTICLES,
    )
    reddit_posts = await get_reddit_client().search(ticker_symbol, limit=10)
    try:
        filings = await asyncio.to_thread(fundamentals_service.get_filings, ticker_symbol, limit=5)
    except Exception:
        logger.warning("Could not fetch filings for chat context on %s", ticker_symbol)
        filings = []
    market_snapshot = await _build_market_snapshot(db, ticker_symbol)

    context = ResearchContext(
        gdelt_articles=gdelt_articles, reddit_posts=reddit_posts, filings=filings, market_snapshots=[market_snapshot]
    )
    return context, build_sources_from_context(context)


async def get_or_refresh_chat_context(
    db: AsyncSession, ticker_symbol: str, force: bool = False
) -> tuple[ResearchContext, list[ResearchSourceRef]]:
    ticker_symbol = ticker_symbol.upper()
    row = await db.scalar(select(ResearchChatContext).where(ResearchChatContext.ticker == ticker_symbol))
    is_stale = row is None or (datetime.now(UTC) - row.fetched_at) > timedelta(hours=CHAT_CONTEXT_TTL_HOURS)

    if row is not None and not force and not is_stale:
        return ResearchContext.model_validate(row.context_json), [
            ResearchSourceRef.model_validate(s) for s in row.sources_json
        ]

    context, sources = await _fetch_chat_context(db, ticker_symbol)
    sources_json = [s.model_dump(mode="json") for s in sources]
    if row is None:
        row = ResearchChatContext(
            ticker=ticker_symbol,
            context_json=context.model_dump(mode="json"),
            sources_json=sources_json,
            fetched_at=datetime.now(UTC),
        )
        db.add(row)
    else:
        row.context_json = context.model_dump(mode="json")
        row.sources_json = sources_json
        row.fetched_at = datetime.now(UTC)
    await db.commit()
    return context, sources


async def get_chat_thread(
    db: AsyncSession, ticker_symbol: str
) -> tuple[list[ResearchChatMessage], list[ResearchSourceRef]]:
    ticker_symbol = ticker_symbol.upper()
    result = await db.execute(
        select(ResearchChatMessage)
        .where(ResearchChatMessage.ticker == ticker_symbol)
        .order_by(ResearchChatMessage.created_at)
    )
    messages = list(result.scalars().all())

    context_row = await db.scalar(select(ResearchChatContext).where(ResearchChatContext.ticker == ticker_symbol))
    sources = [ResearchSourceRef.model_validate(s) for s in context_row.sources_json] if context_row else []
    return messages, sources


async def reset_chat_thread(db: AsyncSession, ticker_symbol: str) -> None:
    ticker_symbol = ticker_symbol.upper()
    await db.execute(delete(ResearchChatMessage).where(ResearchChatMessage.ticker == ticker_symbol))
    await db.execute(delete(ResearchChatContext).where(ResearchChatContext.ticker == ticker_symbol))
    await db.commit()


async def stream_chat_message(db: AsyncSession, ticker_symbol: str, user_message: str | None):
    """SSE-friendly generator for the inline research chat: yields `{"thinking": delta}` and
    `{"content": delta}` events as the model streams (Ollama's `think`-separated output), then a
    final `{"done": True, "message_id": ..., "sources": [...]}` once the turn is persisted."""
    ticker_symbol = ticker_symbol.upper()
    client = get_research_agent_client()

    prior_messages, _ = await get_chat_thread(db, ticker_symbol)
    context, sources = await get_or_refresh_chat_context(db, ticker_symbol)

    if user_message:
        db.add(
            ResearchChatMessage(
                ticker=ticker_symbol, role="user", content=user_message, thinking=None, created_at=datetime.now(UTC)
            )
        )
        await db.commit()

    # The comprehensive-analysis instruction only belongs on a true cold start (no history, no
    # specific question) — it must NOT be prepended ahead of a real follow-up question, or the
    # model anchors on "cover news/insider/congress/13F/sentiment" and answers that instead of
    # what was actually asked (e.g. "what does V stand for" got a full sector-style report,
    # because the model saw the comprehensive-analysis prompt as message #1 either way).
    if not prior_messages and not user_message:
        llm_messages = [{"role": "user", "content": DEFAULT_CHAT_PROMPT.format(ticker=ticker_symbol)}]
    else:
        llm_messages = [{"role": m.role, "content": m.content} for m in prior_messages]
        if user_message:
            llm_messages.append({"role": "user", "content": user_message})

    thinking_parts: list[str] = []
    content_parts: list[str] = []
    try:
        async for chunk in client.stream_chat(llm_messages, context, ticker_symbol):
            if chunk.thinking:
                thinking_parts.append(chunk.thinking)
                yield {"thinking": chunk.thinking}
            if chunk.content:
                content_parts.append(chunk.content)
                yield {"content": chunk.content}
    except NotImplementedError:
        yield {"error": "The configured research agent doesn't support live chat (Ollama only, for now)."}
        return

    assistant_row = ResearchChatMessage(
        ticker=ticker_symbol,
        role="assistant",
        content="".join(content_parts),
        thinking="".join(thinking_parts) or None,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_row)
    await db.commit()

    yield {
        "done": True,
        "message_id": str(assistant_row.id),
        "sources": [s.model_dump(mode="json") for s in sources],
    }
