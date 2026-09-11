"""Persistence for hotspot episodes, authorities and the alert trail.

These three belong together because they are one write path: a detected episode
is stored, the jurisdiction containing it is looked up, and an alert is recorded
against both. Splitting them would mean a service holding a half-written episode
while it consulted a second repository.

The jurisdiction lookup is the only place responsibility is decided. It is
spatial rather than configured per station because a hotspot can appear on
ground no monitor covers -- which is the entire purpose of estimating a surface
between stations.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.alerting import AlertRecord
from app.core.enums import AlertStatus, HotspotStatus, Pollutant
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.repositories.models import Alert, Authority, Hotspot, Station


@dataclass(frozen=True, slots=True)
class HotspotRow:
    """A detected episode ready to persist."""

    h3_cell: H3Cell
    coordinates: LonLat
    station_id: int | None
    pollutant: Pollutant
    first_seen_at: datetime
    last_seen_at: datetime
    intervals: int
    peak_z: float
    peak_residual: float
    peak_observed: float


@dataclass(frozen=True, slots=True)
class AlertDetail:
    """One alert with the context an operator needs to act on it.

    Carries the hotspot's excess rather than only its concentration: an inbox
    ordered by concentration would put a citywide bad day above a single
    anomalous source, which inverts the priority the detector exists to express.
    """

    alert_id: int
    status: AlertStatus
    sent_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    authority_id: int
    authority_name: str
    hotspot_id: int
    station_name: str | None
    coordinates: LonLat
    pollutant: Pollutant
    first_seen_at: datetime
    last_seen_at: datetime
    peak_observed: float
    peak_excess: float
    peak_z: float


def _point_wkt(point: LonLat) -> str:
    """Render a coordinate as EWKT for PostGIS, in (lon, lat) order."""
    lon, lat = point
    return f"SRID=4326;POINT({lon} {lat})"


def _polygon_wkt(ring: Sequence[LonLat]) -> str:
    """Render a closed ring as EWKT, in (lon, lat) order.

    The ring is closed here if the caller did not close it, because PostGIS
    rejects an unclosed polygon and a jurisdiction that fails to store is a
    jurisdiction whose hotspots reach nobody.
    """
    closed = list(ring)
    if closed[0] != closed[-1]:
        closed.append(closed[0])
    points = ", ".join(f"{lon} {lat}" for lon, lat in closed)
    return f"SRID=4326;POLYGON(({points}))"


# ---------------------------------------------------------------------------
# Authorities
# ---------------------------------------------------------------------------


def upsert_authority(
    session: Session,
    *,
    name: str,
    jurisdiction: Sequence[LonLat],
    contact_email: str | None = None,
    escalation_tier: int = 1,
) -> int:
    """Insert an authority, or update its jurisdiction if the name is known."""
    statement = (
        insert(Authority)
        .values(
            name=name,
            jurisdiction=_polygon_wkt(jurisdiction),
            contact_email=contact_email,
            escalation_tier=escalation_tier,
        )
        .on_conflict_do_update(
            index_elements=[Authority.name],
            set_={
                "jurisdiction": _polygon_wkt(jurisdiction),
                "contact_email": contact_email,
                "escalation_tier": escalation_tier,
            },
        )
        .returning(Authority.id)
    )
    return int(session.execute(statement).scalar_one())


def authorities_containing(session: Session, point: LonLat) -> list[tuple[int, int]]:
    """Return ``(authority_id, escalation_tier)`` for every jurisdiction containing a point.

    Returns every match rather than picking one, because choosing between
    overlapping jurisdictions is a policy decision and policy lives in
    ``core/alerting``, not in SQL.
    """
    statement = select(Authority.id, Authority.escalation_tier).where(
        func.ST_Contains(Authority.jurisdiction, func.ST_GeomFromEWKT(_point_wkt(point)))
    )
    return [(int(row[0]), int(row[1])) for row in session.execute(statement).all()]


def count_authorities(session: Session) -> int:
    """Total registered authorities."""
    return int(session.execute(select(func.count()).select_from(Authority)).scalar_one())


# ---------------------------------------------------------------------------
# Hotspot episodes
# ---------------------------------------------------------------------------


def upsert_hotspot(session: Session, row: HotspotRow) -> int:
    """Store a detected episode, or update it if the episode is already known.

    Identity is ``(h3_cell, first_seen_at, pollutant)``. A continuing episode
    re-detected on a later run is the same episode with a later end, not a new
    one, so re-running detection over an overlapping window converges instead of
    filling the table with duplicates of the same event.
    """
    statement = (
        insert(Hotspot)
        .values(
            geom=_point_wkt(row.coordinates),
            h3_cell=row.h3_cell,
            station_id=row.station_id,
            pollutant=row.pollutant,
            first_seen_at=row.first_seen_at,
            last_seen_at=row.last_seen_at,
            intervals=row.intervals,
            peak_z=row.peak_z,
            peak_residual=row.peak_residual,
            peak_observed=row.peak_observed,
            status=HotspotStatus.CONFIRMED,
        )
        .on_conflict_do_update(
            constraint="uq_hotspot_episode",
            set_={
                "last_seen_at": row.last_seen_at,
                "intervals": row.intervals,
                "peak_z": row.peak_z,
                "peak_residual": row.peak_residual,
                "peak_observed": row.peak_observed,
            },
        )
        .returning(Hotspot.id)
    )
    return int(session.execute(statement).scalar_one())


def count_hotspots(session: Session) -> int:
    """Total stored hotspot episodes."""
    return int(session.execute(select(func.count()).select_from(Hotspot)).scalar_one())


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


def _to_record(alert: Alert) -> AlertRecord:
    """Convert a stored row into the shape the lifecycle rules operate on."""
    return AlertRecord(
        alert_id=alert.id,
        hotspot_id=alert.hotspot_id,
        authority_id=alert.authority_id,
        status=alert.status,
        sent_at=alert.sent_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
    )


def alerts_for(session: Session, hotspot_id: int, authority_id: int) -> list[AlertRecord]:
    """Alerts already raised for this hotspot and authority."""
    statement = select(Alert).where(
        Alert.hotspot_id == hotspot_id, Alert.authority_id == authority_id
    )
    return [_to_record(alert) for alert in session.execute(statement).scalars()]


def create_alert(
    session: Session, *, hotspot_id: int, authority_id: int, sent_at: datetime
) -> AlertRecord:
    """Record that an alert was routed to an authority."""
    alert = Alert(
        hotspot_id=hotspot_id,
        authority_id=authority_id,
        status=AlertStatus.SENT,
        sent_at=sent_at,
    )
    session.add(alert)
    session.flush()
    return _to_record(alert)


def get_alert(session: Session, alert_id: int) -> AlertRecord | None:
    """One alert by id, or None."""
    alert = session.get(Alert, alert_id)
    return None if alert is None else _to_record(alert)


def save_alert_state(session: Session, record: AlertRecord, *, note: str | None = None) -> None:
    """Write a lifecycle transition back to the row it came from.

    The transition itself is decided in ``core/alerting``; this only persists the
    result, so the rules stay testable without a database.
    """
    alert = session.get(Alert, record.alert_id)
    if alert is None:  # pragma: no cover - callers load the record first.
        return
    alert.status = record.status
    alert.acknowledged_at = record.acknowledged_at
    alert.resolved_at = record.resolved_at
    if note is not None:
        alert.resolution_note = note
    session.flush()


def list_alert_details(session: Session, *, status: AlertStatus | None = None) -> list[AlertDetail]:
    """Every alert with its hotspot and authority, most urgent first.

    Ordered by standardised excess rather than by time or concentration. The
    oldest unanswered alert is not necessarily the one to open first, and the
    highest concentration may simply be a bad day everywhere.
    """
    statement = (
        select(
            Alert.id,
            Alert.status,
            Alert.sent_at,
            Alert.acknowledged_at,
            Alert.resolved_at,
            Alert.resolution_note,
            Authority.id,
            Authority.name,
            Hotspot.id,
            Station.name,
            Hotspot.geom.ST_X(),
            Hotspot.geom.ST_Y(),
            Hotspot.pollutant,
            Hotspot.first_seen_at,
            Hotspot.last_seen_at,
            Hotspot.peak_observed,
            Hotspot.peak_residual,
            Hotspot.peak_z,
        )
        .join(Authority, Authority.id == Alert.authority_id)
        .join(Hotspot, Hotspot.id == Alert.hotspot_id)
        .outerjoin(Station, Station.id == Hotspot.station_id)
        .order_by(Hotspot.peak_z.desc())
    )
    if status is not None:
        statement = statement.where(Alert.status == status)

    return [_to_detail(row) for row in session.execute(statement).all()]


def _to_detail(row: Row[tuple[object, ...]]) -> AlertDetail:
    """Map one joined row onto the console's view type."""
    (
        alert_id,
        status,
        sent_at,
        acknowledged_at,
        resolved_at,
        resolution_note,
        authority_id,
        authority_name,
        hotspot_id,
        station_name,
        lon,
        lat,
        pollutant,
        first_seen_at,
        last_seen_at,
        peak_observed,
        peak_residual,
        peak_z,
    ) = row
    return AlertDetail(
        alert_id=int(alert_id),
        status=AlertStatus(status),
        sent_at=sent_at,
        acknowledged_at=acknowledged_at,
        resolved_at=resolved_at,
        resolution_note=None if resolution_note is None else str(resolution_note),
        authority_id=int(authority_id),
        authority_name=str(authority_name),
        hotspot_id=int(hotspot_id),
        station_name=None if station_name is None else str(station_name),
        coordinates=(float(lon), float(lat)),
        pollutant=Pollutant(pollutant),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        peak_observed=float(peak_observed),
        peak_excess=float(peak_residual),
        peak_z=float(peak_z),
    )
