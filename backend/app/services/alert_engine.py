"""Evaluates alert_rules against fresh data immediately after each pillar's refresh task —
called from price_tasks/fundamentals_tasks/whales_tasks/research_tasks, all of which already
hold a sync Session mid-transaction. Each evaluate_* function logs an AlertLog row per rule
that fires, and best-effort-sends a web push to that user (push_service no-ops quietly if
they have no subscription or VAPID isn't configured — the in-app feed always works either way)."""

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.research import ResearchCandidate
from app.models.ticker import Ticker
from app.models.user import AlertLog, AlertRule, Watchlist
from app.models.whales import HoldingsChange, Institution
from app.services import push_service

logger = logging.getLogger(__name__)


def _log_alert(db: Session, rule: AlertRule, message: str) -> None:
    delivered = push_service.send_push_to_user(db, rule.user_id, "FinTrack Alert", message) > 0
    db.add(AlertLog(alert_rule_id=rule.id, triggered_at=datetime.now(UTC), message=message, delivered=delivered))
    logger.info("Alert fired (rule %s, type %s): %s", rule.id, rule.rule_type, message)


def _condition_met(condition: str | None, value: float, threshold: float) -> bool:
    if condition == "lt":
        return value < threshold
    return value > threshold  # "gt" and unset both default to greater-than


def evaluate_price_alert(db: Session, ticker: Ticker, change_percent: float) -> int:
    """Price move alerts trigger on absolute move past the threshold — direction doesn't
    matter, condition/threshold sign is ignored, only magnitude is compared."""
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.rule_type == "price_move", AlertRule.ticker_id == ticker.id, AlertRule.active.is_(True)
        )
    ).all()
    fired = 0
    for rule in rules:
        if rule.threshold is not None and abs(change_percent) >= rule.threshold:
            _log_alert(db, rule, f"{ticker.symbol} moved {change_percent:+.2f}% today (threshold {rule.threshold}%)")
            fired += 1
    return fired


def evaluate_fundamental_alert(db: Session, ticker: Ticker, fundamentals_summary: dict) -> int:
    debt_to_equity = fundamentals_summary.get("debt_to_equity")
    if debt_to_equity is None:
        return 0
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.rule_type == "fundamental_threshold",
            AlertRule.ticker_id == ticker.id,
            AlertRule.active.is_(True),
        )
    ).all()
    fired = 0
    for rule in rules:
        if rule.threshold is not None and _condition_met(rule.condition, debt_to_equity, rule.threshold):
            _log_alert(
                db,
                rule,
                f"{ticker.symbol} debt-to-equity is {debt_to_equity:.2f} "
                f"({rule.condition or 'gt'} {rule.threshold})",
            )
            fired += 1
    return fired


def evaluate_whale_alert(db: Session, change: HoldingsChange, ticker: Ticker, institution: Institution) -> int:
    """plan.md's example is specifically opens/exits — increase/decrease are already visible
    in the whale activity feed without needing a dedicated alert."""
    if change.change_type not in ("new", "exit"):
        return 0
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.rule_type == "whale_movement", AlertRule.ticker_id == ticker.id, AlertRule.active.is_(True)
        )
    ).all()
    verb = "opened" if change.change_type == "new" else "exited"
    fired = 0
    for rule in rules:
        _log_alert(db, rule, f"{institution.name} {verb} a position in {ticker.symbol}")
        fired += 1
    return fired


def evaluate_candidate_alerts(db: Session, candidates: list[ResearchCandidate]) -> int:
    fired = 0
    for candidate in candidates:
        ticker = None
        if candidate.subject_type == "ticker":
            ticker = db.scalar(select(Ticker).where(Ticker.symbol == candidate.subject))

        conditions = [AlertRule.subject == candidate.subject]
        if ticker:
            conditions.append(AlertRule.ticker_id == ticker.id)
        rules = db.scalars(
            select(AlertRule).where(
                AlertRule.rule_type == "candidate_flagged", AlertRule.active.is_(True), or_(*conditions)
            )
        ).all()
        for rule in rules:
            _log_alert(db, rule, f"Candidate flagged: {candidate.subject} — {candidate.reason}")
            fired += 1

        if ticker:
            fired += _evaluate_watchlist_candidate_match(db, candidate, ticker)
    return fired


def _evaluate_watchlist_candidate_match(db: Session, candidate: ResearchCandidate, ticker: Ticker) -> int:
    watcher_user_ids = db.scalars(select(Watchlist.user_id).where(Watchlist.ticker_id == ticker.id)).all()
    if not watcher_user_ids:
        return 0
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.rule_type == "watchlist_candidate_match",
            AlertRule.active.is_(True),
            AlertRule.user_id.in_(watcher_user_ids),
        )
    ).all()
    fired = 0
    for rule in rules:
        _log_alert(db, rule, f"Watchlisted {ticker.symbol} was flagged: {candidate.reason}")
        fired += 1
    return fired


# --- Rule management (async, called from the FastAPI router) --------------------------------


async def create_rule(
    db: AsyncSession,
    user_id: UUID,
    rule_type: str,
    ticker_symbol: str | None,
    subject: str | None,
    condition: str | None,
    threshold: float | None,
) -> AlertRule:
    ticker_id = None
    if ticker_symbol:
        ticker = await db.scalar(select(Ticker).where(Ticker.symbol == ticker_symbol.upper()))
        if not ticker:
            raise ValueError(f"Unknown ticker {ticker_symbol.upper()}")
        ticker_id = ticker.id

    rule = AlertRule(
        user_id=user_id,
        rule_type=rule_type,
        ticker_id=ticker_id,
        subject=subject,
        condition=condition,
        threshold=threshold,
        active=True,
        created_at=datetime.now(UTC),
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


async def list_rules(db: AsyncSession, user_id: UUID) -> list[tuple[AlertRule, str | None]]:
    result = await db.execute(
        select(AlertRule, Ticker.symbol)
        .outerjoin(Ticker, AlertRule.ticker_id == Ticker.id)
        .where(AlertRule.user_id == user_id, AlertRule.active.is_(True))
        .order_by(AlertRule.created_at.desc())
    )
    return [(rule, symbol) for rule, symbol in result.all()]


async def delete_rule(db: AsyncSession, user_id: UUID, rule_id: UUID) -> bool:
    """Deactivates rather than hard-deletes — a rule with alert_log history can't be deleted
    without either cascading (destroying the audit trail) or violating the FK. Since `active`
    exists for exactly this purpose, "delete" from the user's perspective just turns it off."""
    rule = await db.scalar(select(AlertRule).where(AlertRule.id == rule_id, AlertRule.user_id == user_id))
    if not rule:
        return False
    rule.active = False
    await db.commit()
    return True


async def list_log(db: AsyncSession, user_id: UUID, limit: int = 50) -> list[tuple[AlertLog, str, str | None]]:
    result = await db.execute(
        select(AlertLog, AlertRule.rule_type, Ticker.symbol)
        .join(AlertRule, AlertLog.alert_rule_id == AlertRule.id)
        .outerjoin(Ticker, AlertRule.ticker_id == Ticker.id)
        .where(AlertRule.user_id == user_id)
        .order_by(AlertLog.triggered_at.desc())
        .limit(limit)
    )
    return [(log, rule_type, symbol) for log, rule_type, symbol in result.all()]
