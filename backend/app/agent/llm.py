import json
import re
from typing import Any

from langchain_openai import ChatOpenAI

from app.agent.state import QueryRequest

_SYSTEM = (
    "You translate questions into read-only database queries. "
    "Use only tables/collections and columns present in the schema. "
    "Return ONLY the query, no explanation and no markdown fences."
)
_FENCE = re.compile(r"^```[a-zA-Z]*\s*|\s*```$")
# Classic chat models that accept `temperature`. OpenAI's reasoning models (o-series,
# gpt-5.x, gpt-6.x, ...) reject it, and new names keep appearing, so everything NOT
# listed here is treated as a reasoning model and sent without temperature.
_TEMPERATURE_MODELS = re.compile(r"^(gpt-3\.5|gpt-4|chatgpt-4o|gpt-5-chat)", re.IGNORECASE)


def supports_temperature(model: str) -> bool:
    return bool(_TEMPERATURE_MODELS.match(model.strip()))


def _is_temperature_rejection(exc: Exception) -> bool:
    return "temperature" in str(exc).lower() and "unsupported" in str(exc).lower()


class _AdaptiveChatModel:
    """ChatOpenAI wrapper: temperature=0 only where supported, and a one-time
    fallback without it if the API rejects it for an unlisted model."""

    def __init__(self, model: str, api_key: str, timeout: int) -> None:
        self._model = model
        self._api_key = api_key
        self._timeout = timeout
        self._client = self._build(supports_temperature(model))

    def _build(self, with_temperature: bool) -> ChatOpenAI:
        options: dict[str, Any] = {"model": self._model, "api_key": self._api_key, "timeout": self._timeout}
        if with_temperature:
            options["temperature"] = 0
        return ChatOpenAI(**options)

    async def ainvoke(self, messages: list[tuple[str, str]]) -> Any:
        try:
            return await self._client.ainvoke(messages)
        except Exception as exc:  # noqa: BLE001 - re-raised unless it is the temperature rejection
            if not _is_temperature_rejection(exc):
                raise
            self._client = self._build(with_temperature=False)
            return await self._client.ainvoke(messages)


class OpenAIQueryLLM:
    """QueryLLM backed by OpenAI chat models (reasoning and non-reasoning) via LangChain."""

    def __init__(self, api_key: str, model: str, fast_model: str, timeout: int) -> None:
        self._smart = _AdaptiveChatModel(model, api_key, timeout)
        self._fast = _AdaptiveChatModel(fast_model, api_key, timeout)

    async def generate_query(self, request: QueryRequest) -> str:
        reply = await self._smart.ainvoke([("system", _SYSTEM), ("human", self._build_prompt(request))])
        return _FENCE.sub("", str(reply.content).strip()).strip().rstrip(";")

    async def summarize(self, question: str, query: str, result: dict[str, Any]) -> str:
        sample = {**result, "rows": result["rows"][:20]}
        prompt = (
            f"Question: {question}\nQuery: {query}\n"
            f"Result ({result['row_count']} rows, first 20 shown): {json.dumps(sample, default=str)}\n"
            "Answer the question concisely in plain language using only this data."
        )
        reply = await self._fast.ainvoke([("human", prompt)])
        return str(reply.content).strip()

    @staticmethod
    def _build_prompt(request: QueryRequest) -> str:
        parts = [f"Schema:\n{request.schema}", request.dialect_hint]
        if request.history:
            turns = "\n".join(f"{role}: {text}" for role, text in request.history)
            parts.append(
                "Recent conversation (a [query used: ...] note is the query behind that answer; "
                "reuse or adapt it when the question is a follow-up):\n" + turns
            )
        if request.failed_attempts:
            tried = "\n".join(
                f"- Query: {a['query']}\n  Problem ({a['stage']}): {a['error']}"
                for a in request.failed_attempts
            )
            parts.append(
                "Previous attempts failed. Fix the problem and do NOT repeat these queries:\n" + tried
            )
        parts.append(f"Question: {request.question}")
        return "\n\n".join(parts)
