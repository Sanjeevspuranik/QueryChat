"""initial schema: users, connections, chat_sessions, messages

Tables are created only when missing, so databases that were bootstrapped with
`create_all` before Alembic was introduced adopt this revision without errors.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

_TS = sa.DateTime(timezone=True)


def _missing(name: str) -> bool:
    return name not in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _missing("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("email", sa.String(255), nullable=False),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("created_at", _TS, nullable=False),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)
    if _missing("connections"):
        op.create_table(
            "connections",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("db_type", sa.String(30), nullable=False),
            sa.Column("url_encrypted", sa.Text, nullable=False),
            sa.Column("created_at", _TS, nullable=False),
        )
        op.create_index("ix_connections_user_id", "connections", ["user_id"])
    if _missing("chat_sessions"):
        op.create_table(
            "chat_sessions",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("connection_id", sa.String(32), sa.ForeignKey("connections.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("created_at", _TS, nullable=False),
        )
        op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
        op.create_index("ix_chat_sessions_connection_id", "chat_sessions", ["connection_id"])
    if _missing("messages"):
        op.create_table(
            "messages",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("session_id", sa.String(32), sa.ForeignKey("chat_sessions.id"), nullable=False),
            sa.Column("seq", sa.Integer, nullable=False),
            sa.Column("role", sa.String(10), nullable=False),
            sa.Column("content", sa.Text, nullable=False),
            sa.Column("query", sa.Text),
            sa.Column("result_json", sa.JSON),
            sa.Column("attempts_json", sa.JSON),
            sa.Column("status", sa.String(10), nullable=False),
            sa.Column("created_at", _TS, nullable=False),
            sa.UniqueConstraint("session_id", "seq"),
        )
        op.create_index("ix_messages_session_id", "messages", ["session_id"])


def downgrade() -> None:
    for table in ("messages", "chat_sessions", "connections", "users"):
        op.drop_table(table)
