"""Sends Web Push notifications via VAPID. Best-effort by design: no subscription on record,
no VAPID keys configured, or a send failure should never block or fail alert evaluation —
the in-app alert feed (AlertLog) always works regardless of push delivery."""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID

from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import PushSubscription

logger = logging.getLogger(__name__)


async def subscribe(db: AsyncSession, user_id: UUID, endpoint: str, p256dh: str, auth: str) -> PushSubscription:
    existing = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if existing:
        existing.p256dh = p256dh
        existing.auth = auth
        await db.commit()
        return existing

    sub = PushSubscription(
        user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, created_at=datetime.now(UTC)
    )
    db.add(sub)
    await db.commit()
    await db.refresh(sub)
    return sub


async def unsubscribe(db: AsyncSession, endpoint: str) -> None:
    existing = await db.scalar(select(PushSubscription).where(PushSubscription.endpoint == endpoint))
    if existing:
        await db.delete(existing)
        await db.commit()


def send_push_to_user(db: Session, user_id: UUID, title: str, body: str) -> int:
    """Sends to every subscription on record for this user (sync — called from alert_engine,
    which runs inside Celery tasks on a sync Session). Returns the count actually delivered."""
    if not settings.vapid_private_key or not settings.vapid_public_key:
        return 0

    subs = db.scalars(select(PushSubscription).where(PushSubscription.user_id == user_id)).all()
    delivered = 0
    for sub in subs:
        try:
            webpush(
                subscription_info={"endpoint": sub.endpoint, "keys": {"p256dh": sub.p256dh, "auth": sub.auth}},
                data=json.dumps({"title": title, "body": body}),
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_subject},
            )
            delivered += 1
        except WebPushException as exc:
            logger.warning("Push send failed for subscription %s: %s", sub.id, exc)
            if exc.response is not None and exc.response.status_code in (404, 410):
                db.delete(sub)  # endpoint expired or the browser unsubscribed client-side
        except Exception:
            # pywebpush surfaces raw requests exceptions (timeout, DNS failure, connection
            # refused) unwrapped — best-effort delivery must not let those reach the caller.
            logger.exception("Push send failed for subscription %s (network error)", sub.id)
    return delivered
