import asyncio

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, NoSuchModuleError, SQLAlchemyError
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.adapters.sqlite_path import SqliteFileError, read_only_url, resolve_sqlite_file
from app.adapters.base import (
    ColumnInfo,
    DatabaseAdapter,
    ExecutionLimits,
    QueryResult,
    SchemaInfo,
    TableInfo,
    sanitize_error,
    to_jsonable,
)
from app.core.errors import (
    DatabaseConnectionError,
    QueryExecutionError,
    QueryValidationError,
    SecurityViolationError,
)

# Session-level read-only switches, applied on every new DBAPI connection.
_READ_ONLY_STATEMENTS = {
    "sqlite": "PRAGMA query_only = ON",
    "postgresql": "SET default_transaction_read_only = on",
    "mysql": "SET SESSION TRANSACTION READ ONLY",
    "mariadb": "SET SESSION TRANSACTION READ ONLY",
}

_SQLGLOT_DIALECTS = {"postgresql": "postgres", "mssql": "tsql", "mariadb": "mysql"}

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Merge, exp.TruncateTable, exp.Transaction, exp.Commit,
    exp.Rollback, exp.Use, exp.Into,
)


class SqlAdapter(DatabaseAdapter):
    """Any database reachable through SQLAlchemy (SQLite, Postgres, MySQL, MSSQL, Oracle...)."""

    def __init__(self, url: str, limits: ExecutionLimits) -> None:
        super().__init__(url, limits)
        self._backend = make_url(url).get_backend_name()
        self.dialect = self._backend
        self._glot_dialect = _SQLGLOT_DIALECTS.get(self._backend, self._backend)
        self._engine: Engine | None = None

    async def connect(self) -> None:
        try:
            self._engine = await asyncio.to_thread(self._create_engine)
        except NoSuchModuleError as exc:
            raise DatabaseConnectionError(
                f"No driver installed for '{self._backend}'. Install the matching Python driver."
            ) from exc
        except SqliteFileError as exc:
            raise DatabaseConnectionError(str(exc)) from exc
        except (SQLAlchemyError, ModuleNotFoundError, OSError) as exc:
            raise DatabaseConnectionError(sanitize_error(str(exc), self._url)) from exc

    def _create_engine(self) -> Engine:
        kwargs: dict = {"pool_pre_ping": True, "pool_recycle": 1800}
        url = self._url
        if self._backend == "sqlite":
            kwargs["connect_args"] = {"check_same_thread": False}
            url = read_only_url(resolve_sqlite_file(self._url))
        else:
            kwargs.update(pool_size=3, max_overflow=0)
        engine = create_engine(url, **kwargs)
        read_only = _READ_ONLY_STATEMENTS.get(self._backend)
        if read_only:
            @event.listens_for(engine, "connect")
            def _set_read_only(dbapi_conn, _record):
                cursor = dbapi_conn.cursor()
                cursor.execute(read_only)
                cursor.close()
                dbapi_conn.commit()
        with engine.connect():  # fail fast on bad credentials / host
            pass
        return engine

    async def close(self) -> None:
        if self._engine is not None:
            await asyncio.to_thread(self._engine.dispose)
            self._engine = None

    def validate(self, query: str) -> None:
        try:
            statements = [s for s in sqlglot.parse(query, read=self._glot_dialect) if s]
        except SqlglotError as exc:
            raise QueryValidationError(f"SQL could not be parsed: {exc}") from exc
        if len(statements) != 1:
            raise QueryValidationError("Exactly one SQL statement is required.")
        statement = statements[0]
        if not isinstance(statement, exp.Query):
            raise SecurityViolationError("Only SELECT queries are allowed.")
        if any(statement.find_all(*_FORBIDDEN_NODES)):
            raise SecurityViolationError("Query contains a write or administrative operation.")

    async def execute(self, query: str) -> QueryResult:
        if self._engine is None:
            raise DatabaseConnectionError("Adapter is not connected.")
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run, query), self._limits.query_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise QueryExecutionError(
                f"Query exceeded {self._limits.query_timeout_seconds}s timeout."
            ) from exc
        except DBAPIError as exc:
            if exc.connection_invalidated:
                raise DatabaseConnectionError("Database connection was lost.") from exc
            raise QueryExecutionError(sanitize_error(str(exc.orig or exc), self._url)) from exc
        except SQLAlchemyError as exc:
            raise QueryExecutionError(sanitize_error(str(exc), self._url)) from exc

    def _run(self, query: str) -> QueryResult:
        assert self._engine is not None
        with self._engine.connect() as conn:
            cursor = conn.exec_driver_sql(query)  # raw: avoids ':name' bind parsing
            if not cursor.returns_rows:
                return QueryResult()
            fetched = cursor.fetchmany(self._limits.max_rows + 1)
            truncated = len(fetched) > self._limits.max_rows
            rows = [[to_jsonable(v) for v in row] for row in fetched[: self._limits.max_rows]]
            return QueryResult(list(cursor.keys()), rows, truncated)

    async def _load_schema(self) -> str:
        return (await self._load_schema_info()).render()

    async def _load_schema_info(self) -> SchemaInfo:
        return await asyncio.to_thread(self._describe)

    def _describe(self) -> SchemaInfo:
        assert self._engine is not None
        inspector = inspect(self._engine)
        tables: list[TableInfo] = []
        for table in inspector.get_table_names():
            pk = set(inspector.get_pk_constraint(table).get("constrained_columns") or [])
            fks = {
                col: f"{fk['referred_table']}.{ref}"
                for fk in inspector.get_foreign_keys(table)
                for col, ref in zip(fk["constrained_columns"], fk["referred_columns"])
            }
            columns = [
                ColumnInfo(col["name"], str(col["type"]), col["name"] in pk, fks.get(col["name"]))
                for col in inspector.get_columns(table)
            ]
            tables.append(TableInfo(table, columns))
        return SchemaInfo(tables)
