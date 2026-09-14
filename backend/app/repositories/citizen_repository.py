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
from datetime import datetime, timedelta

from sqlalchemy import Row, Select, func, select
from sqlalchemy.orm import Session

from app.core.constants import CITIZEN_COLOCATION_RADIUS_M, CITIZEN_REFERENCE_MAX_GAP_MINUTES
from app.core.enums import ComplaintCategory, Pollutant, StationTier, VisibleSource
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.ml.haze_calibration import CalibrationPair
from app.repositories.models import CitizenReport, Measurement, Station

#: Key under a report's ``extra`` document holding Gemini's reading of the photo.
_PHOTO_READING_KEY = "photo_reading"


@dataclass(frozen=True, slots=True)
class PhotoReadingRow:
    """What Gemini saw in a photograph, as stored with its report."""

    visible_source: VisibleSource
    confidence: float
    observation: str
    model: str


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
    category: ComplaintCategory | None = None
    description: str | None = None
    #: What the photo's own metadata said, kept so a report can repeat it later.
    provenance: str | None = None


@dataclass(frozen=True, slots=True)
class StoredPhotoReport:
    """One stored photograph report, as its submitter's complaint report needs it."""

    report_id: int
    coordinates: LonLat
    h3_cell: H3Cell
    captured_at: datetime
    submitted_at: datetime
    haze_index: float
    trust_score: float
    category: ComplaintCategory | None
    description: str | None
    provenance: str | None
    reference_station_name: str | None
    reference_value: float | None
    reference_distance_m: float | None
    photo_reading: PhotoReadingRow | None = None


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
    at: datetime,
    *,
    radius_m: int = CITIZEN_COLOCATION_RADIUS_M,
    max_gap: timedelta = timedelta(minutes=CITIZEN_REFERENCE_MAX_GAP_MINUTES),
) -> NearestReading | None:
    """The plausible reading closest in time to ``at``, from the nearest station in range.

    Only readings within ``max_gap`` of the photograph count: a pair compares a
    photo with the air a monitor measured at the same moment, and a reading from
    another day describes different air.

    Returns None when no monitor is close enough, or none reported near that
    time. That is the common case away from a city centre, and it is the case the
    citizen tier exists for: no comparison is available, so the submission
    extends coverage rather than calibrating it.
    """
    origin = func.ST_GeomFromEWKT(_point_wkt(point))
    distance = func.ST_DistanceSphere(Station.geom, origin)
    gap = func.abs(func.extract("epoch", Measurement.observed_at - at))

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
            # A photo is calibrated against ground truth, never another estimate.
            Station.tier == StationTier.REFERENCE,
            distance <= radius_m,
            Measurement.observed_at >= at - max_gap,
            Measurement.observed_at <= at + max_gap,
        )
        .order_by(distance, gap)
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
        category=row.category,
        description=row.description,
        extra=None if row.provenance is None else {"provenance": row.provenance},
    )
    session.add(report)
    session.flush()
    return int(report.id)


def set_photo_reading(session: Session, report_id: int, reading: PhotoReadingRow) -> None:
    """Attach Gemini's reading to a stored report, keeping what ``extra`` already holds."""
    report = session.get(CitizenReport, report_id)
    if report is None:
        return
    report.extra = {
        **(report.extra or {}),
        _PHOTO_READING_KEY: {
            "visible_source": reading.visible_source.value,
            "confidence": reading.confidence,
            "observation": reading.observation,
            "model": reading.model,
        },
    }
    session.flush()


def _photo_reading(extra: dict[str, object] | None) -> PhotoReadingRow | None:
    """Read a stored photo reading back, or None when there is none or it no longer parses."""
    stored = (extra or {}).get(_PHOTO_READING_KEY)
    if not isinstance(stored, dict):
        return None
    try:
        return PhotoReadingRow(
            visible_source=VisibleSource(str(stored["visible_source"])),
            confidence=float(str(stored["confidence"])),
            observation=str(stored["observation"]),
            model=str(stored["model"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _stored_photo_statement() -> Select[tuple[CitizenReport, float, float, str | None]]:
    return select(
        CitizenReport,
        CitizenReport.geom.ST_X(),
        CitizenReport.geom.ST_Y(),
        Station.name,
    ).outerjoin(Station, Station.id == CitizenReport.reference_station_id)


def _to_stored_photo(row: Row[tuple[CitizenReport, float, float, str | None]]) -> StoredPhotoReport:
    report, lon, lat, station_name = row
    provenance = (report.extra or {}).get("provenance")
    return StoredPhotoReport(
        report_id=report.id,
        coordinates=(float(lon), float(lat)),
        h3_cell=report.h3_cell,
        captured_at=report.captured_at,
        submitted_at=report.submitted_at,
        haze_index=report.haze_index,
        trust_score=report.trust_score,
        category=report.category,
        description=report.description,
        provenance=None if provenance is None else str(provenance),
        reference_station_name=station_name,
        reference_value=report.reference_value,
        reference_distance_m=report.reference_distance_m,
        photo_reading=_photo_reading(report.extra),
    )


def photo_for_device(session: Session, report_id: int, device_id: str) -> StoredPhotoReport | None:
    """One photograph report, only if this device submitted it.

    A mismatch returns None exactly as a missing id does, so a caller cannot use
    the difference to learn which ids exist.
    """
    statement = _stored_photo_statement().where(
        CitizenReport.id == report_id, CitizenReport.device_id == device_id
    )
    row = session.execute(statement).first()
    return None if row is None else _to_stored_photo(row)


def photos_for_device(session: Session, device_id: str, *, limit: int) -> list[StoredPhotoReport]:
    """A device's photograph reports, newest first."""
    statement = (
        _stored_photo_statement()
        .where(CitizenReport.device_id == device_id)
        .order_by(CitizenReport.submitted_at.desc())
        .limit(limit)
    )
    return [_to_stored_photo(row) for row in session.execute(statement).all()]


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
