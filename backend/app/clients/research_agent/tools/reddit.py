from __future__ import annotations

import logging

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)


class RedditTool(Tool):
    name = "get_reddit"
    description = (
        "Search Reddit for discussions about a ticker or theme. Returns post titles, scores, "
        "comment counts, and subreddits. Useful for retail sentiment. "
        "Args: {\"query\": \"NVDA earnings\", \"limit\": 10}"
    )

    async def run(self, args: dict) -> ToolResult:
        query = args.get("query", "")
        limit = int(args.get("limit", 10))
        if not query:
            return ToolResult(content=None, error="query is required")
        try:
            from app.clients.reddit import get_reddit_client

            posts = await get_reddit_client().search(query, limit=limit)
            return ToolResult(
                content=[
                    {
                        "subreddit": p.subreddit,
                        "title": p.title,
                        "score": p.score,
                        "num_comments": p.num_comments,
                        "url": p.permalink,
                        "created_utc": p.created_utc.isoformat(),
                    }
                    for p in posts
                ],
                tokens=len(str(posts)) // 4,
            )
        except Exception as exc:
            logger.warning("Reddit tool failed for %r: %s", query, exc)
            return ToolResult(content=[], error=str(exc))
