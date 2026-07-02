from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class FundamentalsTool(Tool):
    name = "get_fundamentals"
    description = (
        "Fetch SEC EDGAR fundamentals for a ticker: revenue, net income, total debt, assets, "
        "capex trend (quarterly history). Sourced directly from EDGAR XBRL filings. "
        "Args: {\"ticker\": \"NVDA\", \"quarters\": 8}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        quarters = int(args.get("quarters", 8))
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            from app.services import fundamentals_service

            summary = await asyncio.to_thread(fundamentals_service.get_fundamentals_summary, ticker)
            history = await asyncio.to_thread(fundamentals_service.get_fundamentals_history, ticker, quarters)
            capex = await asyncio.to_thread(fundamentals_service.get_capex_trend, ticker, quarters)

            return ToolResult(
                content={
                    "ticker": ticker,
                    "latest": summary,
                    "quarterly_history": history[:quarters],
                    "capex_trend": [{"period": str(c["period"]), "capex": c["capex"]} for c in capex],
                },
                tokens=(len(str(summary)) + len(str(history))) // 4,
            )
        except Exception as exc:
            logger.warning("Fundamentals tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
