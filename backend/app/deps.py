from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.container import Container
from app.core.errors import AuthenticationError
from app.db.models import User
from app.services.auth_service import AuthService
from app.services.chat_service import ChatService
from app.services.connection_service import ConnectionService
from app.services.session_service import SessionService

COOKIE_NAME = "access_token"


def get_container(request: Request) -> Container:
    return request.app.state.container


async def get_db(container: Container = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async with container.session_factory() as session:
        yield session


def get_auth_service(db: AsyncSession = Depends(get_db), c: Container = Depends(get_container)) -> AuthService:
    return AuthService(db, c.hasher, c.tokens)


def get_connection_service(
    db: AsyncSession = Depends(get_db), c: Container = Depends(get_container)
) -> ConnectionService:
    return ConnectionService(db, c.cipher, c.policy, c.registry, c.pool)


def get_session_service(db: AsyncSession = Depends(get_db)) -> SessionService:
    return SessionService(db)


def get_chat_service(
    c: Container = Depends(get_container),
    sessions: SessionService = Depends(get_session_service),
    connections: ConnectionService = Depends(get_connection_service),
) -> ChatService:
    return ChatService(c.settings, sessions, connections, c.pool, c.guard, c.llm, c.session_factory)


async def get_current_user(
    request: Request, auth: AuthService = Depends(get_auth_service)
) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise AuthenticationError("Not authenticated.")
    return await auth.get_user(token)
