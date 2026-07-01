from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.deps import get_current_user
from app.models.ticker import Ticker
from app.schemas.alerts import AlertLogItem, AlertRuleCreate, AlertRuleResponse
from app.services import alert_engine

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("/rules", response_model=list[AlertRuleResponse])
async def list_rules(
    user_id: UUID = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AlertRuleResponse]:
    rows = await alert_engine.list_rules(db, user_id)
    return [
        AlertRuleResponse(
            id=rule.id,
            rule_type=rule.rule_type,
            ticker=symbol,
            subject=rule.subject,
            condition=rule.condition,
            threshold=rule.threshold,
            active=rule.active,
            created_at=rule.created_at,
        )
        for rule, symbol in rows
    ]


@router.post("/rules", response_model=AlertRuleResponse, status_code=201)
async def create_rule(
    body: AlertRuleCreate, user_id: UUID = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> AlertRuleResponse:
    try:
        rule = await alert_engine.create_rule(
            db, user_id, body.rule_type, body.ticker, body.subject, body.condition, body.threshold
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    ticker_symbol = None
    if rule.ticker_id:
        ticker_symbol = await db.scalar(select(Ticker.symbol).where(Ticker.id == rule.ticker_id))

    return AlertRuleResponse(
        id=rule.id,
        rule_type=rule.rule_type,
        ticker=ticker_symbol,
        subject=rule.subject,
        condition=rule.condition,
        threshold=rule.threshold,
        active=rule.active,
        created_at=rule.created_at,
    )


@router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: UUID, user_id: UUID = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> None:
    deleted = await alert_engine.delete_rule(db, user_id, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert rule not found")


@router.get("/log", response_model=list[AlertLogItem])
async def get_log(
    limit: int = 50, user_id: UUID = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[AlertLogItem]:
    rows = await alert_engine.list_log(db, user_id, limit)
    return [
        AlertLogItem(
            id=log.id,
            rule_type=rule_type,
            ticker=symbol,
            subject=None,
            triggered_at=log.triggered_at,
            message=log.message,
            delivered=log.delivered,
        )
        for log, rule_type, symbol in rows
    ]
