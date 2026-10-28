import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from app.db.migrate import upgrade_to_head
from app.db.models import Base


def _tables(path) -> set[str]:
    return set(inspect(create_engine(f"sqlite:///{path}")).get_table_names())


def test_migration_creates_schema_matching_models(tmp_path):
    path = tmp_path / "app.db"
    upgrade_to_head(f"sqlite+aiosqlite:///{path}")
    assert {"users", "connections", "chat_sessions", "messages", "alembic_version"} <= _tables(path)

    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as conn:
        drift = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    assert drift == [], f"models and migrations diverged: {drift}"


def test_migration_is_idempotent(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"
    upgrade_to_head(url)
    upgrade_to_head(url)


def test_migration_adopts_database_created_by_create_all(tmp_path):
    path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{path}")
    Base.metadata.create_all(engine)
    with sqlite3.connect(path) as conn:
        conn.execute("INSERT INTO users (id, email, password_hash, created_at) VALUES ('u', 'a@b.c', 'x', '2024-01-01')")

    upgrade_to_head(f"sqlite+aiosqlite:///{path}")

    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT email FROM users").fetchall() == [("a@b.c",)]
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == ("0001",)
