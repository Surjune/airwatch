"""Tests for the citizen submission endpoints.

The wire contract matters more here than anywhere else in the API, because the
consumer is a member of the public rather than another system. A null
`estimate` has to arrive alongside an explanation, or it reads as a broken
feature rather than as the system declining to overstate what a photograph can
establish.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.constants import CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR
from app.repositories.session import get_db_session
from app.tests.services.test_citizen_service import DELHI, REMOTE, photo_bytes

pytestmark = pytest.mark.integration

DEVICE = "route-device-000001"


@pytest.fixture
def api(app: FastAPI, session: Session) -> Iterator[TestClient]:
    """A client whose requests run inside the test's own transaction."""

    def _session() -> Iterator[Any]:
        yield session

    app.dependency_overrides[get_db_session] = _session
    with TestClient(app) as client:
        yield client


def submit(
    api: TestClient,
    *,
    haze: float = 0.4,
    blurred: bool = False,
    position: tuple[float, float] = DELHI,
    device: str = DEVICE,
) -> Any:
    """Post a photograph the way a phone client would, as multipart form data."""
    longitude, latitude = position
    return api.post(
        "/v1/citizen/reports",
        files={"photo": ("scene.jpg", photo_bytes(haze=haze, blurred=blurred), "image/jpeg")},
        data={
            "longitude": str(longitude),
            "latitude": str(latitude),
            "captured_at": datetime.now(UTC).isoformat(),
            "device_id": device,
        },
    )


class TestSubmission:
    def test_accepts_a_usable_photograph(self, api: TestClient) -> None:
        response = submit(api)

        assert response.status_code == 200
        body = response.json()
        assert body["report_id"] > 0
        assert 0.0 <= body["haze_index"] <= 1.0
        assert body["h3_cell"]

    def test_reports_no_concentration_before_calibration(self, api: TestClient) -> None:
        body = submit(api).json()

        # Null is the answer, not a failure. The explanation is what stops it
        # reading as a bug.
        assert body["estimate"] is None
        assert body["calibration"]["is_calibrated"] is False
        assert len(body["calibration"]["explanation"]) > 50

    def test_says_how_many_pairs_are_still_needed(self, api: TestClient) -> None:
        calibration = submit(api).json()["calibration"]

        assert calibration["pairs_needed"] > calibration["pairs"]

    def test_a_blurred_photograph_is_refused_with_a_reason(self, api: TestClient) -> None:
        response = submit(api, blurred=True)

        assert response.status_code == 422
        body = response.json()
        assert body["accepted"] is False
        assert body["reason"] == "out_of_focus"
        # Written for the person who took the photo, so they can retake it.
        assert "blur" in body["detail"].lower()

    def test_rejects_a_position_outside_india(self, api: TestClient) -> None:
        response = submit(api, position=(2.35, 48.86))

        assert response.status_code == 422
        assert response.json()["error"]["code"] in {"invalid_geometry", "validation_error"}

    def test_rejects_a_file_that_is_not_an_image(self, api: TestClient) -> None:
        response = api.post(
            "/v1/citizen/reports",
            files={"photo": ("notes.txt", b"not an image at all", "text/plain")},
            data={
                "longitude": str(DELHI[0]),
                "latitude": str(DELHI[1]),
                "captured_at": datetime.now(UTC).isoformat(),
                "device_id": DEVICE,
            },
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    def test_rejects_a_short_device_identifier(self, api: TestClient) -> None:
        response = submit(api, device="abc")
        assert response.status_code == 422

    def test_rate_limits_one_device(self, api: TestClient) -> None:
        for _ in range(CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR):
            submit(api, position=REMOTE)

        response = submit(api, position=REMOTE)

        assert response.status_code == 429
        assert response.json()["error"]["code"] == "rate_limit_exceeded"


class TestReportsList:
    def test_lists_a_submission_that_was_just_made(self, api: TestClient) -> None:
        submit(api)

        body = api.get("/v1/citizen/reports", params={"window_hours": 24}).json()

        assert body["report_count"] >= 1
        report = body["reports"][0]
        # GeoJSON order: Delhi sits near 77E, 28N, so longitude exceeds latitude.
        assert report["position"]["longitude"] > report["position"]["latitude"]
        assert 0.0 <= report["haze_index"] <= 1.0

    def test_flags_which_submissions_also_calibrate(self, api: TestClient) -> None:
        # A submission near a monitor does two jobs: it reports, and it supplies
        # a pair. A consumer can see which, so progress toward calibration is
        # legible rather than opaque.
        submit(api)

        report = api.get("/v1/citizen/reports").json()["reports"][0]
        assert isinstance(report["had_reference"], bool)

    def test_carries_the_calibration_state_with_the_list(self, api: TestClient) -> None:
        body = api.get("/v1/citizen/reports").json()
        assert "is_calibrated" in body["calibration"]

    def test_rejects_a_window_outside_the_supported_range(self, api: TestClient) -> None:
        assert api.get("/v1/citizen/reports", params={"window_hours": 0}).status_code == 422


class TestCalibrationEndpoint:
    def test_reports_the_state_of_the_relation(self, api: TestClient) -> None:
        body = api.get("/v1/citizen/calibration").json()

        assert body["is_calibrated"] is False
        assert body["pairs_needed"] > 0
        assert body["mae"] is None
        assert body["explanation"]
