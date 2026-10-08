"""Integration tests for storing CPCB's daily bulletin and reading a city's newest line."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.repositories import bulletin_repository
from app.repositories.bulletin_repository import BulletinRow

pytestmark = pytest.mark.integration

OCT_7 = date(2026, 10, 7)
OCT_8 = date(2026, 10, 8)


def _line(city: str, day: date, aqi: int) -> BulletinRow:
    return BulletinRow(city, day, aqi, "Good", (Pollutant.PM25, Pollutant.NO2), 2, 4)


def test_serves_a_citys_newest_line_with_its_pollutants(session: Session) -> None:
    bulletin_repository.upsert_bulletins(
        session,
        [_line("Kanpur", OCT_7, 86), _line("Kanpur", OCT_8, 44), _line("Delhi", OCT_8, 162)],
    )
    session.flush()

    line = bulletin_repository.latest_for_city(session, "Kanpur")

    assert line == _line("Kanpur", OCT_8, 44)
    assert bulletin_repository.latest_for_city(session, "Coimbatore") is None


def test_a_reread_day_replaces_the_stored_line(session: Session) -> None:
    bulletin_repository.upsert_bulletins(session, [_line("Kanpur", OCT_8, 44)])
    bulletin_repository.upsert_bulletins(session, [_line("Kanpur", OCT_8, 45)])
    session.flush()

    assert bulletin_repository.has_day(session, OCT_8)
    assert not bulletin_repository.has_day(session, OCT_7)
    line = bulletin_repository.latest_for_city(session, "Kanpur")
    assert line is not None
    assert line.aqi == 45
