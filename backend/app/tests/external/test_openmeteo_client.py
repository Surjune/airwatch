"""Tests for the Open-Meteo client.

The fixture mirrors a real response: columnar arrays sharing an index with
``hourly.time``, wind as speed plus meteorological direction.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from app.core.constants import OPENMETEO_BASE_URL, OPENMETEO_MAX_FORECAST_DAYS
from app.core.exceptions import UpstreamResponseError
from app.external.openmeteo_client import OpenMeteoClient

DELHI = (77.2090, 28.6139)
FORECAST_URL = f"{OPENMETEO_BASE_URL}/forecast"


def response_body(**overrides: Any) -> dict[str, Any]:
    """A real-shaped response. Wind is a westerly, so u is positive."""
    hourly: dict[str, Any] = {
        "time": ["2026-09-08T00:00", "2026-09-08T01:00", "2026-09-08T02:00"],
        "temperature_2m": [25.8, 25.5, 26.2],
        "relative_humidity_2m": [81, 81, 84],
        "wind_speed_10m": [4.0, 6.6, 9.0],
        # 270 is a westerly: air moving east, so wind_u must be positive.
        "wind_direction_10m": [270, 180, 90],
        "boundary_layer_height": [85.0, 65.0, 175.0],
        "precipitation": [0.0, 0.0, 1.2],
    }
    hourly.update(overrides)
    return {
        "latitude": 28.576448,
        "longitude": 77.18678,
        "timezone": "GMT",
        "elevation": 214.0,
        "hourly_units": {"temperature_2m": "°C", "wind_speed_10m": "m/s"},
        "hourly": hourly,
    }


def build_client() -> OpenMeteoClient:
    return OpenMeteoClient(backoff_base_seconds=0.0)


class TestForecastParsing:
    @respx.mock
    async def test_reassembles_columnar_arrays_into_rows(self) -> None:
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert len(hours) == 3
        assert hours[0].temperature_c == pytest.approx(25.8)
        assert hours[2].temperature_c == pytest.approx(26.2)

    @respx.mock
    async def test_labels_timestamps_as_utc(self) -> None:
        # Open-Meteo returns no timezone suffix; the request pins timezone=UTC,
        # so a naive value must be labelled rather than left to the local zone.
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert hours[0].observed_at == datetime(2026, 9, 8, 0, 0, tzinfo=UTC)
        assert hours[0].observed_at.tzinfo is UTC

    @respx.mock
    async def test_carries_boundary_layer_height(self) -> None:
        # The variable that explains why the same emission rate produces a far
        # worse concentration on a still winter night.
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert hours[0].pbl_height_m == pytest.approx(85.0)

    @respx.mock
    async def test_carries_precipitation(self) -> None:
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert hours[2].precipitation_mm == pytest.approx(1.2)


class TestWindConversion:
    @respx.mock
    async def test_converts_speed_and_direction_to_components(self) -> None:
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        # 270 degrees is a westerly: air travels east, so u is positive.
        assert hours[0].wind_u == pytest.approx(4.0, abs=1e-9)
        assert hours[0].wind_v == pytest.approx(0.0, abs=1e-9)

        # 180 is a southerly: air travels north, so v is positive.
        assert hours[1].wind_v == pytest.approx(6.6, abs=1e-9)
        assert hours[1].wind_u == pytest.approx(0.0, abs=1e-9)

        # 90 is an easterly: air travels west, so u is negative.
        assert hours[2].wind_u == pytest.approx(-9.0, abs=1e-9)

    @respx.mock
    async def test_requests_metres_per_second(self) -> None:
        # Open-Meteo defaults to km/h. A silent 3.6x error in the wind field
        # would misplace every back-trajectory built on it.
        route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            await client.forecast(DELHI)

        assert route.calls.last.request.url.params["wind_speed_unit"] == "ms"

    @respx.mock
    async def test_requests_the_boundary_layer_variable(self) -> None:
        route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            await client.forecast(DELHI)

        assert "boundary_layer_height" in route.calls.last.request.url.params["hourly"]


class TestRequestParameters:
    @respx.mock
    async def test_sends_latitude_and_longitude_separately(self) -> None:
        route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            await client.forecast(DELHI)

        params = route.calls.last.request.url.params
        assert float(params["latitude"]) == pytest.approx(28.6139)
        assert float(params["longitude"]) == pytest.approx(77.2090)

    @respx.mock
    async def test_caps_the_forecast_horizon(self) -> None:
        route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            await client.forecast(DELHI, forecast_days=99)

        assert route.calls.last.request.url.params["forecast_days"] == str(
            OPENMETEO_MAX_FORECAST_DAYS
        )

    @respx.mock
    async def test_can_request_past_hours_for_a_back_trajectory(self) -> None:
        # Tracing a hotspot backwards needs the wind field for hours that have
        # already happened, not only the forecast.
        route = respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=response_body()))

        async with build_client() as client:
            await client.forecast(DELHI, past_days=2)

        assert route.calls.last.request.url.params["past_days"] == "2"


class TestMalformedResponses:
    @respx.mock
    async def test_a_misaligned_array_is_rejected_not_padded(self) -> None:
        # This is the dangerous one. A short array padded to length would shift
        # every later hour's wind onto the wrong timestamp, and a trajectory
        # built on shifted wind names a source confidently and wrongly.
        body = response_body(wind_speed_10m=[4.0, 6.6])
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="misaligned"):
                await client.forecast(DELHI)

    @respx.mock
    async def test_a_missing_variable_is_an_error(self) -> None:
        body = response_body()
        del body["hourly"]["boundary_layer_height"]
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="boundary_layer_height"):
                await client.forecast(DELHI)

    @respx.mock
    async def test_a_missing_hourly_block_is_an_error(self) -> None:
        respx.get(FORECAST_URL).mock(
            return_value=httpx.Response(200, json={"latitude": 28.6, "longitude": 77.2})
        )

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="hourly"):
                await client.forecast(DELHI)

    @respx.mock
    async def test_a_non_numeric_value_is_an_error_not_a_coercion(self) -> None:
        body = response_body(temperature_2m=["warm", 25.5, 26.2])
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            with pytest.raises(UpstreamResponseError, match="expected a number"):
                await client.forecast(DELHI)


class TestMissingValues:
    @respx.mock
    async def test_drops_an_hour_with_no_wind_rather_than_calling_it_calm(self) -> None:
        # Defaulting a null wind to zero asserts calm air, which is a physical
        # claim the data does not make and which would stall a trajectory.
        body = response_body(wind_speed_10m=[4.0, None, 9.0])
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert len(hours) == 2
        assert [hour.observed_at.hour for hour in hours] == [0, 2]

    @respx.mock
    async def test_a_null_boundary_layer_is_kept_as_unknown(self) -> None:
        # Unlike wind, a missing PBL does not invalidate the hour; it is recorded
        # as unknown so downstream code can widen its uncertainty instead.
        body = response_body(boundary_layer_height=[None, 65.0, 175.0])
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert len(hours) == 3
        assert hours[0].pbl_height_m is None

    @respx.mock
    async def test_a_null_precipitation_becomes_zero(self) -> None:
        body = response_body(precipitation=[None, 0.0, 1.2])
        respx.get(FORECAST_URL).mock(return_value=httpx.Response(200, json=body))

        async with build_client() as client:
            hours = await client.forecast(DELHI)

        assert hours[0].precipitation_mm == pytest.approx(0.0)
