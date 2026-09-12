"""Tests for the federation dashboard.

The assertion that matters most separates two things a careless implementation
would merge: a city whose monitors have never reported, and a city whose
readings have merely stopped arriving here. The first is a monitoring gap and is
the entire argument for federating. The second is this deployment's ingestion
falling behind, and reporting it as the first would be a false claim about a
real place with a real monitoring network.

The rest is about reporting the transfer result as measured, including when it
says the design did not work.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.constants import PILOT_CITY_CENTRES, PILOT_REPORTING_WINDOW_HOURS
from app.core.enums import Pollutant, StationTier
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow
from app.services import federation_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

DELHI = PILOT_CITY_CENTRES["delhi"]
COIMBATORE = PILOT_CITY_CENTRES["coimbatore"]


def _station(session: Session, label: str, coordinates: tuple[float, float]) -> int:
    return station_repository.upsert_station(
        session,
        source="test",
        source_station_id=label,
        name=label,
        tier=StationTier.REFERENCE,
        coordinates=coordinates,
    )


def _reading(session: Session, station_id: int, observed_at: datetime) -> None:
    observation_repository.upsert_measurements(
        session,
        [
            MeasurementRow(
                station_id=station_id,
                observed_at=observed_at,
                pollutant=Pollutant.PM25,
                value_raw=95.0,
                unit="ug/m3",
            )
        ],
    )
    session.flush()


def _coverage_for(session: Session, node: str) -> federation_service.NodeCoverage:
    return next(item for item in federation_service.node_coverage(session) if item.node == node)


class TestUnmonitoredVersusStale:
    def test_a_station_that_never_reported_is_unmonitored(self, session: Session) -> None:
        # Coimbatore's real situation: a site exists, and it has produced no
        # particulate data at all. That is the gap federation exists to close.
        _station(session, "coimbatore-site", COIMBATORE)
        session.flush()

        coverage = _coverage_for(session, "coimbatore")

        assert coverage.stations == 1
        assert coverage.readings == 0
        assert coverage.is_unmonitored is True
        assert coverage.is_stale is False

    def test_a_station_with_old_data_is_stale_not_unmonitored(self, session: Session) -> None:
        # The distinction that must not be lost. A city with thousands of
        # readings that simply stopped arriving has a working network; calling
        # that a monitoring gap would be a false claim about a real place.
        station_id = _station(session, "delhi-site", DELHI)
        _reading(session, station_id, NOW - timedelta(days=30))

        coverage = _coverage_for(session, "delhi")

        assert coverage.readings == 1
        assert coverage.is_unmonitored is False
        assert coverage.is_stale is True

    def test_a_recent_reading_counts_as_reporting(self, session: Session) -> None:
        station_id = _station(session, "delhi-live", DELHI)
        _reading(session, station_id, datetime.now(UTC) - timedelta(hours=1))

        coverage = _coverage_for(session, "delhi")

        assert coverage.reporting_stations == 1
        assert coverage.is_stale is False
        assert coverage.is_unmonitored is False

    def test_a_station_just_outside_the_window_is_not_reporting(self, session: Session) -> None:
        station_id = _station(session, "delhi-lapsed", DELHI)
        _reading(
            session,
            station_id,
            datetime.now(UTC) - timedelta(hours=PILOT_REPORTING_WINDOW_HOURS + 1),
        )

        assert _coverage_for(session, "delhi").reporting_stations == 0

    def test_silent_stations_are_counted(self, session: Session) -> None:
        # A city can hold several monitors and still have no current particulate
        # data, which is what every published "active stations" count hides.
        live = _station(session, "delhi-a", DELHI)
        _station(session, "delhi-b", (DELHI[0] + 0.01, DELHI[1]))
        _reading(session, live, datetime.now(UTC) - timedelta(minutes=30))

        coverage = _coverage_for(session, "delhi")

        assert coverage.stations == 2
        assert coverage.reporting_stations == 1
        assert coverage.silent_stations == 1


class TestSummary:
    def test_names_an_unmonitored_city_as_a_monitoring_gap(self, session: Session) -> None:
        _station(session, "coimbatore-site", COIMBATORE)
        session.flush()

        summary = federation_service.status(session).summary

        assert "Coimbatore" in summary
        assert "never reported" in summary

    def test_describes_stale_data_as_an_ingestion_problem(self, session: Session) -> None:
        station_id = _station(session, "delhi-site", DELHI)
        _reading(session, station_id, NOW - timedelta(days=30))

        summary = federation_service.status(session).summary

        assert "ingestion falling behind" in summary
        assert "rather than a gap in their network" in summary

    def test_reports_the_harm_without_softening_it(self, session: Session) -> None:
        # The measured result says federation hurt the sparse node. A dashboard
        # that phrased that as provisional would be advertising a design rather
        # than reporting a measurement.
        summary = federation_service.status(session).summary

        assert "measurably harmed" in summary
        assert "Kanpur" in summary


class TestTransferResults:
    def test_the_sparse_node_is_flagged_as_harmed(self) -> None:
        kanpur = next(r for r in federation_service.transfer_results() if r.node == "kanpur")

        assert kanpur.improvement < 0
        assert kanpur.is_harmed is True
        assert kanpur.recommendation == "keep the local model"

    def test_a_change_inside_the_noise_is_not_called_harm(self) -> None:
        delhi = next(r for r in federation_service.transfer_results() if r.node == "delhi")

        assert delhi.is_harmed is False
        assert "noise" in delhi.recommendation

    def test_every_result_publishes_the_sample_it_rests_on(self) -> None:
        # A holdout of a few dozen rows is a signal, not a settled fact, and a
        # reader has to be able to see which they are being shown.
        for result in federation_service.transfer_results():
            assert result.train_rows > 0
            assert result.test_rows > 0
