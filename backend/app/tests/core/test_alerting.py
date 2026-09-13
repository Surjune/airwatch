"""Tests for alert routing, suppression and the accountability trail."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.alerting import (
    AlertRecord,
    CoordinationTarget,
    SourceJurisdiction,
    acknowledge,
    choose_authority,
    coordination_targets,
    find_sla_breaches,
    resolve,
    should_suppress,
)
from app.core.constants import COORDINATION_MIN_CONFIDENCE
from app.core.enums import AlertStatus
from app.core.exceptions import ValidationError

SENT_AT = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)


def alert(
    *,
    alert_id: int = 1,
    status: AlertStatus = AlertStatus.SENT,
    sent_at: datetime = SENT_AT,
    acknowledged_at: datetime | None = None,
    resolved_at: datetime | None = None,
) -> AlertRecord:
    return AlertRecord(
        alert_id=alert_id,
        hotspot_id=100,
        authority_id=7,
        status=status,
        sent_at=sent_at,
        acknowledged_at=acknowledged_at,
        resolved_at=resolved_at,
    )


class TestRouting:
    def test_the_lowest_tier_authority_is_notified(self) -> None:
        # A municipal body before a state board. Alerting both invites each to
        # assume the other is handling it.
        assert choose_authority([(5, 2), (9, 1), (3, 3)]) == 9

    def test_a_single_jurisdiction_is_used_directly(self) -> None:
        assert choose_authority([(4, 2)]) == 4

    def test_ground_outside_every_jurisdiction_routes_nowhere(self) -> None:
        # Returning None rather than a nearest guess: sending an inspector to
        # somewhere outside their remit wastes the alert and their time.
        assert choose_authority([]) is None


class TestCoordination:
    LOCAL = 1

    def test_asks_the_jurisdiction_that_holds_the_source(self) -> None:
        targets = coordination_targets(
            self.LOCAL, [SourceJurisdiction("Brick kiln cluster", 0.72, authority_id=2)]
        )

        assert targets == [
            CoordinationTarget(authority_id=2, source_name="Brick kiln cluster", confidence=0.72)
        ]

    def test_never_asks_the_local_authority_twice(self) -> None:
        # It already has the alert for the hotspot itself.
        assert coordination_targets(self.LOCAL, [SourceJurisdiction("Depot", 0.9, 1)]) == []

    def test_a_source_on_unregistered_ground_has_nobody_to_ask(self) -> None:
        assert coordination_targets(self.LOCAL, [SourceJurisdiction("Fire", 0.9, None)]) == []

    def test_a_weak_candidate_does_not_spend_a_neighbours_inspectors(self) -> None:
        weak = SourceJurisdiction("Landfill", COORDINATION_MIN_CONFIDENCE - 0.01, 2)

        assert coordination_targets(self.LOCAL, [weak]) == []

    def test_a_candidate_at_the_threshold_is_sent(self) -> None:
        edge = SourceJurisdiction("Landfill", COORDINATION_MIN_CONFIDENCE, 2)

        assert len(coordination_targets(self.LOCAL, [edge])) == 1

    def test_one_request_per_authority_for_its_most_plausible_source(self) -> None:
        targets = coordination_targets(
            self.LOCAL,
            [
                SourceJurisdiction("Kiln A", 0.55, 2),
                SourceJurisdiction("Kiln B", 0.81, 2),
                SourceJurisdiction("Fire", 0.66, 3),
            ],
        )

        assert [(t.authority_id, t.source_name) for t in targets] == [(2, "Kiln B"), (3, "Fire")]

    def test_an_unrouted_hotspot_can_still_reach_the_sources_authority(self) -> None:
        # No jurisdiction holds the hotspot, but one holds the source: that body
        # is still the one able to act.
        targets = coordination_targets(None, [SourceJurisdiction("Kiln", 0.7, 4)])

        assert [target.authority_id for target in targets] == [4]


class TestSuppression:
    def test_an_open_alert_suppresses_a_repeat(self) -> None:
        # An eight-hour fire is one event. Alerting every detection interval
        # turns the console into noise, and noise stops being read.
        existing = [alert(status=AlertStatus.SENT, sent_at=SENT_AT)]
        assert should_suppress(existing, SENT_AT + timedelta(hours=2)) is True

    def test_an_acknowledged_alert_still_suppresses(self) -> None:
        existing = [
            alert(status=AlertStatus.ACKNOWLEDGED, acknowledged_at=SENT_AT + timedelta(minutes=30))
        ]
        assert should_suppress(existing, SENT_AT + timedelta(hours=1)) is True

    def test_a_resolved_alert_does_not_suppress_a_new_flare_up(self) -> None:
        # The same location burning again after being closed is a new event,
        # and the authority needs to know.
        existing = [alert(status=AlertStatus.RESOLVED, resolved_at=SENT_AT + timedelta(hours=1))]
        assert should_suppress(existing, SENT_AT + timedelta(hours=2)) is False

    def test_suppression_expires(self) -> None:
        existing = [alert(status=AlertStatus.SENT, sent_at=SENT_AT)]
        assert should_suppress(existing, SENT_AT + timedelta(hours=48)) is False

    def test_no_history_never_suppresses(self) -> None:
        assert should_suppress([], SENT_AT) is False


class TestAcknowledgement:
    def test_records_when_the_authority_saw_it(self) -> None:
        seen_at = SENT_AT + timedelta(minutes=45)
        updated = acknowledge(alert(), seen_at)

        assert updated.status is AlertStatus.ACKNOWLEDGED
        assert updated.acknowledged_at == seen_at

    def test_cannot_acknowledge_a_resolved_alert(self) -> None:
        closed = alert(status=AlertStatus.RESOLVED, resolved_at=SENT_AT + timedelta(hours=1))
        with pytest.raises(ValidationError, match="already resolved"):
            acknowledge(closed, SENT_AT + timedelta(hours=2))

    def test_cannot_acknowledge_before_it_was_sent(self) -> None:
        # Would corrupt the response-time record the accountability case rests on.
        with pytest.raises(ValidationError, match="before it was sent"):
            acknowledge(alert(), SENT_AT - timedelta(hours=1))


class TestResolution:
    def test_records_the_outcome(self) -> None:
        closed_at = SENT_AT + timedelta(hours=3)
        updated = resolve(alert(), closed_at, note="Waste fire extinguished; operator warned.")

        assert updated.status is AlertStatus.RESOLVED
        assert updated.resolved_at == closed_at

    def test_a_note_is_required(self) -> None:
        # A resolution with no explanation records that someone clicked a
        # button, not that anything was done.
        with pytest.raises(ValidationError, match="without a note"):
            resolve(alert(), SENT_AT + timedelta(hours=1), note="   ")

    def test_cannot_resolve_before_it_was_sent(self) -> None:
        with pytest.raises(ValidationError, match="before it was sent"):
            resolve(alert(), SENT_AT - timedelta(hours=1), note="Checked.")

    def test_resolution_preserves_the_acknowledgement_time(self) -> None:
        seen_at = SENT_AT + timedelta(minutes=20)
        acknowledged = acknowledge(alert(), seen_at)
        closed = resolve(acknowledged, SENT_AT + timedelta(hours=4), note="Site inspected.")

        assert closed.acknowledged_at == seen_at


class TestSlaBreaches:
    def test_an_unacknowledged_alert_breaches_first(self) -> None:
        stale = alert(sent_at=SENT_AT)
        breaches = find_sla_breaches([stale], now=SENT_AT + timedelta(hours=5))

        assert len(breaches) == 1
        assert breaches[0].stage == "acknowledgement"

    def test_a_fresh_alert_does_not_breach(self) -> None:
        breaches = find_sla_breaches([alert()], now=SENT_AT + timedelta(minutes=30))
        assert breaches == []

    def test_an_acknowledged_alert_breaches_on_resolution(self) -> None:
        seen = alert(
            status=AlertStatus.ACKNOWLEDGED, acknowledged_at=SENT_AT + timedelta(minutes=30)
        )
        breaches = find_sla_breaches([seen], now=SENT_AT + timedelta(hours=30))

        assert len(breaches) == 1
        assert breaches[0].stage == "resolution"

    def test_a_resolved_alert_never_breaches(self) -> None:
        closed = alert(status=AlertStatus.RESOLVED, resolved_at=SENT_AT + timedelta(hours=1))
        assert find_sla_breaches([closed], now=SENT_AT + timedelta(days=30)) == []

    def test_the_longest_overdue_is_reported_first(self) -> None:
        # This ordering is what makes sustained non-response visible rather than
        # buried among fresher misses.
        recent = alert(alert_id=1, sent_at=SENT_AT)
        ancient = alert(alert_id=2, sent_at=SENT_AT - timedelta(days=5))

        breaches = find_sla_breaches([recent, ancient], now=SENT_AT + timedelta(hours=6))

        assert [breach.alert.alert_id for breach in breaches] == [2, 1]

    def test_a_breach_renders_for_a_human(self) -> None:
        breaches = find_sla_breaches([alert()], now=SENT_AT + timedelta(hours=5))
        assert "overdue for acknowledgement" in breaches[0].render()
