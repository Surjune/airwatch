"""Tests for classifying OpenAQ locations, wind history, and catching up missed hours.

The regression these guard: every location was once stored as a reference
monitor, which put five AirGradient units into detection and validation as if
they were regulatory analysers.
"""

from __future__ import annotations

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.constants import (
    BACKFILL_DAYS,
    HOURS_PER_DAY,
    OPENAQ_BASE_URL,
    OPENAQ_CATCH_UP_GAP_HOURS,
    OPENAQ_CATCH_UP_MAX_DAYS,
    OPENMETEO_BASE_URL,
)
from app.core.enums import Pollutant, StationTier
from app.external.openaq_client import OpenAQClient, OpenAQLocation, OpenAQReading
from app.repositories import observation_repository
from app.repositories.observation_repository import MeasurementRow, WeatherRow
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


#: The newest reading in these tests, on the half hour as Indian stations report,
#: and relative to now so the history window never ages out from under them.
NEWEST = datetime.now(UTC).replace(minute=30, second=0, microsecond=0) - timedelta(hours=1)
STATION_ID = 7


def reading(pollutant: Pollutant, sensor_id: int, observed_at: datetime) -> OpenAQReading:
    return OpenAQReading(
        location_id=1,
        sensor_id=sensor_id,
        pollutant=pollutant,
        value=40.0,
        # Already normalised: the client maps OpenAQ's "µg/m³" before a reading exists.
        unit="ug/m3",
        observed_at=observed_at,
        coordinates=(77.2, 28.6),
    )


def hours_body(starts: list[datetime]) -> dict[str, object]:
    return {
        "meta": {"found": len(starts)},
        "results": [
            {
                "value": 50.0 + index,
                "period": {
                    "datetimeFrom": {"utc": start.isoformat()},
                    "datetimeTo": {"utc": (start + timedelta(hours=1)).isoformat()},
                },
                "coverage": {"percentComplete": 100.0},
            }
            for index, start in enumerate(starts)
        ],
    }


class TestCatchUp:
    """The hours a stalled relay held back are stored once it resumes."""

    @pytest.fixture
    def stored(self, monkeypatch: pytest.MonkeyPatch) -> list[MeasurementRow]:
        rows: list[MeasurementRow] = []

        def upsert(_session: object, batch: list[MeasurementRow]) -> int:
            rows.extend(batch)
            return len(batch)

        def delete(_session: object, station_id: int, pollutant: Pollutant, **window: Any) -> int:
            self.retired.append((station_id, pollutant, window["after"], window["until"]))
            return 2

        self.retired: list[tuple[int, Pollutant, datetime, datetime]] = []
        monkeypatch.setattr(ingestion_service, "session_scope", nullcontext)
        monkeypatch.setattr(observation_repository, "upsert_measurements", upsert)
        monkeypatch.setattr(observation_repository, "delete_superseded", delete)
        return rows

    async def _catch_up(
        self,
        settings: Settings,
        readings: list[OpenAQReading],
        previous: dict[Pollutant, datetime],
    ) -> int:
        site = location(is_monitor=True, parameters=ANALYSER_SITE)
        async with OpenAQClient(
            "test-key", backoff_base_seconds=0.0, min_request_interval_seconds=0.0
        ) as client:
            return await IngestionService(settings)._catch_up(
                client, site, STATION_ID, readings, previous
            )

    @respx.mock
    async def test_stores_the_hours_between_the_last_stored_reading_and_the_newest(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        last = NEWEST - timedelta(hours=5)
        respx.get(f"{OPENAQ_BASE_URL}/sensors/0/hours").mock(
            return_value=httpx.Response(
                200, json=hours_body([last + timedelta(hours=step) for step in range(6)])
            )
        )

        written = await self._catch_up(
            settings, [reading(Pollutant.PM25, 0, NEWEST)], {Pollutant.PM25: last}
        )

        # The four hours in between; neither end is rewritten.
        assert written == 4
        assert [row.observed_at for row in stored] == [
            last + timedelta(hours=step) for step in range(1, 5)
        ]
        assert {row.station_id for row in stored} == {STATION_ID}
        assert {row.pollutant for row in stored} == {Pollutant.PM25}

    @respx.mock
    async def test_an_ordinary_delay_costs_no_request(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        route = respx.get(f"{OPENAQ_BASE_URL}/sensors/0/hours")
        last = NEWEST - timedelta(hours=OPENAQ_CATCH_UP_GAP_HOURS)

        written = await self._catch_up(
            settings, [reading(Pollutant.PM25, 0, NEWEST)], {Pollutant.PM25: last}
        )

        assert written == 0
        assert not route.called

    @respx.mock
    async def test_gases_and_first_readings_are_not_caught_up(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        route = respx.get(url__regex=rf"{OPENAQ_BASE_URL}/sensors/\d+/hours")
        long_ago = NEWEST - timedelta(days=2)

        written = await self._catch_up(
            settings,
            [reading(Pollutant.NO2, 2, NEWEST), reading(Pollutant.PM10, 1, NEWEST)],
            {Pollutant.NO2: long_ago},
        )

        assert written == 0
        assert not route.called

    @respx.mock
    async def test_reaches_back_no_further_than_the_history_views_read(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        route = respx.get(f"{OPENAQ_BASE_URL}/sensors/1/hours").mock(
            return_value=httpx.Response(200, json=hours_body([]))
        )

        await self._catch_up(
            settings,
            [reading(Pollutant.PM10, 1, NEWEST)],
            {Pollutant.PM10: NEWEST - timedelta(days=60)},
        )

        requested_from = route.calls.last.request.url.params["datetime_from"]
        earliest = datetime.now(UTC) - timedelta(days=OPENAQ_CATCH_UP_MAX_DAYS)
        assert requested_from == earliest.date().isoformat()

    @respx.mock
    async def test_a_failed_fill_is_logged_and_the_cycle_goes_on(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/sensors/0/hours").mock(
            return_value=httpx.Response(404, json={"detail": "not found"})
        )

        written = await self._catch_up(
            settings,
            [reading(Pollutant.PM25, 0, NEWEST)],
            {Pollutant.PM25: NEWEST - timedelta(hours=10)},
        )

        assert written == 0
        assert stored == []

    @respx.mock
    async def test_retires_the_backup_feeds_stand_ins_for_the_hours_it_refilled(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        last = NEWEST - timedelta(hours=5)
        respx.get(f"{OPENAQ_BASE_URL}/sensors/0/hours").mock(
            return_value=httpx.Response(
                200, json=hours_body([last + timedelta(hours=step) for step in range(6)])
            )
        )

        await self._catch_up(settings, [reading(Pollutant.PM25, 0, NEWEST)], {Pollutant.PM25: last})

        assert self.retired == [(STATION_ID, Pollutant.PM25, last, NEWEST)]

    @respx.mock
    async def test_keeps_the_stand_ins_where_openaq_has_nothing_for_the_gap(
        self, settings: Settings, stored: list[MeasurementRow]
    ) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/sensors/0/hours").mock(
            return_value=httpx.Response(200, json=hours_body([]))
        )

        await self._catch_up(
            settings,
            [reading(Pollutant.PM25, 0, NEWEST)],
            {Pollutant.PM25: NEWEST - timedelta(hours=10)},
        )

        assert self.retired == []
