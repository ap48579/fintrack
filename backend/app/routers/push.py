from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.base import get_db
from app.deps import get_current_user
from app.schemas.push import PushSubscribeRequest, PushUnsubscribeRequest, VapidPublicKeyResponse
from app.services import push_service

router = APIRouter(prefix="/push", tags=["push"])


@router.get("/vapid-public-key", response_model=VapidPublicKeyResponse)
async def get_vapid_public_key() -> VapidPublicKeyResponse:
    return VapidPublicKeyResponse(public_key=settings.vapid_public_key)


@router.post("/subscribe", status_code=201)
async def subscribe(
    body: PushSubscribeRequest, user_id: UUID = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    await push_service.subscribe(db, user_id, body.endpoint, body.keys.p256dh, body.keys.auth)
    return {"status": "subscribed"}


@router.post("/unsubscribe", status_code=204)
async def unsubscribe(body: PushUnsubscribeRequest, db: AsyncSession = Depends(get_db)) -> None:
    await push_service.unsubscribe(db, body.endpoint)
