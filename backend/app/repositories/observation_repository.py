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

from sqlalchemy import Row, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import MeasurementOrigin, Pollutant, StationTier
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell, point_to_cell
from app.core.observations import ObservedReading
from app.repositories.models import FireDetection, Measurement, Station, WeatherObservation


@dataclass(frozen=True, slots=True)
class MeasurementRow:
    """One reading ready to persist, already unit-normalised."""

    station_id: int
    observed_at: datetime
    pollutant: Pollutant
    value_raw: float
    unit: str
    is_plausible: bool = True
    origin: MeasurementOrigin = MeasurementOrigin.OPENAQ


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


def _payload(rows: Sequence[MeasurementRow]) -> list[dict[str, object]]:
    return [
        {
            "station_id": row.station_id,
            "observed_at": row.observed_at,
            "pollutant": row.pollutant,
            "value_raw": row.value_raw,
            "unit": row.unit,
            "is_plausible": row.is_plausible,
            "origin": row.origin.value,
        }
        for row in rows
    ]


def upsert_measurements(session: Session, rows: Sequence[MeasurementRow]) -> int:
    """Persist readings, replacing any already stored for the same key.

    The raw value is updated but ``value_calibrated`` is deliberately left alone:
    a re-ingested raw reading must not silently discard a calibration that a
    later model run produced for it. The origin is replaced too, so a reading
    OpenAQ delivers takes over an hour the backup feed had filled.

    Returns:
        The number of rows submitted.
    """
    if not rows:
        return 0

    payload = _payload(rows)
    statement = insert(Measurement).values(payload)
    statement = statement.on_conflict_do_update(
        index_elements=["station_id", "observed_at", "pollutant"],
        set_={
            "value_raw": statement.excluded.value_raw,
            "unit": statement.excluded.unit,
            "is_plausible": statement.excluded.is_plausible,
            "origin": statement.excluded.origin,
        },
    )
    session.execute(statement)
    return len(payload)


def insert_missing_measurements(session: Session, rows: Sequence[MeasurementRow]) -> int:
    """Persist readings only where nothing is stored for the same key.

    For the backup feed: a converted figure must never overwrite a reading
    OpenAQ delivered for the same station and hour.

    Returns:
        The number of rows written.
    """
    if not rows:
        return 0
    statement = (
        insert(Measurement)
        .values(_payload(rows))
        .on_conflict_do_nothing(index_elements=["station_id", "observed_at", "pollutant"])
        .returning(Measurement.station_id)
    )
    return len(session.execute(statement).all())


def delete_superseded(
    session: Session,
    station_id: int,
    pollutant: Pollutant,
    *,
    origin: MeasurementOrigin,
    after: datetime,
    until: datetime,
) -> int:
    """Remove one origin's readings for a station inside ``(after, until]``.

    Run once OpenAQ has back-filled a gap, so the backup feed's converted
    figures do not sit beside the originals in hours they no longer stand in for.

    Returns:
        The number of readings removed.
    """
    statement = (
        delete(Measurement)
        .where(
            Measurement.station_id == station_id,
            Measurement.pollutant == pollutant,
            Measurement.origin == origin.value,
            Measurement.observed_at > after,
            Measurement.observed_at <= until,
        )
        .returning(Measurement.station_id)
    )
    return len(session.execute(statement).all())


def newest_by_station(
    session: Session, pollutants: Sequence[Pollutant], tier: StationTier
) -> dict[tuple[int, Pollutant], datetime]:
    """When each station of a tier last had a reading stored, per pollutant, from any relay."""
    statement = (
        select(Measurement.station_id, Measurement.pollutant, func.max(Measurement.observed_at))
        .join(Station, Station.id == Measurement.station_id)
        .where(Measurement.pollutant.in_(pollutants), Station.tier == tier)
        .group_by(Measurement.station_id, Measurement.pollutant)
    )
    return {
        (int(station_id), Pollutant(pollutant)): observed_at
        for station_id, pollutant, observed_at in session.execute(statement).all()
    }


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


def reflag_measurements(session: Session, pollutant: Pollutant, low: float, high: float) -> int:
    """Re-derive ``is_plausible`` for every stored reading of one pollutant.

    Sets the flag in both directions, so tightening a bound flags rows and
    loosening one restores them; the stored value itself is never touched.

    Returns:
        How many readings of the pollutant are flagged afterwards.
    """
    session.execute(
        update(Measurement)
        .where(Measurement.pollutant == pollutant)
        .values(is_plausible=Measurement.value_raw.between(low, high))
    )
    return int(
        session.execute(
            select(func.count())
            .select_from(Measurement)
            .where(Measurement.pollutant == pollutant, Measurement.is_plausible.is_(False))
        ).scalar_one()
    )


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


def latest_reading_per_station(
    session: Session, pollutant: Pollutant, tier: StationTier = StationTier.REFERENCE
) -> list[Row[tuple[int, str, float, float, str, datetime, float, str, str]]]:
    """Return each station's most recent reading for a pollutant, for one tier.

    Reference monitors by default. Low-cost sensors read systematically high in
    humid air until calibrated, so they are only ever returned when asked for by
    name -- never mixed into a surface or a detector that assumes ground truth.

    Uses DISTINCT ON, which on PostgreSQL returns the first row of each group in
    the ordering given -- the natural way to ask "latest per station" in one
    pass rather than one query per station.
    """
    statement = (
        select(
            Station.id,
            Station.name,
            Station.geom.ST_X(),
            Station.geom.ST_Y(),
            Station.h3_cell,
            Measurement.observed_at,
            Measurement.value_raw,
            Measurement.unit,
            Measurement.origin,
        )
        .join(Measurement, Measurement.station_id == Station.id)
        .where(
            Measurement.pollutant == pollutant,
            Measurement.is_plausible.is_(True),
            Station.tier == tier,
        )
        .distinct(Station.id)
        .order_by(Station.id, Measurement.observed_at.desc())
    )
    return list(session.execute(statement).all())


def latest_observed_at(
    session: Session, station_id: int, origin: MeasurementOrigin = MeasurementOrigin.OPENAQ
) -> dict[Pollutant, datetime]:
    """When each pollutant was last stored for a station from one relay, plausible or not.

    OpenAQ's by default: a gap OpenAQ left is still a gap to fill with its own
    readings, even where the backup feed stood in for it meanwhile.
    """
    statement = (
        select(Measurement.pollutant, func.max(Measurement.observed_at))
        .where(Measurement.station_id == station_id, Measurement.origin == origin.value)
        .group_by(Measurement.pollutant)
    )
    return {
        Pollutant(pollutant): observed_at
        for pollutant, observed_at in session.execute(statement).all()
    }


def daily_means(
    session: Session,
    pollutant: Pollutant,
    tier: StationTier,
    *,
    since: datetime,
    until: datetime,
) -> dict[int, tuple[float, int]]:
    """Each station's average reading over a window, and how many hours it covers.

    Readings are averaged within each hour first, then across hours, so a
    station reporting every fifteen minutes weighs each hour once, as an
    hourly one does. Keyed by station id; a station with no plausible reading
    in the window is absent.
    """
    hour = func.date_trunc("hour", Measurement.observed_at)
    hourly = (
        select(
            Measurement.station_id.label("station_id"),
            func.avg(Measurement.value_raw).label("value"),
        )
        .join(Station, Station.id == Measurement.station_id)
        .where(
            Measurement.pollutant == pollutant,
            Measurement.is_plausible.is_(True),
            Station.tier == tier,
            Measurement.observed_at > since,
            Measurement.observed_at <= until,
        )
        .group_by(Measurement.station_id, hour)
        .subquery()
    )
    statement = select(hourly.c.station_id, func.avg(hourly.c.value), func.count()).group_by(
        hourly.c.station_id
    )
    return {
        int(station_id): (float(mean), int(hours))
        for station_id, mean, hours in session.execute(statement).all()
    }


def readings_in_window(
    session: Session,
    pollutant: Pollutant,
    since: datetime,
    until: datetime | None = None,
    *,
    origins: Sequence[MeasurementOrigin] | None = None,
) -> list[Row[tuple[int, str, float, float, str, datetime, float]]]:
    """Every plausible reading for a pollutant in a time window.

    ``until`` is optional because the live API always means "since then, up to
    now". It exists for replaying a recorded episode, where an unbounded window
    would quietly include observations from after the episode and make the
    replay depend on whatever else the database happens to hold. ``origins``
    narrows the readings to some relays; every relay by default.
    """
    statement = (
        select(
            Station.id,
            Station.name,
            Station.geom.ST_X(),
            Station.geom.ST_Y(),
            Station.h3_cell,
            Measurement.observed_at,
            Measurement.value_raw,
        )
        .join(Measurement, Measurement.station_id == Station.id)
        .where(
            Measurement.pollutant == pollutant,
            Measurement.is_plausible.is_(True),
            Measurement.observed_at >= since,
            # Analysis assumes ground truth; uncalibrated low-cost sensors are not.
            Station.tier == StationTier.REFERENCE,
        )
        .order_by(Measurement.observed_at)
    )
    if until is not None:
        statement = statement.where(Measurement.observed_at < until)
    if origins is not None:
        statement = statement.where(Measurement.origin.in_([origin.value for origin in origins]))
    return list(session.execute(statement).all())


def observed_readings_in_window(
    session: Session,
    pollutant: Pollutant,
    since: datetime,
    until: datetime | None = None,
    *,
    origins: Sequence[MeasurementOrigin] | None = None,
) -> list[ObservedReading]:
    """Readings since a point in time, shaped for analysis.

    The same query as :func:`readings_in_window`, returned as a domain type
    rather than raw rows. Analysis needs the shaped form and several callers
    need the same shaping, so it is done once here instead of being repeated in
    every service that runs detection.
    """
    return [
        ObservedReading(
            station_id=int(station_id),
            station_name=str(name),
            coordinates=(float(lon), float(lat)),
            h3_cell=str(cell),
            observed_at=observed_at,
            value=float(value),
        )
        for station_id, name, lon, lat, cell, observed_at, value in readings_in_window(
            session, pollutant, since, until, origins=origins
        )
    ]


def weather_in_window(session: Session, since: datetime) -> list[WeatherObservation]:
    """Every weather record since a point in time."""
    statement = (
        select(WeatherObservation)
        .where(WeatherObservation.observed_at >= since)
        .order_by(WeatherObservation.observed_at)
    )
    return list(session.execute(statement).scalars())


def fire_detections_in_window(
    session: Session, since: datetime
) -> list[Row[tuple[int, float, float, datetime, float, float]]]:
    """Fire detections since a point in time, with coordinates as numbers."""
    statement = (
        select(
            FireDetection.id,
            FireDetection.geom.ST_X(),
            FireDetection.geom.ST_Y(),
            FireDetection.observed_at,
            FireDetection.frp_mw,
            FireDetection.confidence,
        )
        .where(FireDetection.observed_at >= since)
        .order_by(FireDetection.frp_mw.desc())
    )
    return list(session.execute(statement).all())
