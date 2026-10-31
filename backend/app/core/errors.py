"""Error types and the handlers that turn them into the API error envelope.

Every error response has the shape
`{"error": {"code": "...", "message": "...", "retryable": bool}}`.
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pymongo.errors import ConnectionFailure, DuplicateKeyError, ExecutionTimeout, PyMongoError, WTimeoutError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain.errors import DomainError

log = logging.getLogger(__name__)


class AppError(Exception):
    """Base error for anything the API reports to the client."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 500,
        retryable: bool = False,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details


class NotFoundError(AppError):
    def __init__(self, what: str) -> None:
        super().__init__("not_found", f"{what} not found.", status_code=404)


def error_body(code: str, message: str, retryable: bool = False, details: Any = None) -> dict:
    body: dict[str, Any] = {"code": code, "message": message, "retryable": retryable}
    if details is not None:
        body["details"] = details
    return {"error": body}


class UnexpectedErrorMiddleware:
    """Turns any unhandled exception into the 500 error envelope.

    It sits inside CORSMiddleware (unlike Starlette's outermost ServerErrorMiddleware), so the
    browser still gets CORS headers and the frontend can read {"error": ...} instead of a CORS failure.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def track(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, receive, track)
        except Exception:
            # Never leak internals to the client; the full trace goes to the server log.
            log.exception("Unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if started:
                raise
            response = JSONResponse(status_code=500,
                                    content=error_body("internal_error", "Something went wrong on our side."))
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.retryable, exc.details),
        )

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(status_code=422, content=error_body(exc.code, exc.message))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body("invalid_request", "The request is not valid.", False, details),
        )

    @app.exception_handler(PyMongoError)
    async def _database_error(_: Request, exc: PyMongoError) -> JSONResponse:
        if isinstance(exc, (ConnectionFailure, ExecutionTimeout, WTimeoutError)):
            log.error("Database unreachable: %s", exc)
            return JSONResponse(status_code=503, content=error_body(
                "database_unavailable", "The database is not responding. Try again shortly.", True))
        if isinstance(exc, DuplicateKeyError):
            log.warning("Write conflict: %s", exc)
            return JSONResponse(status_code=409, content=error_body(
                "conflict", "Someone else saved the same record at the same moment. Try again.", True))
        log.exception("Database error")
        return JSONResponse(status_code=500, content=error_body("database_error", "The database rejected the request."))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(f"http_{exc.status_code}", str(exc.detail)),
        )
