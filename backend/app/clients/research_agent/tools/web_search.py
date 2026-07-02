from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class WebSearchTool(Tool):
    name = "web_search"
    description = (
        "Search the web for recent news, analyst commentary, or context about a ticker or theme. "
        "Use for anything not covered by the structured data tools (macro context, recent events, "
        "analyst opinion). Args: {\"query\": \"string\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        if not query:
            return ToolResult(content=None, error="query is required")
        try:
            results = await asyncio.to_thread(self._search, query)
            return ToolResult(content=results, tokens=len(str(results)) // 4)
        except Exception as exc:
            logger.warning("DuckDuckGo search failed for %r: %s", query, exc)
            return ToolResult(content=[], error=str(exc))

    def _search(self, query: str) -> list[dict]:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=8))
        return [{"title": r.get("title"), "url": r.get("href"), "snippet": r.get("body")} for r in raw]
