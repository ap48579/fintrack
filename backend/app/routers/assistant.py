import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_db
from app.schemas.research import ChatMessageItem
from app.services import global_assistant_service

router = APIRouter(prefix="/assistant", tags=["assistant"])


class AssistantSendRequest(BaseModel):
    message: str


@router.get("/chat", response_model=list[ChatMessageItem])
async def get_assistant_thread(db: AsyncSession = Depends(get_db)) -> list[ChatMessageItem]:
    messages = await global_assistant_service.get_global_chat_thread(db)
    return [ChatMessageItem.model_validate(m) for m in messages]


@router.delete("/chat", status_code=204)
async def reset_assistant_thread(db: AsyncSession = Depends(get_db)) -> None:
    await global_assistant_service.reset_global_chat_thread(db)


@router.post("/chat/stream")
async def stream_assistant_chat(body: AssistantSendRequest, db: AsyncSession = Depends(get_db)) -> StreamingResponse:
    """Server-Sent Events, same shape as /research/chat/{ticker}/stream: thinking/content deltas
    then a final done event."""

    async def event_stream():
        async for event in global_assistant_service.stream_global_chat_message(db, body.message):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
