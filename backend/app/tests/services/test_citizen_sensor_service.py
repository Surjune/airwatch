"""Tests for accepting readings from citizens' own sensors.

What is under test is restraint again. A household sensor's number looks like a
monitor's on a map, so the service must refuse what cannot be ambient air, store
what it accepts exactly as reported, and only ever compare it with ground truth.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.constants import (
    CITIZEN_SENSOR_MAX_AGE_HOURS,
    CITIZEN_SENSOR_MAX_READINGS_PER_DEVICE_PER_HOUR,
)
from app.core.enums import PilotCity, Pollutant, StationTier
from app.core.exceptions import RateLimitExceededError, ValidationError
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow
from app.services import citizen_sensor_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)

#: Connaught Place, in (longitude, latitude) order.
DELHI: tuple[float, float] = (77.2167, 28.6333)

#: A point far from the seeded station, outside the co-location radius.
REMOTE: tuple[float, float] = (77.4500, 28.9000)

DEVICE = "sensor-device-0001"


def _seed_station(
    session: Session, value: float = 100.0, tier: StationTier = StationTier.REFERENCE
) -> None:
    station_id = station_repository.upsert_station(
        session,
        source="test",
        source_station_id=f"sensor-ref-{tier.value}",
        name="Reference Monitor",
        tier=tier,
        coordinates=DELHI,
    )
    observation_repository.upsert_measurements(
        session,
        [
            MeasurementRow(
                station_id=station_id,
                observed_at=NOW,
                pollutant=Pollutant.PM25,
                value_raw=value,
                unit="ug/m3",
            )
        ],
    )
    session.flush()


def _submit(
    session: Session,
    *,
    value: float = 140.0,
    position: tuple[float, float] = DELHI,
    pollutant: Pollutant = Pollutant.PM25,
    observed_at: datetime = NOW,
    device: str = DEVICE,
) -> citizen_sensor_service.AcceptedReading:
    return citizen_sensor_service.submit(
        session,
        coordinates=position,
        pollutant=pollutant,
        value=value,
        observed_at=observed_at,
        device_id=device,
        sensor_model="AirGradient ONE",
        now=NOW,
    )


class TestSubmit:
    def test_stores_the_value_exactly_as_reported(self, session: Session) -> None:
        accepted = _submit(session, value=141.5)

        assert accepted.reading_id > 0
        assert accepted.value == 141.5

    def test_compares_with_the_nearest_reference_monitor(self, session: Session) -> None:
        _seed_station(session, value=100.0)

        accepted = _submit(session, value=140.0)

        assert accepted.reference is not None
        assert accepted.reference.station_name == "Reference Monitor"
        assert accepted.relative_difference == pytest.approx(0.4)

    def test_never_compares_with_another_low_cost_sensor(self, session: Session) -> None:
        # A comparison is only evidence if one side is ground truth.
        _seed_station(session, tier=StationTier.LOW_COST)

        assert _submit(session).reference is None

    def test_far_from_any_monitor_there_is_nothing_to_compare(self, session: Session) -> None:
        _seed_station(session)

        accepted = _submit(session, position=REMOTE)

        assert accepted.reference is None
        assert accepted.relative_difference is None

    def test_one_pair_is_reported_but_not_established(self, session: Session) -> None:
        _seed_station(session, value=100.0)

        accepted = _submit(session, value=130.0)

        assert accepted.colocation.pairs == 1
        assert accepted.colocation.median_ratio == pytest.approx(1.3)
        assert accepted.colocation.is_established is False

    def test_refuses_a_gas_reading(self, session: Session) -> None:
        with pytest.raises(ValidationError, match=r"PM2\.5 or PM10"):
            _submit(session, pollutant=Pollutant.NO2, value=40.0)

    def test_refuses_a_value_no_ambient_air_can_reach(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="outside"):
            _submit(session, value=50_000.0)

    def test_refuses_a_reading_from_the_future(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="future"):
            _submit(session, observed_at=NOW + timedelta(hours=1))

    def test_refuses_a_stale_reading(self, session: Session) -> None:
        stale = NOW - timedelta(hours=CITIZEN_SENSOR_MAX_AGE_HOURS, minutes=1)

        with pytest.raises(ValidationError, match="older than"):
            _submit(session, observed_at=stale)

    def test_refuses_a_position_outside_india(self, session: Session) -> None:
        with pytest.raises(ValidationError):
            _submit(session, position=(2.35, 48.85))

    def test_rate_limits_one_device(self, session: Session) -> None:
        for _ in range(CITIZEN_SENSOR_MAX_READINGS_PER_DEVICE_PER_HOUR):
            _submit(session, value=60.0)

        with pytest.raises(RateLimitExceededError):
            _submit(session, value=60.0)


class TestRecent:
    def test_lists_readings_with_their_raw_sub_index(self, session: Session) -> None:
        _submit(session, value=95.0)

        readings, _ = citizen_sensor_service.recent(session, Pollutant.PM25, now=NOW)

        assert len(readings) == 1
        assert readings[0].reading.value == 95.0
        assert readings[0].raw_aqi > 0
        assert readings[0].raw_category

    def test_scopes_to_a_city(self, session: Session) -> None:
        _submit(session)

        in_delhi, _ = citizen_sensor_service.recent(
            session, Pollutant.PM25, city=PilotCity.DELHI, now=NOW
        )
        in_coimbatore, _ = citizen_sensor_service.recent(
            session, Pollutant.PM25, city=PilotCity.COIMBATORE, now=NOW
        )

        assert len(in_delhi) == 1
        assert in_coimbatore == []

    def test_keeps_pollutants_apart(self, session: Session) -> None:
        _submit(session, pollutant=Pollutant.PM10, value=180.0)

        readings, _ = citizen_sensor_service.recent(session, Pollutant.PM25, now=NOW)

        assert readings == []


class TestExplanation:
    def test_says_what_to_do_when_nothing_is_paired(self, session: Session) -> None:
        text = citizen_sensor_service.colocation_explanation(
            citizen_sensor_service.colocation(session, Pollutant.PM25)
        )

        assert "reference monitor" in text
