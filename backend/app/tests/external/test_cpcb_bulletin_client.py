"""Tests for the CPCB daily bulletin reader.

The rows mirror CPCB's bulletin for 8 October 2026. The PDFs are built here, so
the client is exercised on a real document without a file in the repository.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest
import respx
from fpdf import FPDF

from app.core.constants import CPCB_BULLETIN_BASE_URL, CPCB_BULLETIN_PATH
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.external.cpcb_bulletin_client import CpcbBulletinClient

DAY = date(2026, 10, 8)

ROWS = (
    "74 Coimbatore Good 44 PM2.5 1/2",
    "80 Delhi Moderate 162 PM10 44/49",
    "137 Kanpur Good 44 PM2.5, NO2 2/4",
    "152 Navi mumbai Very Poor 310 PM10, O3 3/5",
)


def bulletin_url(day: date) -> str:
    return CPCB_BULLETIN_BASE_URL + CPCB_BULLETIN_PATH.format(day=day.strftime("%Y%m%d"))


def bulletin_pdf(heading: str = "Air Quality Index on Oct 08, 2026 @ 4 PM", *rows: str) -> bytes:
    """A bulletin laid out as CPCB's is: a heading, then one line per city."""
    document = FPDF()
    document.add_page()
    document.set_font("Helvetica", size=10)
    for line in (heading, "(Average of past 24 hours)", "S.No City Air Quality Index", *rows):
        document.cell(text=line, new_x="LMARGIN", new_y="NEXT")
    return bytes(document.output())


@respx.mock
async def test_reads_each_citys_line() -> None:
    respx.get(bulletin_url(DAY)).mock(
        return_value=httpx.Response(
            200, content=bulletin_pdf("Air Quality Index on Oct 08, 2026 @ 4 PM", *ROWS)
        )
    )

    async with CpcbBulletinClient() as client:
        bulletin = await client.bulletin(DAY)

    assert bulletin is not None
    by_city = {line.city: line for line in bulletin.cities}
    kanpur = by_city["Kanpur"]
    assert (kanpur.aqi, kanpur.category) == (44, "Good")
    assert kanpur.prominent_pollutants == [Pollutant.PM25, Pollutant.NO2]
    assert (kanpur.stations_reporting, kanpur.stations_total) == (2, 4)
    # A two-word city and a two-word category are both read whole.
    assert by_city["Navi mumbai"].category == "Very Poor"
    assert by_city["Navi mumbai"].prominent_pollutants == [Pollutant.PM10, Pollutant.O3]


@respx.mock
async def test_a_bulletin_not_yet_published_is_none() -> None:
    respx.get(bulletin_url(DAY)).mock(return_value=httpx.Response(404, text="Not Found"))

    async with CpcbBulletinClient() as client:
        assert await client.bulletin(DAY) is None


@respx.mock
async def test_a_bulletin_dated_another_day_is_an_error() -> None:
    respx.get(bulletin_url(DAY)).mock(
        return_value=httpx.Response(
            200, content=bulletin_pdf("Air Quality Index on Oct 07, 2026 @ 4 PM", *ROWS)
        )
    )

    async with CpcbBulletinClient() as client:
        with pytest.raises(UpstreamResponseError, match="is dated 2026-10-07"):
            await client.bulletin(DAY)


@respx.mock
async def test_a_bulletin_without_city_rows_is_an_error_not_an_empty_day() -> None:
    respx.get(bulletin_url(DAY)).mock(return_value=httpx.Response(200, content=bulletin_pdf()))

    async with CpcbBulletinClient() as client:
        with pytest.raises(UpstreamResponseError, match="no city rows"):
            await client.bulletin(DAY)


@respx.mock
async def test_a_document_that_is_not_a_pdf_is_an_error() -> None:
    respx.get(bulletin_url(DAY)).mock(
        return_value=httpx.Response(200, content=b"<html>maintenance</html>")
    )

    async with CpcbBulletinClient() as client:
        with pytest.raises(UpstreamResponseError, match="could not be read"):
            await client.bulletin(DAY)
