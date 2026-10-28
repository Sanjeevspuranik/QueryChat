from typing import Any

from app.adapters.base import DatabaseAdapter, ExecutionLimits, QueryResult
from app.agent.graph import build_agent_graph
from app.agent.nodes import AgentNodes
from app.agent.state import QueryRequest
from app.core.errors import (
    DatabaseConnectionError,
    QueryExecutionError,
    QueryValidationError,
    SecurityViolationError,
)


class ScriptedLLM:
    def __init__(self, queries: list[str]) -> None:
        self._queries = list(queries)
        self.requests: list[QueryRequest] = []

    async def generate_query(self, request: QueryRequest) -> str:
        self.requests.append(request)
        return self._queries.pop(0)

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str:
        return f"{result['row_count']} rows"


class FakeAdapter(DatabaseAdapter):
    """Behaviour keyed by query text: 'bad-validate', 'bad-security', 'bad-exec', 'conn', 'empty'."""

    def __init__(self) -> None:
        super().__init__("fake://", ExecutionLimits())

    async def connect(self) -> None: ...
    async def close(self) -> None: ...
    async def _load_schema(self) -> str:
        return "TABLE t (id INTEGER)"

    def validate(self, query: str) -> None:
        if query == "bad-validate":
            raise QueryValidationError("parse error")
        if query == "bad-security":
            raise SecurityViolationError("write")

    async def execute(self, query: str) -> QueryResult:
        if query.startswith("bad-exec"):
            raise QueryExecutionError("no such column")
        if query == "conn":
            raise DatabaseConnectionError("lost")
        if query == "empty":
            return QueryResult(["id"], [])
        return QueryResult(["id"], [[1]])


async def run(queries: list[str], max_retries: int = 3):
    llm = ScriptedLLM(queries)
    graph = build_agent_graph(AgentNodes(llm, FakeAdapter(), max_retries))
    state = await graph.ainvoke({"question": "q", "attempts": [], "retry_count": 0})
    return state, llm


async def test_success_first_try():
    state, llm = await run(["good"])
    assert state["status"] == "ok" and len(llm.requests) == 1


async def test_recovers_after_execution_error_and_feeds_error_back():
    state, llm = await run(["bad-exec-1", "good"])
    assert state["status"] == "ok"
    assert llm.requests[1].failed_attempts[0]["error"] == "no such column"


async def test_recovers_on_final_retry():
    state, llm = await run(["bad-validate", "bad-exec-1", "bad-exec-2", "good"])
    assert state["status"] == "ok" and len(llm.requests) == 4


async def test_exhaustion_stops_after_max_retries():
    state, llm = await run(["bad-exec-1", "bad-exec-2", "bad-exec-3", "bad-exec-4", "never"])
    assert state["status"] == "failed"
    assert len(llm.requests) == 4  # 1 initial + 3 retries
    assert "4 attempts" in state["answer"]


async def test_custom_retry_cap():
    state, llm = await run(["bad-exec-1", "bad-exec-2", "never"], max_retries=1)
    assert state["status"] == "failed" and len(llm.requests) == 2


async def test_duplicate_query_counts_as_failed_attempt():
    state, llm = await run(["bad-exec-1", "BAD-EXEC-1", "good"])
    assert state["status"] == "ok"
    assert state["attempts"][1]["stage"] == "duplicate"


async def test_security_violation_is_not_retried():
    state, llm = await run(["bad-security", "never"])
    assert state["status"] == "failed" and len(llm.requests) == 1


async def test_connection_error_is_not_retried():
    state, llm = await run(["conn", "never"])
    assert state["status"] == "failed" and len(llm.requests) == 1


async def test_empty_result_retries_once_then_accepts():
    state, llm = await run(["empty", "empty2-different"])
    # second query hits the default branch (returns a row), proving the retry happened
    assert state["status"] == "ok" and len(llm.requests) == 2
