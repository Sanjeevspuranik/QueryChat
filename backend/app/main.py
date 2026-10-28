from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.container import Container
from app.core.config import Settings
from app.core.logging_setup import RequestLogMiddleware, configure_logging
from app.core.errors import (
    AuthenticationError,
    ConflictError,
    DatabaseConnectionError,
    NotFoundError,
    QueryChatError,
    RateLimitError,
    UnsupportedDatabaseError,
)
from app.db.migrate import migrate
from app.db.models import init_schema
from app.routers import auth, connections, sessions

logger = logging.getLogger("querychat.app")

_STATUS = {
    AuthenticationError: 401,
    NotFoundError: 404,
    ConflictError: 409,
    RateLimitError: 429,
    UnsupportedDatabaseError: 400,
    DatabaseConnectionError: 400,
}


def create_app(container: Container | None = None) -> FastAPI:
    container = container or Container(Settings())  # type: ignore[call-arg]
    log_path = configure_logging(container.settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        logger.info("starting QueryChat (log file: %s, model: %s)", log_path or "disabled", container.settings.llm_model)
        if container.settings.db_bootstrap == "migrate":
            await migrate(container.settings.app_database_url)
        else:
            await init_schema(container.engine)
        yield
        logger.info("shutting down")
        await container.pool.close_all()
        await container.engine.dispose()

    app = FastAPI(title="QueryChat API", lifespan=lifespan)
    app.state.container = container
    app.add_middleware(RequestLogMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(QueryChatError)
    async def handle_domain_error(request: Request, exc: QueryChatError):
        status = next((code for cls, code in _STATUS.items() if isinstance(exc, cls)), 400)
        logger.warning("%s on %s %s: %s", type(exc).__name__, request.method, request.url.path, exc)
        return JSONResponse({"detail": str(exc)}, status_code=status)

    for router in (auth.router, connections.router, sessions.router):
        app.include_router(router, prefix="/api")

    @app.get("/api/health")
    async def health():
        return {"status": "ok"}

    return app


def get_app() -> FastAPI:
    return create_app()
