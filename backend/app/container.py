from collections.abc import Callable
from functools import cached_property

from app.adapters.base import ExecutionLimits
from app.adapters.pool import AdapterPool
from app.adapters.registry import AdapterRegistry, default_registry
from app.adapters.url_policy import UrlPolicy
from app.agent.llm import OpenAIQueryLLM
from app.agent.state import QueryLLM
from app.core.config import Settings
from app.core.security import CredentialCipher, PasswordHasher, TokenService
from app.db.models import create_session_factory
from app.services.query_runner import QueryRunner
from app.services.run_guard import RunGuard, SlidingWindowLimiter


class Container:
    """Composition root: builds long-lived singletons once and exposes them to routers."""

    def __init__(self, settings: Settings, llm_factory: Callable[[], QueryLLM] | None = None) -> None:
        self.settings = settings
        self.engine, self.session_factory = create_session_factory(settings.app_database_url)
        self.hasher = PasswordHasher()
        self.tokens = TokenService(settings.secret_key, settings.access_token_minutes)
        self.cipher = CredentialCipher(settings.encryption_key)
        limits = ExecutionLimits(
            settings.query_timeout_seconds,
            settings.max_result_rows,
            settings.max_schema_chars,
            settings.schema_ttl_seconds,
        )
        self.registry: AdapterRegistry = default_registry(limits)
        self.policy = UrlPolicy(settings.allow_private_hosts, settings.sqlite_allowed_dir)
        self.pool = AdapterPool(self.registry, settings.max_engines, settings.engine_idle_seconds)
        self.guard = RunGuard(
            settings.max_concurrent_runs,
            settings.max_runs_per_user,
            settings.max_runs_per_connection,
            settings.run_deadline_seconds + 30,
        )
        self.login_limiter = SlidingWindowLimiter(max_attempts=10, window_seconds=300)
        self.runner = QueryRunner(self.pool)
        self._llm_factory = llm_factory or self._openai_llm

    def _openai_llm(self) -> QueryLLM:
        s = self.settings
        return OpenAIQueryLLM(s.openai_api_key, s.llm_model, s.llm_fast_model, s.llm_timeout_seconds)

    @cached_property
    def llm(self) -> QueryLLM:
        return self._llm_factory()
