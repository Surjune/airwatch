"""Tests for the OpenAQ client.

Fixtures are trimmed copies of real API responses, so a shape change upstream
shows up here rather than in production. Tests never make real network calls.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from app.core.constants import OPENAQ_BASE_URL, OPENAQ_MAX_RADIUS_M
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.external.openaq_client import OpenAQClient, OpenAQLocation

DELHI = (77.2090, 28.6139)

#: A live station. Note `datetimeLast` is an object, and CO is reported in
#: micrograms even though the CPCB CO index is in milligrams.
ACTIVE_LOCATION: dict[str, Any] = {
    "id": 235,
    "name": "Anand Vihar, New Delhi - DPCC",
    "timezone": "Asia/Kolkata",
    "provider": {"id": 168, "name": "CPCB"},
    "isMobile": False,
    "isMonitor": True,
    "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
    "sensors": [
        {
            "id": 34,
            "name": "pm25 ug/m3",
            "parameter": {"id": 2, "name": "pm25", "units": "µg/m³", "displayName": "PM2.5"},
        },
        {
            "id": 33,
            "name": "co ug/m3",
            "parameter": {"id": 4, "name": "co", "units": "µg/m³", "displayName": "CO mass"},
        },
        {
            # Black carbon is outside the CPCB AQI set and must be skipped.
            "id": 99,
            "name": "bc ug/m3",
            "parameter": {"id": 11, "name": "bc", "units": "µg/m³", "displayName": "BC"},
        },
    ],
    "datetimeFirst": {"utc": "2016-11-02T17:30:00Z", "local": "2016-11-02T23:00:00+05:30"},
    "datetimeLast": {"utc": "2026-09-05T18:15:00Z", "local": "2026-09-05T23:45:00+05:30"},
}

#: A station that stopped reporting in 2018 but is still returned by the API.
DORMANT_LOCATION: dict[str, Any] = {
    "id": 103,
    "name": "Income Tax Office, Delhi - CPCB",
    "coordinates": {"latitude": 28.6286, "longitude": 77.2411},
    "sensors": [],
    "datetimeLast": {"utc": "2018-02-22T03:45:00Z", "local": "2018-02-22T09:15:00+05:30"},
}

#: A station that has never reported at all.
NEVER_REPORTED_LOCATION: dict[str, Any] = {
    "id": 16,
    "name": "Civil Lines",
    "coordinates": {"latitude": 28.6787, "longitude": 77.2262},
    "sensors": [],
    "datetimeLast": None,
}

#: The /latest endpoint gives a value and a sensorsId but never the parameter.
LATEST_RESULTS: list[dict[str, Any]] = [
    {
        "datetime": {"utc": "2026-09-05T18:15:00Z", "local": "2026-09-05T23:45:00+05:30"},
        "value": 118.4,
        "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
        "sensorsId": 34,
        "locationsId": 235,
    },
    {
        "datetime": {"utc": "2026-09-05T18:15:00Z", "local": "2026-09-05T23:45:00+05:30"},
        "value": 1200.0,
        "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
        "sensorsId": 33,
        "locationsId": 235,
    },
    {
        # A sensor absent from the location record: cannot be attributed.
        "datetime": {"utc": "2026-09-05T18:15:00Z", "local": "2026-09-05T23:45:00+05:30"},
        "value": 7.0,
        "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
        "sensorsId": 999_999,
        "locationsId": 235,
    },
]

NOW = datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


def envelope(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "meta": {"name": "openaq-api", "page": 1, "limit": 100, "found": len(results)},
        "results": results,
    }


def build_client() -> OpenAQClient:
    return OpenAQClient("test-key", backoff_base_seconds=0.0)


class TestListLocations:
    @respx.mock
    async def test_parses_a_real_location_payload(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json=envelope([ACTIVE_LOCATION]))
        )

        async with build_client() as client:
            locations = await client.list_locations(DELHI)

        assert len(locations) == 1
        assert locations[0].name == "Anand Vihar, New Delhi - DPCC"
        assert locations[0].provider is not None
        assert locations[0].provider.name == "CPCB"

    @respx.mock
    async def test_sends_coordinates_as_latitude_longitude(self) -> None:
        # OpenAQ wants "lat,lon" -- the reverse of AirWatch's (lon, lat). Getting
        # this backwards would silently query a point in the Arabian Sea.
        route = respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json=envelope([]))
        )

        async with build_client() as client:
            await client.list_locations(DELHI)

        assert route.calls.last.request.url.params["coordinates"] == "28.6139,77.209"

    @respx.mock
    async def test_sends_the_api_key(self) -> None:
        route = respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json=envelope([]))
        )

        async with build_client() as client:
            await client.list_locations(DELHI)

        assert route.calls.last.request.headers["X-API-Key"] == "test-key"

    @respx.mock
    async def test_caps_the_radius_at_the_upstream_maximum(self) -> None:
        route = respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json=envelope([]))
        )

        async with build_client() as client:
            await client.list_locations(DELHI, radius_m=999_999)

        assert route.calls.last.request.url.params["radius"] == str(OPENAQ_MAX_RADIUS_M)

    @respx.mock
    async def test_a_missing_results_array_is_an_error(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json={"meta": {}})
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="results"):
                await client.list_locations(DELHI)

    @respx.mock
    async def test_a_malformed_record_is_an_error_not_a_silent_skip(self) -> None:
        # Dropping unparseable records would understate pollution, so schema
        # drift has to be loud.
        respx.get(f"{OPENAQ_BASE_URL}/locations").mock(
            return_value=httpx.Response(200, json=envelope([{"id": 1}]))
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="OpenAQLocation"):
                await client.list_locations(DELHI)


class TestCoordinateOrder:
    def test_converts_openaq_lat_lon_to_airwatch_lon_lat(self) -> None:
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)
        lon, lat = location.coordinates.to_lon_lat()
        assert lon == pytest.approx(77.3161)
        assert lat == pytest.approx(28.6469)


class TestActivityFiltering:
    def test_keeps_a_recently_reporting_station(self) -> None:
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)
        assert location.is_active(as_of=NOW, stale_after_days=7) is True

    def test_drops_a_station_last_seen_in_2018(self) -> None:
        location = OpenAQLocation.model_validate(DORMANT_LOCATION)
        assert location.is_active(as_of=NOW, stale_after_days=7) is False

    def test_drops_a_station_that_never_reported(self) -> None:
        location = OpenAQLocation.model_validate(NEVER_REPORTED_LOCATION)
        assert location.last_reading_at is None
        assert location.is_active(as_of=NOW, stale_after_days=7) is False

    def test_filter_keeps_only_the_live_station(self) -> None:
        # The real Delhi response mixes live and decade-dead stations in one
        # list; ingesting both would dilute the fused surface with 2018 air.
        locations = [
            OpenAQLocation.model_validate(record)
            for record in (ACTIVE_LOCATION, DORMANT_LOCATION, NEVER_REPORTED_LOCATION)
        ]

        active = build_client().active_locations(locations, as_of=NOW, stale_after_days=7)

        assert [location.id for location in active] == [235]


class TestSensorPollutantJoin:
    def test_maps_sensor_ids_to_pollutants(self) -> None:
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)
        mapping = location.pollutant_by_sensor_id()
        assert mapping[34] == (Pollutant.PM25, "ug/m3")
        assert mapping[33] == (Pollutant.CO, "ug/m3")

    def test_skips_a_parameter_outside_the_cpcb_set(self) -> None:
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)
        # Black carbon is a real measurement but not part of the CPCB AQI.
        assert 99 not in location.pollutant_by_sensor_id()

    def test_normalises_the_unicode_unit_spelling(self) -> None:
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)
        _, unit = location.pollutant_by_sensor_id()[34]
        # core/aqi.py converts on "ug/m3", not on OpenAQ's "µg/m³".
        assert unit == "ug/m3"


class TestLatestReadings:
    @respx.mock
    async def test_joins_each_reading_to_its_pollutant(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location)

        by_pollutant = {reading.pollutant: reading for reading in readings}
        assert by_pollutant[Pollutant.PM25].value == pytest.approx(118.4)
        assert by_pollutant[Pollutant.CO].value == pytest.approx(1200.0)

    @respx.mock
    async def test_skips_a_sensor_it_cannot_attribute(self) -> None:
        # Guessing the pollutant for an unknown sensor would record PM2.5 as NO2,
        # which is corruption no downstream check could detect.
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location)

        assert len(readings) == 2
        assert all(reading.sensor_id != 999_999 for reading in readings)

    @respx.mock
    async def test_carries_the_unit_through_for_later_conversion(self) -> None:
        # CO arrives in ug/m3; the AQI table needs mg/m3. The client records the
        # unit rather than converting, so the conversion stays in core/aqi.py.
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location)

        co = next(reading for reading in readings if reading.pollutant is Pollutant.CO)
        assert co.unit == "ug/m3"

    @respx.mock
    async def test_records_the_utc_timestamp(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location)

        assert readings[0].observed_at == datetime(2026, 9, 5, 18, 15, tzinfo=UTC)

    @respx.mock
    async def test_stores_coordinates_in_lon_lat_order(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location)

        lon, lat = readings[0].coordinates
        assert lon == pytest.approx(77.3161)
        assert lat == pytest.approx(28.6469)

    @respx.mock
    async def test_an_empty_latest_response_yields_no_readings(self) -> None:
        # A dormant station genuinely has nothing; that is not a failure.
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope([]))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            assert await client.latest_readings(location) == []


class TestStaleReadingFilter:
    """A live station can carry a decommissioned sensor whose final value is years old."""

    @respx.mock
    async def test_drops_a_2018_reading_from_a_live_station(self) -> None:
        # Exactly what R K Puram returns: a 2026 PM2.5 of 37 beside a 2018
        # PM2.5 of 201, both the "latest" value for their own sensor.
        results = [
            {
                "datetime": {"utc": "2026-09-05T18:15:00Z"},
                "value": 37.0,
                "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
                "sensorsId": 34,
                "locationsId": 235,
            },
            {
                "datetime": {"utc": "2018-02-21T21:15:00Z"},
                "value": 201.0,
                "coordinates": {"latitude": 28.6469, "longitude": 77.3161},
                "sensorsId": 33,
                "locationsId": 235,
            },
        ]
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(results))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location, as_of=NOW, stale_after_days=7)

        assert len(readings) == 1
        assert readings[0].value == pytest.approx(37.0)
        assert readings[0].pollutant is Pollutant.PM25

    @respx.mock
    async def test_keeps_everything_when_all_readings_are_recent(self) -> None:
        respx.get(f"{OPENAQ_BASE_URL}/locations/235/latest").mock(
            return_value=httpx.Response(200, json=envelope(LATEST_RESULTS))
        )
        location = OpenAQLocation.model_validate(ACTIVE_LOCATION)

        async with build_client() as client:
            readings = await client.latest_readings(location, as_of=NOW, stale_after_days=7)

        assert len(readings) == 2
