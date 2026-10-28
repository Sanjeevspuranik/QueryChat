import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse

from app.core.errors import NotFoundError
from app.db.models import User
from app.deps import (
    get_chat_service,
    get_connection_service,
    get_current_user,
    get_session_service,
)
from app.schemas import ChatRequest, MessageOut, SessionCreate, SessionDetail, SessionOut
from app.services.chat_service import ChatService
from app.services.connection_service import ConnectionService
from app.services.export_service import export_result, safe_filename
from app.services.session_service import SessionService

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreate,
    user: User = Depends(get_current_user),
    connections: ConnectionService = Depends(get_connection_service),
    sessions: SessionService = Depends(get_session_service),
):
    connection = await connections.get_owned(user.id, body.connection_id)
    return await sessions.create(user.id, connection.id)


@router.get("", response_model=list[SessionOut])
async def list_sessions(
    user: User = Depends(get_current_user),
    sessions: SessionService = Depends(get_session_service),
):
    return await sessions.list_all(user.id)


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(
    session_id: str,
    user: User = Depends(get_current_user),
    sessions: SessionService = Depends(get_session_service),
):
    session = await sessions.get_owned(user.id, session_id)
    messages = await sessions.messages(session.id)
    return SessionDetail(
        **SessionOut.model_validate(session).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.get("/{session_id}/messages/{message_id}/export")
async def export_message_result(
    session_id: str,
    message_id: str,
    format: str = "csv",
    user: User = Depends(get_current_user),
    sessions: SessionService = Depends(get_session_service),
):
    """Download the stored result of an assistant message (no query is re-run)."""
    session, message = await sessions.get_owned_message(user.id, session_id, message_id)
    if not message.result_json:
        raise NotFoundError("This message has no result to export.")
    body, media_type = export_result(message.result_json, format)
    filename = safe_filename(session.title, format)
    return Response(
        body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    user: User = Depends(get_current_user),
    sessions: SessionService = Depends(get_session_service),
):
    await sessions.delete(user.id, session_id)


async def _sse(events: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    async for event in events:
        yield f"data: {json.dumps(event, default=str)}\n\n"


@router.post("/{session_id}/chat")
async def chat(
    session_id: str,
    body: ChatRequest,
    user: User = Depends(get_current_user),
    service: ChatService = Depends(get_chat_service),
):
    context = await service.prepare(user.id, session_id, body.question)
    return StreamingResponse(
        _sse(service.stream(context)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
