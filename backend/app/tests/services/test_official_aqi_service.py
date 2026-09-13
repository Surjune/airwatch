"""Tests for CPCB's rule for stating a station AQI, and the stored city view."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.enums import PilotCity, Pollutant
from app.repositories import official_aqi_repository
from app.repositories.official_aqi_repository import OfficialRow
from app.services.official_aqi_service import latest_for_city, station_aqi

NOW = datetime(2026, 9, 13, 8, 30, tzinfo=UTC)


class TestStationAqi:
    def test_is_the_highest_sub_index_with_the_pollutant_that_sets_it(self) -> None:
        overall, dominant = station_aqi({Pollutant.PM10: 28, Pollutant.NO2: 22, Pollutant.CO: 44})
        assert overall == 44
        assert dominant is Pollutant.CO

    def test_is_not_stated_with_fewer_than_three_pollutants(self) -> None:
        assert station_aqi({Pollutant.PM25: 180, Pollutant.NO2: 40}) == (None, None)

    def test_is_not_stated_without_a_particulate(self) -> None:
        # Three gases alone could understate a smoky day entirely.
        gases = {Pollutant.NO2: 40, Pollutant.SO2: 30, Pollutant.O3: 60}
        assert station_aqi(gases) == (None, None)


def _row(pollutant: Pollutant, value: float, reported_at: datetime) -> OfficialRow:
    return OfficialRow(
        station_name="SIDCO Kurichi, Coimbatore - TNPCB",
        city="Coimbatore",
        state="TamilNadu",
        coordinates=(76.979, 10.9425),
        pollutant=pollutant,
        reported_at=reported_at,
        sub_index=value,
        sub_index_min=None,
        sub_index_max=None,
    )


@pytest.mark.integration
def test_combines_only_the_latest_report_into_an_aqi(session: Session) -> None:
    earlier = NOW - timedelta(hours=1)
    official_aqi_repository.upsert_sub_indices(
        session,
        [
            _row(Pollutant.PM10, 28, NOW),
            _row(Pollutant.NO2, 22, NOW),
            _row(Pollutant.CO, 44, NOW),
            # An older, higher value from another hour must not leak into now's AQI.
            _row(Pollutant.SO2, 150, earlier),
        ],
    )
    session.flush()

    stations = latest_for_city(session, PilotCity.COIMBATORE)

    assert len(stations) == 1
    station = stations[0]
    assert station.reported_at == NOW
    assert Pollutant.SO2 not in station.sub_indices
    assert station.aqi == 44
    assert station.category == "Good"
