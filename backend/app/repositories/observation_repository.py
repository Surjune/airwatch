"""Persistence for time-series observations: measurements, weather and fires.

All three share one concern — bulk, idempotent writes into hypertables or
uniquely-keyed tables — so they share a module rather than being split into three
near-identical files.

Every write is an upsert. Ingestion re-reads overlapping time windows by design
(a station's "latest" value is unchanged between runs, and FIRMS re-reports the
same pixel across requests), so a second run must converge on the same rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell, point_to_cell
from app.repositories.models import FireDetection, Measurement, WeatherObservation


@dataclass(frozen=True, slots=True)
class MeasurementRow:
    """One reading ready to persist, already unit-normalised."""

    station_id: int
    observed_at: datetime
    pollutant: Pollutant
    value_raw: float
    unit: str
    is_plausible: bool = True


@dataclass(frozen=True, slots=True)
class WeatherRow:
    """One hour of meteorology for a cell."""

    h3_cell: H3Cell
    observed_at: datetime
    wind_u: float
    wind_v: float
    temperature_c: float
    relative_humidity_pct: float
    pbl_height_m: float | None
    precipitation_mm: float
    is_forecast: bool


@dataclass(frozen=True, slots=True)
class FireRow:
    """One active-fire detection."""

    coordinates: LonLat
    observed_at: datetime
    confidence: float
    frp_mw: float
    brightness_k: float | None
    is_daytime: bool
    satellite: str


def _point_wkt(point: LonLat) -> str:
    """Render a coordinate as EWKT for PostGIS, in (lon, lat) order."""
    lon, lat = point
    return f"SRID=4326;POINT({lon} {lat})"


def upsert_measurements(session: Session, rows: Sequence[MeasurementRow]) -> int:
    """Persist readings, replacing any already stored for the same key.

    The raw value is updated but ``value_calibrated`` is deliberately left alone:
    a re-ingested raw reading must not silently discard a calibration that a
    later model run produced for it.

    Returns:
        The number of rows submitted.
    """
    if not rows:
        return 0

    payload = [
        {
            "station_id": row.station_id,
            "observed_at": row.observed_at,
            "pollutant": row.pollutant,
            "value_raw": row.value_raw,
            "unit": row.unit,
            "is_plausible": row.is_plausible,
        }
        for row in rows
    ]

    statement = insert(Measurement).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["station_id", "observed_at", "pollutant"],
        set_={
            "value_raw": statement.excluded.value_raw,
            "unit": statement.excluded.unit,
            "is_plausible": statement.excluded.is_plausible,
        },
    )
    session.execute(statement)
    return len(payload)


def upsert_weather(session: Session, rows: Sequence[WeatherRow]) -> int:
    """Persist hourly meteorology, replacing any stored for the same cell-hour.

    A forecast hour is overwritten by the observation once that hour arrives,
    which is why ``is_forecast`` is part of the update rather than the key.
    """
    if not rows:
        return 0

    payload = [
        {
            "h3_cell": row.h3_cell,
            "observed_at": row.observed_at,
            "wind_u": row.wind_u,
            "wind_v": row.wind_v,
            "temperature_c": row.temperature_c,
            "relative_humidity_pct": row.relative_humidity_pct,
            "pbl_height_m": row.pbl_height_m,
            "precipitation_mm": row.precipitation_mm,
            "is_forecast": row.is_forecast,
        }
        for row in rows
    ]

    statement = insert(WeatherObservation).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["h3_cell", "observed_at"],
        set_={
            "wind_u": statement.excluded.wind_u,
            "wind_v": statement.excluded.wind_v,
            "temperature_c": statement.excluded.temperature_c,
            "relative_humidity_pct": statement.excluded.relative_humidity_pct,
            "pbl_height_m": statement.excluded.pbl_height_m,
            "precipitation_mm": statement.excluded.precipitation_mm,
            "is_forecast": statement.excluded.is_forecast,
        },
    )
    session.execute(statement)
    return len(payload)


def upsert_fire_detections(session: Session, rows: Sequence[FireRow]) -> int:
    """Persist fire detections, ignoring pixels already recorded.

    Unlike the other two this is DO NOTHING rather than DO UPDATE: a detection is
    an immutable observation of a moment, so re-reporting it carries no new
    information to write.
    """
    if not rows:
        return 0

    payload = [
        {
            "geom": _point_wkt(row.coordinates),
            "h3_cell": point_to_cell(row.coordinates),
            "observed_at": row.observed_at,
            "confidence": row.confidence,
            "frp_mw": row.frp_mw,
            "brightness_k": row.brightness_k,
            "is_daytime": row.is_daytime,
            "satellite": row.satellite,
        }
        for row in rows
    ]

    statement = insert(FireDetection).values(payload)
    statement = statement.on_conflict_do_nothing(constraint="uq_fire_detection_identity")
    session.execute(statement)
    return len(payload)


def count_measurements(session: Session) -> int:
    """Total stored readings."""
    return int(session.execute(select(func.count()).select_from(Measurement)).scalar_one())


def count_weather(session: Session) -> int:
    """Total stored weather hours."""
    return int(session.execute(select(func.count()).select_from(WeatherObservation)).scalar_one())


def count_fire_detections(session: Session) -> int:
    """Total stored fire detections."""
    return int(session.execute(select(func.count()).select_from(FireDetection)).scalar_one())


def latest_measurement_at(session: Session) -> datetime | None:
    """Timestamp of the most recent reading, or None when the table is empty."""
    return session.execute(select(func.max(Measurement.observed_at))).scalar_one_or_none()
