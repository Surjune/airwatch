"""Tests for the shared upstream HTTP client.

The behaviour that matters most is the last group: every failure mode must raise
a typed error. An upstream failure that quietly became an empty list would render
as "no pollution detected" — a wrong answer that looks like good news.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.core.exceptions import (
    UpstreamRateLimitedError,
    UpstreamResponseError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)
from app.core.logging import bind_request_id
from app.external.base import UpstreamClient

BASE_URL = "https://upstream.test"
ENDPOINT = f"{BASE_URL}/readings"


class ProbeClient(UpstreamClient):
    """A concrete client standing in for a real provider."""

    provider_name = "Probe"
    base_url = BASE_URL


def build_client(**overrides: object) -> ProbeClient:
    """A probe client that retries without ever actually sleeping."""
    kwargs: dict[str, object] = {"backoff_base_seconds": 0.0}
    kwargs.update(overrides)
    return ProbeClient(**kwargs)  # type: ignore[arg-type]


class TestSuccessfulRequests:
    @respx.mock
    async def test_returns_the_decoded_body(self) -> None:
        respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={"pm25": 42}))

        async with build_client() as client:
            assert await client.get_json("/readings") == {"pm25": 42}

    @respx.mock
    async def test_passes_query_parameters(self) -> None:
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[]))

        async with build_client() as client:
            await client.get_json("/readings", params={"city": "Delhi", "limit": 10})

        assert route.calls.last.request.url.params["city"] == "Delhi"
        assert route.calls.last.request.url.params["limit"] == "10"

    @respx.mock
    async def test_propagates_the_correlation_id_upstream(self) -> None:
        # Lets a slow third-party call be traced back to the request that caused it.
        bind_request_id("trace-me")
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json={}))

        async with build_client() as client:
            await client.get_json("/readings")

        assert route.calls.last.request.headers["X-Request-ID"] == "trace-me"

    @respx.mock
    async def test_an_empty_list_is_a_valid_answer(self) -> None:
        # Distinct from a failure: the upstream really did report no readings.
        respx.get(ENDPOINT).mock(return_value=httpx.Response(200, json=[]))

        async with build_client() as client:
            assert await client.get_json("/readings") == []


class TestRetries:
    @respx.mock
    async def test_retries_a_server_error_then_succeeds(self) -> None:
        route = respx.get(ENDPOINT).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(200, json={"recovered": True}),
            ]
        )

        async with build_client(max_attempts=3) as client:
            assert await client.get_json("/readings") == {"recovered": True}

        assert route.call_count == 2

    @respx.mock
    async def test_gives_up_after_the_attempt_budget(self) -> None:
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(500))

        async with build_client(max_attempts=3) as client:
            with pytest.raises(UpstreamUnavailableError):
                await client.get_json("/readings")

        assert route.call_count == 3

    @respx.mock
    async def test_does_not_retry_a_client_error(self) -> None:
        # Repeating a rejected request cannot succeed; retrying only wastes quota.
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(404))

        async with build_client(max_attempts=3) as client:
            with pytest.raises(UpstreamResponseError):
                await client.get_json("/readings")

        assert route.call_count == 1

    @respx.mock
    async def test_does_not_retry_an_unauthorised_request(self) -> None:
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(401))

        async with build_client(max_attempts=3) as client:
            with pytest.raises(UpstreamResponseError):
                await client.get_json("/readings")

        assert route.call_count == 1

    @respx.mock
    async def test_retries_a_rate_limit(self) -> None:
        route = respx.get(ENDPOINT).mock(
            side_effect=[httpx.Response(429), httpx.Response(200, json={})]
        )

        async with build_client(max_attempts=2) as client:
            await client.get_json("/readings")

        assert route.call_count == 2

    @respx.mock
    async def test_max_attempts_of_one_disables_retrying(self) -> None:
        route = respx.get(ENDPOINT).mock(return_value=httpx.Response(500))

        async with build_client(max_attempts=1) as client:
            with pytest.raises(UpstreamUnavailableError):
                await client.get_json("/readings")

        assert route.call_count == 1


class TestTypedErrors:
    @respx.mock
    async def test_timeout_raises_a_timeout_error(self) -> None:
        respx.get(ENDPOINT).mock(side_effect=httpx.ConnectTimeout("too slow"))

        async with build_client(max_attempts=2) as client:
            with pytest.raises(UpstreamTimeoutError) as excinfo:
                await client.get_json("/readings")

        assert excinfo.value.code == "upstream_timeout"
        assert excinfo.value.details["provider"] == "Probe"

    @respx.mock
    async def test_connection_failure_raises_unavailable(self) -> None:
        respx.get(ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))

        async with build_client(max_attempts=2) as client:
            with pytest.raises(UpstreamUnavailableError) as excinfo:
                await client.get_json("/readings")

        assert excinfo.value.code == "upstream_unavailable"

    @respx.mock
    async def test_rate_limit_surfaces_retry_after(self) -> None:
        respx.get(ENDPOINT).mock(return_value=httpx.Response(429, headers={"Retry-After": "120"}))

        async with build_client(max_attempts=1) as client:
            with pytest.raises(UpstreamRateLimitedError) as excinfo:
                await client.get_json("/readings")

        assert excinfo.value.details["retry_after"] == "120"

    @respx.mock
    async def test_a_non_json_body_is_an_error_not_an_empty_result(self) -> None:
        # A gateway error page must not be coerced into "no readings".
        respx.get(ENDPOINT).mock(
            return_value=httpx.Response(200, text="<html>gateway timeout</html>")
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="not valid JSON"):
                await client.get_json("/readings")

    @respx.mock
    async def test_errors_name_the_provider_for_the_operator(self) -> None:
        respx.get(ENDPOINT).mock(return_value=httpx.Response(500))

        async with build_client(max_attempts=1) as client:
            with pytest.raises(UpstreamUnavailableError) as excinfo:
                await client.get_json("/readings")

        # Without the provider name an operator cannot tell which of four
        # upstreams is down.
        assert "Probe" in excinfo.value.message
        assert excinfo.value.details["status_code"] == 500


class TestTransportLifecycle:
    async def test_closes_a_transport_it_created(self) -> None:
        client = build_client()
        await client.close()
        assert client._client.is_closed

    async def test_leaves_an_injected_transport_open(self) -> None:
        # The caller owns an injected client, so closing it here would break a
        # shared connection pool.
        injected = httpx.AsyncClient(base_url=BASE_URL)
        client = ProbeClient(client=injected)

        await client.close()

        assert not injected.is_closed
        await injected.aclose()
