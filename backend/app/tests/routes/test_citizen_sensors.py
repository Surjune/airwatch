"""Tests for the citizen sensor reading endpoints.

The wire contract carries ``is_calibrated: false`` on every reading, because the
consumer that matters is a map: without the flag a client has no way to draw a
household sensor differently from a reference monitor.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.repositories.session import get_db_session
from app.tests.services.test_citizen_sensor_service import DELHI

pytestmark = pytest.mark.integration

DEVICE = "route-sensor-000001"


@pytest.fixture
def api(app: FastAPI, session: Session) -> Iterator[TestClient]:
    """A client whose requests run inside the test's own transaction."""

    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        yield client


def post(api: TestClient, **overrides: Any) -> Any:
    longitude, latitude = DELHI
    body: dict[str, Any] = {
        "longitude": longitude,
        "latitude": latitude,
        "pollutant": "pm25",
        "value_ugm3": 88.0,
        "observed_at": datetime.now(UTC).isoformat(),
        "device_id": DEVICE,
        "sensor_model": "AirGradient ONE",
    }
    body.update(overrides)
    return api.post("/v1/citizen/sensor-readings", json=body)


class TestSubmit:
    def test_accepts_a_reading_and_marks_it_uncalibrated(self, api: TestClient) -> None:
        response = post(api)

        assert response.status_code == 200
        body = response.json()
        assert body["reading_id"] > 0
        assert body["value_ugm3"] == 88.0
        assert body["is_calibrated"] is False

    def test_carries_an_explanation_of_the_bias_so_far(self, api: TestClient) -> None:
        body = post(api).json()

        assert body["colocation"]["is_established"] is False
        assert body["colocation"]["explanation"]

    def test_rejects_a_gas_pollutant_at_the_boundary(self, api: TestClient) -> None:
        assert post(api, pollutant="no2").status_code == 422

    def test_rejects_a_negative_value(self, api: TestClient) -> None:
        assert post(api, value_ugm3=-1).status_code == 422

    def test_rejects_an_implausible_value_with_a_reason(self, api: TestClient) -> None:
        response = post(api, value_ugm3=90_000)

        assert response.status_code == 422
        assert "outside" in response.json()["error"]["message"]

    def test_rejects_a_short_device_identifier(self, api: TestClient) -> None:
        assert post(api, device_id="short").status_code == 422


class TestList:
    def test_lists_a_reading_that_was_just_submitted(self, api: TestClient) -> None:
        post(api, value_ugm3=77.0)

        body = api.get("/v1/citizen/sensor-readings", params={"city": "delhi"}).json()

        assert body["reading_count"] == 1
        assert body["readings"][0]["value_ugm3"] == 77.0
        assert body["readings"][0]["is_calibrated"] is False
        assert body["note"]

    def test_rejects_an_unknown_city(self, api: TestClient) -> None:
        response = api.get("/v1/citizen/sensor-readings", params={"city": "atlantis"})

        assert response.status_code == 422
