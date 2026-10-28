import hashlib
import logging
import time
from typing import Any

from app.adapters.base import DatabaseAdapter
from app.agent.state import AgentState, Failure, QueryLLM, QueryRequest
from app.core.errors import (
    DatabaseConnectionError,
    QueryExecutionError,
    QueryValidationError,
    SecurityViolationError,
)

logger = logging.getLogger("querychat.agent")


def _fingerprint(query: str) -> str:
    return hashlib.sha1(" ".join(query.lower().split()).encode()).hexdigest()


class AgentNodes:
    """Graph node implementations. Each node does one job and returns a state update;
    routing is decided by the small `route_*` methods, never by the LLM."""

    def __init__(
        self,
        llm: QueryLLM,
        adapter: DatabaseAdapter,
        max_retries: int,
        max_empty_retries: int = 1,
    ) -> None:
        self._llm = llm
        self._adapter = adapter
        self._max_retries = max_retries
        self._max_empty_retries = max_empty_retries

    # ---- nodes -------------------------------------------------------

    async def load_schema(self, state: AgentState) -> dict[str, Any]:
        try:
            return {"schema": await self._adapter.get_schema(), "failure": None}
        except Exception as exc:  # noqa: BLE001 - any driver error ends the run
            logger.warning("schema load failed: %s", exc)
            return self._failed(state, "schema", f"Could not read the database schema: {exc}", False)

    async def generate(self, state: AgentState) -> dict[str, Any]:
        failed = [a for a in state.get("attempts", []) if a["stage"] != "executed"]
        request = QueryRequest(
            question=state["question"],
            schema=state["schema"],
            dialect_hint=self._adapter.prompt_hint,
            history=state.get("history", []),
            failed_attempts=failed,
        )
        query = await self._llm.generate_query(request)
        return {"query": query, "failure": None, "started_at": time.monotonic()}

    async def validate(self, state: AgentState) -> dict[str, Any]:
        query = state["query"]
        tried = {_fingerprint(a["query"]) for a in state.get("attempts", [])}
        if _fingerprint(query) in tried:
            return self._failed(
                state, "duplicate", "This exact query was already tried. Produce a different one.", True
            )
        try:
            self._adapter.validate(query)
        except SecurityViolationError as exc:
            return self._failed(state, "validation", str(exc), False)
        except QueryValidationError as exc:
            return self._failed(state, "validation", str(exc), True)
        return {"failure": None}

    async def execute(self, state: AgentState) -> dict[str, Any]:
        try:
            result = await self._adapter.execute(state["query"])
        except DatabaseConnectionError as exc:
            return self._failed(state, "execution", str(exc), False)
        except QueryExecutionError as exc:
            return self._failed(state, "execution", str(exc), True)

        if result.row_count == 0 and self._may_retry_empty(state):
            return self._failed(
                state,
                "empty_result",
                "Query returned no rows. Re-check filters, value spellings, joins and table choice.",
                True,
            )
        attempts = [*state.get("attempts", []), self._attempt(state, "executed", None)]
        return {"result": result.to_dict(), "attempts": attempts, "failure": None}

    async def retry_gate(self, state: AgentState) -> dict[str, Any]:
        failure = state["failure"]
        used = state.get("retry_count", 0)
        if failure and failure["retryable"] and used < self._max_retries:
            return {"retry_count": used + 1, "status": "retrying"}
        return {"status": "failed"}

    async def summarize(self, state: AgentState) -> dict[str, Any]:
        result = state["result"] or {}
        try:
            answer = await self._llm.summarize(state["question"], state["query"], result)
        except Exception as exc:  # noqa: BLE001 - data is still valid without the summary
            logger.warning("summarize failed: %s", exc)
            answer = f"The query returned {result.get('row_count', 0)} rows."
        return {"answer": answer, "status": "ok"}

    async def fail(self, state: AgentState) -> dict[str, Any]:
        failure = state.get("failure") or {"stage": "unknown", "error": "Unknown error", "retryable": False}
        attempts = len(state.get("attempts", []))
        if failure["retryable"]:
            lead = f"I couldn't produce a working query after {attempts} attempts."
        else:
            lead = "I couldn't complete this request."
        answer = (
            f"{lead} Last problem ({failure['stage']}): {failure['error']} "
            "Try rephrasing, naming specific tables or columns, or refreshing the schema."
        )
        return {"answer": answer, "status": "failed"}

    # ---- routing -----------------------------------------------------

    @staticmethod
    def route_after_schema(state: AgentState) -> str:
        return "fail" if state.get("failure") else "generate"

    @staticmethod
    def route_after_validate(state: AgentState) -> str:
        return "retry_gate" if state.get("failure") else "execute"

    @staticmethod
    def route_after_execute(state: AgentState) -> str:
        return "retry_gate" if state.get("failure") else "summarize"

    @staticmethod
    def route_after_gate(state: AgentState) -> str:
        return "generate" if state["status"] == "retrying" else "fail"

    # ---- helpers -----------------------------------------------------

    def _may_retry_empty(self, state: AgentState) -> bool:
        empties = sum(1 for a in state.get("attempts", []) if a["stage"] == "empty_result")
        return empties < self._max_empty_retries and state.get("retry_count", 0) < self._max_retries

    @staticmethod
    def _attempt(state: AgentState, stage: str, error: str | None) -> dict[str, Any]:
        started = state.get("started_at") or time.monotonic()
        return {
            "n": len(state.get("attempts", [])) + 1,
            "query": state.get("query", ""),
            "stage": stage,
            "error": error,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }

    def _failed(self, state: AgentState, stage: str, error: str, retryable: bool) -> dict[str, Any]:
        failure: Failure = {"stage": stage, "error": error, "retryable": retryable}
        attempts = state.get("attempts", [])
        if stage != "schema":
            attempts = [*attempts, self._attempt(state, stage, error)]
        return {"failure": failure, "attempts": attempts}
