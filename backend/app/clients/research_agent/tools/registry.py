from __future__ import annotations

from app.clients.research_agent.tools import Tool
from app.clients.research_agent.tools.web_search import WebSearchTool
from app.clients.research_agent.tools.gdelt import GDELTNewsTool
from app.clients.research_agent.tools.reddit import RedditTool
from app.clients.research_agent.tools.edgar import EDGARFilingsTool
from app.clients.research_agent.tools.insider_trades import InsiderTradesTool
from app.clients.research_agent.tools.filing_reader import ReadFilingSectionTool
from app.clients.research_agent.tools.earnings import EarningsTool
from app.clients.research_agent.tools.fundamentals import FundamentalsTool
from app.clients.research_agent.tools.key_ratios import KeyRatiosTool
from app.clients.research_agent.tools.price import PriceTool
from app.clients.research_agent.tools.whales import WhalesTool
from app.clients.research_agent.tools.screener import ScreenerTool

# Tools that can run concurrently (no DB writes, no shared rate-limited resource)
PARALLEL_SAFE: set[str] = {
    "web_search",
    "get_news",
    "get_reddit",
    "get_price",
    "get_earnings",
    "get_key_ratios",
}

TOOL_REGISTRY: dict[str, Tool] = {
    t.name: t
    for t in [
        WebSearchTool(),
        GDELTNewsTool(),
        RedditTool(),
        EDGARFilingsTool(),
        InsiderTradesTool(),
        ReadFilingSectionTool(),
        EarningsTool(),
        FundamentalsTool(),
        KeyRatiosTool(),
        PriceTool(),
        WhalesTool(),
        ScreenerTool(),
    ]
}


def tool_descriptions() -> str:
    lines = []
    for name, tool in TOOL_REGISTRY.items():
        lines.append(f"- **{name}**: {tool.description}")
    return "\n".join(lines)
