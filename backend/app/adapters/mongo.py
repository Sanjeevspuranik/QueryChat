import asyncio
import json
from typing import Any

from pymongo import MongoClient
from pymongo.errors import ConfigurationError, PyMongoError

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

_ALLOWED_STAGES = {
    "$match", "$group", "$project", "$sort", "$limit", "$skip", "$count",
    "$unwind", "$addFields", "$set", "$lookup", "$sample", "$facet", "$sortByCount",
}
_FORBIDDEN_KEYS = {"$out", "$merge", "$function", "$accumulator", "$where"}


class MongoAdapter(DatabaseAdapter):
    """MongoDB through a constrained JSON aggregation spec.

    The LLM emits: {"collection": "name", "pipeline": [ ... ]}. Only an allowlist of
    read-only stages is accepted; code-executing operators are rejected.
    """

    dialect = "mongodb"
    query_language = "aggregation"

    def __init__(self, url: str, limits: ExecutionLimits) -> None:
        super().__init__(url, limits)
        self._client: MongoClient | None = None
        self._db: Any = None

    @property
    def prompt_hint(self) -> str:
        return (
            'Respond with a JSON object only: {"collection": "<name>", "pipeline": [<stages>]}. '
            f"Allowed stages: {', '.join(sorted(_ALLOWED_STAGES))}. Never use $out, $merge, "
            "$function, $accumulator or $where."
        )

    async def connect(self) -> None:
        try:
            await asyncio.to_thread(self._open)
        except (PyMongoError, ConfigurationError) as exc:
            raise DatabaseConnectionError(sanitize_error(str(exc), self._url)) from exc

    def _open(self) -> None:
        client = MongoClient(self._url, serverSelectionTimeoutMS=5000, appname="querychat")
        try:
            self._db = client.get_default_database()
        except ConfigurationError as exc:
            client.close()
            raise ConfigurationError("The MongoDB URL must include a database name.") from exc
        client.admin.command("ping")
        self._client = client

    async def close(self) -> None:
        if self._client is not None:
            await asyncio.to_thread(self._client.close)
            self._client = None

    def validate(self, query: str) -> None:
        spec = self._parse(query)
        pipeline = spec["pipeline"]
        for stage in pipeline:
            if not isinstance(stage, dict) or len(stage) != 1:
                raise QueryValidationError("Each pipeline stage must be an object with one operator.")
            operator = next(iter(stage))
            if operator not in _ALLOWED_STAGES:
                raise SecurityViolationError(f"Pipeline stage '{operator}' is not allowed.")
        if self._contains_forbidden(pipeline):
            raise SecurityViolationError("Pipeline uses a forbidden operator.")

    @staticmethod
    def _parse(query: str) -> dict[str, Any]:
        try:
            spec = json.loads(query)
        except json.JSONDecodeError as exc:
            raise QueryValidationError(f"Query is not valid JSON: {exc}") from exc
        if (
            not isinstance(spec, dict)
            or not isinstance(spec.get("collection"), str)
            or not isinstance(spec.get("pipeline"), list)
        ):
            raise QueryValidationError('Expected {"collection": str, "pipeline": list}.')
        return spec

    def _contains_forbidden(self, node: Any) -> bool:
        if isinstance(node, dict):
            return any(k in _FORBIDDEN_KEYS or self._contains_forbidden(v) for k, v in node.items())
        if isinstance(node, list):
            return any(self._contains_forbidden(v) for v in node)
        return False

    async def execute(self, query: str) -> QueryResult:
        if self._db is None:
            raise DatabaseConnectionError("Adapter is not connected.")
        spec = self._parse(query)
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._run, spec), self._limits.query_timeout_seconds
            )
        except asyncio.TimeoutError as exc:
            raise QueryExecutionError("Query exceeded the time limit.") from exc
        except PyMongoError as exc:
            raise QueryExecutionError(sanitize_error(str(exc), self._url)) from exc

    def _run(self, spec: dict[str, Any]) -> QueryResult:
        pipeline = [*spec["pipeline"], {"$limit": self._limits.max_rows + 1}]
        timeout_ms = self._limits.query_timeout_seconds * 1000
        docs = list(self._db[spec["collection"]].aggregate(pipeline, maxTimeMS=timeout_ms))
        truncated = len(docs) > self._limits.max_rows
        docs = docs[: self._limits.max_rows]
        columns: list[str] = []
        for doc in docs:
            columns.extend(k for k in doc if k not in columns)
        rows = [[to_jsonable(doc.get(col)) for col in columns] for doc in docs]
        return QueryResult(columns, rows, truncated)

    async def _load_schema(self) -> str:
        return await asyncio.to_thread(self._describe)

    async def _load_schema_info(self) -> SchemaInfo:
        return await asyncio.to_thread(self._describe_info)

    def _describe_info(self) -> SchemaInfo:
        tables = []
        for name in self._db.list_collection_names():
            sample = self._db[name].find_one() or {}
            tables.append(TableInfo(name, [ColumnInfo(k, type(v).__name__) for k, v in sample.items()]))
        return SchemaInfo(tables)

    def _describe(self) -> str:
        lines = []
        for name in self._db.list_collection_names():
            sample = self._db[name].find_one() or {}
            fields = ", ".join(f"{k}: {type(v).__name__}" for k, v in sample.items())
            lines.append(f"COLLECTION {name} {{{fields}}}")
        return "\n".join(lines)
