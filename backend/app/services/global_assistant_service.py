"""Cross-cutting research assistant: answers questions using everything the tool has ingested —
domain-cloud buy concentration, hypothesis backtest results, and aggregate signal stats — rather
than one ticker's context like the per-ticker chat. Reuses ResearchChatMessage for persistence,
keyed by a sentinel "ticker" value, since a chat thread is a chat thread regardless of scope.

Unlike the per-ticker chat's context (GDELT/Reddit/EDGAR — all slow external calls, hence cached
with a TTL), everything here is a fast local DB aggregation, so it's rebuilt fresh on every
message instead of cached — always current, no staleness to manage.
"""

import asyncio
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import edgar_client
from app.clients.research_agent import get_research_agent_client
from app.db.sync import get_sync_db
from app.models.agent_verdict import AgentVerdict
from app.models.backtest import Hypothesis, HypothesisRun
from app.models.congress import CongressTrade
from app.models.insiders import InsiderTrade
from app.models.research import ResearchChatMessage
from app.models.ticker import Ticker
from app.models.whales import HoldingsChange, Institution
from app.services import signals_service

GLOBAL_KEY = "__GLOBAL__"

SYSTEM_PREAMBLE = (
    "You are FinTrack's research assistant. You answer questions using ONLY the data below, "
    "pulled from everything this tool has ingested: SEC Form 4 insider trades, House PTR "
    "congressional trades, 13F institutional (whale) holdings, and backtest results over that "
    "data. You have NO internet access and no data beyond what's listed here.\n\n"
    "CRITICAL: never state a ticker symbol, sector, or trading fact about a company unless it "
    "appears explicitly in the context below. If the user asks about a specific company and "
    "there is no '## Specific data on <TICKER>' section for it below, that means this tool has "
    "no data on it — say exactly that ('I don't have data on <company> in what's been ingested') "
    "instead of guessing its ticker, sector, or activity from general knowledge. Getting a "
    "ticker symbol or sector wrong is worse than admitting you don't know.\n\n"
    "If a '## Specific data on <TICKER>' section IS present, that is real, current data — use it "
    "directly, including any AI verdict already generated for it, rather than re-deriving your "
    "own view from scratch.\n\n"
    "The data is split into distinct categories — Insider trades, Congressional trades, and 13F "
    "whale activity. These are different populations of people/entities and must not be mixed up: "
    "a name from '13F whale activity' is an institution (a fund), never a member of Congress; a "
    "name from 'Congressional trades' is a legislator or their family, never a fund. When a ticker "
    "section includes 'INSIDER NET' / 'CONGRESS NET' / 'WHALE NET' lines, those are the correct, "
    "pre-computed net direction for each category — lead your answer with those, and only use the "
    "detail rows below them for supporting color, being careful not to attribute a detail row to "
    "the wrong category.\n\n"
)


def _detect_ticker_sync(db: Session, message: str) -> dict | None:
    """Looks for a ticker symbol or company name in the user's free-text message, so a question
    about one specific company (e.g. "is bloom energy good to buy?") gets that company's actual
    data injected into context instead of the model guessing its ticker/sector from memory —
    which is exactly what produced a wrong ticker ("BLS" for Bloom Energy, real symbol BE) and a
    wrong sector in the first version of this assistant."""
    words = re.findall(r"[A-Za-z][A-Za-z&.]*", message)

    for w in words:
        if w.isupper() and 1 <= len(w) <= 5:
            t = db.scalar(select(Ticker).where(Ticker.symbol == w))
            if t:
                return {"symbol": t.symbol, "name": t.name, "sector": t.sector, "ticker_row": t}

    for size in (3, 2, 1):
        for i in range(len(words) - size + 1):
            phrase = " ".join(words[i : i + size])
            if len(phrase) < 4:
                continue
            matches = edgar_client.search_companies(phrase, limit=1)
            if not matches:
                continue
            name_lower = matches[0]["name"].lower()
            if phrase.lower() in name_lower or name_lower.startswith(phrase.lower()):
                symbol = matches[0]["ticker"]
                t = db.scalar(select(Ticker).where(Ticker.symbol == symbol))
                return {
                    "symbol": symbol,
                    "name": matches[0]["name"],
                    "sector": t.sector if t else None,
                    "ticker_row": t,
                }
    return None


_BUY_LIKE = {"buy", "new", "increase"}
_SELL_LIKE = {"sell", "decrease", "exit"}


def _net_direction_label(signals: list[dict]) -> str:
    buys = sum(1 for s in signals if s["direction"] in _BUY_LIKE)
    sells = sum(1 for s in signals if s["direction"] in _SELL_LIKE)
    actors = len({s["actor"] for s in signals})
    if buys > sells:
        net = f"net BUY ({buys} buy-side vs {sells} sell-side events)"
    elif sells > buys:
        net = f"net SELL ({sells} sell-side vs {buys} buy-side events)"
    else:
        net = f"MIXED/even ({buys} buy-side, {sells} sell-side events)"
    return f"{net}, {actors} distinct {'person/entity' if actors == 1 else 'people/entities'}"


def _build_ticker_spotlight(db: Session, detected: dict) -> str:
    symbol, name = detected["symbol"], detected["name"]
    t = detected["ticker_row"]
    lines = [f"## Specific data on {symbol} ({name})", f"Sector: {detected['sector'] or 'not on record'}"]

    if t is None:
        lines.append(
            "No insider, congressional, or 13F disclosures on record for this ticker — it hasn't shown up in "
            "any ingested filing."
        )
    else:
        insider = signals_service.get_insider_signals(db, 10, ticker_id=t.id)
        congress = signals_service.get_congress_signals(db, 10, ticker_id=t.id)
        whale = signals_service.get_whale_signals(db, 10, ticker_id=t.id)

        # Net direction is computed here, in Python, rather than left for the model to derive from
        # three raw lists — a small local model reliably conflates "who's in which list" once it
        # has to cross-reference several rows itself (verified: it attributed 13F institution
        # names to "Congressional trades" even with the raw lists correctly labeled below). Giving
        # it the already-correct headline first means a mid-summary mix-up can't change the
        # conclusion, only blur some supporting detail.
        lines.append(f"INSIDER NET: {_net_direction_label(insider)}" if insider else "INSIDER NET: no data")
        lines.append(f"CONGRESS NET: {_net_direction_label(congress)}" if congress else "CONGRESS NET: no data")
        lines.append(f"WHALE NET: {_net_direction_label(whale)}" if whale else "WHALE NET: no data")

        if insider:
            lines.append(
                "Insider trade detail (each row is an INSIDER, i.e. a company officer/director — never a "
                "legislator or fund): "
                + "; ".join(f"{s['actor']} {s['direction']} {s['amount_label']} (filed {s['date']})" for s in insider)
            )
        if congress:
            lines.append(
                "Congressional trade detail (each row is a MEMBER OF CONGRESS or their family — never a fund): "
                + "; ".join(f"{s['actor']} {s['direction']} {s['amount_label']} (filed {s['date']})" for s in congress)
            )
        if whale:
            lines.append(
                "13F whale detail (each row is an INSTITUTIONAL FUND — never a legislator): "
                + "; ".join(f"{s['actor']} {s['direction']} {s['amount_label']}" for s in whale)
            )
        if not (insider or congress or whale):
            lines.append("No insider, congressional, or 13F disclosures on record for this ticker.")

    verdict = db.scalar(select(AgentVerdict).where(AgentVerdict.ticker == symbol))
    if verdict:
        lines.append(
            f"AI bull/bear verdict already generated: **{verdict.verdict}** ({verdict.confidence * 100:.0f}% "
            f"confidence). Key risks: {verdict.key_risks} Key catalysts: {verdict.key_catalysts}"
        )
    else:
        lines.append(
            "No AI bull/bear verdict has been generated for this ticker yet (available from the domain cloud's "
            "sparkle icon on the landing page, if it's a top-3 pick in its sector)."
        )
    return "\n".join(lines)


def _build_aggregate_context_sync(user_message: str) -> str:
    """Runs in a thread (sync DB session) since it's plain SQL aggregation, no LLM/HTTP calls."""
    lines = []
    with get_sync_db() as db:
        detected = _detect_ticker_sync(db, user_message)
        if detected:
            lines.append(_build_ticker_spotlight(db, detected))
            lines.append("")

        since_180 = date.today() - timedelta(days=180)
        domains = signals_service.get_domain_buy_signals(db, since=since_180, min_weight=2, per_domain_limit=5)
        if domains:
            lines.append("## Where disclosed buying is concentrated (last 6 months, 2+ distinct buyers)")
            for d in domains[:10]:
                tickers_str = ", ".join(f"{t['ticker']} (x{t['weight']})" for t in d["tickers"])
                lines.append(f"- {d['sector']}: {tickers_str}")

        hyps = db.scalars(select(Hypothesis).where(Hypothesis.active.is_(True))).all()
        if hyps:
            lines.append("\n## Hypothesis backtest results (signal correlation with forward returns)")
            for hyp in hyps:
                latest = db.scalar(
                    select(HypothesisRun)
                    .where(HypothesisRun.hypothesis_id == hyp.id)
                    .order_by(HypothesisRun.run_at.desc())
                )
                if not latest:
                    continue
                stats = "; ".join(
                    f"{h}: n={v.get('n')} mean_excess={v.get('mean_excess')}% win_rate={v.get('win_rate')}%"
                    for h, v in latest.results.items()
                    if isinstance(v, dict) and "mean_excess" in v
                )
                lines.append(f"- **{hyp.name}** ({hyp.description}): {stats or 'not enough data yet'}")

        insider_count = db.scalar(select(func.count(InsiderTrade.id)))
        congress_count = db.scalar(select(func.count(CongressTrade.id)))
        whale_count = db.scalar(select(func.count(HoldingsChange.id)))
        institutions = sorted(db.scalars(select(Institution.name)).all())
        lines.append(
            f"\n## Data coverage\n- {insider_count} insider (Form 4) trades, {congress_count} congressional "
            f"(PTR) trades, {whale_count} institutional (13F) holdings-change rows on record.\n"
            f"- Tracked institutions: {', '.join(institutions)}"
        )
    return "\n".join(lines) if lines else "(no data ingested yet)"


async def build_global_context(user_message: str) -> str:
    return await asyncio.to_thread(_build_aggregate_context_sync, user_message)


async def get_global_chat_thread(db: AsyncSession) -> list[ResearchChatMessage]:
    result = await db.execute(
        select(ResearchChatMessage)
        .where(ResearchChatMessage.ticker == GLOBAL_KEY)
        .order_by(ResearchChatMessage.created_at)
    )
    return list(result.scalars().all())


async def reset_global_chat_thread(db: AsyncSession) -> None:
    await db.execute(delete(ResearchChatMessage).where(ResearchChatMessage.ticker == GLOBAL_KEY))
    await db.commit()


async def stream_global_chat_message(db: AsyncSession, user_message: str):
    """SSE-friendly generator, same event shape as research_service.stream_chat_message."""
    client = get_research_agent_client()

    prior_messages = await get_global_chat_thread(db)

    db.add(
        ResearchChatMessage(
            ticker=GLOBAL_KEY, role="user", content=user_message, thinking=None, created_at=datetime.now(UTC)
        )
    )
    await db.commit()

    context_text = await build_global_context(user_message)
    system_prompt = SYSTEM_PREAMBLE + context_text
    llm_messages = [{"role": m.role, "content": m.content} for m in prior_messages]
    llm_messages.append({"role": "user", "content": user_message})

    thinking_parts: list[str] = []
    content_parts: list[str] = []
    try:
        async for chunk in client.stream_text_chat(llm_messages, system_prompt):
            if chunk.thinking:
                thinking_parts.append(chunk.thinking)
                yield {"thinking": chunk.thinking}
            if chunk.content:
                content_parts.append(chunk.content)
                yield {"content": chunk.content}
    except NotImplementedError:
        yield {"error": "The configured research agent doesn't support the assistant chat (Ollama only, for now)."}
        return

    assistant_row = ResearchChatMessage(
        ticker=GLOBAL_KEY,
        role="assistant",
        content="".join(content_parts),
        thinking="".join(thinking_parts) or None,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_row)
    await db.commit()
    yield {"done": True, "message_id": str(assistant_row.id)}
