"""Integration tests for satellite ingestion and the city picture.

The Earth Engine client is replaced by a plain function; storage and the
aggregation queries run against PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.enums import PilotCity, SatelliteProduct
from app.core.geo import LonLat
from app.external.s5p_client import CellMean
from app.services import satellite_service

pytestmark = pytest.mark.integration

TODAY = date(2026, 9, 13)


type Fetch = Callable[[SatelliteProduct, dict[str, list[LonLat]], date], list[CellMean]]


def fetcher(value_for_day: dict[date, float]) -> tuple[Fetch, list[date]]:
    """A stand-in client: every cell reads the given value on the given days."""
    calls: list[date] = []

    def fetch(
        product: SatelliteProduct, cells: dict[str, list[LonLat]], day: date
    ) -> list[CellMean]:
        calls.append(day)
        if day not in value_for_day:
            return []
        return [CellMean(cell=cell, value=value_for_day[day], pixel_count=30) for cell in cells]

    return fetch, calls


def test_covers_a_city_with_coarse_cells_around_its_centre() -> None:
    cells = satellite_service.city_cells(PilotCity.COIMBATORE)
    assert len(cells) > 1
    assert all(len(ring) == 6 for ring in cells.values())


def test_ingests_past_days_only_and_counts_the_days_observed(session: Session) -> None:
    yesterday = TODAY - timedelta(days=1)
    fetch, calls = fetcher({yesterday: 4.0e-5})

    summary = satellite_service.ingest_city(
        session,
        PilotCity.COIMBATORE,
        fetch,
        days=3,
        today=TODAY,
        products=(SatelliteProduct.NO2,),
    )

    # Today's overpass may not be processed yet, so it is never requested.
    assert TODAY not in calls
    assert summary.days_observed[SatelliteProduct.NO2] == 1
    assert summary.stored == len(satellite_service.city_cells(PilotCity.COIMBATORE))


def test_the_picture_averages_each_day_and_keeps_each_cells_latest(session: Session) -> None:
    older, newer = TODAY - timedelta(days=3), TODAY - timedelta(days=1)
    fetch, _ = fetcher({older: 2.0e-5, newer: 6.0e-5})
    satellite_service.ingest_city(
        session, PilotCity.DELHI, fetch, days=4, today=TODAY, products=(SatelliteProduct.NO2,)
    )
    session.flush()

    picture = satellite_service.city_picture(
        session, PilotCity.DELHI, SatelliteProduct.NO2, days=7, today=TODAY
    )

    assert [day.observed_on for day in picture.series] == [older, newer]
    assert picture.series[-1].value == pytest.approx(6.0e-5)
    assert picture.cells
    assert all(cell.observed_on == newer for cell in picture.cells)
    assert picture.unit == "mol/m2"


def test_a_rerun_replaces_rather_than_duplicates(session: Session) -> None:
    day = TODAY - timedelta(days=1)
    for value in (1.0e-5, 3.0e-5):
        fetch, _ = fetcher({day: value})
        satellite_service.ingest_city(
            session, PilotCity.KANPUR, fetch, days=1, today=TODAY, products=(SatelliteProduct.CO,)
        )
    session.flush()

    picture = satellite_service.city_picture(
        session, PilotCity.KANPUR, SatelliteProduct.CO, days=3, today=TODAY
    )
    assert len(picture.series) == 1
    assert picture.series[0].value == pytest.approx(3.0e-5)
