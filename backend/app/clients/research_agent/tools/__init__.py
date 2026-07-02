from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    content: Any
    tokens: int = 0
    error: str | None = None

    def is_empty(self) -> bool:
        return not self.content and not self.error

    def to_text(self, max_chars: int = 2000) -> str:
        if self.error:
            return f"[ERROR] {self.error}"
        text = str(self.content) if not isinstance(self.content, str) else self.content
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... [truncated, {len(text) - max_chars} chars omitted]"
        return text


class Tool:
    name: str = ""
    description: str = ""

    async def run(self, args: dict) -> ToolResult:
        raise NotImplementedError

    def run_sync(self, args: dict) -> ToolResult:
        return asyncio.get_event_loop().run_until_complete(self.run(args))
