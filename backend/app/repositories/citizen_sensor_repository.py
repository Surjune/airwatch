"""Persistence for readings citizens submit from their own sensors.

The comparison against a reference monitor is found with
``citizen_repository.nearest_station_reading``, the same query that pairs a
photograph, so both citizen tiers are checked against ground truth by one rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Row, Select, func, select
from sqlalchemy.orm import Session

from app.core.enums import ComplaintCategory, Pollutant
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.ml.sensor_colocation import ColocatedPair
from app.repositories.models import CitizenSensorReading, Station


@dataclass(frozen=True, slots=True)
class SensorReadingRow:
    """A reading ready to persist."""

    coordinates: LonLat
    h3_cell: H3Cell
    observed_at: datetime
    device_id: str
    sensor_model: str
    pollutant: Pollutant
    value: float
    reference_station_id: int | None
    reference_value: float | None
    reference_distance_m: float | None
    category: ComplaintCategory | None = None
    description: str | None = None


@dataclass(frozen=True, slots=True)
class DeviceSensorReading:
    """One stored reading, as its submitter's complaint report needs it."""

    reading_id: int
    coordinates: LonLat
    h3_cell: H3Cell
    observed_at: datetime
    submitted_at: datetime
    sensor_model: str
    pollutant: Pollutant
    value: float
    category: ComplaintCategory | None
    description: str | None
    reference_station_name: str | None
    reference_value: float | None
    reference_distance_m: float | None


@dataclass(frozen=True, slots=True)
class StoredSensorReading:
    """A stored reading, with the name of the monitor it was compared against."""

    reading_id: int
    coordinates: LonLat
    h3_cell: H3Cell
    observed_at: datetime
    sensor_model: str
    pollutant: Pollutant
    value: float
    reference_station_name: str | None
    reference_value: float | None
    reference_distance_m: float | None


def _point_wkt(point: LonLat) -> str:
    """Render a coordinate as EWKT for PostGIS, in (lon, lat) order."""
    lon, lat = point
    return f"SRID=4326;POINT({lon} {lat})"


def insert_reading(session: Session, row: SensorReadingRow) -> int:
    """Store a reading. Returns its id."""
    reading = CitizenSensorReading(
        geom=_point_wkt(row.coordinates),
        h3_cell=row.h3_cell,
        observed_at=row.observed_at,
        device_id=row.device_id,
        sensor_model=row.sensor_model,
        pollutant=row.pollutant,
        value=row.value,
        reference_station_id=row.reference_station_id,
        reference_value=row.reference_value,
        reference_distance_m=row.reference_distance_m,
        category=row.category,
        description=row.description,
    )
    session.add(reading)
    session.flush()
    return int(reading.id)


def _device_statement() -> Select[tuple[CitizenSensorReading, float, float, str | None]]:
    return select(
        CitizenSensorReading,
        CitizenSensorReading.geom.ST_X(),
        CitizenSensorReading.geom.ST_Y(),
        Station.name,
    ).outerjoin(Station, Station.id == CitizenSensorReading.reference_station_id)


def _to_device_reading(
    row: Row[tuple[CitizenSensorReading, float, float, str | None]],
) -> DeviceSensorReading:
    reading, lon, lat, station_name = row
    return DeviceSensorReading(
        reading_id=reading.id,
        coordinates=(float(lon), float(lat)),
        h3_cell=reading.h3_cell,
        observed_at=reading.observed_at,
        submitted_at=reading.submitted_at,
        sensor_model=reading.sensor_model,
        pollutant=reading.pollutant,
        value=reading.value,
        category=reading.category,
        description=reading.description,
        reference_station_name=station_name,
        reference_value=reading.reference_value,
        reference_distance_m=reading.reference_distance_m,
    )


def reading_for_device(
    session: Session, reading_id: int, device_id: str
) -> DeviceSensorReading | None:
    """One reading, only if this device submitted it; a mismatch looks like a missing id."""
    statement = _device_statement().where(
        CitizenSensorReading.id == reading_id, CitizenSensorReading.device_id == device_id
    )
    row = session.execute(statement).first()
    return None if row is None else _to_device_reading(row)


def readings_for_device(
    session: Session, device_id: str, *, limit: int
) -> list[DeviceSensorReading]:
    """A device's readings, newest first."""
    statement = (
        _device_statement()
        .where(CitizenSensorReading.device_id == device_id)
        .order_by(CitizenSensorReading.submitted_at.desc())
        .limit(limit)
    )
    return [_to_device_reading(row) for row in session.execute(statement).all()]


def count_readings_since(session: Session, device_id: str, since: datetime) -> int:
    """How many readings a device has submitted since a point in time."""
    statement = (
        select(func.count())
        .select_from(CitizenSensorReading)
        .where(
            CitizenSensorReading.device_id == device_id,
            CitizenSensorReading.submitted_at >= since,
        )
    )
    return int(session.execute(statement).scalar_one())


def recent_readings(
    session: Session, pollutant: Pollutant, since: datetime, *, limit: int
) -> list[StoredSensorReading]:
    """Readings of one pollutant observed since a point in time, newest first."""
    statement = (
        select(
            CitizenSensorReading.id,
            CitizenSensorReading.geom.ST_X(),
            CitizenSensorReading.geom.ST_Y(),
            CitizenSensorReading.h3_cell,
            CitizenSensorReading.observed_at,
            CitizenSensorReading.sensor_model,
            CitizenSensorReading.pollutant,
            CitizenSensorReading.value,
            Station.name,
            CitizenSensorReading.reference_value,
            CitizenSensorReading.reference_distance_m,
        )
        .outerjoin(Station, Station.id == CitizenSensorReading.reference_station_id)
        .where(
            CitizenSensorReading.pollutant == pollutant,
            CitizenSensorReading.observed_at >= since,
        )
        .order_by(CitizenSensorReading.observed_at.desc())
        .limit(limit)
    )
    return [
        StoredSensorReading(
            reading_id=int(reading_id),
            coordinates=(float(lon), float(lat)),
            h3_cell=str(cell),
            observed_at=observed_at,
            sensor_model=str(model),
            pollutant=Pollutant(stored_pollutant),
            value=float(value),
            reference_station_name=None if station_name is None else str(station_name),
            reference_value=None if reference_value is None else float(reference_value),
            reference_distance_m=None if distance is None else float(distance),
        )
        for (
            reading_id,
            lon,
            lat,
            cell,
            observed_at,
            model,
            stored_pollutant,
            value,
            station_name,
            reference_value,
            distance,
        ) in session.execute(statement).all()
    ]


def colocated_pairs(session: Session, pollutant: Pollutant) -> list[ColocatedPair]:
    """Every stored reading of a pollutant that was paired with a reference reading."""
    statement = select(CitizenSensorReading.value, CitizenSensorReading.reference_value).where(
        CitizenSensorReading.pollutant == pollutant,
        CitizenSensorReading.reference_value.is_not(None),
    )
    return [
        ColocatedPair(sensor_value=float(value), reference_value=float(reference))
        for value, reference in session.execute(statement).all()
    ]
