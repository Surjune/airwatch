"""Integration tests for citizen sensor reading persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Pollutant, StationTier
from app.core.h3_grid import point_to_cell
from app.repositories import citizen_sensor_repository, station_repository
from app.repositories.citizen_sensor_repository import SensorReadingRow

pytestmark = pytest.mark.integration

NOW = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)
POINT: tuple[float, float] = (76.9790, 10.9425)


def _row(
    *,
    value: float = 60.0,
    reference_station_id: int | None = None,
    reference_value: float | None = None,
    pollutant: Pollutant = Pollutant.PM25,
    observed_at: datetime = NOW,
) -> SensorReadingRow:
    return SensorReadingRow(
        coordinates=POINT,
        h3_cell=point_to_cell(POINT),
        observed_at=observed_at,
        device_id="repo-sensor-0001",
        sensor_model="AirGradient ONE",
        pollutant=pollutant,
        value=value,
        reference_station_id=reference_station_id,
        reference_value=reference_value,
        reference_distance_m=None if reference_station_id is None else 850.0,
    )


class TestReadings:
    def test_round_trips_a_reading_with_its_monitors_name(self, session: Session) -> None:
        station_id = station_repository.upsert_station(
            session,
            source="test",
            source_station_id="kurichi",
            name="SIDCO Kurichi",
            tier=StationTier.REFERENCE,
            coordinates=POINT,
        )
        citizen_sensor_repository.insert_reading(
            session, _row(reference_station_id=station_id, reference_value=50.0)
        )

        [reading] = citizen_sensor_repository.recent_readings(
            session, Pollutant.PM25, NOW - timedelta(hours=1), limit=10
        )

        assert reading.coordinates == pytest.approx(POINT)
        assert reading.reference_station_name == "SIDCO Kurichi"
        assert reading.reference_value == 50.0

    def test_excludes_readings_before_the_window(self, session: Session) -> None:
        citizen_sensor_repository.insert_reading(session, _row(observed_at=NOW - timedelta(days=2)))

        assert (
            citizen_sensor_repository.recent_readings(
                session, Pollutant.PM25, NOW - timedelta(hours=1), limit=10
            )
            == []
        )


class TestPairs:
    def test_only_paired_readings_of_the_pollutant_count(self, session: Session) -> None:
        citizen_sensor_repository.insert_reading(session, _row(value=70.0, reference_value=50.0))
        citizen_sensor_repository.insert_reading(session, _row(value=90.0))
        citizen_sensor_repository.insert_reading(
            session, _row(value=150.0, reference_value=100.0, pollutant=Pollutant.PM10)
        )

        pairs = citizen_sensor_repository.colocated_pairs(session, Pollutant.PM25)

        assert [(pair.sensor_value, pair.reference_value) for pair in pairs] == [(70.0, 50.0)]

    def test_counts_a_devices_recent_submissions(self, session: Session) -> None:
        citizen_sensor_repository.insert_reading(session, _row())
        citizen_sensor_repository.insert_reading(session, _row())

        count = citizen_sensor_repository.count_readings_since(
            session, "repo-sensor-0001", datetime.now(UTC) - timedelta(hours=1)
        )

        assert count == 2
