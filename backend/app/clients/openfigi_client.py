"""Resolves CUSIPs (used by 13F holdings) to ticker symbols via OpenFIGI's free, keyless
mapping API. Used only by Pillar 3 — Pillars 1/2 work directly with ticker symbols."""

import logging
import time

import httpx

_URL = "https://api.openfigi.com/v3/mapping"
_BATCH_SIZE = 10  # keyless tier is rate-limited; keep batches modest
_PREFERRED_EXCHANGE = "US"

logger = logging.getLogger(__name__)


def resolve_cusips(cusips: list[str]) -> dict[str, str | None]:
    """Returns {cusip: ticker_symbol or None}. Best-effort — failures resolve to None rather
    than raising, since a handful of unresolvable CUSIPs shouldn't fail the whole refresh."""
    results: dict[str, str | None] = {}
    unique_cusips = list(dict.fromkeys(cusips))

    for i in range(0, len(unique_cusips), _BATCH_SIZE):
        batch = unique_cusips[i : i + _BATCH_SIZE]
        jobs = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        try:
            resp = httpx.post(_URL, json=jobs, headers={"Content-Type": "application/json"}, timeout=15)
            resp.raise_for_status()
            for cusip, job_result in zip(batch, resp.json(), strict=True):
                results[cusip] = _best_ticker(job_result.get("data"))
        except Exception:
            logger.exception("OpenFIGI batch resolution failed for %s", batch)
            for cusip in batch:
                results.setdefault(cusip, None)
        if i + _BATCH_SIZE < len(unique_cusips):
            time.sleep(2.5)  # stay well under the keyless rate limit

    return results


def _best_ticker(entries: list[dict] | None) -> str | None:
    if not entries:
        return None
    for entry in entries:
        if entry.get("exchCode") == _PREFERRED_EXCHANGE and entry.get("ticker"):
            return entry["ticker"]
    return entries[0].get("ticker")
