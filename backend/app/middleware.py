"""ASGI middleware for the API edge.

Correlation IDs are bound here, at the boundary, so that every log line emitted
anywhere downstream — services, repositories, external clients — carries the same
request identifier without it being threaded through function signatures.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.constants import REQUEST_ID_HEADER
from app.core.logging import bind_request_id, get_logger, new_request_id

logger = get_logger(__name__)

#: Milliseconds per second, for reporting request duration.
_MS_PER_SECOND = 1000.0


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Bind a correlation ID to the request and log its outcome.

    Honours an inbound ``X-Request-ID`` so a trace started by an upstream caller
    — a partner city's node, or a gateway — stays continuous across services.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or new_request_id()
        bind_request_id(request_id)
        request.state.request_id = request_id

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * _MS_PER_SECOND

        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request.completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round(duration_ms, 2),
        )
        return response
