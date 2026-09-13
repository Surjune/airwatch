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
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.core.constants import RATE_LIMIT_EXEMPT_PATHS, REQUEST_ID_HEADER
from app.core.exceptions import RateLimitExceededError
from app.core.logging import bind_request_id, get_logger, new_request_id
from app.core.rate_limit import TokenBucketLimiter

logger = get_logger(__name__)

#: Milliseconds per second, for reporting request duration.
_MS_PER_SECOND = 1000.0

#: Key used when the server cannot see a client address at all.
_UNKNOWN_CLIENT = "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Refuse a client that has spent its allowance, with a 429 envelope.

    The key is the connecting address. ``X-Forwarded-For`` is deliberately not
    read: any caller can set it, so trusting it would let a scraper name a fresh
    address on every request and never be limited. A deployment behind a reverse
    proxy must have the proxy set the real address (uvicorn's
    ``--proxy-headers`` with ``--forwarded-allow-ips``), which is where that trust
    decision belongs.

    Preflight requests are not counted: a browser sends one before a real call
    it cannot suppress, and charging for it would halve a dashboard's allowance.
    """

    def __init__(self, app: ASGIApp, *, limiter: TokenBucketLimiter) -> None:
        super().__init__(app)
        self._limiter = limiter

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method == "OPTIONS" or request.url.path in RATE_LIMIT_EXEMPT_PATHS:
            return await call_next(request)

        client = request.client.host if request.client else _UNKNOWN_CLIENT
        decision = self._limiter.check(client, time.monotonic())

        if not decision.allowed:
            logger.warning(
                "request.rate_limited",
                path=request.url.path,
                retry_after_seconds=decision.retry_after_seconds,
            )
            error = RateLimitExceededError(
                f"Too many requests: the limit is {decision.limit} per minute. "
                f"Retry in {decision.retry_after_seconds} seconds.",
                details={"limit_per_minute": decision.limit},
            )
            return JSONResponse(
                status_code=error.status_code,
                content=error.to_envelope(getattr(request.state, "request_id", None)),
                headers={
                    "Retry-After": str(decision.retry_after_seconds),
                    "RateLimit-Limit": str(decision.limit),
                    "RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["RateLimit-Limit"] = str(decision.limit)
        response.headers["RateLimit-Remaining"] = str(decision.remaining)
        return response


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
