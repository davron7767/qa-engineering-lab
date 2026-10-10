"""QA Commerce application factory."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.config import get_settings
from app.errors import register_error_handlers

logger = logging.getLogger("qa_commerce.http")

STATIC_DIR = Path(__file__).parent / "static"


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="QA Commerce API",
        version=settings.app_version,
        description=(
            "Fictional order-management application used as a test-automation target. "
            "Money values are serialized as decimal strings with two fractional digits."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    register_error_handlers(app)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Accept a caller-supplied request id (useful for correlating test logs) or mint one.
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if 0 < len(incoming) <= 64 else uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-ID"] = request_id
        # Only method, path, status and timing are logged: never headers, bodies or tokens.
        logger.info(
            "%s %s -> %s (%.1f ms) request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            request_id,
        )
        return response

    app.include_router(api_router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
