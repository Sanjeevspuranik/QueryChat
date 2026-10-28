"""Server logging: one rotating file plus the console, with a request id on every line.

Never log secrets, database URLs, passwords or the text of user questions; log ids,
sizes, statuses and timings instead."""
import logging
import time
import uuid
from contextvars import ContextVar
from logging.handlers import RotatingFileHandler
from pathlib import Path

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import BACKEND_DIR, Settings

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_FORMAT = "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s"
_MARK = "_querychat_handler"
_QUIET_PATHS = {"/api/health"}
_FRAMEWORK_LOGGERS = ("uvicorn", "uvicorn.error", "alembic")

access_logger = logging.getLogger("querychat.access")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def log_file_path(settings: Settings) -> Path:
    return (Path(settings.log_dir) if settings.log_dir else BACKEND_DIR / "logs") / "server.log"


def configure_logging(settings: Settings) -> Path | None:
    """Idempotent (safe under --reload and in tests). Returns the log file path, if any."""
    root = logging.getLogger()
    for handler in [h for h in root.handlers if getattr(h, _MARK, False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(_FORMAT)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    path: Path | None = None
    if settings.log_to_file:
        path = log_file_path(settings)
        path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                path, maxBytes=settings.log_max_mb * 1024 * 1024,
                backupCount=settings.log_backups, encoding="utf-8",
            )
        )
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.addFilter(_RequestIdFilter())
        setattr(handler, _MARK, True)
        root.addHandler(handler)

    root.setLevel(settings.log_level)
    for name in _FRAMEWORK_LOGGERS:  # let framework records reach our handlers instead of their own
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.error").handlers.clear()
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    return path


class RequestLogMiddleware(BaseHTTPMiddleware):
    """Assigns a request id (returned as X-Request-ID) and logs method, path, status and duration."""

    async def dispatch(self, request: Request, call_next) -> Response:
        rid = request.headers.get("x-request-id", "")[:64] or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            access_logger.exception("%s %s -> unhandled error", request.method, request.url.path)
            response = JSONResponse(
                {"detail": f"Internal server error. Reference: {rid}"}, status_code=500
            )
        else:
            if request.url.path not in _QUIET_PATHS:
                ms = (time.perf_counter() - started) * 1000
                level = logging.WARNING if response.status_code >= 400 else logging.INFO
                access_logger.log(
                    level, "%s %s -> %s (%.0f ms)", request.method, request.url.path, response.status_code, ms
                )
        response.headers["X-Request-ID"] = rid
        request_id_var.reset(token)
        return response
