"""Shared HTTP foundation for every upstream data client.

Business code never imports ``httpx`` directly. Each upstream client subclasses
:class:`UpstreamClient`, which centralises timeouts, retries, correlation-ID
propagation and — most importantly — the mapping from a transport failure to a
typed exception.

That mapping is the point. An upstream that times out, returns a 500, or returns
a body in an unexpected shape must surface as an explicit error, never as an
empty result. An empty result renders as "no pollution detected", which in a
public-health context is a wrong answer dressed up as a reassuring one.
"""

from __future__ import annotations

import asyncio
from types import TracebackType
from typing import Self

import httpx

from app.core.constants import (
    HTTP_BACKOFF_BASE_SECONDS,
    HTTP_MAX_ATTEMPTS,
    HTTP_TIMEOUT_SECONDS,
    REQUEST_ID_HEADER,
)
from app.core.exceptions import (
    UpstreamRateLimitedError,
    UpstreamResponseError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.logging import get_logger, get_request_id

logger = get_logger(__name__)

#: A decoded JSON document. Recursive, because upstream payloads nest freely.
#: Clients parse this into Pydantic models at once; it never reaches a service.
type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None

#: Lowest HTTP status treated as a server-side fault worth retrying.
_SERVER_ERROR_STATUS = 500

#: Status returned when an upstream quota is exhausted.
_RATE_LIMITED_STATUS = 429

#: Lowest status indicating the request itself was rejected.
_CLIENT_ERROR_STATUS = 400


class UpstreamClient:
    """Base class for a typed client wrapping one external data provider.

    Subclasses set :attr:`provider_name` and :attr:`base_url`, then call
    :meth:`get_json` and parse the result into their own models.
    """

    #: Human-readable provider name, used in errors and logs.
    provider_name: str = "upstream"

    #: Root URL every relative path is resolved against.
    base_url: str = ""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = HTTP_TIMEOUT_SECONDS,
        max_attempts: int = HTTP_MAX_ATTEMPTS,
        backoff_base_seconds: float = HTTP_BACKOFF_BASE_SECONDS,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Construct a client.

        Args:
            base_url: Overrides the class-level base URL.
            timeout_seconds: Per-request timeout.
            max_attempts: Total attempts including the first. 1 disables retries.
            backoff_base_seconds: First backoff interval, doubling each retry.
                Injectable so tests can exercise the retry path without waiting.
            client: An injected transport, used by tests. When supplied the
                caller owns its lifecycle and :meth:`close` leaves it open.
        """
        self._timeout = timeout_seconds
        self._max_attempts = max(1, max_attempts)
        self._backoff_base = backoff_base_seconds
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url if base_url is not None else self.base_url,
            timeout=timeout_seconds,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the transport, unless it was injected by the caller."""
        if self._owns_client:
            await self._client.aclose()

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        """Build request headers, propagating the correlation ID.

        Passing the request's correlation ID upstream means a slow third-party
        call can be tied back to the user request that triggered it.
        """
        headers = {"Accept": "application/json"}
        request_id = get_request_id()
        if request_id is not None:
            headers[REQUEST_ID_HEADER] = request_id
        if extra:
            headers.update(extra)
        return headers

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int | float] | None = None,
        headers: dict[str, str] | None = None,
    ) -> JsonValue:
        """GET a path and return the decoded JSON body.

        Retries transient failures — timeouts, connection errors, 5xx and 429 —
        with exponential backoff. A 4xx other than 429 is not retried, because
        repeating a malformed or unauthorised request cannot succeed.

        Args:
            path: Path relative to the base URL.
            params: Query parameters.
            headers: Extra headers merged over the defaults.

        Returns:
            The decoded JSON body.

        Raises:
            UpstreamTimeoutError: Every attempt timed out.
            UpstreamUnavailableError: The upstream could not be reached or kept
                returning a server error.
            UpstreamRateLimitedError: The provider's quota is exhausted.
            UpstreamResponseError: The request was rejected, or the body was not
                the JSON the caller requires.
        """
        last_error: Exception | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._client.get(
                    path,
                    params=params,
                    headers=self._headers(headers),
                )
            except httpx.TimeoutException:
                last_error = UpstreamTimeoutError(
                    self.provider_name,
                    f"{self.provider_name} did not respond within {self._timeout}s.",
                    details={"path": path, "attempt": attempt},
                )
            except httpx.TransportError as error:
                last_error = UpstreamUnavailableError(
                    self.provider_name,
                    f"Could not reach {self.provider_name}: {error}.",
                    details={"path": path, "attempt": attempt},
                )
            else:
                error_for_status = self._classify(response, path, attempt)
                if error_for_status is None:
                    return self._decode(response, path)
                last_error = error_for_status
                if not self._is_retryable(response.status_code):
                    raise last_error

            logger.warning(
                "upstream.attempt_failed",
                provider=self.provider_name,
                path=path,
                attempt=attempt,
                max_attempts=self._max_attempts,
            )

            if attempt < self._max_attempts:
                # Exponential backoff: 1s, 2s, 4s. Gives a briefly overloaded
                # upstream room to recover instead of adding to the load.
                await asyncio.sleep(self._backoff_base * (2 ** (attempt - 1)))

        if last_error is None:  # pragma: no cover - the loop always sets it.
            raise UpstreamUnavailableError(
                self.provider_name,
                f"{self.provider_name} could not be reached.",
                details={"path": path},
            )
        raise last_error

    def _classify(self, response: httpx.Response, path: str, attempt: int) -> Exception | None:
        """Map a response status to a typed error, or None when it succeeded."""
        status = response.status_code
        details = {"path": path, "status_code": status, "attempt": attempt}

        if status == _RATE_LIMITED_STATUS:
            return UpstreamRateLimitedError(
                self.provider_name,
                f"{self.provider_name} rate limit exceeded.",
                details={**details, "retry_after": response.headers.get("Retry-After")},
            )
        if status >= _SERVER_ERROR_STATUS:
            return UpstreamUnavailableError(
                self.provider_name,
                f"{self.provider_name} returned server error {status}.",
                details=details,
            )
        if status >= _CLIENT_ERROR_STATUS:
            return UpstreamResponseError(
                self.provider_name,
                f"{self.provider_name} rejected the request with status {status}.",
                details=details,
            )
        return None

    @staticmethod
    def _is_retryable(status_code: int) -> bool:
        """Whether repeating a request that returned this status could succeed."""
        return status_code == _RATE_LIMITED_STATUS or status_code >= _SERVER_ERROR_STATUS

    def _decode(self, response: httpx.Response, path: str) -> JsonValue:
        """Decode a JSON body, raising a typed error when it is not JSON."""
        try:
            decoded: JsonValue = response.json()
        except ValueError as error:
            # Coercing this to an empty result would be indistinguishable from a
            # genuine "no readings" answer.
            raise UpstreamResponseError(
                self.provider_name,
                f"{self.provider_name} returned a body that was not valid JSON.",
                details={"path": path, "content_type": response.headers.get("Content-Type")},
            ) from error
        return decoded
