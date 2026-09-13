"""Alert routing and the accountability trail.

Detection and attribution are worth nothing if the finding stops here. This is
the part that turns a measurement into an action: work out who is responsible
for the ground the hotspot sits on, notify them once, and record what they did
about it.

Three rules shape the design, and all three exist to protect the one thing the
chain depends on — that alerts keep being read.

* **Route geographically, not per station.** A hotspot can appear anywhere on
  the grid, including ground no monitor covers, so responsibility is decided by
  which jurisdiction contains it -- and, when the likeliest source lies across a
  boundary, the jurisdiction containing the source is asked to act as well.
* **Alert once per episode.** A source that burns for eight hours is one event.
  Emitting an alert every detection interval turns a console into noise, and a
  console that is noise is a console nobody opens.
* **Record silence as a finding.** An alert sent and never acknowledged is
  itself evidence. The timestamps here are what make "nobody responded for two
  days" a statement backed by a record rather than an accusation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.core.constants import (
    ALERT_ACK_SLA_HOURS,
    ALERT_RESOLUTION_SLA_HOURS,
    ALERT_SUPPRESSION_HOURS,
    COORDINATION_MIN_CONFIDENCE,
)
from app.core.enums import AlertStatus
from app.core.exceptions import ValidationError
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AlertRecord:
    """The state of one routed alert, as far as escalation logic is concerned."""

    alert_id: int
    hotspot_id: int
    authority_id: int
    status: AlertStatus
    sent_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SlaBreach:
    """An alert that has outlived the time its authority had to respond."""

    alert: AlertRecord
    stage: str
    overdue_by: timedelta

    def render(self) -> str:
        hours = self.overdue_by.total_seconds() / 3600.0
        return f"alert {self.alert.alert_id} overdue for {self.stage} by {hours:.1f} h"


def choose_authority(
    candidates: list[tuple[int, int]],
) -> int | None:
    """Pick which authority to notify when jurisdictions overlap.

    Args:
        candidates: ``(authority_id, escalation_tier)`` pairs whose jurisdiction
            contains the hotspot, in any order.

    Returns:
        The id of the lowest-tier authority, or None when none contains it.
        Lowest tier first means a municipal body is reached before a state
        board, rather than both being alerted for the same event and each
        assuming the other is handling it.
    """
    if not candidates:
        return None
    return min(candidates, key=lambda pair: pair[1])[0]


@dataclass(frozen=True, slots=True)
class SourceJurisdiction:
    """A ranked candidate source, and the authority whose ground it sits on."""

    source_name: str
    confidence: float
    #: The responsible authority chosen by :func:`choose_authority` for the
    #: source's position, or None when no registered jurisdiction contains it.
    authority_id: int | None


@dataclass(frozen=True, slots=True)
class CoordinationTarget:
    """An authority asked to act on a source for a neighbouring jurisdiction."""

    authority_id: int
    source_name: str
    confidence: float


def coordination_targets(
    local_authority_id: int | None,
    candidates: list[SourceJurisdiction],
    *,
    min_confidence: float = COORDINATION_MIN_CONFIDENCE,
) -> list[CoordinationTarget]:
    """Decide which other jurisdictions to ask for help with one hotspot.

    The authority a hotspot sits in often cannot act on its cause: the kiln, the
    depot or the fire is across a district or state line. The body that can is
    the one whose ground holds the source, so it receives a coordination request
    alongside the local alert.

    Args:
        local_authority_id: The authority already alerted for the hotspot itself,
            or None when the hotspot fell inside no jurisdiction.
        candidates: Ranked sources with the authority containing each.
        min_confidence: Candidates below this do not justify spending another
            body's inspection capacity.

    Returns:
        One target per authority, for its most plausible source, most plausible
        first. The local authority is never a target -- it already has the
        alert -- and a source on unregistered ground has nobody to ask.
    """
    best: dict[int, SourceJurisdiction] = {}
    for candidate in candidates:
        if candidate.authority_id is None or candidate.authority_id == local_authority_id:
            continue
        if candidate.confidence < min_confidence:
            continue
        current = best.get(candidate.authority_id)
        if current is None or candidate.confidence > current.confidence:
            best[candidate.authority_id] = candidate

    return sorted(
        (
            CoordinationTarget(
                authority_id=authority_id,
                source_name=candidate.source_name,
                confidence=candidate.confidence,
            )
            for authority_id, candidate in best.items()
        ),
        key=lambda target: target.confidence,
        reverse=True,
    )


def should_suppress(
    existing: list[AlertRecord],
    now: datetime,
    *,
    suppression_hours: int = ALERT_SUPPRESSION_HOURS,
) -> bool:
    """Whether an alert for this hotspot and authority is already in flight.

    Args:
        existing: Alerts already raised for this hotspot and authority.
        now: Current time, injected so the decision is deterministic in tests.
        suppression_hours: Window within which a repeat is suppressed.

    Returns:
        True when a recent alert is still open. A resolved alert does not
        suppress a new one: if the same location flares up again after being
        closed, that is a new event and the authority needs to know.
    """
    cutoff = now - timedelta(hours=suppression_hours)
    return any(
        alert.status is not AlertStatus.RESOLVED and alert.sent_at >= cutoff for alert in existing
    )


def acknowledge(alert: AlertRecord, at_time: datetime) -> AlertRecord:
    """Record that an authority has seen an alert.

    Raises:
        ValidationError: The alert is already resolved, or the acknowledgement
            predates the alert. Both would corrupt the response-time record
            that the accountability argument rests on.
    """
    if alert.status is AlertStatus.RESOLVED:
        raise ValidationError(f"Alert {alert.alert_id} is already resolved.")
    if at_time < alert.sent_at:
        raise ValidationError(
            f"Alert {alert.alert_id} cannot be acknowledged before it was sent.",
        )
    return AlertRecord(
        alert_id=alert.alert_id,
        hotspot_id=alert.hotspot_id,
        authority_id=alert.authority_id,
        status=AlertStatus.ACKNOWLEDGED,
        sent_at=alert.sent_at,
        acknowledged_at=at_time,
        resolved_at=alert.resolved_at,
    )


def resolve(alert: AlertRecord, at_time: datetime, note: str) -> AlertRecord:
    """Close an alert with a note describing what was found or done.

    The note is required. A resolution with no explanation records that someone
    clicked a button, which is not the same as recording that something was
    done, and the difference is the entire value of the trail.

    Raises:
        ValidationError: The note is empty, or the resolution predates the alert.
    """
    if not note.strip():
        raise ValidationError(
            f"Alert {alert.alert_id} cannot be resolved without a note describing the outcome.",
        )
    if at_time < alert.sent_at:
        raise ValidationError(
            f"Alert {alert.alert_id} cannot be resolved before it was sent.",
        )
    return AlertRecord(
        alert_id=alert.alert_id,
        hotspot_id=alert.hotspot_id,
        authority_id=alert.authority_id,
        status=AlertStatus.RESOLVED,
        sent_at=alert.sent_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=at_time,
    )


def find_sla_breaches(
    alerts: list[AlertRecord],
    now: datetime | None = None,
    *,
    ack_sla_hours: int = ALERT_ACK_SLA_HOURS,
    resolution_sla_hours: int = ALERT_RESOLUTION_SLA_HOURS,
) -> list[SlaBreach]:
    """Find alerts whose response window has elapsed.

    Args:
        alerts: Alerts to check.
        now: Current time, defaulting to now.
        ack_sla_hours: Hours an authority has to acknowledge.
        resolution_sla_hours: Hours an acknowledged alert has to be resolved.

    Returns:
        Breaches, longest overdue first. This is the output that makes
        non-response visible; without it an ignored alert is indistinguishable
        from one that was never sent.
    """
    reference = now or datetime.now(UTC)
    breaches: list[SlaBreach] = []

    for alert in alerts:
        if alert.status is AlertStatus.RESOLVED:
            continue

        if alert.acknowledged_at is None:
            deadline = alert.sent_at + timedelta(hours=ack_sla_hours)
            stage = "acknowledgement"
        else:
            deadline = alert.acknowledged_at + timedelta(hours=resolution_sla_hours)
            stage = "resolution"

        if reference > deadline:
            breaches.append(SlaBreach(alert=alert, stage=stage, overdue_by=reference - deadline))

    breaches.sort(key=lambda breach: breach.overdue_by, reverse=True)
    return breaches
