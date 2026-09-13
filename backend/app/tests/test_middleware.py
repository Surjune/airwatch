"""Tests for the API edge: correlation IDs and per-client rate limiting."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.constants import REQUEST_ID_HEADER
from app.main import create_app

LIMIT = 3


def limited_client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings.model_copy(update={"rate_limit_per_minute": LIMIT})))


def test_requests_within_the_limit_report_what_remains(settings: Settings) -> None:
    client = limited_client(settings)

    # 404 is fine: the limit applies to every route, found or not.
    response = client.get("/v1/does-not-exist")

    assert response.headers["RateLimit-Limit"] == str(LIMIT)
    assert response.headers["RateLimit-Remaining"] == str(LIMIT - 1)


def test_a_client_over_the_limit_gets_a_429_envelope(settings: Settings) -> None:
    client = limited_client(settings)
    for _ in range(LIMIT):
        client.get("/v1/does-not-exist")

    response = client.get("/v1/does-not-exist", headers={REQUEST_ID_HEADER: "trace-429"})

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1
    body = response.json()
    assert body["error"]["code"] == "rate_limit_exceeded"
    assert body["error"]["details"] == {"limit_per_minute": LIMIT}
    # Refused requests stay traceable.
    assert body["error"]["request_id"] == "trace-429"
    assert response.headers[REQUEST_ID_HEADER] == "trace-429"


def test_the_liveness_probe_is_never_refused(settings: Settings) -> None:
    client = limited_client(settings)
    for _ in range(LIMIT * 3):
        assert client.get("/v1/health").status_code == 200


def test_browser_preflight_does_not_spend_the_allowance(settings: Settings) -> None:
    client = limited_client(settings)
    preflight = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    for _ in range(LIMIT * 3):
        client.options("/v1/stations", headers=preflight)

    assert client.get("/v1/does-not-exist").headers["RateLimit-Remaining"] == str(LIMIT - 1)


def test_a_browser_can_read_the_refusal(settings: Settings) -> None:
    # CORS must wrap the limiter, or the browser hides the 429 behind an opaque
    # network error and the dashboard cannot say what happened.
    client = limited_client(settings)
    origin = {"Origin": "http://localhost:5173"}
    for _ in range(LIMIT):
        client.get("/v1/does-not-exist", headers=origin)

    response = client.get("/v1/does-not-exist", headers=origin)

    assert response.status_code == 429
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_each_application_instance_starts_with_fresh_allowances(settings: Settings) -> None:
    first = limited_client(settings)
    for _ in range(LIMIT):
        first.get("/v1/does-not-exist")
    assert first.get("/v1/does-not-exist").status_code == 429

    assert limited_client(settings).get("/v1/does-not-exist").status_code == 404
