"""Celery beat periodic task schedule. Populated incrementally as each pillar's background job is built.
Plain dict (no celery_app import) to avoid circular imports — celery_app.py applies this to its config."""

BEAT_SCHEDULE: dict[str, dict] = {
    "poll-watchlisted-prices": {
        "task": "price.poll_watchlisted",
        "schedule": 15 * 60,  # every 15 minutes; the task itself no-ops outside market hours
    },
    "check-fundamentals-filings": {
        "task": "fundamentals.check_and_update",
        "schedule": 24 * 60 * 60,  # daily; the task itself no-ops when no new filing is detected
    },
    "check-whale-13f-filings": {
        "task": "whales.check_and_update",
        "schedule": 7 * 24 * 60 * 60,  # weekly; the task itself no-ops when no new 13F is detected
    },
    "research-passive-scan": {
        "task": "research.passive_scan",
        "schedule": 24 * 60 * 60,  # daily; keyless GDELT only, no LLM cost
    },
}
