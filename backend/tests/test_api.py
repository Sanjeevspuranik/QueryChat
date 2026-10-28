import json
import sqlite3
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.agent.state import QueryRequest
from app.container import Container
from app.core.config import Settings
from app.main import create_app


class FlakyLLM:
    """First query references a missing column; second is correct."""

    def __init__(self) -> None:
        self._queries = ["SELECT nope FROM pets", "SELECT species, COUNT(*) AS n FROM pets GROUP BY species"]

    async def generate_query(self, request: QueryRequest) -> str:
        return self._queries.pop(0)

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str:
        return "There are 2 species."


@pytest.fixture
async def client(tmp_path):
    user_db = tmp_path / "user.db"
    with sqlite3.connect(user_db) as conn:
        conn.execute("CREATE TABLE pets (name TEXT, species TEXT)")
        conn.executemany("INSERT INTO pets VALUES (?, ?)", [("a", "cat"), ("b", "dog"), ("c", "cat")])
    settings = Settings(  # type: ignore[call-arg]
        app_database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        db_bootstrap="create_all",
    )
    app = create_app(Container(settings, llm_factory=FlakyLLM))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            c.user_db_url = f"sqlite:///{user_db}"  # type: ignore[attr-defined]
            yield c


async def _login(c: AsyncClient, email: str = "a@example.com") -> None:
    r = await c.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 201


async def test_requires_auth(client):
    assert (await client.get("/api/sessions")).status_code == 401


async def test_full_flow_with_self_correction_and_isolation(client):
    await _login(client)
    conn = await client.post("/api/connections", json={"name": "pets", "url": client.user_db_url})
    assert conn.status_code == 201 and "url" not in conn.json()
    session = (await client.post("/api/sessions", json={"connection_id": conn.json()["id"]})).json()

    r = await client.post(f"/api/sessions/{session['id']}/chat", json={"question": "pets per species?"})
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert "attempt_failed" in types and "retrying" in types and types[-1] == "done"
    final = events[-1]["message"]
    assert final["status"] == "ok" and final["result"]["row_count"] == 2
    assert len(final["attempts"]) == 2

    detail = (await client.get(f"/api/sessions/{session['id']}")).json()
    assert [m["role"] for m in detail["messages"]] == ["user", "assistant"]

    assistant_id = detail["messages"][1]["id"]
    export = await client.get(f"/api/sessions/{session['id']}/messages/{assistant_id}/export?format=csv")
    assert export.status_code == 200 and "attachment" in export.headers["content-disposition"]
    assert export.content.decode("utf-8-sig").splitlines()[0] == "species,n"
    assert (await client.get(f"/api/sessions/{session['id']}/messages/{assistant_id}/export?format=xlsx")).status_code == 400
    user_id = detail["messages"][0]["id"]
    assert (await client.get(f"/api/sessions/{session['id']}/messages/{user_id}/export")).status_code == 404

    schema = await client.get(f"/api/connections/{conn.json()['id']}/schema")
    assert schema.status_code == 200
    assert schema.json()["tables"][0]["name"] == "pets"

    other = AsyncClient(transport=client._transport, base_url="http://test")
    await _login(other, "b@example.com")
    assert (await other.get(f"/api/sessions/{session['id']}")).status_code == 404
    await other.aclose()


async def test_rejects_vector_store_url(client):
    await _login(client)
    r = await client.post("/api/connections/test", json={"url": "qdrant://host/collection"})
    assert r.status_code == 400
