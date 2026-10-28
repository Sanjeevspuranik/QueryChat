from app.adapters.base import QueryResult, SchemaInfo
from app.adapters.pool import AdapterPool


class QueryRunner:
    """The one place that turns (connection, query) into a result: pooled adapter ->
    validate -> execute. Chat edits, dashboards and scheduled refreshes reuse it so
    every read path gets the same safety checks, limits and timeouts."""

    def __init__(self, pool: AdapterPool) -> None:
        self._pool = pool

    async def run(self, connection_id: str, url: str, query: str) -> QueryResult:
        adapter = await self._pool.acquire(connection_id, url)
        adapter.validate(query)
        return await adapter.execute(query)

    async def schema_info(self, connection_id: str, url: str) -> SchemaInfo:
        adapter = await self._pool.acquire(connection_id, url)
        return await adapter.get_schema_info()
