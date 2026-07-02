from __future__ import annotations

import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class PriceTool(Tool):
    name = "get_price"
    description = (
        "Fetch current price, change %, and volume for a ticker (15-min delayed via yfinance). "
        "Args: {\"ticker\": \"NVDA\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            from app.services import price_service

            quote = await price_service.get_quote(ticker)
            return ToolResult(
                content={
                    "ticker": ticker,
                    "price": quote.price,
                    "change_percent": quote.change_percent,
                    "volume": quote.volume,
                    "last_updated": quote.last_updated.isoformat(),
                },
                tokens=100,
            )
        except Exception as exc:
            logger.warning("Price tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
