"""Turning a detection into someone's responsibility.

Detection and attribution are worth nothing if the finding stops at a dashboard.
This service is the step that makes a hotspot actionable: persist the episode,
work out whose ground it sits on, notify them once, and keep the record of what
they did about it.

The rules themselves -- who to notify when jurisdictions overlap, when a repeat
is suppressed, whether a transition is legal, what counts as overdue -- all live
in ``core/alerting`` as pure functions. This layer only supplies them with
stored state and writes the result back, which is why the rules can be tested
exhaustively without a database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.alerting import (
    AlertRecord,
    SlaBreach,
    acknowledge,
    choose_authority,
    find_sla_breaches,
    resolve,
    should_suppress,
)
from app.core.cities import in_city
from app.core.enums import AlertStatus, PilotCity, Pollutant
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.ml.hotspot_detection import Hotspot, detect_over_window
from app.repositories import alert_repository, observation_repository
from app.repositories.alert_repository import AlertDetail, HotspotRow

logger = get_logger(__name__)

#: Default window, in hours, that a dispatch run looks back over.
DEFAULT_DISPATCH_WINDOW_HOURS = 24


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """What one dispatch run did, in enough detail to explain itself.

    ``unrouted`` is reported rather than discarded. A hotspot nobody is
    responsible for is a gap in the authority registry, and silently dropping it
    would make an incomplete registry look like a quiet day.
    """

    detected: int
    stored: int
    raised: list[AlertRecord]
    suppressed: int
    unrouted: int


def dispatch(
    session: Session,
    pollutant: Pollutant,
    *,
    window_hours: int = DEFAULT_DISPATCH_WINDOW_HOURS,
    now: datetime | None = None,
) -> DispatchOutcome:
    """Detect hotspots over a recent window and route alerts for them.

    Args:
        session: Database session.
        pollutant: Pollutant to analyse.
        window_hours: How far back to look.
        now: Reference time, injectable for tests.

    Returns:
        A summary of what was detected, stored, raised and suppressed.
    """
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)

    readings = observation_repository.observed_readings_in_window(session, pollutant, since)
    hotspots = detect_over_window(readings)

    raised: list[AlertRecord] = []
    suppressed = 0
    unrouted = 0

    for hotspot in hotspots:
        hotspot_id = alert_repository.upsert_hotspot(session, _hotspot_row(hotspot, pollutant))

        authority_id = choose_authority(
            alert_repository.authorities_containing(session, hotspot.coordinates)
        )
        if authority_id is None:
            unrouted += 1
            continue

        existing = alert_repository.alerts_for(session, hotspot_id, authority_id)
        if should_suppress(existing, reference):
            suppressed += 1
            continue

        raised.append(
            alert_repository.create_alert(
                session,
                hotspot_id=hotspot_id,
                authority_id=authority_id,
                sent_at=reference,
            )
        )

    logger.info(
        "alerts.dispatched",
        pollutant=pollutant.value,
        window_hours=window_hours,
        detected=len(hotspots),
        raised=len(raised),
        suppressed=suppressed,
        unrouted=unrouted,
    )

    return DispatchOutcome(
        detected=len(hotspots),
        stored=len(hotspots),
        raised=raised,
        suppressed=suppressed,
        unrouted=unrouted,
    )


def _hotspot_row(hotspot: Hotspot, pollutant: Pollutant) -> HotspotRow:
    """Convert a detected episode into its stored form."""
    return HotspotRow(
        h3_cell=hotspot.h3_cell,
        coordinates=hotspot.coordinates,
        station_id=hotspot.station_id,
        pollutant=pollutant,
        first_seen_at=hotspot.first_seen_at,
        last_seen_at=hotspot.last_seen_at,
        intervals=hotspot.intervals,
        peak_z=hotspot.peak_z,
        peak_residual=hotspot.peak_residual,
        peak_observed=hotspot.peak_observed,
    )


def list_alerts(
    session: Session, *, status: AlertStatus | None = None, city: PilotCity | None = None
) -> list[AlertDetail]:
    """The alert inbox, most urgent first, optionally for one city."""
    return [
        detail
        for detail in alert_repository.list_alert_details(session, status=status)
        if in_city(detail.coordinates, city)
    ]


def acknowledge_alert(
    session: Session, alert_id: int, *, now: datetime | None = None
) -> AlertDetail:
    """Record that an authority has seen an alert.

    Raises:
        NotFoundError: No alert with this id.
        ValidationError: The transition is not legal, raised by the rules in
            ``core/alerting``.
    """
    record = _require(session, alert_id)
    updated = acknowledge(record, now or datetime.now(UTC))
    alert_repository.save_alert_state(session, updated)

    logger.info("alerts.acknowledged", alert_id=alert_id, authority_id=updated.authority_id)
    return _detail(session, alert_id)


def resolve_alert(
    session: Session, alert_id: int, note: str, *, now: datetime | None = None
) -> AlertDetail:
    """Close an alert with a note describing what was found or done.

    Raises:
        NotFoundError: No alert with this id.
        ValidationError: The note is empty or the transition is not legal.
    """
    record = _require(session, alert_id)
    updated = resolve(record, now or datetime.now(UTC), note)
    alert_repository.save_alert_state(session, updated, note=note)

    logger.info("alerts.resolved", alert_id=alert_id, authority_id=updated.authority_id)
    return _detail(session, alert_id)


def sla_breaches(
    session: Session, *, now: datetime | None = None, city: PilotCity | None = None
) -> list[SlaBreach]:
    """Alerts whose response window has elapsed, longest overdue first.

    This is the output that makes non-response visible. Without it an ignored
    alert is indistinguishable from one that was never sent, and the
    accountability claim collapses.
    """
    open_alerts = [
        AlertRecord(
            alert_id=detail.alert_id,
            hotspot_id=detail.hotspot_id,
            authority_id=detail.authority_id,
            status=detail.status,
            sent_at=detail.sent_at,
            acknowledged_at=detail.acknowledged_at,
            resolved_at=detail.resolved_at,
        )
        for detail in alert_repository.list_alert_details(session)
        if in_city(detail.coordinates, city)
    ]
    return find_sla_breaches(open_alerts, now)


def _require(session: Session, alert_id: int) -> AlertRecord:
    """Load an alert or raise a typed not-found."""
    record = alert_repository.get_alert(session, alert_id)
    if record is None:
        raise NotFoundError("alert", str(alert_id))
    return record


def _detail(session: Session, alert_id: int) -> AlertDetail:
    """Re-read an alert in its console form after a transition."""
    for detail in alert_repository.list_alert_details(session):
        if detail.alert_id == alert_id:
            return detail
    raise NotFoundError("alert", str(alert_id))  # pragma: no cover - just written.
