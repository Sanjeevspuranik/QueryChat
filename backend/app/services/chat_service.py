import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.pool import AdapterPool
from app.agent.events import to_events
from app.agent.graph import RECURSION_LIMIT, build_agent_graph
from app.agent.nodes import AgentNodes
from app.agent.state import AgentState, QueryLLM
from app.core.config import Settings
from app.core.errors import QueryChatError
from app.schemas import MessageOut
from app.services.connection_service import ConnectionService
from app.services.run_guard import RunGuard
from app.services.session_service import SessionService

logger = logging.getLogger("querychat.chat")
HISTORY_MESSAGES = 6
HISTORY_TEXT_CHARS = 300
HISTORY_SQL_CHARS = 1200
CANCELLED_ANSWER = "This request was stopped before it finished."


def build_history(messages: list[Any]) -> list[tuple[str, str]]:
    """Recent turns for the prompt. Assistant turns carry the query that produced the
    answer, so a follow-up ("only those from France") can edit it instead of guessing."""
    turns = []
    for m in messages:
        text = m.content[:HISTORY_TEXT_CHARS]
        if m.role == "assistant" and m.status == "ok" and m.query:
            text += f"\n[query used: {m.query[:HISTORY_SQL_CHARS]}]"
        turns.append((m.role, text))
    return turns


@dataclass(frozen=True)
class ChatContext:
    session_id: str
    connection_id: str
    url: str
    question: str
    history: list[tuple[str, str]]


class ChatService:
    """Orchestrates one chat turn: authorise -> reserve a run slot -> run the agent
    graph -> stream events -> persist the assistant message."""

    def __init__(
        self,
        settings: Settings,
        sessions: SessionService,
        connections: ConnectionService,
        pool: AdapterPool,
        guard: RunGuard,
        llm: QueryLLM,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._settings = settings
        self._sessions = sessions
        self._connections = connections
        self._pool = pool
        self._guard = guard
        self._llm = llm
        self._session_factory = session_factory

    async def prepare(self, user_id: str, session_id: str, question: str) -> ChatContext:
        """Validate ownership and reserve a run slot. Raises before streaming starts."""
        session = await self._sessions.get_owned(user_id, session_id)
        connection = await self._connections.get_owned(user_id, session.connection_id)
        history = build_history(await self._sessions.messages(session.id, HISTORY_MESSAGES))
        self._guard.acquire(session.id, user_id, connection.id)
        try:
            await self._sessions.add_message(session.id, "user", question)
            if session.title == "New chat":
                await self._sessions.rename(session, question[:60])
        except Exception:
            self._guard.release(session.id)
            raise
        return ChatContext(session.id, connection.id, self._connections.reveal_url(connection), question, history)

    async def stream(self, ctx: ChatContext) -> AsyncIterator[dict[str, Any]]:
        state: AgentState = {
            "question": ctx.question,
            "history": ctx.history,
            "attempts": [],
            "retry_count": 0,
        }
        started = time.monotonic()
        logger.info(
            "run start session=%s connection=%s question_chars=%d history=%d",
            ctx.session_id, ctx.connection_id, len(ctx.question), len(ctx.history),
        )
        try:
            yield {"type": "status", "message": "Connecting to database"}
            try:
                adapter = await self._pool.acquire(ctx.connection_id, ctx.url)
                graph = build_agent_graph(AgentNodes(self._llm, adapter, self._settings.agent_max_retries))
                async with asyncio.timeout(self._settings.run_deadline_seconds):
                    async for chunk in graph.astream(
                        state, config={"recursion_limit": RECURSION_LIMIT}, stream_mode="updates"
                    ):
                        for node, update in chunk.items():
                            state.update(update)  # type: ignore[typeddict-item]
                            failure = update.get("failure")
                            if failure:
                                logger.warning(
                                    "attempt failed session=%s stage=%s retryable=%s: %s",
                                    ctx.session_id, failure["stage"], failure["retryable"], failure["error"][:300],
                                )
                            for event in to_events(node, update, self._settings.agent_max_retries):
                                yield event
            except QueryChatError as exc:
                logger.warning("run rejected session=%s: %s", ctx.session_id, exc)
                state.update(status="failed", answer=str(exc))
            except TimeoutError:
                logger.warning("run timed out session=%s after %ss", ctx.session_id, self._settings.run_deadline_seconds)
                state.update(status="failed", answer="The request took too long and was stopped.")
            except (asyncio.CancelledError, GeneratorExit):
                # Client went away mid-run. Save what we have so the chat history stays
                # consistent (no dangling user message), then let the cancellation propagate.
                logger.info("run cancelled by client session=%s", ctx.session_id)
                state.update(status="failed", answer=CANCELLED_ANSWER)
                await asyncio.shield(self._persist(ctx, state))
                raise
            except Exception:
                logger.exception("agent run crashed session=%s", ctx.session_id)
                state.update(status="failed", answer="Something went wrong while answering. Please try again.")

            message = await self._persist(ctx, state)
            logger.info(
                "run end session=%s status=%s attempts=%d rows=%s ms=%.0f",
                ctx.session_id, state.get("status"), len(state.get("attempts", [])),
                (state.get("result") or {}).get("row_count"), (time.monotonic() - started) * 1000,
            )
            yield {"type": "done", "message": message}
        finally:
            self._guard.release(ctx.session_id)

    async def _persist(self, ctx: ChatContext, state: AgentState) -> dict[str, Any]:
        async with self._session_factory() as db:
            stored = await SessionService(db).add_message(
                ctx.session_id,
                "assistant",
                state.get("answer", ""),
                query=state.get("query"),
                result_json=state.get("result"),
                attempts_json=state.get("attempts"),
                status=state.get("status", "failed"),
            )
            return MessageOut.model_validate(stored).model_dump(mode="json")
