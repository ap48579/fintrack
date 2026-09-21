"""Local-hosted research agent — runs entirely on-machine via Ollama, no API key, no per-call
cost. Trade-off versus AnthropicResearchAgentClient: no live web_search tool, so the model
reasons only over the pre-fetched GDELT/Reddit/EDGAR/market context — which is also why
`sources` is built deterministically in Python (see _context_sources) rather than asked of the
model: a 7B local model reproducing URLs/dates from memory is a hallucination risk we don't need
to take when the structured data is already sitting right there in `context`.

Uses Ollama's `format` (JSON-schema-constrained decoding) so the response parses directly into
ResearchAgentResult, the same shape every other client produces. Any model pulled via
`ollama pull <name>` works as long as it accepts a `format` schema — set OLLAMA_MODEL to pick
a different one than the default.
"""

import json
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from app.clients.research_agent._context_sources import build_sources_from_context
from app.clients.research_agent.base import (
    ChatChunk,
    ResearchAgentClient,
    ResearchAgentResult,
    ResearchContext,
    TickerExposure,
    VerdictPhaseEvent,
    VerdictResult,
)
from app.config import settings

_VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "confidence": {"type": "number"},
        "key_risks": {"type": "string"},
        "key_catalysts": {"type": "string"},
    },
    "required": ["verdict", "confidence", "key_risks", "key_catalysts"],
}

# Mirrors research_service.NEWS_LOOKBACK_DAYS/NEWS_MAX_ARTICLES (display-only here, so duplicated
# as a plain constant rather than imported, to avoid a research_agent <-> services import cycle).
NEWS_LOOKBACK_DAYS = 30
NEWS_MAX_ARTICLES = 30

_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "sentiment_direction": {"type": "string", "enum": ["bullish", "bearish", "neutral", "mixed"]},
        "full_report": {"type": "string"},
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
            },
        },
    },
    "required": ["summary", "sentiment_direction", "full_report", "ticker_links"],
}


class OllamaResearchAgentClient(ResearchAgentClient):
    def __init__(self) -> None:
        self._base_url = settings.ollama_base_url
        self._model = settings.ollama_model

    async def run_deep_research(
        self,
        subject_type: Literal["ticker", "theme"],
        subject: str,
        query: str,
        context: ResearchContext,
    ) -> ResearchAgentResult:
        sources = build_sources_from_context(context)

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": self._build_prompt(subject_type, subject, query, context)}],
                    "format": _RESULT_SCHEMA,
                    "stream": False,
                },
            )
        resp.raise_for_status()
        data = json.loads(resp.json()["message"]["content"])

        return ResearchAgentResult(
            summary=data["summary"],
            sentiment_direction=data["sentiment_direction"],
            full_report=data["full_report"],
            sources=sources,
            ticker_links=[TickerExposure(**t) for t in data["ticker_links"]] if subject_type == "theme" else [],
        )

    async def stream_chat(
        self, messages: list[dict], context: ResearchContext, subject: str
    ) -> AsyncIterator[ChatChunk]:
        """Free-form conversational counterpart to run_deep_research: no JSON-schema constraint
        (so no `format` param — that's what keeps `think: true` meaningful; the two don't compose
        well since a schema-constrained final answer leaves the model little room to reason in
        prose first), and streamed so the frontend can render the thinking trace live and then the
        answer, the way a hosted reasoning-model chat UI does."""
        system_prompt = (
            f"You are a financial research analyst having a conversation about {subject}. You have NO internet "
            "access — base every answer strictly on the pre-fetched context below, and say plainly when the "
            "context doesn't cover something rather than guessing.\n\n"
            "Answer only what the user's latest message actually asks. A short factual question (e.g. what a "
            "ticker abbreviation stands for, when a filing was made) gets a short direct answer — do not pad it "
            "into a full news/insider/congress/13F/sentiment report unless the user's message specifically asks "
            "for a broad analysis.\n\n" + self._build_context_block(context)
        )
        async for chunk in self._stream_with_system_prompt(system_prompt, messages):
            yield chunk

    async def stream_text_chat(self, messages: list[dict], system_prompt: str) -> AsyncIterator[ChatChunk]:
        """Same streaming mechanics as stream_chat, but takes an already-built system prompt
        directly instead of a ResearchContext — for callers whose context isn't ticker-shaped
        (e.g. the global assistant, whose context is domain-cloud/hypothesis/aggregate data)."""
        async for chunk in self._stream_with_system_prompt(system_prompt, messages):
            yield chunk

    async def _stream_with_system_prompt(self, system_prompt: str, messages: list[dict]) -> AsyncIterator[ChatChunk]:
        ollama_messages = [{"role": "system", "content": system_prompt}, *messages]

        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream(
                "POST",
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": ollama_messages, "think": True, "stream": True},
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line:
                        continue
                    data = json.loads(line)
                    msg = data.get("message", {})
                    if msg.get("thinking"):
                        yield ChatChunk(thinking=msg["thinking"])
                    if msg.get("content"):
                        yield ChatChunk(content=msg["content"])
                    if data.get("done"):
                        break

    async def generate_verdict(self, ticker: str, context: ResearchContext) -> AsyncIterator[VerdictPhaseEvent]:
        """Three sequential non-streamed passes rather than one: a bull case, a bear case built
        from the *same* context (so it can't claim to be missing information the bull case had),
        then a judge pass that only sees both arguments — not the raw context — and has to weigh
        them rather than re-deriving its own take from scratch."""
        context_block = self._build_context_block(context)

        bull_prompt = (
            f"You are a bullish equity analyst building the strongest possible case FOR buying {ticker}, using "
            f"ONLY the context below. Be specific — cite the actual disclosed trades, news, and data points. If "
            f"the case is genuinely weak, say so rather than manufacturing optimism.\n\n{context_block}"
        )
        bull_case = await self._generate_text(bull_prompt)
        yield VerdictPhaseEvent(phase="bull", text=bull_case)

        bear_prompt = (
            f"You are a skeptical equity analyst building the strongest possible case AGAINST buying {ticker}, "
            f"using ONLY the context below. Look specifically for insider/institutional selling, disclosure "
            f"patterns that cut against the bull thesis, regulatory or valuation risk, and thin/contradictory "
            f"data. Be specific and cite actual data points.\n\n{context_block}"
        )
        bear_case = await self._generate_text(bear_prompt)
        yield VerdictPhaseEvent(phase="bear", text=bear_case)

        judge_prompt = (
            f"You are a portfolio risk manager. Two analysts have argued opposite cases for {ticker}. Weigh them "
            "against each other and reach a verdict — you do not get to see the raw data again, only these two "
            "arguments, so judge them on the strength and specificity of their evidence, not on which one "
            "sounds more confident.\n\n"
            f"BULL CASE:\n{bull_case}\n\nBEAR CASE:\n{bear_case}\n\n"
            "Return a verdict (bullish/bearish/neutral), a confidence between 0 and 1, the key risks, and the "
            "key catalysts to watch. Neutral with low confidence is a legitimate answer when the two cases are "
            "evenly matched or the underlying evidence is thin — do not force a strong call either way."
        )
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={
                    "model": self._model,
                    "messages": [{"role": "user", "content": judge_prompt}],
                    "format": _VERDICT_SCHEMA,
                    "stream": False,
                },
            )
        resp.raise_for_status()
        data = json.loads(resp.json()["message"]["content"])
        result = VerdictResult(
            bull_case=bull_case,
            bear_case=bear_case,
            verdict=data["verdict"],
            confidence=data["confidence"],
            key_risks=data["key_risks"],
            key_catalysts=data["key_catalysts"],
        )
        yield VerdictPhaseEvent(phase="judge", result=result)

    async def _generate_text(self, prompt: str) -> str:
        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json={"model": self._model, "messages": [{"role": "user", "content": prompt}], "stream": False},
            )
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    def _build_context_block(self, context: ResearchContext) -> str:
        lines = ["Pre-fetched context:"]
        if context.gdelt_articles:
            lines.append(
                f"NEWS ({len(context.gdelt_articles)} articles, last {NEWS_LOOKBACK_DAYS} days, "
                "searched for partnerships/M&A, regulatory/FDA actions, earnings, legal, and similar):"
            )
        for a in context.gdelt_articles[:NEWS_MAX_ARTICLES]:
            lines.append(f"- NEWS: {a.get('title')} ({a.get('domain')}, {a.get('seendate')}) {a.get('url')}")
        if context.reddit_posts:
            lines.append("COMMUNITY SENTIMENT (Reddit — informal opinion, not verified news, use only for sentiment/tone):")
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
            if s.get("disclosed_trades"):
                lines.append(f"    disclosed insider/congressional trades: {s['disclosed_trades']}")
        if not (context.gdelt_articles or context.reddit_posts or context.filings or context.market_snapshots):
            lines.append("(no context was found for this subject)")
        return "\n".join(lines)

    def _build_prompt(self, subject_type: str, subject: str, query: str, context: ResearchContext) -> str:
        return "\n".join(
            [
                f"You are a financial research analyst. Research subject_type={subject_type} subject={subject!r}.",
                f"User query: {query}",
                "",
                "You have NO internet access. Base your entire analysis strictly on the pre-fetched context below "
                "— do not invent facts, prices, or events not present here. If the context is thin, say so "
                "plainly in the report rather than filling gaps with assumptions.",
                "",
                self._build_context_block(context),
                "",
                "Synthesize a research report from the context above: an overall sentiment direction, a short "
                "summary (1-2 sentences), and a longer full_report in markdown with headed sections covering "
                "news, discussion, and market/filing data as relevant. Only if subject_type is 'theme', also "
                "identify tickers exposed to this theme from the context, each with positive/negative/neutral "
                "exposure and a confidence between 0 and 1 — otherwise return an empty ticker_links list.",
            ]
        )
