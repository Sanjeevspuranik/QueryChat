from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.pool import AdapterPool
from app.adapters.registry import AdapterRegistry
from app.adapters.url_policy import UrlPolicy
from app.core.errors import NotFoundError
from app.core.security import CredentialCipher
from app.db.models import ChatSession, Connection, Message


class ConnectionService:
    """Manages a user's saved database connections. URLs are encrypted at rest."""

    def __init__(
        self,
        db: AsyncSession,
        cipher: CredentialCipher,
        policy: UrlPolicy,
        registry: AdapterRegistry,
        pool: AdapterPool,
    ) -> None:
        self._db = db
        self._cipher = cipher
        self._policy = policy
        self._registry = registry
        self._pool = pool

    async def test(self, url: str) -> str:
        """Verify the URL is allowed and reachable. Returns the schema preview."""
        await self._policy.check(url)
        adapter = self._registry.create(url)
        await adapter.connect()
        try:
            return await adapter.get_schema()
        finally:
            await adapter.close()

    async def create(self, user_id: str, name: str, url: str) -> Connection:
        await self.test(url)
        connection = Connection(
            user_id=user_id,
            name=name,
            db_type=self._registry.db_type(url),
            url_encrypted=self._cipher.encrypt(url),
        )
        self._db.add(connection)
        await self._db.commit()
        return connection

    async def list_all(self, user_id: str) -> list[Connection]:
        rows = await self._db.scalars(
            select(Connection).where(Connection.user_id == user_id).order_by(Connection.created_at)
        )
        return list(rows)

    async def get_owned(self, user_id: str, connection_id: str) -> Connection:
        connection = await self._db.get(Connection, connection_id)
        if connection is None or connection.user_id != user_id:
            raise NotFoundError("Connection not found.")
        return connection

    async def delete(self, user_id: str, connection_id: str) -> None:
        connection = await self.get_owned(user_id, connection_id)
        session_ids = select(ChatSession.id).where(ChatSession.connection_id == connection.id)
        await self._db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
        await self._db.execute(delete(ChatSession).where(ChatSession.connection_id == connection.id))
        await self._db.delete(connection)
        await self._db.commit()
        await self._pool.evict(connection.id)

    def reveal_url(self, connection: Connection) -> str:
        return self._cipher.decrypt(connection.url_encrypted)
