"""Global exception handlers producing one consistent JSON error envelope.

Every error a client can see passes through here, so no unhandled 500 with a
stack trace ever reaches the outside. The envelope shape is fixed:

.. code-block:: json

    {"error": {"code": "...", "message": "...", "details": {}, "request_id": "..."}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AirWatchError, ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Status code used when an unexpected exception escapes the application.
_INTERNAL_ERROR_STATUS = 500


def _request_id(request: Request) -> str | None:
    """Read the correlation ID bound by the middleware, if present."""
    return getattr(request.state, "request_id", None)


async def handle_airwatch_error(request: Request, exc: AirWatchError) -> JSONResponse:
    """Render a deliberate AirWatch error as its envelope."""
    logger.warning(
        "request.failed",
        error_code=exc.code,
        error_message=exc.message,
        details=exc.details,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_envelope(_request_id(request)),
    )


async def handle_validation_error(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render a Pydantic request-validation failure in the same envelope.

    FastAPI's default 422 body has a different shape from every other error this
    API returns; normalising it means a client needs exactly one error parser.
    """
    error = ValidationError(
        "Request validation failed.",
        details={"fields": exc.errors()},
    )
    logger.warning(
        "request.invalid",
        path=request.url.path,
        error_count=len(exc.errors()),
    )
    return JSONResponse(
        status_code=error.status_code,
        content=error.to_envelope(_request_id(request)),
    )


async def handle_http_exception(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Render Starlette's own HTTP errors — 404, 405 — in the same envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"http_{exc.status_code}",
                "message": str(exc.detail),
                "request_id": _request_id(request),
            }
        },
        headers=getattr(exc, "headers", None),
    )


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Catch anything that escaped, log it in full, and return a safe envelope.

    The client is told nothing about the internals; the correlation ID is the
    thread back to the full traceback in the logs.
    """
    logger.exception(
        "request.unhandled_error",
        path=request.url.path,
        error_type=type(exc).__name__,
    )
    return JSONResponse(
        status_code=_INTERNAL_ERROR_STATUS,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred.",
                "request_id": _request_id(request),
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    """Attach every handler to the application.

    Starlette types ``add_exception_handler`` as taking a handler of the base
    ``Exception``, so a handler narrowed to a specific subclass does not match
    the declared signature even though it is exactly what the runtime dispatches.
    The ignores below are unavoidable for that reason, not a papered-over bug.
    """
    app.add_exception_handler(AirWatchError, handle_airwatch_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, handle_unexpected_error)
