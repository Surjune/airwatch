"""Tests for the health endpoint and the global error envelope."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.constants import H3_RESOLUTION, REQUEST_ID_HEADER


class TestHealthEndpoint:
    def test_reports_ok(self, client: TestClient) -> None:
        response = client.get("/v1/health")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["environment"] == "test"

    def test_publishes_the_canonical_grid_resolution(self, client: TestClient) -> None:
        # Federated nodes must agree on the analysis grid before exchanging
        # weights, so it is part of the advertised contract rather than an
        # internal detail.
        assert client.get("/v1/health").json()["h3_resolution"] == H3_RESOLUTION

    def test_names_every_unconfigured_upstream(self, client: TestClient) -> None:
        upstreams = client.get("/v1/health").json()["upstreams"]
        assert upstreams, "health must report upstream configuration state"
        assert all(entry["configured"] is False for entry in upstreams)
        # The env var name is what an operator needs to fix the deployment.
        assert all(entry["required_env_var"] for entry in upstreams)


class TestRequestCorrelation:
    def test_generates_a_request_id_when_absent(self, client: TestClient) -> None:
        response = client.get("/v1/health")
        assert response.headers[REQUEST_ID_HEADER]

    def test_honours_an_inbound_request_id(self, client: TestClient) -> None:
        # A trace started by a partner node or a gateway must stay continuous.
        inbound = "trace-from-an-upstream-caller"
        response = client.get("/v1/health", headers={REQUEST_ID_HEADER: inbound})
        assert response.headers[REQUEST_ID_HEADER] == inbound


class TestErrorEnvelope:
    def test_unknown_route_uses_the_standard_envelope(self, client: TestClient) -> None:
        response = client.get("/v1/does-not-exist")
        assert response.status_code == 404
        error = response.json()["error"]
        assert error["code"] == "http_404"
        # The correlation ID is the thread back to the logs for this request.
        assert error["request_id"]
