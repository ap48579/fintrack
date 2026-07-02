"""OllamaResearchAgentClient — ReAct loop powered by deepseek-r1:7b running locally via Ollama.

Loop: Plan → [Think → Action → Observe] × ≤5 → Synthesize
Confidence gate: stops early when ≥ 0.75 of weighted signal coverage is reached.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, Literal

import httpx

from app.clients.research_agent.base import (
    ResearchAgentClient,
    ResearchAgentResult,
    ResearchContext,
    ResearchSourceRef,
    TickerExposure,
)
from app.clients.research_agent.scratchpad import Scratchpad
from app.clients.research_agent.tool_executor import execute_tool
from app.clients.research_agent.tools.registry import tool_descriptions

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signal weights for confidence gate
# ---------------------------------------------------------------------------
_SIGNAL_WEIGHTS: dict[str, float] = {
    "get_insider_trades": 3.0,
    "get_whale_activity": 2.5,
    "get_earnings": 2.0,
    "get_news": 1.5,
    "get_price": 1.0,
    "get_reddit": 0.5,
}
_MAX_WEIGHT = sum(_SIGNAL_WEIGHTS.values())  # 10.5

_MAX_ITERATIONS = 5
_CONFIDENCE_THRESHOLD = 0.75
_OLLAMA_TIMEOUT = 120.0


# ---------------------------------------------------------------------------
# Signal tracker
# ---------------------------------------------------------------------------

class _SignalTracker:
    def __init__(self) -> None:
        self._signals: dict[str, Any] = {}

    def record(self, tool_name: str, content: Any) -> None:
        if content is not None:
            self._signals[tool_name] = content

    def confidence(self) -> float:
        score = sum(_SIGNAL_WEIGHTS.get(t, 0.0) for t in self._signals)
        return score / _MAX_WEIGHT

    def summary_str(self, max_chars: int = 3000) -> str:
        parts = []
        for tool, data in self._signals.items():
            snippet = json.dumps(data, default=str)[:500]
            parts.append(f"[{tool}] {snippet}")
        return "\n".join(parts)[:max_chars]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_think_and_action(text: str) -> tuple[str, dict]:
    """Extract <think>...</think> and the JSON action that follows."""
    think = ""
    think_match = re.search(r"<think>(.*?)</think>", text, re.DOTALL)
    if think_match:
        think = think_match.group(1).strip()

    # Find first JSON object after </think> (or anywhere if no think block)
    remainder = text[think_match.end():] if think_match else text
    json_match = re.search(r"\{[^{}]*\}", remainder, re.DOTALL)
    if json_match:
        try:
            action = json.loads(json_match.group())
            if "tool" in action:
                return think, action
        except json.JSONDecodeError:
            pass

    # Fallback: try to find any JSON in the full text
    for m in re.finditer(r"\{[\s\S]*?\}", text):
        try:
            obj = json.loads(m.group())
            if "tool" in obj:
                return think, obj
        except json.JSONDecodeError:
            continue

    return think, {"tool": "done", "args": {"confidence": 0.5, "reason": "parse_failed"}}


def _context_summary(context: ResearchContext) -> str:
    lines = []
    if context.gdelt_articles:
        headlines = [a.get("title", "") for a in context.gdelt_articles[:5]]
        lines.append(f"Pre-fetched news ({len(context.gdelt_articles)} articles): " + " | ".join(headlines))
    if context.reddit_posts:
        titles = [p.title for p in context.reddit_posts[:3]]
        lines.append(f"Pre-fetched Reddit ({len(context.reddit_posts)} posts): " + " | ".join(titles))
    if context.filings:
        lines.append(f"Pre-fetched filings: {len(context.filings)} recent SEC filings")
    if context.market_snapshots:
        tickers = [s["ticker"] for s in context.market_snapshots]
        lines.append(f"Pre-fetched market snapshots: {', '.join(tickers)}")
    return "\n".join(lines) if lines else "No pre-fetched context."


def _extract_sources(signals: _SignalTracker, context: ResearchContext) -> list[ResearchSourceRef]:
    sources: list[ResearchSourceRef] = []

    # From pre-fetched GDELT articles
    for article in context.gdelt_articles[:5]:
        url = article.get("url", "")
        if url:
            sources.append(ResearchSourceRef(
                source_type="news",
                url=url,
                title=article.get("title", "Untitled"),
                published_at=_parse_gdelt_date(article.get("seendate")),
                excerpt=f"Covered by {article.get('domain', 'unknown')}",
            ))

    # From pre-fetched Reddit
    for post in context.reddit_posts[:3]:
        sources.append(ResearchSourceRef(
            source_type="reddit",
            url=post.permalink,
            title=post.title,
            published_at=post.created_utc,
            excerpt=post.selftext[:200],
        ))

    # From pre-fetched filings
    for filing in context.filings[:2]:
        sources.append(ResearchSourceRef(
            source_type="edgar",
            url=filing.get("edgar_url", ""),
            title=f"{filing.get('filing_type', 'Filing')} filed {filing.get('filed_date', '')}",
            published_at=None,
            excerpt="SEC filing retrieved during research.",
        ))

    # From web_search tool if it ran
    web_data = signals._signals.get("web_search")
    if isinstance(web_data, list):
        for r in web_data[:3]:
            url = r.get("url") or r.get("href", "")
            if url:
                sources.append(ResearchSourceRef(
                    source_type="web",
                    url=url,
                    title=r.get("title", "Web result"),
                    published_at=None,
                    excerpt=r.get("body", r.get("snippet", ""))[:200],
                ))

    return sources


def _parse_gdelt_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ")
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Ollama client
# ---------------------------------------------------------------------------

class OllamaResearchAgentClient(ResearchAgentClient):

    def __init__(self) -> None:
        from app.config import settings
        self._base_url = settings.ollama_base_url.rstrip("/")
        self._model = settings.ollama_model

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def run_deep_research(
        self,
        subject_type: Literal["ticker", "theme"],
        subject: str,
        query: str,
        context: ResearchContext,
    ) -> ResearchAgentResult:
        session_id = f"{subject}_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        pad = Scratchpad(session_id)
        signals = _SignalTracker()

        # ---- Plan ---------------------------------------------------------
        questions = await self._plan(subject_type, subject, query, context)
        pad.plan(questions)
        logger.info("[%s] Plan: %s", session_id, questions)

        # ---- ReAct loop ---------------------------------------------------
        for iteration in range(_MAX_ITERATIONS):
            logger.info("[%s] Iteration %d (confidence=%.2f)", session_id, iteration, signals.confidence())

            prompt = self._react_prompt(subject_type, subject, query, questions, pad, signals, context)
            raw = await self._call_ollama(prompt)
            think, action = _parse_think_and_action(raw)

            pad.think(think)
            logger.debug("[%s] think: %s", session_id, think[:200])

            tool_name = action.get("tool", "done")
            if tool_name == "done":
                logger.info("[%s] Agent chose done at iteration %d", session_id, iteration)
                break

            args = action.get("args", {})
            pad.action(tool_name, args)

            result = await execute_tool(tool_name, args)
            if result.error:
                pad.observation(tool_name, "", error=result.error)
            else:
                signals.record(tool_name, result.content)
                pad.observation(tool_name, result.to_text(max_chars=800))

            if signals.confidence() >= _CONFIDENCE_THRESHOLD:
                logger.info("[%s] Confidence gate reached: %.2f", session_id, signals.confidence())
                break

        # ---- Synthesize ---------------------------------------------------
        return await self._synthesize(subject_type, subject, query, context, pad, signals)

    # ------------------------------------------------------------------
    # Planner
    # ------------------------------------------------------------------

    async def _plan(
        self,
        subject_type: str,
        subject: str,
        query: str,
        context: ResearchContext,
    ) -> list[str]:
        system = (
            "You are a financial research strategist. Given a research subject, "
            "output a JSON array of 3-5 key questions to investigate. "
            "Only output valid JSON — no other text."
        )
        ctx_str = _context_summary(context)
        user = (
            f"Research subject: {subject} ({subject_type})\n"
            f"User query: {query}\n"
            f"Pre-fetched context:\n{ctx_str}\n\n"
            'Output a JSON array of questions, e.g. ["Is the growth story intact?", ...]'
        )
        raw = await self._call_ollama(user, system=system)
        try:
            m = re.search(r"\[.*?\]", raw, re.DOTALL)
            if m:
                questions = json.loads(m.group())
                if isinstance(questions, list) and questions:
                    return [str(q) for q in questions[:5]]
        except (json.JSONDecodeError, ValueError):
            pass
        return [
            f"What is the current financial health of {subject}?",
            f"What do recent insider trades say about {subject}?",
            f"What are institutional whale positions in {subject}?",
        ]

    # ------------------------------------------------------------------
    # ReAct step
    # ------------------------------------------------------------------

    def _react_prompt(
        self,
        subject_type: str,
        subject: str,
        query: str,
        questions: list[str],
        pad: Scratchpad,
        signals: _SignalTracker,
        context: ResearchContext,
    ) -> str:
        tools_str = tool_descriptions()
        questions_str = "\n".join(f"- {q}" for q in questions)
        scratchpad_str = pad.to_context_str(max_entries=20)
        conf = signals.confidence()
        ctx_summary = _context_summary(context)

        return f"""You are an expert financial research analyst using a ReAct loop.

## Research task
Subject: **{subject}** ({subject_type})
Query: {query}

## Questions to investigate
{questions_str}

## Available tools
{tools_str}

## Pre-fetched context (already available — no need to re-fetch these)
{ctx_summary}

## Research trail so far
{scratchpad_str if scratchpad_str else "(none yet)"}

## Current confidence: {conf:.2f} / 1.00 (stop loop at ≥ 0.75)

## Instructions
Choose ONE tool to call next, or choose "done" if you have enough information.
Respond ONLY in this format:

<think>
Your reasoning about what you know and what gap you need to fill next.
</think>
{{"tool": "tool_name", "args": {{"ticker": "{subject if subject_type == "ticker" else "SYMBOL"}"}}}}

To stop:
{{"tool": "done", "args": {{"confidence": 0.85}}}}
"""

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------

    async def _synthesize(
        self,
        subject_type: str,
        subject: str,
        query: str,
        context: ResearchContext,
        pad: Scratchpad,
        signals: _SignalTracker,
    ) -> ResearchAgentResult:
        scratchpad_str = pad.to_context_str(max_entries=40)
        signals_str = signals.summary_str()
        ctx_summary = _context_summary(context)

        system = (
            "You are a senior financial analyst writing a research report. "
            "Output ONLY valid JSON — no markdown fences, no preamble."
        )
        user = f"""Write a research report for the following:

Subject: {subject} ({subject_type})
Query: {query}

Pre-fetched context:
{ctx_summary}

Research trail:
{scratchpad_str}

Signal data collected:
{signals_str if signals_str else "(no tool signals collected)"}

Output a single JSON object with these exact keys:
{{
  "summary": "2-3 sentence executive summary",
  "sentiment_direction": "bullish" | "bearish" | "neutral" | "mixed",
  "full_report": "full markdown analysis report (use ## headers, bullet points)",
  "ticker_links": [
    {{"ticker": "NVDA", "exposure_type": "positive" | "negative" | "neutral", "confidence": 0.8}}
  ]
}}

ticker_links should list relevant tickers exposed to this {'theme' if subject_type == 'theme' else 'subject'}.
For subject_type=ticker, include the ticker itself and any peers mentioned.
"""
        raw = await self._call_ollama(user, system=system)
        result_dict = self._parse_synthesis(raw)

        sources = _extract_sources(signals, context)

        ticker_links = [
            TickerExposure(
                ticker=t.get("ticker", ""),
                exposure_type=t.get("exposure_type", "neutral"),
                confidence=float(t.get("confidence", 0.5)),
            )
            for t in result_dict.get("ticker_links", [])
            if t.get("ticker")
        ]

        return ResearchAgentResult(
            summary=result_dict.get("summary", f"Research complete for {subject}."),
            sentiment_direction=result_dict.get("sentiment_direction", "neutral"),
            full_report=result_dict.get("full_report", raw[:4000]),
            sources=sources,
            ticker_links=ticker_links,
        )

    def _parse_synthesis(self, raw: str) -> dict:
        # Strip markdown code fences if present
        cleaned = re.sub(r"```(?:json)?", "", raw).strip()
        # Find the outermost JSON object
        try:
            m = re.search(r"\{[\s\S]*\}", cleaned)
            if m:
                return json.loads(m.group())
        except (json.JSONDecodeError, ValueError):
            pass
        logger.warning("Could not parse synthesis JSON; using fallback")
        return {
            "summary": raw[:300],
            "sentiment_direction": "neutral",
            "full_report": raw[:4000],
            "ticker_links": [],
        }

    # ------------------------------------------------------------------
    # Ollama HTTP call
    # ------------------------------------------------------------------

    async def _call_ollama(self, user_message: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_ctx": 16384,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_OLLAMA_TIMEOUT) as client:
                resp = await client.post(
                    f"{self._base_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["message"]["content"]
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama HTTP error: %s", exc)
            raise
        except httpx.RequestError as exc:
            logger.error("Ollama connection error (is Ollama running?): %s", exc)
            raise
