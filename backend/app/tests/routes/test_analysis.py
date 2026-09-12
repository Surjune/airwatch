"""Tests for the analysis endpoints.

These run the real route, the real service and the real Pydantic schemas, with
only the repositories stubbed. That combination is deliberate: the layer most
likely to break silently is the translation between an internal dataclass and
the JSON a partner city consumes, and a test that stubbed the service would not
exercise it.

The contract assertions here are the ones a consumer depends on -- that
uncertainty is always present, that an excess is reported alongside the
concentration, and that a bad request produces a typed envelope rather than a
stack trace.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repositories import observation_repository, station_repository
from app.repositories.session import get_db_session
from app.tests.services.test_analysis_service import (
    NOW,
    latest_rows,
    reading_rows,
    wind_hours,
)


@pytest.fixture
def stubbed_app(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    """The application with its database replaced by in-memory fixtures.

    Overriding ``get_db_session`` stops the request ever reaching an engine, so
    these tests need no container running and cannot be affected by whatever is
    in the developer's local database.
    """
    monkeypatch.setattr(
        observation_repository, "latest_reading_per_station", lambda *a, **k: latest_rows()
    )
    monkeypatch.setattr(
        observation_repository, "readings_in_window", lambda *a, **k: reading_rows(hours=72)
    )
    monkeypatch.setattr(observation_repository, "weather_in_window", lambda *a, **k: wind_hours())
    monkeypatch.setattr(observation_repository, "fire_detections_in_window", lambda *a, **k: [])
    monkeypatch.setattr(station_repository, "list_sources_with_coordinates", lambda *a, **k: [])

    def _no_database() -> Iterator[Any]:
        yield object()

    app.dependency_overrides[get_db_session] = _no_database
    return app


@pytest.fixture
def api(stubbed_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(stubbed_app) as client:
        yield client


class TestStations:
    def test_returns_every_station_worst_first(self, api: TestClient) -> None:
        response = api.get("/v1/stations")

        assert response.status_code == 200
        body = response.json()
        assert body["station_count"] == len(body["readings"])
        aqis = [reading["aqi"] for reading in body["readings"]]
        assert aqis == sorted(aqis, reverse=True)

    def test_every_reading_carries_its_band_and_position(self, api: TestClient) -> None:
        reading = api.get("/v1/stations").json()["readings"][0]

        assert reading["category"]
        assert reading["unit"]
        # GeoJSON order is (lon, lat) and Delhi sits near 77E, 28N. A transposed
        # payload would put latitude at 77, which is off the planet's populated
        # range for this network and is the classic failure this asserts against.
        assert 68.0 < reading["position"]["longitude"] < 98.0
        assert 6.0 < reading["position"]["latitude"] < 38.0

    def test_rejects_an_unknown_pollutant(self, api: TestClient) -> None:
        response = api.get("/v1/stations", params={"pollutant": "radon"})
        assert response.status_code == 422


class TestHotspots:
    def test_returns_the_planted_hotspot_with_its_excess(self, api: TestClient) -> None:
        body = api.get("/v1/hotspots", params={"window_hours": 72}).json()

        assert body["hotspot_count"] == 1
        hotspot = body["hotspots"][0]
        # Observed, expected and excess must all be present. Publishing the
        # concentration alone would turn a contextual detector back into a
        # threshold alarm at the API boundary.
        assert hotspot["peak_observed"] > hotspot["peak_expected"]
        assert hotspot["peak_excess"] == pytest.approx(
            hotspot["peak_observed"] - hotspot["peak_expected"]
        )
        assert hotspot["peak_z"] > 3.0

    def test_reports_whether_the_trajectory_could_be_traced(self, api: TestClient) -> None:
        hotspot = api.get("/v1/hotspots", params={"window_hours": 72}).json()["hotspots"][0]

        # Distinguishes "nothing explains this" from "we could not look". A
        # consumer that cannot tell them apart would read a calm night as an
        # all-clear.
        assert hotspot["trajectory_unavailable"] is False

    def test_an_empty_registry_yields_no_attributions(self, api: TestClient) -> None:
        hotspot = api.get("/v1/hotspots", params={"window_hours": 72}).json()["hotspots"][0]

        # Meaningful emptiness: nothing registered explains the excess, which
        # points at a source not in the registry.
        assert hotspot["attributions"] == []

    @pytest.mark.parametrize("window", [0, 721])
    def test_rejects_a_window_outside_the_supported_range(
        self, api: TestClient, window: int
    ) -> None:
        assert api.get("/v1/hotspots", params={"window_hours": window}).status_code == 422


class TestCorridorForecast:
    def test_forecasts_along_a_supported_route(self, api: TestClient) -> None:
        body = api.get(
            "/v1/forecast/corridor",
            params={"points": "77.185,28.590;77.220,28.615", "horizon_hours": 24},
        ).json()

        assert body["point_count"] > 0
        assert body["method"]
        for point in body["points"]:
            # Uncertainty is a required field precisely so a client has to
            # decide to ignore it rather than never seeing it.
            assert point["uncertainty"] > 0
            assert point["upper_bound"] == pytest.approx(point["value"] + point["uncertainty"])
            assert point["category"]

    def test_reports_how_much_of_the_route_is_covered(self, api: TestClient) -> None:
        # The points alone cannot express this. A route whose western stretch
        # returns nothing looks identical to a shorter route, and a consumer
        # that cannot tell them apart reads unmonitored ground as clean.
        body = api.get(
            "/v1/forecast/corridor",
            params={"points": "77.185,28.590;77.220,28.615", "horizon_hours": 24},
        ).json()

        assert body["corridor_length_km"] > 0
        assert body["covered_length_km"] <= body["corridor_length_km"]

    def test_an_unsupported_route_still_reports_its_length(self, api: TestClient) -> None:
        body = api.get(
            "/v1/forecast/corridor",
            params={"points": "72.80,19.00;72.85,19.05"},
        ).json()

        assert body["point_count"] == 0
        assert body["covered_length_km"] == 0
        # The route exists; nothing supports it. Those are different facts.
        assert body["corridor_length_km"] > 0

    def test_a_route_no_station_supports_returns_no_points(self, api: TestClient) -> None:
        body = api.get(
            "/v1/forecast/corridor",
            params={"points": "72.80,19.00;72.85,19.05"},
        ).json()

        # Unknown, not clean. An interpolation from nothing would be worse than
        # an empty answer.
        assert body["point_count"] == 0

    @pytest.mark.parametrize(
        "points",
        [
            "77.2,28.6",  # one vertex
            "77.2",  # not a pair
            "east,north",  # not numbers
            "277.2,28.6;77.3,28.7",  # longitude off the globe
        ],
    )
    def test_rejects_a_malformed_corridor(self, api: TestClient, points: str) -> None:
        response = api.get("/v1/forecast/corridor", params={"points": points})

        # 422 rather than 400: the request is well formed but describes a
        # corridor that cannot exist, which is what unprocessable means.
        assert response.status_code == 422
        body = response.json()
        assert body["error"]["code"] in {"validation_error", "invalid_geometry"}
        assert body["error"]["message"]

    def test_an_error_carries_a_correlation_id(self, api: TestClient) -> None:
        response = api.get("/v1/forecast/corridor", params={"points": "nope"})

        # Every failure has to be traceable back to its log lines, or an
        # operator cannot investigate a report of a bad answer.
        assert response.headers.get("X-Request-ID")

    def test_rejects_a_horizon_beyond_what_was_validated(self, api: TestClient) -> None:
        response = api.get(
            "/v1/forecast/corridor",
            params={"points": "77.185,28.590;77.220,28.615", "horizon_hours": 999},
        )
        assert response.status_code == 422


def test_the_reference_hour_is_fixed() -> None:
    """Guard the shared fixture clock.

    The route tests reuse the service tests' synthetic network. If that clock
    ever became ``datetime.now`` these tests would pass or fail depending on the
    hour they ran.
    """
    assert NOW.tzinfo is not None
