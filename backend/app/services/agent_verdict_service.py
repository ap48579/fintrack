"""TradingAgents-style bull/bear/judge debate, cached per ticker. Reuses the same pre-fetched
context (news/insider/congress/whale/filings) that the research chat already builds and caches —
a verdict is just a different lens on the same material, not a separate data pipeline."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.research_agent import get_research_agent_client
from app.models.agent_verdict import AgentVerdict
from app.services.research_service import get_or_refresh_chat_context

VERDICT_TTL_HOURS = 24


async def get_cached_verdict(db: AsyncSession, ticker: str) -> AgentVerdict | None:
    return await db.scalar(select(AgentVerdict).where(AgentVerdict.ticker == ticker.upper()))


def is_stale(verdict: AgentVerdict) -> bool:
    return (datetime.now(UTC) - verdict.generated_at) > timedelta(hours=VERDICT_TTL_HOURS)


async def stream_verdict_generation(db: AsyncSession, ticker: str):
    """SSE-friendly generator: yields `{"phase": "bull"|"bear", "text": ...}` as each argument
    completes, then `{"phase": "judge", "verdict": {...}}` once the synthesis is persisted."""
    ticker = ticker.upper()
    client = get_research_agent_client()
    context, _ = await get_or_refresh_chat_context(db, ticker)

    try:
        async for event in client.generate_verdict(ticker, context):
            if event.phase in ("bull", "bear"):
                yield {"phase": event.phase, "text": event.text}
                continue

            result = event.result
            row = await get_cached_verdict(db, ticker)
            if row:
                row.bull_case = result.bull_case
                row.bear_case = result.bear_case
                row.verdict = result.verdict
                row.confidence = result.confidence
                row.key_risks = result.key_risks
                row.key_catalysts = result.key_catalysts
                row.generated_at = datetime.now(UTC)
            else:
                row = AgentVerdict(
                    ticker=ticker,
                    bull_case=result.bull_case,
                    bear_case=result.bear_case,
                    verdict=result.verdict,
                    confidence=result.confidence,
                    key_risks=result.key_risks,
                    key_catalysts=result.key_catalysts,
                    generated_at=datetime.now(UTC),
                )
                db.add(row)
            await db.commit()
            yield {
                "phase": "judge",
                "verdict": {
                    "ticker": ticker,
                    "bull_case": result.bull_case,
                    "bear_case": result.bear_case,
                    "verdict": result.verdict,
                    "confidence": result.confidence,
                    "key_risks": result.key_risks,
                    "key_catalysts": result.key_catalysts,
                    "generated_at": row.generated_at.isoformat(),
                },
            }
    except NotImplementedError:
        yield {"error": "The configured research agent doesn't support verdict generation (Ollama only, for now)."}
