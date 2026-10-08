"""Tests for fetching CPCB's daily bulletin and serving a city's line."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest
import respx

from app.core.enums import PilotCity, Pollutant
from app.core.exceptions import UpstreamUnavailableError
from app.repositories import bulletin_repository
from app.repositories.bulletin_repository import BulletinRow
from app.services import bulletin_service
from app.tests.external.test_cpcb_bulletin_client import ROWS, bulletin_pdf, bulletin_url

#: 21:00 IST on 8 October 2026, after that day's bulletin is out.
EVENING = datetime(2026, 10, 8, 15, 30, tzinfo=UTC)
#: 10:00 IST on 9 October 2026, before that day's bulletin is out.
MORNING = datetime(2026, 10, 9, 4, 30, tzinfo=UTC)

OCT_8 = date(2026, 10, 8)
OCT_9 = date(2026, 10, 9)
HEADING = "Air Quality Index on Oct 08, 2026 @ 4 PM"


@pytest.fixture
def stored(monkeypatch: pytest.MonkeyPatch) -> list[BulletinRow]:
    rows: list[BulletinRow] = []

    def upsert(_session: Any, batch: list[BulletinRow]) -> int:
        rows.extend(batch)
        return len(batch)

    monkeypatch.setattr(bulletin_repository, "upsert_bulletins", upsert)
    monkeypatch.setattr(
        bulletin_repository, "has_day", lambda _session, day: any(row.day == day for row in rows)
    )
    return rows


@respx.mock
async def test_stores_the_pilot_cities_lines_from_todays_bulletin(
    stored: list[BulletinRow],
) -> None:
    respx.get(bulletin_url(OCT_8)).mock(
        return_value=httpx.Response(200, content=bulletin_pdf(HEADING, *ROWS))
    )

    outcome = await bulletin_service.ingest(object(), now=EVENING)  # type: ignore[arg-type]

    assert (outcome.day, outcome.stored) == (OCT_8, 3)
    assert {row.city for row in stored} == {"Delhi", "Kanpur", "Coimbatore"}
    kanpur = next(row for row in stored if row.city == "Kanpur")
    assert (kanpur.aqi, kanpur.prominent_pollutants) == (44, (Pollutant.PM25, Pollutant.NO2))


@respx.mock
async def test_falls_back_to_yesterdays_before_todays_is_out(stored: list[BulletinRow]) -> None:
    respx.get(bulletin_url(OCT_9)).mock(return_value=httpx.Response(404))
    respx.get(bulletin_url(OCT_8)).mock(
        return_value=httpx.Response(200, content=bulletin_pdf(HEADING, *ROWS))
    )

    outcome = await bulletin_service.ingest(object(), now=MORNING)  # type: ignore[arg-type]

    assert outcome.day == OCT_8
    assert {row.day for row in stored} == {OCT_8}


@respx.mock(assert_all_called=False)
async def test_asks_for_nothing_once_the_days_bulletin_is_held(
    stored: list[BulletinRow], respx_mock: respx.MockRouter
) -> None:
    stored.append(BulletinRow("Kanpur", OCT_8, 44, "Good", (Pollutant.PM25,), 2, 4))
    route = respx_mock.get(bulletin_url(OCT_8))

    outcome = await bulletin_service.ingest(object(), now=EVENING)  # type: ignore[arg-type]

    assert (outcome.day, outcome.stored) == (OCT_8, 0)
    assert not route.called


@respx.mock
async def test_no_bulletin_for_two_days_is_an_error(stored: list[BulletinRow]) -> None:
    respx.get(bulletin_url(OCT_9)).mock(return_value=httpx.Response(404))
    respx.get(bulletin_url(OCT_8)).mock(return_value=httpx.Response(404))

    with pytest.raises(UpstreamUnavailableError, match="no AQI bulletin"):
        await bulletin_service.ingest(object(), now=MORNING)  # type: ignore[arg-type]


def test_a_citys_line_says_when_its_average_ran_to(monkeypatch: pytest.MonkeyPatch) -> None:
    row = BulletinRow("Kanpur", OCT_8, 44, "Good", (Pollutant.PM25, Pollutant.NO2), 2, 4)
    monkeypatch.setattr(bulletin_repository, "latest_for_city", lambda _session, city: row)

    line = bulletin_service.latest_for_city(object(), PilotCity.KANPUR)  # type: ignore[arg-type]

    assert line is not None
    # 4 pm IST is 10:30 UTC.
    assert line.averaged_until == datetime(2026, 10, 8, 10, 30, tzinfo=UTC)
    assert line.source_url.endswith("/AQI_Bulletin_20261008.pdf")
