"""Tests for the CAMS regional model client (Open-Meteo air quality)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.constants import CAMS_BASE_URL, CAMS_VARIABLES
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.external.cams_client import CamsClient

URL = f"{CAMS_BASE_URL}/air-quality"
COIMBATORE = (76.9558, 11.0168)
TIMES = ["2026-09-14T00:00", "2026-09-14T01:00"]


def body(**overrides: object) -> dict[str, object]:
    hourly: dict[str, object] = {"time": TIMES}
    for variable in CAMS_VARIABLES.values():
        hourly[variable] = [10.0, 12.5]
    hourly.update(overrides)
    return {"latitude": 11.0, "longitude": 77.0, "hourly": hourly}


@respx.mock
async def test_rebuilds_one_row_per_pollutant_hour_in_utc() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=body()))

    async with CamsClient() as client:
        series = await client.hourly(COIMBATORE, past_days=14, forecast_days=4)

    assert series.grid_point == (77.0, 11.0)
    assert len(series.hours) == len(CAMS_VARIABLES) * len(TIMES)
    pm25 = [hour for hour in series.hours if hour.pollutant is Pollutant.PM25]
    assert pm25[1].value == 12.5
    assert pm25[0].observed_at == datetime(2026, 9, 14, 0, 0, tzinfo=UTC)


@respx.mock
async def test_asks_for_every_pollutant_with_history_and_forecast_in_utc() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=body()))

    async with CamsClient() as client:
        await client.hourly(COIMBATORE, past_days=14, forecast_days=4)

    params = route.calls.last.request.url.params
    assert set(params["hourly"].split(",")) == set(CAMS_VARIABLES.values())
    assert params["past_days"] == "14"
    assert params["forecast_days"] == "4"
    assert params["timezone"] == "UTC"
    # Separate parameters, so there is no (lat, lon) ordering to get wrong.
    assert float(params["latitude"]) == pytest.approx(11.0168)


@respx.mock
async def test_a_null_hour_is_dropped_not_read_as_clean_air() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=body(pm2_5=[None, 12.5])))

    async with CamsClient() as client:
        series = await client.hourly(COIMBATORE, past_days=1, forecast_days=1)

    assert [hour.value for hour in series.hours if hour.pollutant is Pollutant.PM25] == [12.5]


@pytest.mark.parametrize(
    "payload",
    [
        body(pm10=[10.0]),
        body(ozone=["high", 3.0]),
        {"hourly": {"time": TIMES}},
        {"latitude": 11.0, "longitude": 77.0},
    ],
    ids=["misaligned", "non-numeric", "no-grid-point", "no-hourly"],
)
@respx.mock
async def test_an_unusable_payload_is_a_typed_error(payload: dict[str, object]) -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload))

    async with CamsClient() as client:
        with pytest.raises(UpstreamResponseError):
            await client.hourly(COIMBATORE, past_days=1, forecast_days=1)
