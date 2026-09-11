"""Tests for the alert console endpoints.

These run against the real database because the endpoints exist to expose a
stored trail, and a stubbed store would not have one. The session the route
receives is the test's own transaction, so everything written here is rolled
back and the endpoints are still exercised exactly as deployed.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.repositories.session import get_db_session
from app.services import alert_service
from app.tests.services.test_alert_service import _seed_authority, _seed_network

pytestmark = pytest.mark.integration


@pytest.fixture
def api(app: FastAPI, session: Session) -> Iterator[TestClient]:
    """A client whose requests run inside the test's own transaction."""

    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        yield client


@pytest.fixture
def seeded(session: Session) -> None:
    """A network with one live hotspot, anchored to the present.

    The endpoints read the clock themselves rather than accepting an injected
    time, so readings dated to a fixed past hour would fall outside every window
    a caller can legally request.
    """
    _seed_network(session, anchor=datetime.now(UTC))
    _seed_authority(session)
    session.flush()


class TestDispatchEndpoint:
    def test_dispatch_reports_what_it_did(self, api: TestClient, seeded: None) -> None:
        body = api.post("/v1/alerts/dispatch", params={"window_hours": 720}).json()

        assert body["detected"] >= 1
        assert body["raised"] >= 1
        assert body["unrouted"] == 0

    def test_a_second_dispatch_suppresses(self, api: TestClient, seeded: None) -> None:
        api.post("/v1/alerts/dispatch", params={"window_hours": 720})
        body = api.post("/v1/alerts/dispatch", params={"window_hours": 720}).json()

        assert body["raised"] == 0
        assert body["suppressed"] >= 1

    def test_rejects_a_window_outside_the_supported_range(self, api: TestClient) -> None:
        assert api.post("/v1/alerts/dispatch", params={"window_hours": 0}).status_code == 422


class TestInboxEndpoint:
    def test_lists_alerts_with_their_excess(self, api: TestClient, seeded: None) -> None:
        api.post("/v1/alerts/dispatch", params={"window_hours": 720})

        body = api.get("/v1/alerts").json()

        assert body["alert_count"] >= 1
        alert = body["alerts"][0]
        # The console must be able to say "412 where 78 was expected", not just
        # "412", or it cannot tell a source from a bad day.
        assert alert["peak_observed"] > alert["peak_excess"] > 0
        assert alert["authority_name"]
        assert alert["position"]["longitude"] > alert["position"]["latitude"]

    def test_filters_by_status(self, api: TestClient, seeded: None) -> None:
        api.post("/v1/alerts/dispatch", params={"window_hours": 720})

        assert api.get("/v1/alerts", params={"status": "sent"}).json()["alert_count"] >= 1
        assert api.get("/v1/alerts", params={"status": "resolved"}).json()["alert_count"] == 0

    def test_rejects_an_unknown_status(self, api: TestClient) -> None:
        assert api.get("/v1/alerts", params={"status": "ignored"}).status_code == 422


class TestLifecycleEndpoints:
    def _alert_id(self, session: Session) -> int:
        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=720)
        return outcome.raised[0].alert_id

    def test_acknowledge_then_resolve(
        self, api: TestClient, session: Session, seeded: None
    ) -> None:
        alert_id = self._alert_id(session)

        acknowledged = api.post(f"/v1/alerts/{alert_id}/acknowledge").json()
        assert acknowledged["status"] == "acknowledged"
        assert acknowledged["acknowledged_at"]

        resolved = api.post(
            f"/v1/alerts/{alert_id}/resolve",
            json={"note": "Waste fire behind the terminal, extinguished."},
        ).json()
        assert resolved["status"] == "resolved"
        assert "extinguished" in resolved["resolution_note"]

    def test_resolving_without_a_note_is_refused(
        self, api: TestClient, session: Session, seeded: None
    ) -> None:
        alert_id = self._alert_id(session)

        response = api.post(f"/v1/alerts/{alert_id}/resolve", json={"note": "   "})

        assert response.status_code == 422

    def test_resolving_with_no_body_is_refused(
        self, api: TestClient, session: Session, seeded: None
    ) -> None:
        alert_id = self._alert_id(session)

        assert api.post(f"/v1/alerts/{alert_id}/resolve").status_code == 422

    def test_an_unknown_alert_is_a_typed_404(self, api: TestClient, seeded: None) -> None:
        response = api.post("/v1/alerts/999999/acknowledge")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"


class TestSlaEndpoint:
    def test_reports_no_breach_for_a_fresh_alert(
        self, api: TestClient, session: Session, seeded: None
    ) -> None:
        self._dispatch(api)

        body = api.get("/v1/alerts/sla-breaches").json()

        # The alert was raised at request time, so nothing can be overdue yet.
        assert body["breach_count"] == 0

    def test_the_route_is_not_shadowed_by_the_id_routes(self, api: TestClient) -> None:
        # "sla-breaches" sits where an alert id would if the paths were shaped
        # the same. This asserts the router resolves it as its own endpoint.
        assert api.get("/v1/alerts/sla-breaches").status_code == 200

    @staticmethod
    def _dispatch(api: TestClient) -> None:
        api.post("/v1/alerts/dispatch", params={"window_hours": 720})
