from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.models import ChatSession, Message


class SessionService:
    """CRUD for chat sessions and their messages. Every query is scoped by user_id."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, user_id: str, connection_id: str) -> ChatSession:
        session = ChatSession(user_id=user_id, connection_id=connection_id)
        self._db.add(session)
        await self._db.commit()
        return session

    async def list_all(self, user_id: str) -> list[ChatSession]:
        rows = await self._db.scalars(
            select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at.desc())
        )
        return list(rows)

    async def get_owned(self, user_id: str, session_id: str) -> ChatSession:
        session = await self._db.get(ChatSession, session_id)
        if session is None or session.user_id != user_id:
            raise NotFoundError("Chat session not found.")
        return session

    async def get_owned_message(self, user_id: str, session_id: str, message_id: str) -> tuple[ChatSession, Message]:
        session = await self.get_owned(user_id, session_id)
        message = await self._db.get(Message, message_id)
        if message is None or message.session_id != session.id:
            raise NotFoundError("Message not found.")
        return session, message

    async def messages(self, session_id: str, limit: int | None = None) -> list[Message]:
        query = select(Message).where(Message.session_id == session_id)
        if limit:
            rows = await self._db.scalars(query.order_by(Message.seq.desc()).limit(limit))
            return list(reversed(list(rows)))
        return list(await self._db.scalars(query.order_by(Message.seq)))

    async def delete(self, user_id: str, session_id: str) -> None:
        session = await self.get_owned(user_id, session_id)
        await self._db.execute(delete(Message).where(Message.session_id == session.id))
        await self._db.delete(session)
        await self._db.commit()

    async def rename(self, session: ChatSession, title: str) -> None:
        session.title = title
        await self._db.commit()

    async def add_message(self, session_id: str, role: str, content: str, **extra) -> Message:
        """Append with a per-session monotonic seq (unique constraint guards races)."""
        next_seq = await self._db.scalar(
            select(func.coalesce(func.max(Message.seq), 0) + 1).where(Message.session_id == session_id)
        )
        message = Message(session_id=session_id, seq=next_seq, role=role, content=content, **extra)
        self._db.add(message)
        await self._db.commit()
        return message
