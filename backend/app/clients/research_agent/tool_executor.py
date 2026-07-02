from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.clients.research_agent.tools import ToolResult
from app.clients.research_agent.tools.registry import PARALLEL_SAFE, TOOL_REGISTRY

logger = logging.getLogger(__name__)

_TOOL_TIMEOUT = 15.0  # seconds per tool call


async def _run_one(tool_name: str, args: dict) -> tuple[str, ToolResult]:
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return tool_name, ToolResult(content=None, error=f"Unknown tool: {tool_name}")
    try:
        result = await asyncio.wait_for(tool.run(args), timeout=_TOOL_TIMEOUT)
    except asyncio.TimeoutError:
        result = ToolResult(content=None, error=f"Tool {tool_name} timed out after {_TOOL_TIMEOUT}s")
    except Exception as exc:
        logger.warning("Tool %s raised: %s", tool_name, exc)
        result = ToolResult(content=None, error=str(exc))
    return tool_name, result


async def execute_tool(tool_name: str, args: dict) -> ToolResult:
    """Run a single tool call."""
    _, result = await _run_one(tool_name, args)
    return result


async def execute_parallel(calls: list[dict[str, Any]]) -> dict[str, ToolResult]:
    """
    Run multiple tool calls concurrently when all are in PARALLEL_SAFE,
    otherwise fall back to sequential execution.

    Each call dict: {"tool": "tool_name", "args": {...}}
    Returns mapping tool_name -> ToolResult (keyed by call index if same tool called twice).
    """
    all_safe = all(c["tool"] in PARALLEL_SAFE for c in calls)

    results: dict[str, ToolResult] = {}

    if all_safe and len(calls) > 1:
        tasks = [_run_one(c["tool"], c.get("args", {})) for c in calls]
        outcomes = await asyncio.gather(*tasks, return_exceptions=False)
        for name, result in outcomes:
            results[name] = result
    else:
        for c in calls:
            name, result = await _run_one(c["tool"], c.get("args", {}))
            results[name] = result

    return results
