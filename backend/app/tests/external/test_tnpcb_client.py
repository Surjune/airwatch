"""Tests for the TNPCB AQI page reader. The entries mirror the page on 8 October 2026."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx

from app.core.constants import TNPCB_AQI_PATH, TNPCB_BASE_URL
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.external.tnpcb_client import TnpcbClient

URL = f"{TNPCB_BASE_URL}{TNPCB_AQI_PATH}"

SIDCO: dict[str, object] = {
    "name": "SIDCO Kurichi, Coimbatore - TNPCB",
    "lastUpdate": "08-10-2026 21:00:00",
    "pollutants": [
        {"indexId": "PM2.5", "min": "13", "max": "215", "avg": "51", "Hourly_sub_index": "215"},
        {"indexId": "PM10", "min": "19", "max": "100", "avg": "40", "Hourly_sub_index": "100"},
        {"indexId": "OZONE", "min": "19", "max": "20", "avg": "20", "Hourly_sub_index": "20"},
        {"indexId": "Benzene", "min": "1", "max": "1", "avg": "1", "Hourly_sub_index": "1"},
    ],
}

MANALI_VILLAGE: dict[str, object] = {
    "name": "Manali Village, Chennai - TNPCB",
    "lastUpdate": "08-10-2026 21:00:00",
    "pollutants": [
        {"indexId": "PM2.5", "min": "NA", "max": "NA", "avg": "NA", "Hourly_sub_index": "24"},
        {"indexId": "NO2", "min": "2", "max": "15", "avg": "8", "Hourly_sub_index": "NA"},
    ],
}


def page(*entries: tuple[str, dict[str, object]]) -> str:
    """The page's script as TNPCB writes it, inside the surrounding markup."""
    pushes = "\n".join(
        f'stationsData["{city}"].push({json.dumps(entry)});' for city, entry in entries
    )
    return f"<html><body><script>stationsData = {{}}\n{pushes}\n</script></body></html>"


@respx.mock
async def test_reads_each_pollutants_sub_index_and_converts_ist_to_utc() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=page(("Coimbatore", SIDCO))))

    async with TnpcbClient() as client:
        readings = await client.station_sub_indices()

    by_pollutant = {reading.pollutant: reading for reading in readings}
    assert set(by_pollutant) == {Pollutant.PM25, Pollutant.PM10, Pollutant.O3}
    pm25 = by_pollutant[Pollutant.PM25]
    assert pm25.city == "Coimbatore"
    assert pm25.station == "SIDCO Kurichi, Coimbatore - TNPCB"
    assert (pm25.sub_index, pm25.sub_index_min, pm25.sub_index_max) == (51.0, 13.0, 215.0)
    # 21:00 IST is 15:30 UTC.
    assert pm25.reported_at == datetime(2026, 10, 8, 15, 30, tzinfo=UTC)


@respx.mock
async def test_skips_a_pollutant_with_no_average() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text=page(("Chennai", MANALI_VILLAGE))))

    async with TnpcbClient() as client:
        readings = await client.station_sub_indices()

    assert [reading.pollutant for reading in readings] == [Pollutant.NO2]


@respx.mock
async def test_a_page_without_station_entries_is_an_error_not_an_empty_city() -> None:
    respx.get(URL).mock(return_value=httpx.Response(200, text="<html>Under maintenance</html>"))

    async with TnpcbClient() as client:
        with pytest.raises(UpstreamResponseError, match="no station entries"):
            await client.station_sub_indices()


@respx.mock
async def test_an_entry_of_a_new_shape_is_an_error() -> None:
    reshaped: dict[str, object] = {
        "name": "SIDCO Kurichi, Coimbatore - TNPCB",
        "updated": "08-10-2026 21:00:00",
    }
    respx.get(URL).mock(return_value=httpx.Response(200, text=page(("Coimbatore", reshaped))))

    async with TnpcbClient() as client:
        with pytest.raises(UpstreamResponseError, match="expected shape"):
            await client.station_sub_indices()
