"""Pillar 4 — Research. Two independent halves:
  A. Passive candidate scan (this file, ticker-only): a cheap daily GDELT heuristic that flags
     watchlisted tickers with unusual news volume or tone shift — no LLM cost, just a prompt to
     go look closer.
  B. On-demand deep research (added alongside the mock/real agent clients): user-triggered,
     synthesizes a full report from GDELT + Reddit + EDGAR + web context.
"""

import asyncio
import logging
from datetime import UTC, date, datetime
from statistics import mean
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.clients import gdelt_client
from app.clients.reddit import get_reddit_client
from app.clients.research_agent import get_research_agent_client
from app.clients.research_agent.base import ResearchContext
from app.models.research import ResearchCandidate, ResearchReport, ResearchSource, ResearchTickerLink
from app.models.ticker import Ticker
from app.models.user import Watchlist
from app.services import alert_engine, fundamentals_service, price_service, whales_service

logger = logging.getLogger(__name__)

VOLUME_SPIKE_RATIO = 2.0  # today's volume vs trailing-average must be at least 2x to flag
TONE_SHIFT_THRESHOLD = 3.0  # GDELT "Average Tone" points (roughly -10..+10 scale)
TIMELINE_DAYS = 14


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

    return snapshot


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
    return "\n".join(lines)


async def trigger_research_stream(db: AsyncSession, subject_type: str, subject: str, query: str):
    """Runs the on-demand research loop, yielding a `{"step": "..."}` progress event before each
    phase so the frontend can show a reasoning trace instead of a blank wait, and a final
    `{"done": True, "report_id": ...}` once the report is persisted. `subject` is normalized to
    its ticker symbol for subject_type == "ticker"; left as free text for "theme"."""
    subject = subject.upper() if subject_type == "ticker" else subject.strip()

    yield {"step": f"Searching news for {subject}…"}
    gdelt_articles = await asyncio.to_thread(gdelt_client.get_articles, subject, days=7, max_records=10)

    yield {"step": "Searching Reddit discussions…"}
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
