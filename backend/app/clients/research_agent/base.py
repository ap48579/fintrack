from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.clients.reddit.base import RedditPost


class ResearchContext(BaseModel):
    """Pre-fetched material the agent synthesizes from. Assembled by research_service so this
    shape is identical regardless of which ResearchAgentClient implementation runs.

    market_snapshots is populated up front for subject_type == "ticker" (we already know which
    symbol to enrich, so the agent can reason with the data). For subject_type == "theme" the
    exposed tickers are only known after synthesis, so it stays empty here and research_service
    appends a market/whale snapshot section to the report afterward instead."""

    gdelt_articles: list[dict] = []
    reddit_posts: list[RedditPost] = []
    filings: list[dict] = []  # only populated for subject_type == "ticker"
    market_snapshots: list[dict] = []  # [{ticker, price, change_percent, volume, capex_trend, whale_holders, whale_recent_activity}]


class ResearchSourceRef(BaseModel):
    source_type: Literal["news", "reddit", "edgar", "web"]
    url: str
    title: str
    published_at: datetime | None
    excerpt: str


class TickerExposure(BaseModel):
    ticker: str
    exposure_type: Literal["positive", "negative", "neutral"]
    confidence: float  # 0-1


class ResearchAgentResult(BaseModel):
    summary: str
    sentiment_direction: Literal["bullish", "bearish", "neutral", "mixed"]
    full_report: str  # longer synthesis, markdown
    sources: list[ResearchSourceRef]
    ticker_links: list[TickerExposure]  # populated for theme queries / related-ticker spillover


class ResearchAgentClient(ABC):
    @abstractmethod
    async def run_deep_research(
        self,
        subject_type: Literal["ticker", "theme"],
        subject: str,
        query: str,
        context: ResearchContext,
    ) -> ResearchAgentResult:
        """Runs the full multi-step research loop and returns a structured, ready-to-persist result."""
