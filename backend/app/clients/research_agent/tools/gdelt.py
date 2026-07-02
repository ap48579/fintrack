from __future__ import annotations

import asyncio
import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class GDELTNewsTool(Tool):
    name = "get_news"
    description = (
        "Fetch recent news articles for a ticker or theme from GDELT (global news, tone-scored). "
        "Returns titles, sources, URLs, sentiment tone, and publication dates. "
        "Args: {\"query\": \"NVDA\", \"days\": 7, \"max_results\": 10}"
    )

    async def run(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        days = int(args.get("days", 7))
        max_results = int(args.get("max_results", 10))
        if not query:
            return ToolResult(content=None, error="query is required")
        try:
            from app.clients import gdelt_client

            articles = await asyncio.to_thread(gdelt_client.get_articles, query, days=days, max_records=max_results)
            volume = await asyncio.to_thread(gdelt_client.get_volume_timeline, query, days=days)
            tone = await asyncio.to_thread(gdelt_client.get_tone_timeline, query, days=days)

            today_tone = tone[-1]["value"] if tone else None
            baseline_tone = sum(t["value"] for t in tone[:-1]) / max(len(tone) - 1, 1) if len(tone) > 1 else None
            tone_shift = round(today_tone - baseline_tone, 2) if today_tone is not None and baseline_tone is not None else None

            return ToolResult(
                content={
                    "articles": [
                        {
                            "title": a.get("title"),
                            "domain": a.get("domain"),
                            "url": a.get("url"),
                            "seendate": a.get("seendate"),
                        }
                        for a in articles[:max_results]
                    ],
                    "tone_shift_today_vs_baseline": tone_shift,
                    "volume_today": volume[-1]["value"] if volume else None,
                },
                tokens=len(str(articles)) // 4,
            )
        except Exception as exc:
            logger.warning("GDELT tool failed for %r: %s", query, exc)
            return ToolResult(content=None, error=str(exc))
