"""Alert console endpoints.

Routes parse the request, call exactly one service, and shape the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.enums import AlertStatus, Pollutant
from app.repositories.alert_repository import AlertDetail
from app.repositories.session import get_db_session
from app.schemas.alerts import (
    AlertResponse,
    AlertsResponse,
    DispatchResponse,
    ResolveRequest,
    SlaBreachesResponse,
    SlaBreachResponse,
)
from app.schemas.analysis import Position
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["alerts"])

#: Bounds on the dispatch window a caller may request, in hours.
_MIN_WINDOW_HOURS = 1
_MAX_WINDOW_HOURS = 720

#: Seconds in an hour, for rendering an overdue interval a human reads.
_SECONDS_PER_HOUR = 3600.0


def _to_response(detail: AlertDetail) -> AlertResponse:
    lon, lat = detail.coordinates
    return AlertResponse(
        alert_id=detail.alert_id,
        status=detail.status,
        authority_id=detail.authority_id,
        authority_name=detail.authority_name,
        hotspot_id=detail.hotspot_id,
        station_name=detail.station_name,
        position=Position(longitude=lon, latitude=lat),
        pollutant=detail.pollutant,
        first_seen_at=detail.first_seen_at,
        last_seen_at=detail.last_seen_at,
        peak_observed=detail.peak_observed,
        peak_excess=detail.peak_excess,
        peak_z=detail.peak_z,
        sent_at=detail.sent_at,
        acknowledged_at=detail.acknowledged_at,
        resolved_at=detail.resolved_at,
        resolution_note=detail.resolution_note,
    )


@router.get("", response_model=AlertsResponse, summary="The alert inbox")
def list_alerts(
    session: Annotated[Session, Depends(get_db_session)],
    status: AlertStatus | None = None,
) -> AlertsResponse:
    """Alerts routed to authorities, most urgent first."""
    details = alert_service.list_alerts(session, status=status)
    return AlertsResponse(
        alert_count=len(details),
        alerts=[_to_response(detail) for detail in details],
    )


@router.post(
    "/dispatch",
    response_model=DispatchResponse,
    summary="Detect hotspots and route alerts for them",
)
def dispatch(
    session: Annotated[Session, Depends(get_db_session)],
    pollutant: Pollutant = Pollutant.PM25,
    window_hours: Annotated[
        int, Query(ge=_MIN_WINDOW_HOURS, le=_MAX_WINDOW_HOURS)
    ] = alert_service.DEFAULT_DISPATCH_WINDOW_HOURS,
) -> DispatchResponse:
    """Run detection over a recent window and notify the responsible authorities."""
    outcome = alert_service.dispatch(session, pollutant, window_hours=window_hours)
    return DispatchResponse(
        detected=outcome.detected,
        raised=len(outcome.raised),
        suppressed=outcome.suppressed,
        unrouted=outcome.unrouted,
    )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertResponse,
    summary="Record that an authority has seen an alert",
)
def acknowledge(
    session: Annotated[Session, Depends(get_db_session)],
    alert_id: Annotated[int, Path(ge=1)],
) -> AlertResponse:
    """Acknowledge an alert."""
    return _to_response(alert_service.acknowledge_alert(session, alert_id))


@router.post(
    "/{alert_id}/resolve",
    response_model=AlertResponse,
    summary="Close an alert with a note describing the outcome",
)
def resolve(
    session: Annotated[Session, Depends(get_db_session)],
    alert_id: Annotated[int, Path(ge=1)],
    payload: ResolveRequest,
) -> AlertResponse:
    """Resolve an alert."""
    return _to_response(alert_service.resolve_alert(session, alert_id, payload.note))


@router.get(
    "/sla-breaches",
    response_model=SlaBreachesResponse,
    summary="Alerts past their response deadline",
)
def sla_breaches(
    session: Annotated[Session, Depends(get_db_session)],
) -> SlaBreachesResponse:
    """Alerts whose response window has elapsed, longest overdue first."""
    breaches = alert_service.sla_breaches(session)
    return SlaBreachesResponse(
        breach_count=len(breaches),
        breaches=[
            SlaBreachResponse(
                alert_id=breach.alert.alert_id,
                authority_id=breach.alert.authority_id,
                stage=breach.stage,
                overdue_hours=breach.overdue_by.total_seconds() / _SECONDS_PER_HOUR,
            )
            for breach in breaches
        ],
    )
