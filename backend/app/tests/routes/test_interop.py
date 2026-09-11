"""Tests for the interoperability endpoints.

The contract these protect is a contract with software nobody here controls. A
partner city's ingest is written against the payload shape once and then left
alone, so a field that quietly changes name or a coordinate pair that quietly
transposes does not fail loudly -- it fails as a map of stations in the sea,
months later, in someone else's system.

So these assert on the wire format itself rather than on internal types.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.repositories import observation_repository, station_repository
from app.repositories.session import get_db_session
from app.schemas.interop import CRS_URI
from app.tests.services.test_analysis_service import latest_rows, reading_rows, wind_hours


@pytest.fixture
def api(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """A client whose repositories are stubbed, so no database is needed."""
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
    with TestClient(app) as client:
        yield client


class TestCapabilities:
    def test_describes_the_node_and_its_endpoints(self, api: TestClient) -> None:
        body = api.get("/v1/interop/capabilities").json()

        assert body["node_id"]
        assert body["h3_resolution"] == 8
        assert {endpoint["path"] for endpoint in body["endpoints"]} >= {
            "/v1/interop/observations",
            "/v1/interop/hotspots",
            "/v1/interop/models",
        }

    def test_states_the_coordinate_reference_system(self, api: TestClient) -> None:
        # A silently assumed CRS is the classic way spatial exchange goes wrong.
        assert api.get("/v1/interop/capabilities").json()["crs"] == CRS_URI

    def test_states_a_licence(self, api: TestClient) -> None:
        # A receiving agency cannot lawfully republish data whose terms are unstated.
        assert api.get("/v1/interop/capabilities").json()["licence"]


class TestObservations:
    def test_is_a_valid_geojson_feature_collection(self, api: TestClient) -> None:
        body = api.get("/v1/interop/observations", params={"window_hours": 720}).json()

        assert body["type"] == "FeatureCollection"
        assert body["features"]
        for feature in body["features"][:5]:
            assert feature["type"] == "Feature"
            assert feature["geometry"]["type"] == "Point"
            assert len(feature["geometry"]["coordinates"]) == 2

    def test_coordinates_are_longitude_first(self, api: TestClient) -> None:
        # GeoJSON is (lon, lat). Delhi is near 77E, 28N, so a transposed pair is
        # unmistakable -- and would otherwise reach a partner as a valid-looking
        # point in the Indian Ocean.
        geometry = api.get("/v1/interop/observations", params={"window_hours": 720}).json()[
            "features"
        ][0]["geometry"]
        longitude, latitude = geometry["coordinates"]

        assert 68.0 < longitude < 98.0
        assert 6.0 < latitude < 38.0

    def test_uses_sensorthings_property_names(self, api: TestClient) -> None:
        properties = api.get("/v1/interop/observations", params={"window_hours": 720}).json()[
            "features"
        ][0]["properties"]

        for key in ("@iot.id", "result", "resultTime", "unitOfMeasurement", "observedProperty"):
            assert key in properties

    def test_every_feature_carries_its_provenance(self, api: TestClient) -> None:
        # Anonymous data cannot be audited, and data that cannot be audited does
        # not get used in a decision anyone has to defend.
        properties = api.get("/v1/interop/observations", params={"window_hours": 720}).json()[
            "features"
        ][0]["properties"]

        assert properties["node_id"]
        assert properties["resultQuality"]
        assert properties["@iot.id"].startswith(properties["node_id"])

    def test_declares_the_unit_rather_than_assuming_it(self, api: TestClient) -> None:
        unit = api.get("/v1/interop/observations", params={"window_hours": 720}).json()["features"][
            0
        ]["properties"]["unitOfMeasurement"]

        assert unit["symbol"] == "ug/m3"
        assert unit["definition"].startswith("http")

    def test_metadata_reports_the_terms_and_the_count(self, api: TestClient) -> None:
        metadata = api.get("/v1/interop/observations", params={"window_hours": 720}).json()[
            "metadata"
        ]

        assert metadata["licence"]
        assert metadata["disclaimer"]
        assert metadata["h3_resolution"] == 8
        assert metadata["returned"] >= 1
        assert metadata["truncated"] is False

    def test_rejects_a_window_beyond_what_is_offered(self, api: TestClient) -> None:
        assert (
            api.get("/v1/interop/observations", params={"window_hours": 10_000}).status_code == 422
        )


class TestHotspots:
    def test_publishes_expected_alongside_observed(self, api: TestClient) -> None:
        # A neighbouring state receiving only the concentration cannot tell a
        # local source from a regional episode it is already living through.
        body = api.get("/v1/interop/hotspots", params={"window_hours": 720}).json()

        assert body["type"] == "FeatureCollection"
        properties = body["features"][0]["properties"]
        assert properties["peak_observed"] > properties["peak_expected"]
        assert properties["peak_excess"] == pytest.approx(
            properties["peak_observed"] - properties["peak_expected"]
        )

    def test_states_how_detection_was_done(self, api: TestClient) -> None:
        properties = api.get("/v1/interop/hotspots", params={"window_hours": 720}).json()[
            "features"
        ][0]["properties"]

        assert "inverse-distance" in properties["detection_method"]

    def test_identifiers_are_unique_across_the_federation(self, api: TestClient) -> None:
        features = api.get("/v1/interop/hotspots", params={"window_hours": 720}).json()["features"]

        identifiers = [feature["properties"]["@iot.id"] for feature in features]
        assert len(identifiers) == len(set(identifiers))


class TestModelCatalogue:
    def test_publishes_a_card_per_estimator(self, api: TestClient) -> None:
        body = api.get("/v1/interop/models").json()

        assert body["model_count"] == len(body["models"])
        tasks = [model["task"] for model in body["models"]]
        assert any("no monitor" in task for task in tasks)
        assert any("Forecast" in task for task in tasks)

    def test_every_score_states_how_it_was_validated(self, api: TestClient) -> None:
        for model in api.get("/v1/interop/models").json()["models"]:
            for score in model["performance"]:
                assert score["validation"]

    def test_a_score_with_a_baseline_reports_both_numbers(self, api: TestClient) -> None:
        # And one without a comparison leaves both null rather than naming
        # itself as its own baseline, which would read as a tie against a rival.
        for model in api.get("/v1/interop/models").json()["models"]:
            for score in model["performance"]:
                assert (score["baseline"] is None) == (score["baseline_value"] is None)

    def test_withholding_weights_is_explained(self, api: TestClient) -> None:
        # Publishing a weight vector this node measured to be worse than its own
        # baseline would invite a data-poor city to adopt something harmful.
        for model in api.get("/v1/interop/models").json()["models"]:
            if model["weights"] is None:
                assert model["weights_withheld_because"]

    def test_every_card_states_its_limitations(self, api: TestClient) -> None:
        for model in api.get("/v1/interop/models").json()["models"]:
            assert model["limitations"]
            assert model["licence"]

    def test_the_forecast_card_publishes_the_shared_schema(self, api: TestClient) -> None:
        # Seventeen features, not the model's full set: a feature one node can
        # compute and another cannot does not average.
        forecast = next(
            model
            for model in api.get("/v1/interop/models").json()["models"]
            if "Forecast" in model["task"]
        )

        assert len(forecast["feature_schema"]) == 17
        assert not any(name.startswith("target_wind") for name in forecast["feature_schema"])

    def test_generated_at_is_timezone_aware(self, api: TestClient) -> None:
        generated = api.get("/v1/interop/models").json()["generated_at"]

        assert datetime.fromisoformat(generated).tzinfo is not None
        assert datetime.fromisoformat(generated) <= datetime.now(UTC)
