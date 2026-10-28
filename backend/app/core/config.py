from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
_SQLITE_PREFIX = "sqlite+aiosqlite:///"


class Settings(BaseSettings):
    """All runtime configuration, loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    secret_key: str
    encryption_key: str
    app_database_url: str = "sqlite+aiosqlite:///./querychat.db"
    db_bootstrap: Literal["migrate", "create_all"] = "migrate"  # create_all only for throwaway/in-memory DBs
    cors_origins: list[str] = ["http://localhost:3000"]
    cookie_secure: bool = False
    access_token_minutes: int = 60 * 12

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_to_file: bool = True
    log_dir: str = ""  # default: backend/logs
    log_max_mb: int = Field(default=5, ge=1)
    log_backups: int = Field(default=5, ge=0)

    openai_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_fast_model: str = "gpt-4o-mini"

    agent_max_retries: int = Field(default=3, ge=0, le=5)
    run_deadline_seconds: int = 90
    llm_timeout_seconds: int = 30

    query_timeout_seconds: int = 30
    max_result_rows: int = 1000
    max_schema_chars: int = 12000
    schema_ttl_seconds: int = 600

    max_engines: int = 50
    engine_idle_seconds: int = 900
    max_concurrent_runs: int = 20
    max_runs_per_user: int = 2
    max_runs_per_connection: int = 3

    allow_private_hosts: bool = True
    sqlite_allowed_dir: str = ""

    @field_validator("app_database_url")
    @classmethod
    def _anchor_relative_sqlite(cls, url: str) -> str:
        """A relative SQLite path would depend on where the server was started from."""
        if not url.startswith(_SQLITE_PREFIX):
            return url
        database = url[len(_SQLITE_PREFIX):]
        if not database or database.startswith((":memory:", "file:", "/")) or Path(database).is_absolute():
            return url
        return _SQLITE_PREFIX + (BACKEND_DIR / database).resolve().as_posix()
