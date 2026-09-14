"""Tests for classifying OpenAQ locations, and for how much wind history is kept.

The regression these guard: every location was once stored as a reference
monitor, which put five AirGradient units into detection and validation as if
they were regulatory analysers.
"""

from __future__ import annotations

from contextlib import nullcontext

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.constants import BACKFILL_DAYS, HOURS_PER_DAY, OPENMETEO_BASE_URL
from app.core.enums import StationTier
from app.external.openaq_client import OpenAQLocation
from app.repositories import observation_repository
from app.repositories.observation_repository import WeatherRow
from app.services import ingestion_service
from app.services.ingestion_service import IngestionService, station_tier


def location(*, is_monitor: bool, parameters: list[tuple[str, str]]) -> OpenAQLocation:
    return OpenAQLocation.model_validate(
        {
            "id": 1,
            "name": "Test site",
            "coordinates": {"latitude": 28.6, "longitude": 77.2},
            "isMonitor": is_monitor,
            "sensors": [
                {"id": index, "name": name, "parameter": {"id": index, "name": name, "units": unit}}
                for index, (name, unit) in enumerate(parameters)
            ],
        }
    )


AIRGRADIENT = [("pm1", "µg/m³"), ("pm25", "µg/m³"), ("relativehumidity", "%"), ("um003", "p/cm³")]
ANALYSER_SITE = [("pm25", "µg/m³"), ("pm10", "µg/m³"), ("no2", "µg/m³"), ("so2", "µg/m³")]


def test_a_flagged_monitor_is_reference() -> None:
    assert (
        station_tier(location(is_monitor=True, parameters=ANALYSER_SITE)) is StationTier.REFERENCE
    )


def test_an_optical_particle_sensor_is_low_cost() -> None:
    assert station_tier(location(is_monitor=False, parameters=AIRGRADIENT)) is StationTier.LOW_COST


def test_an_unflagged_site_that_measures_gases_is_still_reference() -> None:
    # Several DPCC and UPPCB analyser sites were added to OpenAQ with the monitor
    # flag unset. An optical sensor cannot measure NO2 or SO2, so they are not
    # low-cost, whatever the flag says.
    assert (
        station_tier(location(is_monitor=False, parameters=ANALYSER_SITE)) is StationTier.REFERENCE
    )


def test_an_unflagged_site_reporting_only_particulates_is_low_cost() -> None:
    particulates = [("pm25", "µg/m³"), ("pm10", "µg/m³")]
    assert station_tier(location(is_monitor=False, parameters=particulates)) is StationTier.LOW_COST


@respx.mock
async def test_wind_is_fetched_for_the_whole_window_detection_looks_back_over(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    # With two past days of wind, a hotspot found in the backfilled fortnight had
    # nothing to trace a trajectory through, and named no candidate source.
    route = respx.get(f"{OPENMETEO_BASE_URL}/forecast").mock(
        return_value=httpx.Response(200, json=weather_body())
    )
    stored: list[int] = []

    def upsert(_session: object, rows: list[WeatherRow]) -> int:
        stored.append(len(rows))
        return len(rows)

    monkeypatch.setattr(ingestion_service, "session_scope", nullcontext)
    monkeypatch.setattr(observation_repository, "upsert_weather", upsert)

    result = await IngestionService(settings)._ingest_weather((77.2, 28.6))

    assert result.succeeded
    assert stored == [1]
    past_days = int(route.calls.last.request.url.params["past_days"])
    assert past_days * HOURS_PER_DAY >= BACKFILL_DAYS * HOURS_PER_DAY


def weather_body() -> dict[str, object]:
    return {
        "hourly": {
            "time": ["2026-09-01T00:00"],
            "temperature_2m": [30.0],
            "relative_humidity_2m": [60.0],
            "wind_speed_10m": [2.0],
            "wind_direction_10m": [270.0],
            "boundary_layer_height": [800.0],
            "precipitation": [0.0],
        }
    }
