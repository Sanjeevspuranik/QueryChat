from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict


class Failure(TypedDict):
    stage: str  # schema | validation | execution | empty_result | duplicate
    error: str
    retryable: bool


class AgentState(TypedDict, total=False):
    question: str
    history: list[tuple[str, str]]
    schema: str
    query: str
    attempts: list[dict[str, Any]]
    retry_count: int
    failure: Failure | None
    result: dict[str, Any] | None
    answer: str
    status: str  # retrying | ok | failed
    started_at: float


@dataclass
class QueryRequest:
    question: str
    schema: str
    dialect_hint: str
    history: list[tuple[str, str]] = field(default_factory=list)
    failed_attempts: list[dict[str, Any]] = field(default_factory=list)


class QueryLLM(Protocol):
    """What the agent needs from a language model (Interface Segregation)."""

    async def generate_query(self, request: QueryRequest) -> str: ...

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str: ...
