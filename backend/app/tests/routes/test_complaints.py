"""Tests for the complaint list and PDF download endpoints."""

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

DEVICE = "route-complaint-0001"


@pytest.fixture
def api(app: FastAPI, session: Session) -> Iterator[TestClient]:
    """A client whose requests run inside the test's own transaction."""

    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        yield client


def submit(api: TestClient, **overrides: Any) -> Any:
    longitude, latitude = DELHI
    body: dict[str, Any] = {
        "longitude": longitude,
        "latitude": latitude,
        "pollutant": "pm25",
        "value_ugm3": 96.0,
        "observed_at": datetime.now(UTC).isoformat(),
        "device_id": DEVICE,
        "sensor_model": "AirGradient ONE",
        "category": "construction_dust",
        "description": "Demolition dust, no water spraying",
    }
    body.update(overrides)
    return api.post("/v1/citizen/sensor-readings", json=body)


class TestSubmissionCarriesAReference:
    def test_a_reading_returns_the_reference_to_quote(self, api: TestClient) -> None:
        body = submit(api).json()

        assert body["complaint_reference"].startswith("AW-S-")

    def test_an_unknown_category_is_refused(self, api: TestClient) -> None:
        assert submit(api, category="alien_activity").status_code == 422

    def test_an_overlong_description_is_refused(self, api: TestClient) -> None:
        assert submit(api, description="x" * 501).status_code == 422


class TestList:
    def test_lists_this_devices_submissions(self, api: TestClient) -> None:
        reference = submit(api).json()["complaint_reference"]

        body = api.get("/v1/citizen/complaints", headers={"X-Device-ID": DEVICE}).json()

        assert body["complaint_count"] == 1
        assert body["complaints"][0]["reference"] == reference
        assert body["complaints"][0]["category"] == "construction_dust"

    def test_another_device_sees_nothing(self, api: TestClient) -> None:
        submit(api)

        body = api.get("/v1/citizen/complaints", headers={"X-Device-ID": "other-device-01"}).json()

        assert body["complaint_count"] == 0

    def test_requires_the_device_header(self, api: TestClient) -> None:
        assert api.get("/v1/citizen/complaints").status_code == 422


class TestPdf:
    def test_downloads_a_pdf_attachment(self, api: TestClient) -> None:
        reference = submit(api).json()["complaint_reference"]

        response = api.get(
            f"/v1/citizen/complaints/{reference}/pdf", headers={"X-Device-ID": DEVICE}
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert f'filename="airwatch-{reference}.pdf"' in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store"
        assert response.content.startswith(b"%PDF-")

    def test_another_device_gets_not_found(self, api: TestClient) -> None:
        reference = submit(api).json()["complaint_reference"]

        response = api.get(
            f"/v1/citizen/complaints/{reference}/pdf", headers={"X-Device-ID": "other-device-01"}
        )

        assert response.status_code == 404

    def test_a_malformed_reference_is_a_validation_error(self, api: TestClient) -> None:
        response = api.get("/v1/citizen/complaints/nonsense/pdf", headers={"X-Device-ID": DEVICE})

        assert response.status_code == 422
