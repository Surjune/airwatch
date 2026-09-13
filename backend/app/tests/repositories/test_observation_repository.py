"""Integration tests for the observation repository.

Every assertion here is about something only PostgreSQL can answer: that
``ON CONFLICT`` makes a re-run converge instead of duplicating, that
``DISTINCT ON`` returns one row per station rather than one per reading, and
that ``ST_X`` yields longitude rather than latitude.

The last of those looks trivial and is the most valuable. Latitude and longitude
are both plain floats, so a transposition raises nothing, stores cleanly, and
surfaces as a map of India with every station in the Indian Ocean.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Pollutant, StationTier
from app.core.h3_grid import point_to_cell
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import FireRow, MeasurementRow, WeatherRow

pytestmark = pytest.mark.integration

#: A fixed reference hour, so a test cannot pass or fail depending on when it ran.
NOW = datetime(2026, 3, 1, 6, 0, tzinfo=UTC)

#: Connaught Place, in (longitude, latitude) order. The two numbers are far
#: enough apart that a transposition is unmistakable in an assertion.
DELHI: tuple[float, float] = (77.2167, 28.6333)


def _station(session: Session, *, station_id: str = "test-1", name: str = "Test Station") -> int:
    return station_repository.upsert_station(
        session,
        source="test",
        source_station_id=station_id,
        name=name,
        tier=StationTier.REFERENCE,
        coordinates=DELHI,
    )


class TestCoordinateOrder:
    def test_longitude_comes_back_as_longitude(self, session: Session) -> None:
        # The whole system stores (lon, lat) and Leaflet consumes (lat, lon).
        # If the repository transposed them, every downstream layer would be
        # consistently and invisibly wrong.
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW,
                    pollutant=Pollutant.PM25,
                    value_raw=120.0,
                    unit="ug/m3",
                )
            ],
        )
        session.flush()

        row = observation_repository.latest_reading_per_station(session, Pollutant.PM25)[0]
        _, _, lon, lat, _, _, _, _ = row

        assert lon == pytest.approx(DELHI[0])
        assert lat == pytest.approx(DELHI[1])


class TestUpsertIdempotency:
    def test_re_ingesting_the_same_window_does_not_duplicate(self, session: Session) -> None:
        # Ingestion re-reads overlapping windows by design, so a second run has
        # to converge on the same rows rather than accumulate them.
        station_id = _station(session)
        rows = [
            MeasurementRow(
                station_id=station_id,
                observed_at=NOW - timedelta(hours=hour),
                pollutant=Pollutant.PM25,
                value_raw=100.0 + hour,
                unit="ug/m3",
            )
            for hour in range(5)
        ]

        observation_repository.upsert_measurements(session, rows)
        session.flush()
        first = observation_repository.count_measurements(session)

        observation_repository.upsert_measurements(session, rows)
        session.flush()

        assert observation_repository.count_measurements(session) == first == 5

    def test_a_corrected_value_replaces_the_earlier_one(self, session: Session) -> None:
        # Upstreams restate readings after quality control. The later statement
        # is the one to keep, and it must not arrive as a second row.
        station_id = _station(session)
        original = MeasurementRow(
            station_id=station_id,
            observed_at=NOW,
            pollutant=Pollutant.PM25,
            value_raw=100.0,
            unit="ug/m3",
        )
        observation_repository.upsert_measurements(session, [original])
        session.flush()

        corrected = MeasurementRow(
            station_id=station_id,
            observed_at=NOW,
            pollutant=Pollutant.PM25,
            value_raw=175.0,
            unit="ug/m3",
        )
        observation_repository.upsert_measurements(session, [corrected])
        session.flush()

        readings = observation_repository.latest_reading_per_station(session, Pollutant.PM25)
        assert len(readings) == 1
        assert readings[0][6] == pytest.approx(175.0)

    def test_a_station_reported_twice_stays_one_station(self, session: Session) -> None:
        # Identity is (source, source_station_id). A renamed station is the same
        # station; treating the name as identity would fork it.
        first = _station(session, name="Old Name")
        session.flush()
        second = _station(session, name="Renamed Station")
        session.flush()

        assert first == second
        assert station_repository.count_stations(session) == 1
        assert station_repository.list_stations(session)[0].name == "Renamed Station"


class TestLatestReadingPerStation:
    def test_returns_one_row_per_station(self, session: Session) -> None:
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW - timedelta(hours=hour),
                    pollutant=Pollutant.PM25,
                    value_raw=50.0 + hour,
                    unit="ug/m3",
                )
                for hour in range(6)
            ],
        )
        session.flush()

        readings = observation_repository.latest_reading_per_station(session, Pollutant.PM25)

        assert len(readings) == 1

    def test_the_row_returned_is_the_most_recent(self, session: Session) -> None:
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW - timedelta(hours=3),
                    pollutant=Pollutant.PM25,
                    value_raw=300.0,
                    unit="ug/m3",
                ),
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW,
                    pollutant=Pollutant.PM25,
                    value_raw=42.0,
                    unit="ug/m3",
                ),
            ],
        )
        session.flush()

        row = observation_repository.latest_reading_per_station(session, Pollutant.PM25)[0]

        # Not the largest value -- the newest. A max() would have returned 300.
        assert row[6] == pytest.approx(42.0)

    def test_an_implausible_reading_is_not_published(self, session: Session) -> None:
        # A wrong number is worse than no number, so a reading flagged during
        # ingestion must not reach a consumer as if it were measured cleanly.
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW,
                    pollutant=Pollutant.PM25,
                    value_raw=99999.0,
                    unit="ug/m3",
                    is_plausible=False,
                )
            ],
        )
        session.flush()

        assert observation_repository.latest_reading_per_station(session, Pollutant.PM25) == []

    def test_a_pollutant_with_no_readings_returns_nothing(self, session: Session) -> None:
        _station(session)
        session.flush()

        assert observation_repository.latest_reading_per_station(session, Pollutant.NO2) == []


class TestReadingsInWindow:
    def test_excludes_readings_before_the_boundary(self, session: Session) -> None:
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW - timedelta(hours=hour),
                    pollutant=Pollutant.PM25,
                    value_raw=60.0,
                    unit="ug/m3",
                )
                for hour in range(10)
            ],
        )
        session.flush()

        within = observation_repository.readings_in_window(
            session, Pollutant.PM25, NOW - timedelta(hours=4)
        )

        # Hours 0..4 inclusive: the boundary itself is inside the window.
        assert len(within) == 5

    def test_returns_readings_in_time_order(self, session: Session) -> None:
        # Detection groups by hour and forecasting builds a climatology, so
        # ordering is relied upon rather than re-sorted downstream.
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW - timedelta(hours=hour),
                    pollutant=Pollutant.PM25,
                    value_raw=60.0,
                    unit="ug/m3",
                )
                for hour in (5, 1, 3, 0)
            ],
        )
        session.flush()

        rows = observation_repository.readings_in_window(
            session, Pollutant.PM25, NOW - timedelta(hours=24)
        )

        timestamps = [row[5] for row in rows]
        assert timestamps == sorted(timestamps)


class TestWeatherAndFires:
    def test_weather_round_trips_its_wind_components(self, session: Session) -> None:
        observation_repository.upsert_weather(
            session,
            [
                WeatherRow(
                    h3_cell=point_to_cell(DELHI),
                    observed_at=NOW,
                    wind_u=-3.5,
                    wind_v=1.25,
                    temperature_c=21.0,
                    relative_humidity_pct=55.0,
                    pbl_height_m=420.0,
                    precipitation_mm=0.0,
                    is_forecast=False,
                )
            ],
        )
        session.flush()

        record = observation_repository.weather_in_window(session, NOW - timedelta(hours=1))[0]

        # Sign is load-bearing: u/v say where the air is going, and a flipped
        # sign would trace every back-trajectory in the wrong direction.
        assert record.wind_u == pytest.approx(-3.5)
        assert record.wind_v == pytest.approx(1.25)

    def test_fires_come_back_strongest_first(self, session: Session) -> None:
        observation_repository.upsert_fire_detections(
            session,
            [
                FireRow(
                    coordinates=(76.5 + index * 0.1, 30.5),
                    observed_at=NOW,
                    confidence=0.8,
                    frp_mw=power,
                    brightness_k=330.0,
                    is_daytime=True,
                    satellite="VIIRS",
                )
                for index, power in enumerate([12.0, 88.0, 40.0])
            ],
        )
        session.flush()

        fires = observation_repository.fire_detections_in_window(session, NOW - timedelta(hours=1))

        powers = [row[4] for row in fires]
        assert powers == sorted(powers, reverse=True)

    def test_an_empty_window_returns_nothing(self, session: Session) -> None:
        assert observation_repository.weather_in_window(session, NOW) == []
        assert observation_repository.fire_detections_in_window(session, NOW) == []


class TestReflagMeasurements:
    def _store(self, session: Session, values: list[float], pollutant: Pollutant) -> int:
        station_id = _station(session)
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=NOW - timedelta(hours=index),
                    pollutant=pollutant,
                    value_raw=value,
                    unit="mg/m3",
                )
                for index, value in enumerate(values)
            ],
        )
        session.flush()
        return station_id

    def test_flags_readings_already_stored_outside_the_bounds(self, session: Session) -> None:
        # The CO readings that arrived before the guard: 0.00137 is ppm stored as ppb.
        self._store(session, [0.00137, 1.2, 60.0], Pollutant.CO)

        flagged = observation_repository.reflag_measurements(session, Pollutant.CO, 0.05, 50.0)

        assert flagged == 2
        latest = observation_repository.latest_reading_per_station(session, Pollutant.CO)
        assert [row[6] for row in latest] == [pytest.approx(1.2)]

    def test_loosening_a_bound_restores_a_reading_and_never_edits_it(
        self, session: Session
    ) -> None:
        self._store(session, [0.01], Pollutant.CO)
        observation_repository.reflag_measurements(session, Pollutant.CO, 0.05, 50.0)

        flagged = observation_repository.reflag_measurements(session, Pollutant.CO, 0.0, 50.0)

        assert flagged == 0
        latest = observation_repository.latest_reading_per_station(session, Pollutant.CO)
        assert latest[0][6] == pytest.approx(0.01)

    def test_leaves_other_pollutants_alone(self, session: Session) -> None:
        self._store(session, [0.01], Pollutant.PM25)

        observation_repository.reflag_measurements(session, Pollutant.CO, 0.05, 50.0)

        assert len(observation_repository.latest_reading_per_station(session, Pollutant.PM25)) == 1
