"""GDELT DOC 2.0 API — free, keyless news search/analysis, used for the passive candidate
scan (volume/tone timelines) and as a context source during deep research (article search).

GDELT's keyless tier documents a 1-request/5-seconds limit but enforces something stricter in
practice (a burst of requests triggers a longer cooldown) — this client serializes all requests
through one minimum-interval gate to stay well clear of it."""

import logging
import threading
import time
from datetime import date, datetime

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_MIN_INTERVAL_SECONDS = 6.0

_last_request_at = 0.0
_lock = threading.Lock()


def _throttled_get(params: dict) -> httpx.Response | None:
    """Returns None (rather than raising) on network failure — GDELT's free tier is flaky
    enough under load that timeouts are a routine outcome, not an exceptional one, and callers
    already treat a missing/bad response as "no data this run" rather than a hard error."""
    global _last_request_at
    with _lock:
        wait = _MIN_INTERVAL_SECONDS - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        try:
            resp = httpx.get(_BASE_URL, params=params, timeout=20)
        except httpx.HTTPError as exc:
            logger.warning("GDELT request failed: %s", exc)
            return None
        finally:
            _last_request_at = time.monotonic()
    return resp


def _safe_json(resp: httpx.Response | None) -> dict | None:
    """GDELT's free tier can return HTTP 200 with a non-JSON body (rate-limit text, an HTML
    maintenance page, a truncated response) — a 200 status doesn't guarantee a parseable body."""
    if resp is None:
        return None
    if resp.status_code != 200:
        logger.warning("GDELT request failed (%s): %s", resp.status_code, resp.text[:200])
        return None
    try:
        return resp.json()
    except ValueError:
        logger.warning("GDELT returned non-JSON body despite 200 status: %s", resp.text[:200])
        return None


def _parse_timeline(resp: httpx.Response | None) -> list[dict]:
    data = _safe_json(resp)
    if data is None:
        return []
    series = data.get("timeline", [])
    if not series:
        return []
    return [
        {"date": datetime.strptime(point["date"], "%Y%m%dT%H%M%SZ").date(), "value": point["value"]}
        for point in series[0]["data"]
    ]


def get_volume_timeline(query: str, days: int = 14) -> list[dict]:
    """Daily 'Volume Intensity' — the share of all monitored global news mentioning `query`."""
    resp = _throttled_get({"query": query, "mode": "timelinevol", "format": "json", "timespan": f"{days}days"})
    return _parse_timeline(resp)


def get_tone_timeline(query: str, days: int = 14) -> list[dict]:
    """Daily 'Average Tone' — roughly -10 (very negative) to +10 (very positive)."""
    resp = _throttled_get({"query": query, "mode": "timelinetone", "format": "json", "timespan": f"{days}days"})
    return _parse_timeline(resp)


def get_articles(query: str, days: int = 2, max_records: int = 10) -> list[dict]:
    """Recent article list — used by Pillar 4b's deep-research context assembly."""
    resp = _throttled_get(
        {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "timespan": f"{days}days",
            "maxrecords": max_records,
            "sort": "hybridrel",
        }
    )
    data = _safe_json(resp)
    return data.get("articles", []) if data else []
