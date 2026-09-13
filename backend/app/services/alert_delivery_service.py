"""Delivering recorded alerts to the systems authorities actually read.

Split from ``alert_service`` because delivery and detection fail differently and
should not be able to take each other down. Detection is fast, local and
deterministic; delivery depends on somebody else's endpoint being up. Running
them inline would mean a slow webhook stalls detection and a failed one loses
the alert, so dispatch records and this drains.

The failure behaviour is the part that matters. An alert that could not be
delivered keeps ``delivered_at`` null and gains the reason, so it stays in the
queue and stays visible. Marking it delivered on failure would lose it silently,
and an accountability trail that can silently lose an alert is not one.

When no endpoint is configured, nothing is claimed to have been sent. The alert
remains recorded and undelivered, which is the honest state of a deployment that
has not been told where to send anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.enums import AlertKind
from app.core.exceptions import AirWatchError
from app.core.logging import get_logger
from app.external.base import JsonValue
from app.external.webhook_client import WebhookClient
from app.repositories import alert_repository
from app.repositories.alert_repository import UndeliveredAlert

logger = get_logger(__name__)

#: Most alerts one delivery run attempts. Bounded so a backlog is drained in
#: predictable batches rather than in one unbounded burst against an endpoint
#: that may already be struggling.
MAX_DELIVERIES_PER_RUN = 50

#: Longest failure reason stored, matching the column width.
_MAX_ERROR_CHARS = 512


@dataclass(frozen=True, slots=True)
class DeliveryOutcome:
    """What one delivery run achieved."""

    attempted: int
    delivered: int
    failed: int

    #: True when no endpoint is configured, so nothing was even attempted.
    #: Distinct from zero pending: one means nothing to send, the other means
    #: nowhere to send it.
    endpoint_configured: bool


def _payload(alert: UndeliveredAlert) -> JsonValue:
    """Render an alert as the event a receiving system files.

    Carries expected alongside observed. A receiver given only the
    concentration cannot tell a local source from a bad day across the whole
    city, and only one of those is theirs to act on.
    """
    longitude, latitude = alert.coordinates
    is_coordination = alert.kind is AlertKind.COORDINATION
    return {
        "event": ("airwatch.coordination_request" if is_coordination else "airwatch.hotspot_alert"),
        "alert_id": alert.alert_id,
        "kind": alert.kind.value,
        "authority": {"id": alert.authority_id, "name": alert.authority_name},
        "requested_action": (
            {
                "inspect_source": alert.source_name,
                "attribution_confidence": alert.source_confidence,
                "reason": (
                    "The hotspot is in a neighbouring jurisdiction; the likeliest "
                    "upwind source is on your ground. The confidence ranks a "
                    "candidate and does not establish a cause."
                ),
            }
            if is_coordination
            else None
        ),
        "location": {
            "type": "Point",
            "coordinates": [longitude, latitude],
            "station_name": alert.station_name,
        },
        "pollutant": alert.pollutant.value,
        "observed_at": {
            "first_seen": alert.first_seen_at.isoformat(),
            "last_seen": alert.last_seen_at.isoformat(),
        },
        "measurement": {
            "peak_observed": alert.peak_observed,
            "peak_expected": alert.peak_observed - alert.peak_excess,
            "peak_excess": alert.peak_excess,
            "standardised_excess": alert.peak_z,
            "unit": "ug/m3",
        },
        "interpretation": (
            f"{alert.peak_observed:.0f} ug/m3 where the surrounding network predicted "
            f"{alert.peak_observed - alert.peak_excess:.0f}. The excess, not the "
            "concentration, is what locates a source."
        ),
    }


async def deliver_pending(
    session: Session,
    settings: Settings,
    *,
    limit: int = MAX_DELIVERIES_PER_RUN,
    now: datetime | None = None,
) -> DeliveryOutcome:
    """Attempt delivery of every alert still waiting.

    Args:
        session: Database session.
        settings: Configuration, for the endpoint URL.
        limit: Most alerts to attempt in one run.
        now: Reference time, injectable for tests.

    Returns:
        What the run achieved. ``endpoint_configured`` false means nothing was
        attempted because nowhere was configured to send to -- reported rather
        than treated as success.
    """
    pending = alert_repository.undelivered(session, limit=limit)

    if not settings.alert_webhook_url:
        logger.warning("alerts.no_endpoint_configured", pending=len(pending))
        return DeliveryOutcome(
            attempted=0,
            delivered=0,
            failed=0,
            endpoint_configured=False,
        )

    delivered = 0
    failed = 0

    async with WebhookClient(settings.alert_webhook_url) as client:
        for alert in pending:
            try:
                status = await client.deliver(_payload(alert))
            except AirWatchError as error:
                # Typed and expected: the endpoint is down, slow or refusing.
                # The alert keeps its place in the queue.
                alert_repository.record_delivery(
                    session,
                    alert.alert_id,
                    delivered_at=None,
                    error=f"{error.code}: {error.message}"[:_MAX_ERROR_CHARS],
                )
                failed += 1
                continue

            alert_repository.record_delivery(
                session,
                alert.alert_id,
                delivered_at=now or datetime.now(UTC),
                error=None,
            )
            delivered += 1
            logger.info(
                "alerts.delivered",
                alert_id=alert.alert_id,
                authority_id=alert.authority_id,
                status=status,
            )

    logger.info(
        "alerts.delivery_run",
        attempted=len(pending),
        delivered=delivered,
        failed=failed,
    )
    return DeliveryOutcome(
        attempted=len(pending),
        delivered=delivered,
        failed=failed,
        endpoint_configured=True,
    )


def pending_count(session: Session) -> int:
    """How many alerts are waiting on delivery."""
    return len(alert_repository.undelivered(session, limit=MAX_DELIVERIES_PER_RUN))
