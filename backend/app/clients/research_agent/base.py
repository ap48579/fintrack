from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
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
    market_snapshots: list[dict] = []  # [{ticker, price, change_percent, volume, capex_trend, whale_holders, whale_recent_activity, disclosed_trades}]


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


class ChatChunk(BaseModel):
    """One streamed delta from stream_chat — thinking and content arrive as separate deltas
    (mirroring Ollama's `think`-enabled response shape), never both set on the same chunk."""

    thinking: str | None = None
    content: str | None = None


class VerdictResult(BaseModel):
    bull_case: str
    bear_case: str
    verdict: Literal["bullish", "bearish", "neutral"]
    confidence: float  # 0-1
    key_risks: str
    key_catalysts: str


class VerdictPhaseEvent(BaseModel):
    """One completed phase of the bull/bear/judge debate — unlike ChatChunk this isn't a
    token-level delta, since each phase is its own non-streamed generation; the frontend shows
    "building bull case..." then reveals the phase's text once this event arrives."""

    phase: Literal["bull", "bear", "judge"]
    text: str | None = None  # set for bull/bear
    result: VerdictResult | None = None  # set for judge (the final structured verdict)


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

    async def stream_chat(
        self, messages: list[dict], context: ResearchContext, subject: str
    ) -> AsyncIterator[ChatChunk]:
        """Conversational counterpart to run_deep_research, for the inline per-ticker research
        chat: streams thinking/content deltas instead of returning one structured result, and
        takes a running message history instead of a single query so follow-ups work. Optional —
        only clients that can stream a live reasoning trace (currently Ollama) implement it."""
        raise NotImplementedError(f"{type(self).__name__} does not support stream_chat")
        yield ChatChunk()  # pragma: no cover — makes this an async generator for type-checking

    async def stream_text_chat(self, messages: list[dict], system_prompt: str) -> AsyncIterator[ChatChunk]:
        """Same as stream_chat but for callers whose context isn't ticker-shaped (e.g. a
        cross-cutting assistant over domain-cloud/hypothesis/aggregate data) — takes an
        already-built system prompt string instead of a ResearchContext."""
        raise NotImplementedError(f"{type(self).__name__} does not support stream_text_chat")
        yield ChatChunk()  # pragma: no cover

    async def generate_verdict(self, ticker: str, context: ResearchContext) -> AsyncIterator[VerdictPhaseEvent]:
        """TradingAgents-style debate: a bull pass argues for buying, a bear pass argues against
        using the same context, then a judge pass weighs both into a verdict — deliberately three
        separate passes rather than one, since a single pass tends to just agree with whatever
        framing it started with. Optional, like stream_chat — only Ollama implements it."""
        raise NotImplementedError(f"{type(self).__name__} does not support generate_verdict")
        yield VerdictPhaseEvent(phase="bull")  # pragma: no cover
