import asyncio
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

from app.adapters.sqlite_path import SqliteFileError, resolve_sqlite_file
from app.core.errors import UnsupportedDatabaseError

_VECTOR_STORES = (
    "pinecone", "weaviate", "qdrant", "chroma", "milvus", "faiss", "lancedb",
    "vespa", "redisearch", "pgvector",
)


class UrlPolicy:
    """Decides whether a user-supplied database URL may be used at all:
    rejects vector stores, SSRF targets and out-of-bounds SQLite paths."""

    def __init__(self, allow_private_hosts: bool, sqlite_allowed_dir: str = "") -> None:
        self._allow_private = allow_private_hosts
        self._sqlite_dir = Path(sqlite_allowed_dir).resolve() if sqlite_allowed_dir else None

    async def check(self, url: str) -> None:
        if "://" not in url or len(url) > 2000:
            raise UnsupportedDatabaseError("Enter a valid database URL, e.g. sqlite:///file.db")
        scheme = url.split("://", 1)[0].lower()
        if any(name in scheme or name in url.lower().split("://", 1)[1].split("/")[0]
               for name in _VECTOR_STORES):
            raise UnsupportedDatabaseError("Vector stores are not supported.")
        if scheme.startswith("sqlite"):
            self._check_sqlite(url)
            return
        if not self._allow_private:
            await self._check_hosts(url)

    def _check_sqlite(self, url: str) -> None:
        try:
            path = resolve_sqlite_file(url)
        except SqliteFileError as exc:
            raise UnsupportedDatabaseError(str(exc)) from exc
        if self._allow_private:
            return
        if self._sqlite_dir is None or not path.is_relative_to(self._sqlite_dir):
            raise UnsupportedDatabaseError("SQLite files are only allowed inside the permitted directory.")

    async def _check_hosts(self, url: str) -> None:
        netloc = urlparse(url).netloc.rsplit("@", 1)[-1]
        for host_port in filter(None, netloc.split(",")):
            if host_port.startswith("["):  # IPv6 literal
                host = host_port[1:].split("]")[0]
            else:
                host = host_port.rsplit(":", 1)[0]
            for address in await self._resolve(host):
                if not address.is_global:
                    raise UnsupportedDatabaseError("Connections to private or local addresses are blocked.")

    @staticmethod
    async def _resolve(host: str) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        try:
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass
        try:
            infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
        except socket.gaierror:
            return []  # unresolvable here; connecting will fail on its own
        return [ipaddress.ip_address(info[4][0]) for info in infos]
