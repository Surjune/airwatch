"""Tests for the data.gov.in CPCB AQI client. The records mirror real portal output."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.constants import CPCB_AQI_BASE_URL, CPCB_AQI_RESOURCE_ID, UPSTREAM_USER_AGENT
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.external.cpcb_client import CpcbAqiClient

API_KEY = "test-cpcb-key-0123456789"
URL = f"{CPCB_AQI_BASE_URL}/resource/{CPCB_AQI_RESOURCE_ID}"


def record(pollutant: str, avg: str, *, low: str = "10", high: str = "60") -> dict[str, str]:
    return {
        "country": "India",
        "state": "TamilNadu",
        "city": "Coimbatore",
        "station": "SIDCO Kurichi, Coimbatore - TNPCB",
        "last_update": "13-09-2026 14:00:00",
        "latitude": "10.942451",
        "longitude": "76.978996",
        "pollutant_id": pollutant,
        "min_value": low,
        "max_value": high,
        "avg_value": avg,
    }


def payload(*records: dict[str, str]) -> dict[str, object]:
    return {"records": list(records), "total": len(records)}


@respx.mock
async def test_parses_sub_indices_and_converts_ist_to_utc() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json=payload(record("PM10", "28"))))

    async with CpcbAqiClient(API_KEY) as client:
        readings = await client.city_sub_indices("Coimbatore")

    reading = readings[0]
    assert reading.pollutant is Pollutant.PM10
    assert reading.sub_index == 28.0
    # 14:00 IST is 08:30 UTC.
    assert reading.reported_at == datetime(2026, 9, 13, 8, 30, tzinfo=UTC)
    assert reading.coordinates == pytest.approx((76.978996, 10.942451))


@respx.mock
async def test_maps_the_portals_pollutant_labels() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, json=payload(record("OZONE", "20"), record("PM2.5", "55")))
    )

    async with CpcbAqiClient(API_KEY) as client:
        readings = await client.city_sub_indices("Coimbatore")

    assert {reading.pollutant for reading in readings} == {Pollutant.O3, Pollutant.PM25}


@respx.mock
async def test_a_sensor_with_no_value_is_skipped_not_read_as_zero() -> None:
    # SIDCO Kurichi's PM2.5 sensor reports "NA"; that is not a sub-index of 0.
    respx.get(URL).mock(
        return_value=httpx.Response(200, json=payload(record("PM2.5", "NA"), record("SO2", "28")))
    )

    async with CpcbAqiClient(API_KEY) as client:
        readings = await client.city_sub_indices("Coimbatore")

    assert [reading.pollutant for reading in readings] == [Pollutant.SO2]


@respx.mock
async def test_sends_the_city_filter_and_a_named_user_agent() -> None:
    # The gateway returns 502 to the default python-httpx agent.
    route = respx.get(URL).mock(return_value=httpx.Response(200, json=payload()))

    async with CpcbAqiClient(API_KEY) as client:
        await client.city_sub_indices("Coimbatore")

    request = route.calls.last.request
    assert request.url.params["filters[city]"] == "Coimbatore"
    assert request.headers["User-Agent"] == UPSTREAM_USER_AGENT


@respx.mock
async def test_a_payload_without_records_is_a_typed_error() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, json={"message": "Invalid key"}))

    async with CpcbAqiClient(API_KEY) as client:
        with pytest.raises(UpstreamResponseError):
            await client.city_sub_indices("Coimbatore")


def test_the_key_is_masked_wherever_it_might_be_echoed() -> None:
    client = CpcbAqiClient(API_KEY)
    assert API_KEY not in client.sanitise_path(f"/resource?api-key={API_KEY}&format=json")
