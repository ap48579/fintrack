from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.clients.research_agent.tools import Tool, ToolResult

logger = logging.getLogger(__name__)

_HEADERS = {"User-Agent": "FinTrack/0.1 (dev@fintrack.local)"}
_MAX_SECTION_CHARS = 4000


def _fetch_and_extract(url: str, section: str) -> str:
    resp = httpx.get(url, headers=_HEADERS, timeout=30, follow_redirects=True)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "")

    if "html" in content_type or url.endswith(".htm") or url.endswith(".html"):
        return _extract_html_section(resp.text, section)
    # Plain text or XML fallback — just regex for the section header
    return _extract_text_section(resp.text, section)


def _strip_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "table"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except ImportError:
        # Fallback: crude tag stripper
        return re.sub(r"<[^>]+>", " ", html)


def _extract_html_section(html: str, section: str) -> str:
    text = _strip_html(html)
    return _extract_text_section(text, section)


def _extract_text_section(text: str, section: str) -> str:
    # Normalise section name for matching: "Item 1A", "item 1a", "MD&A", "mda"
    section_lower = section.lower().strip()
    lines = text.split("\n")

    # Find the start line
    start_idx = None
    for i, line in enumerate(lines):
        line_lower = line.lower().strip()
        if section_lower in line_lower and len(line.strip()) < 120:
            start_idx = i
            break

    if start_idx is None:
        return f"[Section '{section}' not found in filing]"

    # Collect until the next section header (another "Item X" or "Part X" line)
    _next_section_re = re.compile(r"^\s*(item\s+\d|part\s+[iv]+)", re.IGNORECASE)
    collected = []
    for line in lines[start_idx + 1:]:
        if _next_section_re.match(line) and len(collected) > 5:
            break
        collected.append(line)

    extracted = "\n".join(collected).strip()
    if len(extracted) > _MAX_SECTION_CHARS:
        extracted = extracted[:_MAX_SECTION_CHARS] + f"\n... [truncated — {len(extracted) - _MAX_SECTION_CHARS} more chars]"
    return extracted or f"[Section '{section}' found but appears empty]"


class ReadFilingSectionTool(Tool):
    name = "read_filing_section"
    description = (
        "Fetch a specific named section from an SEC filing HTML document (10-K or 10-Q). "
        "Use for Item 1A (Risk Factors), Item 7 (MD&A), Item 1 (Business). "
        "Get the edgar_url first from get_filings. "
        "Args: {\"edgar_url\": \"https://www.sec.gov/...\", \"section\": \"Item 1A\"}"
    )

    async def run(self, args: dict) -> ToolResult:
        url = args.get("edgar_url", "")
        section = args.get("section", "Item 1A")
        if not url:
            return ToolResult(content=None, error="edgar_url is required")
        try:
            text = await asyncio.to_thread(_fetch_and_extract, url, section)
            return ToolResult(content={"section": section, "text": text}, tokens=len(text) // 4)
        except Exception as exc:
            logger.warning("Filing reader failed for %s section %s: %s", url, section, exc)
            return ToolResult(content=None, error=str(exc))
