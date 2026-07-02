from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class EDGARFilingsTool(Tool):
    name = "get_filings"
    description = (
        "List recent SEC filings (10-K, 10-Q, 8-K) for a ticker with EDGAR URLs. "
        "Use to see what filings exist before calling read_filing_section. "
        "Args: {\"ticker\": \"NVDA\", \"limit\": 5}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        limit = int(args.get("limit", 5))
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            from app.services import fundamentals_service

            filings = await asyncio.to_thread(fundamentals_service.get_filings, ticker, limit=limit)
            return ToolResult(
                content=[
                    {
                        "filing_type": f["filing_type"],
                        "filed_date": str(f["filed_date"]),
                        "edgar_url": f["edgar_url"],
                    }
                    for f in filings
                ],
                tokens=300,
            )
        except Exception as exc:
            logger.warning("EDGAR filings tool failed for %s: %s", ticker, exc)
            return ToolResult(content=[], error=str(exc))
