from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCRATCHPAD_DIR = Path(os.getenv("RESEARCH_SCRATCHPAD_DIR", "/tmp/fintrack_research"))
_MAX_TOKENS = 12_000
_APPROX_CHARS_PER_TOKEN = 4


class Scratchpad:
    """JSONL audit trail for one research session."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._entries: list[dict] = []
        self._total_chars: int = 0
        _SCRATCHPAD_DIR.mkdir(parents=True, exist_ok=True)
        self._path = _SCRATCHPAD_DIR / f"{session_id}.jsonl"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def append(self, entry_type: str, data: dict[str, Any]) -> None:
        entry = {
            "ts": time.time(),
            "type": entry_type,
            **data,
        }
        line = json.dumps(entry, default=str)
        self._entries.append(entry)
        self._total_chars += len(line)
        self._flush_line(line)

        if self._total_chars // _APPROX_CHARS_PER_TOKEN > _MAX_TOKENS:
            self._compact()

    def think(self, text: str) -> None:
        self.append("think", {"text": text[:2000]})

    def action(self, tool: str, args: dict) -> None:
        self.append("action", {"tool": tool, "args": args})

    def observation(self, tool: str, result_summary: str, error: str | None = None) -> None:
        self.append("observation", {"tool": tool, "summary": result_summary[:1000], "error": error})

    def plan(self, questions: list[str]) -> None:
        self.append("plan", {"questions": questions})

    def synthesis(self, summary: str, confidence: float) -> None:
        self.append("synthesis", {"summary": summary[:500], "confidence": confidence})

    def to_context_str(self, max_entries: int = 30) -> str:
        """Return recent entries as a compact string for the LLM prompt."""
        recent = self._entries[-max_entries:]
        lines = []
        for e in recent:
            t = e["type"]
            if t == "think":
                lines.append(f"[THINK] {e['text']}")
            elif t == "action":
                lines.append(f"[ACTION] {e['tool']}({json.dumps(e['args'])})")
            elif t == "observation":
                status = f"ERROR: {e['error']}" if e.get("error") else e.get("summary", "")
                lines.append(f"[OBS]   {e['tool']} → {status}")
            elif t == "plan":
                qs = " | ".join(e.get("questions", []))
                lines.append(f"[PLAN]  {qs}")
            elif t == "synthesis":
                lines.append(f"[SYNTH] conf={e['confidence']:.2f}  {e['summary']}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _flush_line(self, line: str) -> None:
        try:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as exc:
            logger.warning("Scratchpad flush failed: %s", exc)

    def _compact(self) -> None:
        """Keep only the last 20 entries in memory; archive the rest to disk (already flushed)."""
        kept = self._entries[-20:]
        self._entries = kept
        self._total_chars = sum(len(json.dumps(e, default=str)) for e in kept)
        logger.debug("Scratchpad compacted for session %s", self.session_id)
