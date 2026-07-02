from __future__ import annotations

import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class WhalesTool(Tool):
    name = "get_whale_activity"
    description = (
        "Fetch institutional (blue whale) holdings and recent position changes for a ticker "
        "from tracked institutions' 13F filings. Shows who holds it and recent buys/sells. "
        "Args: {\"ticker\": \"NVDA\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            from sqlalchemy import select

            from app.db.base import AsyncSessionLocal
            from app.models.ticker import Ticker
            from app.services import whales_service

            async with AsyncSessionLocal() as db:
                ticker_row = await db.scalar(select(Ticker).where(Ticker.symbol == ticker))
                if not ticker_row:
                    return ToolResult(content={"ticker": ticker, "holders": [], "recent_activity": [], "note": "Ticker not tracked in fintrack DB"})

                holders = await whales_service.get_ticker_holders_async(db, ticker_row.id)
                activity = await whales_service.get_recent_activity_for_ticker_async(db, ticker_row.id)

            return ToolResult(
                content={
                    "ticker": ticker,
                    "holders": [
                        {
                            "institution": h["institution"],
                            "shares": h["shares"],
                            "market_value": h["market_value"],
                            "period": str(h["period"]),
                        }
                        for h in holders
                    ],
                    "recent_activity": [
                        {
                            "institution": a["institution"],
                            "change_type": a["change_type"],
                            "period": str(a["period"]),
                        }
                        for a in activity
                    ],
                },
                tokens=len(str(holders)) // 4,
            )
        except Exception as exc:
            logger.warning("Whale tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
