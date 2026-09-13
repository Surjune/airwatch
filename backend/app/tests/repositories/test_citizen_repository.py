"""Integration tests for pairing a citizen photograph with a reference reading.

A pair is the unit the haze calibration is fitted from, so what counts as one
decides whether the fitted relation means anything. These run against PostgreSQL
because the distance and time filters are PostGIS and SQL, not Python.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Pollutant, StationTier
from app.repositories import citizen_repository, observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow

pytestmark = pytest.mark.integration

#: When the photograph was taken.
CAPTURED = datetime(2026, 9, 13, 8, 0, tzinfo=UTC)

#: SIDCO Kurichi, Coimbatore, in (longitude, latitude).
MONITOR = (76.978996, 10.942451)

#: About 1 km north of the monitor, well inside the pairing radius.
NEARBY = (76.979, 10.951)


def _monitor_with_readings(session: Session, readings: dict[datetime, float]) -> None:
    station_id = station_repository.upsert_station(
        session,
        source="test",
        source_station_id="sidco",
        name="SIDCO Kurichi",
        tier=StationTier.REFERENCE,
        coordinates=MONITOR,
    )
    observation_repository.upsert_measurements(
        session,
        [
            MeasurementRow(
                station_id=station_id,
                observed_at=when,
                pollutant=Pollutant.PM25,
                value_raw=value,
                unit="ug/m3",
            )
            for when, value in readings.items()
        ],
    )
    session.flush()


def test_pairs_with_the_reading_closest_in_time_not_the_latest(session: Session) -> None:
    _monitor_with_readings(
        session,
        {
            CAPTURED - timedelta(minutes=30): 41.0,
            CAPTURED + timedelta(hours=5): 90.0,
        },
    )

    reading = citizen_repository.nearest_station_reading(session, NEARBY, Pollutant.PM25, CAPTURED)

    assert reading is not None
    assert reading.value == pytest.approx(41.0)


def test_a_reading_from_another_day_is_not_a_pair(session: Session) -> None:
    # The failure this guards: a monitor whose feed stopped two days ago would
    # otherwise supply its last value for every photograph taken since.
    _monitor_with_readings(session, {CAPTURED - timedelta(days=2): 55.0})

    assert (
        citizen_repository.nearest_station_reading(session, NEARBY, Pollutant.PM25, CAPTURED)
        is None
    )


def test_a_monitor_beyond_the_radius_is_not_a_pair(session: Session) -> None:
    _monitor_with_readings(session, {CAPTURED: 41.0})

    # Gandhipuram, about 8 km north.
    far = (76.9629, 11.0183)
    assert (
        citizen_repository.nearest_station_reading(session, far, Pollutant.PM25, CAPTURED) is None
    )
