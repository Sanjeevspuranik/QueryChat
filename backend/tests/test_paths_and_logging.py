import logging
import sqlite3

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from app.adapters.base import ExecutionLimits
from app.adapters.sql import SqlAdapter
from app.adapters.sqlite_path import SqliteFileError, resolve_sqlite_file
from app.adapters.url_policy import UrlPolicy
from app.container import Container
from app.core.config import BACKEND_DIR, Settings
from app.core.errors import DatabaseConnectionError, UnsupportedDatabaseError
from app.core.logging_setup import configure_logging
from app.main import create_app


@pytest.fixture
def db_file(tmp_path):
    path = tmp_path / "data.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE t (a INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
    return path


def test_resolver_accepts_common_spellings(db_file):
    posix = db_file.as_posix()
    for url in (f"sqlite:///{posix}", f"sqlite:////{posix}", f"sqlite:///{db_file}", f'sqlite:///"{posix}"'):
        assert resolve_sqlite_file(url) == db_file.resolve()


def test_resolver_gives_actionable_errors(tmp_path):
    with pytest.raises(SqliteFileError, match="not found"):
        resolve_sqlite_file(f"sqlite:///{tmp_path.as_posix()}/missing.db")
    with pytest.raises(SqliteFileError, match="folder"):
        resolve_sqlite_file(f"sqlite:///{tmp_path.as_posix()}")
    with pytest.raises(SqliteFileError, match="Relative paths"):
        resolve_sqlite_file("sqlite:///definitely_not_here.db")


async def test_policy_rejects_missing_file_with_clear_message(tmp_path):
    with pytest.raises(UnsupportedDatabaseError, match="not found"):
        await UrlPolicy(True).check(f"sqlite:///{tmp_path.as_posix()}/missing.db")


async def test_adapter_is_read_only_and_never_creates_files(tmp_path, db_file):
    ghost = tmp_path / "ghost.db"
    adapter = SqlAdapter(f"sqlite:///{ghost.as_posix()}", ExecutionLimits())
    with pytest.raises(DatabaseConnectionError, match="not found"):
        await adapter.connect()
    assert not ghost.exists()

    adapter = SqlAdapter(f"sqlite:///{db_file.as_posix()}", ExecutionLimits())
    await adapter.connect()
    try:
        assert (await adapter.execute("SELECT a FROM t")).rows == [[1]]
    finally:
        await adapter.close()


def test_relative_app_database_is_anchored_to_backend_dir():
    settings = Settings(secret_key="s", encryption_key="k", app_database_url="sqlite+aiosqlite:///./querychat.db")
    assert settings.app_database_url == f"sqlite+aiosqlite:///{(BACKEND_DIR / 'querychat.db').as_posix()}"
    absolute = "sqlite+aiosqlite:////tmp/x.db"
    assert Settings(secret_key="s", encryption_key="k", app_database_url=absolute).app_database_url == absolute


@pytest.fixture
async def logged_client(tmp_path):
    log_dir = tmp_path / "logs"
    settings = Settings(  # type: ignore[call-arg]
        app_database_url=f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
        db_bootstrap="create_all",
        encryption_key=Fernet.generate_key().decode(),
        log_to_file=True,
        log_dir=str(log_dir),
    )
    app = create_app(Container(settings))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, log_dir / "server.log"
    configure_logging(Settings(secret_key="s", encryption_key="k", log_to_file=False))  # release the file handle


def _flush() -> None:
    for handler in logging.getLogger().handlers:
        handler.flush()


async def test_server_log_records_requests_with_request_id_and_no_secrets(logged_client):
    client, log_file = logged_client
    secret_url = "postgresql://user:hunter2@db.example.com/prod"

    await client.post("/api/auth/register", json={"email": "a@example.com", "password": "password123"})
    bad = await client.post("/api/connections/test", json={"url": secret_url})
    missing = await client.post("/api/connections/test", json={"url": "sqlite:///no_such_file.db"})
    health = await client.get("/api/health", headers={"x-request-id": "abc123"})
    _flush()

    assert health.headers["x-request-id"] == "abc123"
    assert missing.status_code == 400 and "not found" in missing.json()["detail"]
    assert bad.headers["x-request-id"]
    text = log_file.read_text(encoding="utf-8")
    assert "POST /api/auth/register -> 201" in text
    assert "POST /api/connections/test -> 400" in text
    assert "UnsupportedDatabaseError" in text and "[abc123]" not in text  # health checks stay quiet
    assert "hunter2" not in text and "password123" not in text


async def test_configure_logging_is_idempotent(tmp_path):
    settings = Settings(  # type: ignore[call-arg]
        secret_key="s", encryption_key="k", log_to_file=True, log_dir=str(tmp_path)
    )
    before = len(logging.getLogger().handlers)
    configure_logging(settings)
    first = len(logging.getLogger().handlers)
    configure_logging(settings)
    assert len(logging.getLogger().handlers) == first
    assert first >= before
    configure_logging(Settings(secret_key="s", encryption_key="k", log_to_file=False))
