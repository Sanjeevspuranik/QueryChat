"""Adapter contract. Every supported database family implements this interface;
the agent and services depend only on it (Dependency Inversion)."""
import re
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time as dtime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ExecutionLimits:
    query_timeout_seconds: int = 30
    max_rows: int = 1000
    max_schema_chars: int = 12000
    schema_ttl_seconds: int = 600


@dataclass(frozen=True)
class QueryResult:
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "truncated": self.truncated,
        }


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    type: str
    primary_key: bool = False
    references: str | None = None  # "table.column" for foreign keys


@dataclass(frozen=True)
class TableInfo:
    """A table (SQL) or collection (document stores)."""

    name: str
    columns: list[ColumnInfo] = field(default_factory=list)


@dataclass(frozen=True)
class SchemaInfo:
    """Structured schema: the single source for the LLM prompt text and the schema explorer."""

    tables: list[TableInfo] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def render(self) -> str:
        lines = []
        for table in self.tables:
            cols = []
            for col in table.columns:
                desc = f"{col.name} {col.type}"
                if col.primary_key:
                    desc += " PK"
                if col.references:
                    desc += f" FK->{col.references}"
                cols.append(desc)
            lines.append(f"TABLE {table.name} ({', '.join(cols)})")
        return "\n".join(lines)


def to_jsonable(value: Any) -> Any:
    """Convert driver-specific values into JSON-safe ones."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date, dtime)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(v) for v in value]
    return str(value)


_URL_CREDENTIALS = re.compile(r"(://[^:/@\s]+:)[^@\s]+@")


def sanitize_error(message: str, url: str = "", limit: int = 500) -> str:
    """Strip credentials / connection strings from driver messages."""
    if url:
        message = message.replace(url, "<database-url>")
    message = _URL_CREDENTIALS.sub(r"\1***@", message)
    return message[:limit]


class DatabaseAdapter(ABC):
    """A connection to one user database, able to describe, validate and run queries."""

    dialect: str = "generic"
    query_language: str = "SQL"

    def __init__(self, url: str, limits: ExecutionLimits) -> None:
        self._url = url
        self._limits = limits
        self._schema_cache: tuple[float, str] | None = None

    @property
    def prompt_hint(self) -> str:
        """Dialect-specific guidance appended to the LLM prompt."""
        return f"Write a single read-only {self.dialect} {self.query_language} query."

    @abstractmethod
    async def connect(self) -> None:
        """Open resources and verify connectivity. Raises DatabaseConnectionError."""

    @abstractmethod
    async def close(self) -> None: ...

    @abstractmethod
    def validate(self, query: str) -> None:
        """Raise QueryValidationError / SecurityViolationError if query is not allowed."""

    @abstractmethod
    async def execute(self, query: str) -> QueryResult:
        """Run a validated query. Raises QueryExecutionError."""

    @abstractmethod
    async def _load_schema(self) -> str: ...

    async def _load_schema_info(self) -> SchemaInfo:
        """Structured schema for the explorer. Adapters that cannot provide one return an empty schema."""
        return SchemaInfo()

    async def get_schema_info(self) -> SchemaInfo:
        return await self._load_schema_info()

    async def get_schema(self, force_refresh: bool = False) -> str:
        """Template method: cached schema description, truncated to the prompt budget."""
        cached = self._schema_cache
        fresh = cached and time.monotonic() - cached[0] < self._limits.schema_ttl_seconds
        if fresh and not force_refresh:
            return cached[1]  # type: ignore[index]
        schema = (await self._load_schema())[: self._limits.max_schema_chars]
        self._schema_cache = (time.monotonic(), schema)
        return schema
