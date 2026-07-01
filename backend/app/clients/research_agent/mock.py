"""Builds a deterministic, plausible report from the real (keyless) GDELT/EDGAR context passed
in, plus the mocked Reddit posts — no LLM call. Used when RESEARCH_AGENT_IMPL=mock.
Set RESEARCH_AGENT_IMPL=ollama to use OllamaResearchAgentClient with deepseek-r1:7b instead."""

import random
import re
from datetime import datetime

from app.clients.research_agent.base import (
    ResearchAgentClient,
    ResearchAgentResult,
    ResearchContext,
    ResearchSourceRef,
    TickerExposure,
)

_POSITIVE_WORDS = {"surge", "beat", "growth", "record", "strong", "soar", "rally", "upgrade", "bullish", "gain"}
_NEGATIVE_WORDS = {"slump", "miss", "cut", "fall", "weak", "plunge", "drop", "downgrade", "bearish", "loss", "curb"}

_THEME_TICKER_HINTS: dict[str, list[tuple[str, str]]] = {
    "ai": [("NVDA", "positive"), ("MSFT", "positive")],
    "chip": [("NVDA", "positive"), ("MU", "positive")],
    "memory": [("MU", "positive")],
    "export": [("NVDA", "negative")],
    "rate": [("AAPL", "neutral")],
    "china": [("AAPL", "negative"), ("NVDA", "negative")],
}


def _score_sentiment(texts: list[str]) -> tuple[str, float]:
    pos = neg = 0
    for text in texts:
        words = set(re.findall(r"[a-z]+", text.lower()))
        pos += len(words & _POSITIVE_WORDS)
        neg += len(words & _NEGATIVE_WORDS)

    if pos == 0 and neg == 0:
        return "neutral", 0.5
    if pos > neg * 1.5:
        return "bullish", min(1.0, 0.5 + (pos - neg) / 10)
    if neg > pos * 1.5:
        return "bearish", min(1.0, 0.5 + (neg - pos) / 10)
    return "mixed", 0.5


class MockResearchAgentClient(ResearchAgentClient):
    async def run_deep_research(
        self, subject_type: str, subject: str, query: str, context: ResearchContext
    ) -> ResearchAgentResult:
        headlines = [a.get("title", "") for a in context.gdelt_articles]
        reddit_titles = [p.title for p in context.reddit_posts]
        sentiment_label, confidence = _score_sentiment(headlines + reddit_titles)
        direction = {"bullish": "bullish", "bearish": "bearish", "neutral": "neutral", "mixed": "mixed"}[
            sentiment_label
        ]

        sources = self._build_sources(context)
        summary = self._build_summary(subject_type, subject, headlines, reddit_titles, direction)
        full_report = self._build_full_report(subject_type, subject, query, context, direction, sources)
        ticker_links = self._build_ticker_links(subject_type, subject, query) if subject_type == "theme" else []

        return ResearchAgentResult(
            summary=summary,
            sentiment_direction=direction,
            full_report=full_report,
            sources=sources,
            ticker_links=ticker_links,
        )

    def _build_sources(self, context: ResearchContext) -> list[ResearchSourceRef]:
        sources = []
        for article in context.gdelt_articles[:5]:
            sources.append(
                ResearchSourceRef(
                    source_type="news",
                    url=article.get("url", ""),
                    title=article.get("title", "Untitled"),
                    published_at=_parse_gdelt_date(article.get("seendate")),
                    excerpt=f"Covered by {article.get('domain', 'unknown source')}",
                )
            )
        for post in context.reddit_posts[:3]:
            sources.append(
                ResearchSourceRef(
                    source_type="reddit",
                    url=post.permalink,
                    title=post.title,
                    published_at=post.created_utc,
                    excerpt=post.selftext[:200],
                )
            )
        for filing in context.filings[:2]:
            sources.append(
                ResearchSourceRef(
                    source_type="edgar",
                    url=filing["edgar_url"],
                    title=f"{filing['filing_type']} filed {filing['filed_date']}",
                    published_at=None,
                    excerpt="Recent SEC filing relevant to this research subject.",
                )
            )
        return sources

    def _build_summary(
        self, subject_type: str, subject: str, headlines: list[str], reddit_titles: list[str], direction: str
    ) -> str:
        subject_label = subject if subject_type == "ticker" else f'the theme "{subject}"'
        coverage = f"{len(headlines)} recent news articles and {len(reddit_titles)} Reddit discussions"
        return (
            f"Coverage of {subject_label} skews {direction} based on {coverage} reviewed. "
            f"{headlines[0] if headlines else 'No standout headline this period.'}"
        )

    def _build_full_report(
        self,
        subject_type: str,
        subject: str,
        query: str,
        context: ResearchContext,
        direction: str,
        sources: list[ResearchSourceRef],
    ) -> str:
        lines = [f"## Research: {subject}", f"**Query:** {query}", f"**Sentiment:** {direction}", ""]
        lines.append("## News Coverage")
        if context.gdelt_articles:
            for a in context.gdelt_articles[:5]:
                lines.append(f"- {a.get('title', 'Untitled')} ({a.get('domain', 'unknown')})")
        else:
            lines.append("- No recent news articles found for this query.")
        lines.append("")
        lines.append("## Reddit Discussion")
        if context.reddit_posts:
            for p in context.reddit_posts[:5]:
                lines.append(f"- r/{p.subreddit}: \"{p.title}\" ({p.score} upvotes, {p.num_comments} comments)")
        else:
            lines.append("- No notable Reddit discussion found for this query.")
        if subject_type == "ticker" and context.filings:
            lines.append("")
            lines.append("## Filings Context")
            for f in context.filings[:3]:
                lines.append(f"- {f['filing_type']} filed {f['filed_date']}: {f['edgar_url']}")
        if context.market_snapshots:
            lines.append("")
            lines.append("## Market & Blue Whale Data")
            for s in context.market_snapshots:
                lines.append(f"### {s['ticker']}")
                if "price" in s:
                    lines.append(f"- Price: ${s['price']:.2f} ({s['change_percent']:+.2f}%), Volume: {s['volume']:,}")
                if s.get("capex_trend"):
                    capex_str = ", ".join(f"{row['period']}: ${row['capex'] / 1e9:.2f}B" for row in s["capex_trend"])
                    lines.append(f"- Capex trend: {capex_str}")
                if s.get("whale_holders"):
                    holders_str = "; ".join(
                        f"{h['institution']} ({h['shares']:,} sh, ${h['market_value'] / 1e9:.2f}B)"
                        for h in s["whale_holders"]
                    )
                    lines.append(f"- Blue whale holders: {holders_str}")
                else:
                    lines.append("- Blue whale holders: none of the tracked institutions currently hold this ticker")
        lines.append("")
        lines.append(
            f"*This report was generated by a mock research agent from {len(sources)} sources for demonstration "
            "purposes — swap in a real LLM API key to replace this with actual multi-step agentic synthesis.*"
        )
        return "\n".join(lines)

    def _build_ticker_links(self, subject_type: str, subject: str, query: str) -> list[TickerExposure]:
        text = f"{subject} {query}".lower()
        links: list[TickerExposure] = []
        for keyword, hints in _THEME_TICKER_HINTS.items():
            if keyword in text:
                for ticker, exposure in hints:
                    if ticker not in {link.ticker for link in links}:
                        links.append(TickerExposure(ticker=ticker, exposure_type=exposure, confidence=round(random.uniform(0.55, 0.9), 2)))
        return links[:4]


def _parse_gdelt_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None
