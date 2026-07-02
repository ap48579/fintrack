from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


def _fetch_earnings(ticker: str) -> list[dict]:
    import yfinance as yf

    t = yf.Ticker(ticker)
    hist = t.earnings_history
    if hist is None or hist.empty:
        return []

    records = []
    for idx, row in hist.tail(8).iterrows():
        eps_estimate = row.get("epsEstimate")
        eps_actual = row.get("epsActual")
        surprise_pct = row.get("surprisePercent")
        beat = None
        if eps_estimate is not None and eps_actual is not None:
            beat = float(eps_actual) > float(eps_estimate)
        records.append({
            "quarter": str(idx.date()) if hasattr(idx, "date") else str(idx),
            "eps_estimate": round(float(eps_estimate), 4) if eps_estimate is not None else None,
            "eps_actual": round(float(eps_actual), 4) if eps_actual is not None else None,
            "surprise_pct": round(float(surprise_pct), 2) if surprise_pct is not None else None,
            "beat": beat,
        })
    return records


class EarningsTool(Tool):
    name = "get_earnings"
    description = (
        "Fetch quarterly EPS estimates vs actuals and surprise % for a ticker (last 8 quarters). "
        "Consistent beats indicate management credibility; misses flag execution risk. "
        "Args: {\"ticker\": \"NVDA\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            records = await asyncio.to_thread(_fetch_earnings, ticker)
            if not records:
                return ToolResult(content={"ticker": ticker, "quarters": [], "summary": "No earnings history found"})

            beats = sum(1 for r in records if r["beat"] is True)
            misses = sum(1 for r in records if r["beat"] is False)
            avg_surprise = sum(r["surprise_pct"] for r in records if r["surprise_pct"] is not None) / max(len(records), 1)

            return ToolResult(
                content={
                    "ticker": ticker,
                    "summary": {
                        "beats_last_8q": beats,
                        "misses_last_8q": misses,
                        "avg_surprise_pct": round(avg_surprise, 2),
                        "streak": f"{beats}/{len(records)} beats",
                    },
                    "quarters": records,
                },
                tokens=len(str(records)) // 4,
            )
        except Exception as exc:
            logger.warning("Earnings tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
