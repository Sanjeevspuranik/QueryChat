import asyncio
import sqlite3
from contextlib import suppress
from typing import Any

import pytest
from cryptography.fernet import Fernet

from app.adapters.base import ExecutionLimits, SchemaInfo
from app.adapters.registry import default_registry
from app.agent.state import QueryRequest
from app.container import Container
from app.core.config import Settings
from app.core.errors import QueryExecutionError, SecurityViolationError
from app.db.models import User, init_schema
from app.services.chat_service import CANCELLED_ANSWER, ChatService
from app.services.connection_service import ConnectionService
from app.services.session_service import SessionService


@pytest.fixture
def user_db(tmp_path) -> str:
    path = tmp_path / "shop.db"
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT);
            CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total REAL);
            INSERT INTO customers VALUES (1, 'Ann'), (2, 'Bo');
            INSERT INTO orders VALUES (1, 1, 9.5);
            """
        )
    return f"sqlite:///{path}"


@pytest.fixture
def container(tmp_path) -> Container:
    settings = Settings(  # type: ignore[call-arg]
        app_database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        db_bootstrap="create_all",
        encryption_key=Fernet.generate_key().decode(),
    )
    return Container(settings, llm_factory=HangingLLM)


class HangingLLM:
    async def generate_query(self, request: QueryRequest) -> str:
        await asyncio.Event().wait()
        return ""

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str:
        return ""


async def test_schema_info_is_structured_and_renders_prompt_text(user_db):
    adapter = default_registry(ExecutionLimits()).create(user_db)
    await adapter.connect()
    try:
        info = await adapter.get_schema_info()
        text = await adapter.get_schema()
    finally:
        await adapter.close()

    assert isinstance(info, SchemaInfo)
    orders = next(t for t in info.tables if t.name == "orders")
    fk = next(c for c in orders.columns if c.name == "customer_id")
    assert fk.references == "customers.id"
    assert next(c for c in orders.columns if c.name == "id").primary_key
    assert "TABLE orders (id INTEGER PK, customer_id INTEGER FK->customers.id, total REAL)" in text
    assert info.to_dict()["tables"][0]["columns"][0]["name"]


async def test_query_runner_executes_and_blocks_writes(container, user_db):
    runner = container.runner
    result = await runner.run("c1", user_db, "SELECT name FROM customers ORDER BY id")
    assert result.rows == [["Ann"], ["Bo"]]

    with pytest.raises(SecurityViolationError):
        await runner.run("c1", user_db, "DELETE FROM customers")
    with pytest.raises(QueryExecutionError):
        await runner.run("c1", user_db, "SELECT nope FROM customers")
    await container.pool.close_all()


async def test_cancelled_run_persists_assistant_message_and_releases_slot(container, user_db):
    await init_schema(container.engine)
    async with container.session_factory() as db:
        user = User(email="a@example.com", password_hash="x")
        db.add(user)
        await db.commit()
        connections = ConnectionService(db, container.cipher, container.policy, container.registry, container.pool)
        connection = await connections.create(user.id, "shop", user_db)
        sessions = SessionService(db)
        session = await sessions.create(user.id, connection.id)
        chat = ChatService(
            container.settings, sessions, connections, container.pool, container.guard,
            container.llm, container.session_factory,
        )
        ctx = await chat.prepare(user.id, session.id, "slow question")

        async def consume() -> None:
            async for _ in chat.stream(ctx):
                pass

        task = asyncio.create_task(consume())
        await asyncio.sleep(0.5)
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

        stored = await SessionService(db).messages(session.id)
        assert [m.role for m in stored] == ["user", "assistant"]
        assert stored[1].status == "failed" and stored[1].content == CANCELLED_ANSWER
        container.guard.acquire(session.id, user.id, connection.id)  # slot was released
    await container.pool.close_all()
    await container.engine.dispose()
