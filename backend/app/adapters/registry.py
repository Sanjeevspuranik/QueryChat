from app.adapters.base import DatabaseAdapter, ExecutionLimits
from app.adapters.mongo import MongoAdapter
from app.adapters.sql import SqlAdapter


class AdapterRegistry:
    """Maps URL schemes to adapter classes. New database families register here
    (Open/Closed); anything unregistered falls back to the SQLAlchemy adapter."""

    def __init__(self, limits: ExecutionLimits) -> None:
        self._limits = limits
        self._by_scheme: dict[str, type[DatabaseAdapter]] = {}
        self._default: type[DatabaseAdapter] = SqlAdapter

    def register(self, schemes: list[str], adapter_cls: type[DatabaseAdapter]) -> None:
        for scheme in schemes:
            self._by_scheme[scheme.lower()] = adapter_cls

    def create(self, url: str) -> DatabaseAdapter:
        return self.adapter_class(url)(url, self._limits)

    def adapter_class(self, url: str) -> type[DatabaseAdapter]:
        scheme = url.split("://", 1)[0].lower()
        return self._by_scheme.get(scheme) or self._by_scheme.get(scheme.split("+")[0], self._default)

    def db_type(self, url: str) -> str:
        return url.split("://", 1)[0].split("+")[0].lower()


def default_registry(limits: ExecutionLimits) -> AdapterRegistry:
    registry = AdapterRegistry(limits)
    registry.register(["mongodb", "mongodb+srv"], MongoAdapter)
    return registry
