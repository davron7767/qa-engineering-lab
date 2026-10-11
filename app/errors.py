"""Domain errors and the single JSON error envelope used by every API response.

Envelope:
    {"error": {"code": "...", "message": "...", "details": [...], "request_id": "..."}}
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("qa_commerce.errors")


class AppError(Exception):
    """Base class for expected, client-facing errors."""

    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or []


class AuthenticationRequired(AppError):
    status_code = 401
    code = "AUTHENTICATION_REQUIRED"


class InvalidCredentials(AppError):
    status_code = 401
    code = "INVALID_CREDENTIALS"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ProductNotFound(NotFound):
    code = "PRODUCT_NOT_FOUND"


class OrderNotFound(NotFound):
    code = "ORDER_NOT_FOUND"


class UnknownProduct(AppError):
    """An order references a product id that does not exist."""

    status_code = 400
    code = "UNKNOWN_PRODUCT"


class ProductInactive(AppError):
    status_code = 400
    code = "PRODUCT_INACTIVE"


class InsufficientInventory(AppError):
    status_code = 409
    code = "INSUFFICIENT_INVENTORY"


class IdempotencyKeyReused(AppError):
    status_code = 409
    code = "IDEMPOTENCY_KEY_REUSED"


class OrderNotCancellable(AppError):
    status_code = 409
    code = "ORDER_NOT_CANCELLABLE"


class DuplicateSku(AppError):
    status_code = 409
    code = "SKU_ALREADY_EXISTS"


class DuplicateEmail(AppError):
    status_code = 409
    code = "EMAIL_ALREADY_EXISTS"


def error_body(
    request: Request, code: str, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": getattr(request.state, "request_id", None),
        }
    }


_HTTP_CODES = {
    401: "AUTHENTICATION_REQUIRED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            error_body(request, exc.code, exc.message, exc.details),
            status_code=exc.status_code,
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body(request, "VALIDATION_ERROR", "Request validation failed", details),
            status_code=422,
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Imported lazily to avoid a cycle; injected faults get their own code for clarity.
        from app.faults import InjectedFault

        code = "INJECTED_FAULT" if isinstance(exc, InjectedFault) else "INTERNAL_ERROR"
        logger.error(
            "Unhandled %s request_id=%s",
            type(exc).__name__,
            getattr(request.state, "request_id", None),
            exc_info=not isinstance(exc, InjectedFault),
        )
        # The response never includes exception text or stack traces.
        # Starlette re-raises after this response so the server can log it, and uvicorn then
        # closes the connection. Saying so up front stops keep-alive clients from reusing a
        # socket that is about to close (an intermittent ECONNRESET on their next request).
        return JSONResponse(
            error_body(request, code, "An unexpected error occurred"),
            status_code=500,
            headers={"Connection": "close"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404 and not request.url.path.startswith("/api/"):
            from app.web.routes import not_found_page

            return not_found_page(request)
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            error_body(request, code, str(exc.detail)),
            status_code=exc.status_code,
            headers=getattr(exc, "headers", None),
        )
