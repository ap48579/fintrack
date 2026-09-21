import asyncio

from fastapi import APIRouter
from sqlalchemy import select

from app.db.sync import get_sync_db
from app.models.backtest import Hypothesis, HypothesisRun
from app.schemas.hypothesis import HypothesisItem, HypothesisRunSummary

router = APIRouter(prefix="/hypotheses", tags=["hypotheses"])


@router.get("", response_model=list[HypothesisItem])
async def list_hypotheses() -> list[HypothesisItem]:
    def _run() -> list[HypothesisItem]:
        with get_sync_db() as db:
            hyps = db.scalars(select(Hypothesis).where(Hypothesis.active.is_(True)).order_by(Hypothesis.created_at)).all()
            items = []
            for hyp in hyps:
                latest = db.scalar(
                    select(HypothesisRun)
                    .where(HypothesisRun.hypothesis_id == hyp.id)
                    .order_by(HypothesisRun.run_at.desc())
                )
                items.append(
                    HypothesisItem(
                        name=hyp.name,
                        description=hyp.description,
                        source=hyp.source,
                        params=hyp.params,
                        latest_run=HypothesisRunSummary.model_validate(latest, from_attributes=True)
                        if latest
                        else None,
                    )
                )
            return items

    return await asyncio.to_thread(_run)
