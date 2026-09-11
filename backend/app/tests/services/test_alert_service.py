"""End-to-end tests for the alert chain, against a real database.

This is the pillar that converts an analysis into an action, and almost every
step of it is a database operation: the jurisdiction lookup is ``ST_Contains``,
suppression depends on what is already stored, and the accountability trail *is*
the stored timestamps. Stubbing the repository would test nothing that matters.

The chain is exercised as a sequence -- detect, route, acknowledge, resolve --
because the interesting failures are transitions, not individual calls.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.core.constants import ALERT_ACK_SLA_HOURS
from app.core.enums import AlertStatus, Pollutant, StationTier
from app.core.exceptions import NotFoundError, ValidationError
from app.repositories import alert_repository, observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow
from app.services import alert_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 2, 10, 9, 0, tzinfo=UTC)

#: A synthetic network tight enough for fusion to predict each station from its
#: neighbours. Station 1 is the planted source.
POSITIONS: dict[str, tuple[float, float]] = {
    "dirty": (77.200, 28.600),
    "clean-a": (77.220, 28.600),
    "clean-b": (77.200, 28.615),
    "clean-c": (77.185, 28.590),
    "clean-d": (77.215, 28.612),
}

BACKGROUND_UGM3 = 40.0
HOTSPOT_UGM3 = 400.0

#: A box comfortably containing the whole synthetic network.
DELHI_JURISDICTION: list[tuple[float, float]] = [
    (77.0, 28.4),
    (77.4, 28.4),
    (77.4, 28.8),
    (77.0, 28.8),
]

#: A box containing none of it, for testing that routing is really spatial.
ELSEWHERE_JURISDICTION: list[tuple[float, float]] = [
    (72.7, 18.8),
    (73.0, 18.8),
    (73.0, 19.2),
    (72.7, 19.2),
]


def _seed_network(session: Session, hours: int = 4, anchor: datetime = NOW) -> None:
    """Create the stations and several hours of readings containing one hotspot.

    ``anchor`` is the most recent hour. Tests that drive the service pass a fixed
    reference; tests that drive an HTTP endpoint cannot, because the route reads
    the clock itself, so they anchor to the present instead.
    """
    for label, coordinates in POSITIONS.items():
        station_id = station_repository.upsert_station(
            session,
            source="test",
            source_station_id=label,
            name=label,
            tier=StationTier.REFERENCE,
            coordinates=coordinates,
        )
        value = HOTSPOT_UGM3 if label == "dirty" else BACKGROUND_UGM3
        observation_repository.upsert_measurements(
            session,
            [
                MeasurementRow(
                    station_id=station_id,
                    observed_at=anchor - timedelta(hours=hour),
                    pollutant=Pollutant.PM25,
                    value_raw=value,
                    unit="ug/m3",
                )
                for hour in range(hours)
            ],
        )
    session.flush()


def _seed_authority(session: Session, name: str = "Delhi Pollution Control Committee") -> int:
    return alert_repository.upsert_authority(
        session,
        name=name,
        jurisdiction=DELHI_JURISDICTION,
        contact_email="control@example.invalid",
        escalation_tier=1,
    )


class TestDispatch:
    def test_routes_a_hotspot_to_the_authority_that_contains_it(
        self, session: Session
    ) -> None:
        _seed_network(session)
        authority_id = _seed_authority(session)
        session.flush()

        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert outcome.detected == 1
        assert len(outcome.raised) == 1
        assert outcome.raised[0].authority_id == authority_id

    def test_a_hotspot_outside_every_jurisdiction_is_reported_not_dropped(
        self, session: Session
    ) -> None:
        # An incomplete authority registry must not read as a quiet day. This is
        # the difference between "nobody needs to act" and "we do not know who
        # to tell", and only one of those is good news.
        _seed_network(session)
        alert_repository.upsert_authority(
            session,
            name="Somewhere Else Board",
            jurisdiction=ELSEWHERE_JURISDICTION,
        )
        session.flush()

        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert outcome.detected == 1
        assert outcome.raised == []
        assert outcome.unrouted == 1

    def test_the_lowest_tier_authority_is_notified(self, session: Session) -> None:
        # Overlapping jurisdictions must not both be alerted, or each assumes the
        # other is handling it.
        _seed_network(session)
        municipal = alert_repository.upsert_authority(
            session,
            name="Municipal Corporation",
            jurisdiction=DELHI_JURISDICTION,
            escalation_tier=1,
        )
        alert_repository.upsert_authority(
            session,
            name="State Board",
            jurisdiction=DELHI_JURISDICTION,
            escalation_tier=2,
        )
        session.flush()

        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert [alert.authority_id for alert in outcome.raised] == [municipal]

    def test_a_second_run_suppresses_rather_than_repeats(self, session: Session) -> None:
        # A source that burns for eight hours is one event. Alerting every
        # detection interval turns the console into noise, and a console that is
        # noise is one nobody opens.
        _seed_network(session)
        _seed_authority(session)
        session.flush()

        first = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
        second = alert_service.dispatch(
            session, Pollutant.PM25, window_hours=24, now=NOW + timedelta(hours=1)
        )

        assert len(first.raised) == 1
        assert second.raised == []
        assert second.suppressed == 1

    def test_re_detecting_the_same_episode_does_not_duplicate_the_hotspot(
        self, session: Session
    ) -> None:
        _seed_network(session)
        _seed_authority(session)
        session.flush()

        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert alert_repository.count_hotspots(session) == 1

    def test_a_quiet_network_raises_nothing(self, session: Session) -> None:
        for label, coordinates in POSITIONS.items():
            station_id = station_repository.upsert_station(
                session,
                source="test",
                source_station_id=label,
                name=label,
                tier=StationTier.REFERENCE,
                coordinates=coordinates,
            )
            observation_repository.upsert_measurements(
                session,
                [
                    MeasurementRow(
                        station_id=station_id,
                        observed_at=NOW - timedelta(hours=hour),
                        pollutant=Pollutant.PM25,
                        value_raw=BACKGROUND_UGM3,
                        unit="ug/m3",
                    )
                    for hour in range(4)
                ],
            )
        _seed_authority(session)
        session.flush()

        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert outcome.detected == 0
        assert outcome.raised == []


class TestInbox:
    def test_an_alert_carries_the_excess_not_just_the_concentration(
        self, session: Session
    ) -> None:
        # An inbox ordered by concentration sends an inspector wherever the
        # number is biggest, which on a bad day is everywhere.
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        alert = alert_service.list_alerts(session)[0]

        assert alert.peak_observed == pytest.approx(HOTSPOT_UGM3)
        assert alert.peak_excess > HOTSPOT_UGM3 - BACKGROUND_UGM3 - 1
        assert alert.station_name == "dirty"
        assert alert.authority_name == "Delhi Pollution Control Committee"

    def test_filters_by_status(self, session: Session) -> None:
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert len(alert_service.list_alerts(session, status=AlertStatus.SENT)) == 1
        assert alert_service.list_alerts(session, status=AlertStatus.RESOLVED) == []


class TestLifecycle:
    def _one_alert(self, session: Session) -> int:
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
        return outcome.raised[0].alert_id

    def test_acknowledgement_is_recorded(self, session: Session) -> None:
        alert_id = self._one_alert(session)

        updated = alert_service.acknowledge_alert(
            session, alert_id, now=NOW + timedelta(hours=1)
        )

        assert updated.status is AlertStatus.ACKNOWLEDGED
        assert updated.acknowledged_at == NOW + timedelta(hours=1)

    def test_resolution_records_the_note(self, session: Session) -> None:
        alert_id = self._one_alert(session)
        alert_service.acknowledge_alert(session, alert_id, now=NOW + timedelta(hours=1))

        updated = alert_service.resolve_alert(
            session,
            alert_id,
            "Open waste burning behind the terminal, extinguished and fined.",
            now=NOW + timedelta(hours=3),
        )

        assert updated.status is AlertStatus.RESOLVED
        assert updated.resolution_note is not None
        assert "extinguished" in updated.resolution_note

    def test_resolving_without_a_note_is_refused(self, session: Session) -> None:
        # A resolution with no explanation records that someone clicked a
        # button, which is not the same as recording that something was done.
        alert_id = self._one_alert(session)

        with pytest.raises(ValidationError, match="note"):
            alert_service.resolve_alert(session, alert_id, "   ", now=NOW + timedelta(hours=1))

    def test_acknowledging_a_resolved_alert_is_refused(self, session: Session) -> None:
        alert_id = self._one_alert(session)
        alert_service.resolve_alert(
            session, alert_id, "Inspected, nothing found.", now=NOW + timedelta(hours=2)
        )

        with pytest.raises(ValidationError, match="already resolved"):
            alert_service.acknowledge_alert(session, alert_id, now=NOW + timedelta(hours=3))

    def test_an_unknown_alert_is_a_typed_not_found(self, session: Session) -> None:
        with pytest.raises(NotFoundError):
            alert_service.acknowledge_alert(session, 999_999, now=NOW)


class TestSlaBreaches:
    def test_silence_past_the_deadline_becomes_a_finding(self, session: Session) -> None:
        # The point of the trail: an ignored alert has to be distinguishable
        # from one that was never sent.
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        overdue = NOW + timedelta(hours=ALERT_ACK_SLA_HOURS + 1)
        breaches = alert_service.sla_breaches(session, now=overdue)

        assert len(breaches) == 1
        assert breaches[0].stage == "acknowledgement"
        assert breaches[0].overdue_by > timedelta(0)

    def test_an_alert_inside_its_window_is_not_a_breach(self, session: Session) -> None:
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)

        assert alert_service.sla_breaches(session, now=NOW + timedelta(minutes=30)) == []

    def test_a_resolved_alert_never_breaches(self, session: Session) -> None:
        _seed_network(session)
        _seed_authority(session)
        session.flush()
        outcome = alert_service.dispatch(session, Pollutant.PM25, window_hours=24, now=NOW)
        alert_service.resolve_alert(
            session, outcome.raised[0].alert_id, "Handled.", now=NOW + timedelta(hours=1)
        )

        far_future = NOW + timedelta(days=30)
        assert alert_service.sla_breaches(session, now=far_future) == []
