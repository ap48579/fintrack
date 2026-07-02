from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


def _compute_ratios(ticker: str) -> dict:
    import yfinance as yf
    from app.services import fundamentals_service

    t = yf.Ticker(ticker)
    info = t.get_info()
    summary = fundamentals_service.get_fundamentals_summary(ticker)

    price = info.get("currentPrice") or info.get("regularMarketPrice")
    shares = info.get("sharesOutstanding")
    market_cap = info.get("marketCap")
    total_debt = summary.get("total_debt")
    cash = info.get("totalCash") or info.get("cash")
    net_income = summary.get("net_income")
    revenue = summary.get("revenue")
    total_assets = summary.get("total_assets")
    equity = summary.get("total_equity")

    ratios: dict = {"ticker": ticker}

    if price and shares and net_income and net_income > 0:
        eps = net_income / shares
        ratios["pe_ratio"] = round(price / eps, 2) if eps > 0 else None

    if market_cap and total_debt is not None and cash is not None:
        enterprise_value = market_cap + total_debt - cash
        ratios["enterprise_value"] = enterprise_value
        ratios["ev_over_revenue"] = round(enterprise_value / revenue, 2) if revenue and revenue > 0 else None

    if net_income and total_debt is not None and equity:
        invested_capital = total_debt + equity
        ratios["roic_pct"] = round((net_income / invested_capital) * 100, 2) if invested_capital > 0 else None

    if total_debt and equity and equity > 0:
        ratios["debt_to_equity"] = round(total_debt / equity, 2)

    if net_income and market_cap and market_cap > 0:
        ratios["earnings_yield_pct"] = round((net_income / market_cap) * 100, 2)

    ratios["price"] = price
    ratios["market_cap"] = market_cap
    ratios["revenue"] = revenue
    ratios["net_income"] = net_income

    return ratios


class KeyRatiosTool(Tool):
    name = "get_key_ratios"
    description = (
        "Compute key financial ratios for a ticker: P/E, EV/Revenue, ROIC, debt/equity, "
        "earnings yield. Calculated from EDGAR fundamentals + yfinance price. Free, no new API. "
        "Args: {\"ticker\": \"NVDA\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        ticker = args.get("ticker", "").upper()
        if not ticker:
            return ToolResult(content=None, error="ticker is required")
        try:
            ratios = await asyncio.to_thread(_compute_ratios, ticker)
            return ToolResult(content=ratios, tokens=200)
        except Exception as exc:
            logger.warning("Key ratios tool failed for %s: %s", ticker, exc)
            return ToolResult(content=None, error=str(exc))
