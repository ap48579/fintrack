"""Deterministic ResearchSourceRef construction from a ResearchContext — shared by any client
that shouldn't ask an LLM to reproduce URLs/dates it might get wrong when we already have them
structured (mock and ollama; the Anthropic client instead lets Claude cite its own web_search
results, since those aren't in `context` to begin with)."""

from datetime import datetime

from app.clients.research_agent.base import ResearchContext, ResearchSourceRef


def parse_gdelt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


def build_sources_from_context(context: ResearchContext) -> list[ResearchSourceRef]:
    sources = []
    for article in context.gdelt_articles[:10]:
        sources.append(
            ResearchSourceRef(
                source_type="news",
                url=article.get("url", ""),
                title=article.get("title", "Untitled"),
                published_at=parse_gdelt_date(article.get("seendate")),
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
