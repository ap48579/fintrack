"""Real research agent — built alongside the mock so swapping RESEARCH_AGENT_IMPL=anthropic is
a config change, not a redesign. Unused until ANTHROPIC_API_KEY is configured.

Uses Claude (Opus 4.8) with the server-side web_search tool to fill gaps in the pre-fetched
GDELT/Reddit/EDGAR context, then returns a structured result via output_config.format so the
response can be parsed directly into ResearchAgentResult without prompt-engineering JSON out of
free text."""

import json
from typing import Literal

import anthropic

from app.clients.research_agent.base import (
    ResearchAgentClient,
    ResearchAgentResult,
    ResearchContext,
    ResearchSourceRef,
    TickerExposure,
)
from app.config import settings

_MODEL = "claude-opus-4-8"

_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sentiment_direction": {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
        "full_report": {"type": "string"},
        "sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "source_type": {"type": "string", "enum": ["news", "reddit", "edgar", "web"]},
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "published_at": {"type": ["string", "null"]},
                    "excerpt": {"type": "string"},
                },
                "required": ["source_type", "url", "title", "published_at", "excerpt"],
                "additionalProperties": False,
            },
        },
        "ticker_links": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "exposure_type": {"type": "string", "enum": ["positive", "negative", "neutral"]},
                    "confidence": {"type": "number"},
                },
                "required": ["ticker", "exposure_type", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "sentiment_direction", "full_report", "sources", "ticker_links"],
    "additionalProperties": False,
}


class AnthropicResearchAgentClient(ResearchAgentClient):
    def __init__(self) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    async def run_deep_research(
        self,
        subject_type: Literal["ticker", "theme"],
        subject: str,
        query: str,
        context: ResearchContext,
    ) -> ResearchAgentResult:
        response = await self._client.messages.create(
            model=_MODEL,
            max_tokens=8192,
            thinking={"type": "adaptive"},
            tools=[{"type": "web_search_20260209", "name": "web_search"}],
            output_config={"format": {"type": "json_schema", "schema": _RESULT_SCHEMA}},
            messages=[{"role": "user", "content": self._build_prompt(subject_type, subject, query, context)}],
        )
        data = json.loads(next(b.text for b in response.content if b.type == "text"))
        return ResearchAgentResult(
            summary=data["summary"],
            sentiment_direction=data["sentiment_direction"],
            full_report=data["full_report"],
            sources=[ResearchSourceRef(**s) for s in data["sources"]],
            ticker_links=[TickerExposure(**t) for t in data["ticker_links"]],
        )

    def _build_prompt(self, subject_type: str, subject: str, query: str, context: ResearchContext) -> str:
        lines = [
            f"Research subject_type={subject_type} subject={subject!r}.",
            f"User query: {query}",
            "",
            "Pre-fetched context (use this plus web_search for anything missing or more recent):",
        ]
        for a in context.gdelt_articles[:10]:
            lines.append(f"- NEWS: {a.get('title')} ({a.get('domain')}, {a.get('seendate')}) {a.get('url')}")
        for p in context.reddit_posts[:10]:
            lines.append(f"- REDDIT r/{p.subreddit}: {p.title} ({p.score} upvotes)")
        for f in context.filings[:5]:
            lines.append(f"- FILING: {f['filing_type']} filed {f['filed_date']} {f['edgar_url']}")
        for s in context.market_snapshots:
            lines.append(f"- MARKET DATA for {s['ticker']}:")
            if "price" in s:
                lines.append(f"    price ${s['price']:.2f} ({s['change_percent']:+.2f}%), volume {s['volume']:,}")
            if s.get("capex_trend"):
                lines.append(f"    capex trend: {s['capex_trend']}")
            lines.append(f"    blue whale holders: {s.get('whale_holders') or 'none currently'}")
            if s.get("whale_recent_activity"):
                lines.append(f"    recent whale activity: {s['whale_recent_activity']}")
        lines.append("")
        lines.append(
            "Use web_search to fill gaps in the above context — including current price/volume, recent "
            "capex or investment changes, and institutional ('blue whale') buying/selling for the subject "
            "or any tickers exposed to it — then synthesize a research report: an overall sentiment "
            "direction, a short summary, a longer markdown full_report, a list of cited sources "
            "(news/reddit/edgar/web), and — only if subject_type is 'theme' — a list of exposed tickers "
            "with positive/negative/neutral exposure and a confidence between 0 and 1."
        )
        return "\n".join(lines)
