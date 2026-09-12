"""Persistence for citizen photo reports.

Two queries carry most of the weight. ``nearest_station_reading`` finds the
reference monitor a submission can be compared against, which is what turns a
photograph into a calibration pair. ``calibration_pairs`` reads those pairs back
so the relation can be refitted, weighted by nothing at all -- a low-trust
device's pairs are excluded rather than down-weighted, because a relation fitted
partly on unreliable pairs is unreliable everywhere, not just near them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.core.constants import CITIZEN_COLOCATION_RADIUS_M
from app.core.enums import Pollutant
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.ml.haze_calibration import CalibrationPair
from app.repositories.models import CitizenReport, Measurement, Station


@dataclass(frozen=True, slots=True)
class CitizenReportRow:
    """A report ready to persist."""

    coordinates: LonLat
    h3_cell: H3Cell
    captured_at: datetime
    device_id: str
    haze_index: float
    transmission: float
    mean_luminance: float
    sharpness: float
    trust_score: float
    reference_station_id: int | None
    reference_value: float | None
    reference_distance_m: float | None


@dataclass(frozen=True, slots=True)
class NearestReading:
    """The reference reading a submission can be compared against."""

    station_id: int
    station_name: str
    value: float
    observed_at: datetime
    distance_m: float


def _point_wkt(point: LonLat) -> str:
    """Render a coordinate as EWKT for PostGIS, in (lon, lat) order."""
    lon, lat = point
    return f"SRID=4326;POINT({lon} {lat})"


def nearest_station_reading(
    session: Session,
    point: LonLat,
    pollutant: Pollutant,
    *,
    radius_m: int = CITIZEN_COLOCATION_RADIUS_M,
) -> NearestReading | None:
    """The most recent plausible reading from the nearest station within range.

    Returns None when no monitor is close enough. That is the common case away
    from a city centre, and it is the case the citizen tier exists for: no
    comparison is available, so the submission extends coverage rather than
    calibrating it.
    """
    origin = func.ST_GeomFromEWKT(_point_wkt(point))
    distance = func.ST_DistanceSphere(Station.geom, origin)

    statement = (
        select(
            Station.id,
            Station.name,
            Measurement.value_raw,
            Measurement.observed_at,
            distance.label("distance_m"),
        )
        .join(Measurement, Measurement.station_id == Station.id)
        .where(
            Measurement.pollutant == pollutant,
            Measurement.is_plausible.is_(True),
            distance <= radius_m,
        )
        .order_by(distance, Measurement.observed_at.desc())
        .limit(1)
    )

    row = session.execute(statement).first()
    if row is None:
        return None

    station_id, name, value, observed_at, distance_m = row
    return NearestReading(
        station_id=int(station_id),
        station_name=str(name),
        value=float(value),
        observed_at=observed_at,
        distance_m=float(distance_m),
    )


def insert_report(session: Session, row: CitizenReportRow) -> int:
    """Store a report. Returns its id."""
    report = CitizenReport(
        geom=_point_wkt(row.coordinates),
        h3_cell=row.h3_cell,
        captured_at=row.captured_at,
        device_id=row.device_id,
        haze_index=row.haze_index,
        transmission=row.transmission,
        mean_luminance=row.mean_luminance,
        sharpness=row.sharpness,
        trust_score=row.trust_score,
        reference_station_id=row.reference_station_id,
        reference_value=row.reference_value,
        reference_distance_m=row.reference_distance_m,
    )
    session.add(report)
    session.flush()
    return int(report.id)


def count_reports_since(session: Session, device_id: str, since: datetime) -> int:
    """How many reports a device has submitted since a point in time."""
    statement = (
        select(func.count())
        .select_from(CitizenReport)
        .where(CitizenReport.device_id == device_id, CitizenReport.submitted_at >= since)
    )
    return int(session.execute(statement).scalar_one())


def latest_trust(session: Session, device_id: str) -> float | None:
    """A device's most recent trust score, or None if it has never submitted."""
    statement = (
        select(CitizenReport.trust_score)
        .where(CitizenReport.device_id == device_id)
        .order_by(CitizenReport.submitted_at.desc())
        .limit(1)
    )
    value = session.execute(statement).scalar_one_or_none()
    return None if value is None else float(value)


def calibration_pairs(session: Session, *, min_trust: float) -> list[CalibrationPair]:
    """Every co-located pair from a device trusted enough to contribute.

    Low-trust pairs are excluded outright rather than down-weighted. A relation
    fitted partly on unreliable pairs is unreliable everywhere it is applied,
    not only near where those pairs were taken.
    """
    statement = select(CitizenReport.haze_index, CitizenReport.reference_value).where(
        CitizenReport.reference_value.is_not(None),
        CitizenReport.trust_score >= min_trust,
    )
    return [
        CalibrationPair(haze_index=float(haze), reference_value=float(reference))
        for haze, reference in session.execute(statement).all()
    ]


def count_reports(session: Session) -> int:
    """Total stored citizen reports."""
    return int(session.execute(select(func.count()).select_from(CitizenReport)).scalar_one())


def recent_reports(
    session: Session, since: datetime, *, limit: int
) -> list[Row[tuple[int, float, float, str, datetime, float, float, float | None]]]:
    """Recent reports with coordinates, newest first."""
    statement = (
        select(
            CitizenReport.id,
            CitizenReport.geom.ST_X(),
            CitizenReport.geom.ST_Y(),
            CitizenReport.h3_cell,
            CitizenReport.captured_at,
            CitizenReport.haze_index,
            CitizenReport.trust_score,
            CitizenReport.reference_value,
        )
        .where(CitizenReport.captured_at >= since)
        .order_by(CitizenReport.captured_at.desc())
        .limit(limit)
    )
    return list(session.execute(statement).all())
