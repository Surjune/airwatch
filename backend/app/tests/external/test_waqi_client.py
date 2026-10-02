"""Tests for the World Air Quality Index client."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from app.core.constants import WAQI_BASE_URL
from app.core.exceptions import UpstreamResponseError
from app.external.waqi_client import WaqiClient

TOKEN = "test-waqi-token-0123456789"

ANAND_VIHAR: dict[str, Any] = {
    "aqi": 132,
    "idx": 2553,
    "attributions": [
        {
            "url": "http://dpccairdata.com/",
            "name": "Delhi Pollution Control Commitee (Government of NCT of Delhi)",
        },
        {"url": "https://waqi.info/", "name": "World Air Quality Index Project"},
    ],
    "city": {"geo": [28.647622, 77.315809], "name": "Anand Vihar, Delhi, Delhi, India"},
    "dominentpol": "pm25",
    "iaqi": {"pm25": {"v": 132}, "pm10": {"v": 98}, "no2": {"v": 21.4}, "t": {"v": 31}},
    "time": {"s": "2026-10-02 13:00:00", "tz": "+05:30", "iso": "2026-10-02T13:00:00+05:30"},
}


def ok(data: object) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok", "data": data})


def client() -> WaqiClient:
    return WaqiClient(TOKEN, backoff_base_seconds=0.0, min_request_interval_seconds=0.0)


@respx.mock
async def test_reads_a_station_feed_into_utc() -> None:
    respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=ok(ANAND_VIHAR))

    async with client() as waqi:
        feed = await waqi.feed(2553)

    # 13:00 IST is 07:30 UTC.
    assert feed.observed_at == datetime(2026, 10, 2, 7, 30, tzinfo=UTC)
    assert feed.coordinates == pytest.approx((77.315809, 28.647622))
    assert feed.indices["pm25"] == 132
    assert any("delhi pollution control" in source.lower() for source in feed.attributions)


@respx.mock
async def test_sends_the_token_and_never_logs_it() -> None:
    route = respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=ok(ANAND_VIHAR))

    async with client() as waqi:
        await waqi.feed(2553)
        masked = waqi.sanitise_path(str(route.calls.last.request.url))

    assert route.calls.last.request.url.params["token"] == TOKEN
    assert TOKEN not in masked


@respx.mock
async def test_lists_stations_in_a_box_and_skips_a_malformed_one() -> None:
    route = respx.get(f"{WAQI_BASE_URL}/v2/map/bounds").mock(
        return_value=ok(
            [
                {
                    "lat": 28.6476,
                    "lon": 77.3158,
                    "uid": 2553,
                    "aqi": "132",
                    "station": {"name": "Anand Vihar, Delhi"},
                },
                {"lat": "not a number", "lon": 77.2, "uid": 9, "station": {}},
            ]
        )
    )

    async with client() as waqi:
        stations = await waqi.stations_in_bounds((76.8, 28.2, 77.6, 29.0))

    assert [station.uid for station in stations] == [2553]
    assert stations[0].coordinates == pytest.approx((77.3158, 28.6476))
    # WAQI wants latitude first: south,west,north,east.
    assert route.calls.last.request.url.params["latlng"] == "28.2,76.8,29.0,77.6"


@respx.mock
async def test_a_refused_token_is_a_typed_error() -> None:
    # WAQI answers a bad token with HTTP 200 and a status field.
    respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(
        return_value=httpx.Response(200, json={"status": "error", "data": "Invalid key"})
    )

    async with client() as waqi:
        with pytest.raises(UpstreamResponseError, match="Invalid key"):
            await waqi.feed(2553)


@pytest.mark.parametrize(
    "feed",
    [
        {**ANAND_VIHAR, "time": {"iso": "2026-10-02T13:00:00"}},
        {**ANAND_VIHAR, "city": {"geo": [], "name": "x"}},
        {**ANAND_VIHAR, "time": {}},
    ],
    ids=["time-without-zone", "no-position", "no-time"],
)
@respx.mock
async def test_an_unusable_feed_is_a_typed_error(feed: dict[str, Any]) -> None:
    respx.get(f"{WAQI_BASE_URL}/feed/@2553/").mock(return_value=ok(feed))

    async with client() as waqi:
        with pytest.raises(UpstreamResponseError):
            await waqi.feed(2553)
