from __future__ import annotations

import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class ScreenerTool(Tool):
    name = "screen_tickers"
    description = (
        "Filter tickers from the fintrack watchlist by sector or theme keyword. "
        "Useful for theme queries to find which tracked tickers are exposed. "
        "Args: {\"keyword\": \"semiconductor\", \"limit\": 10}"
    )

    async def run(self, args: dict) -> ToolResult:
        keyword = args.get("keyword", "").lower().strip()
        limit = int(args.get("limit", 10))
        if not keyword:
            return ToolResult(content=None, error="keyword is required")
        try:
            from sqlalchemy import select

            from app.db.base import AsyncSessionLocal
            from app.models.ticker import Ticker

            async with AsyncSessionLocal() as db:
                rows = await db.execute(select(Ticker).limit(200))
                tickers = rows.scalars().all()

            matches = [
                {"symbol": t.symbol, "name": t.name, "sector": getattr(t, "sector", None)}
                for t in tickers
                if keyword in (t.name or "").lower()
                or keyword in (getattr(t, "sector", "") or "").lower()
                or keyword in t.symbol.lower()
            ]

            return ToolResult(content={"keyword": keyword, "matches": matches[:limit]}, tokens=200)
        except Exception as exc:
            logger.warning("Screener tool failed for keyword %r: %s", keyword, exc)
            return ToolResult(content=None, error=str(exc))
