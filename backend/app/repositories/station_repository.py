"""Station persistence.

The only layer permitted to touch a Session. Every write here is idempotent:
ingestion runs on a schedule and re-reads overlapping windows, so re-running it
must converge rather than accumulate duplicates.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import SourceType, StationTier
from app.core.geo import LonLat
from app.core.h3_grid import point_to_cell
from app.repositories.models import PollutionSource, Station


def _point_wkt(point: LonLat) -> str:
    """Render a coordinate as EWKT for PostGIS, in (lon, lat) order."""
    lon, lat = point
    return f"SRID=4326;POINT({lon} {lat})"


def upsert_station(
    session: Session,
    *,
    source: str,
    source_station_id: str,
    name: str,
    tier: StationTier,
    coordinates: LonLat,
    operator: str | None = None,
    last_seen_at: datetime | None = None,
    extra: dict[str, object] | None = None,
) -> int:
    """Insert a station, or update it if this source already reported it.

    Identity is ``(source, source_station_id)`` rather than the name or the
    coordinates: providers rename stations and nudge their coordinates, and
    treating either as identity would fork one physical station into several.

    Returns:
        The database id of the station.
    """
    statement = (
        insert(Station)
        .values(
            source=source,
            source_station_id=source_station_id,
            name=name,
            tier=tier,
            geom=_point_wkt(coordinates),
            h3_cell=point_to_cell(coordinates),
            operator=operator,
            last_seen_at=last_seen_at,
            extra=extra,
        )
        .on_conflict_do_update(
            constraint="uq_station_source_identity",
            set_={
                "name": name,
                "geom": _point_wkt(coordinates),
                "h3_cell": point_to_cell(coordinates),
                "operator": operator,
                "last_seen_at": last_seen_at,
                "extra": extra,
            },
        )
        .returning(Station.id)
    )
    station_id = session.execute(statement).scalar_one()
    return int(station_id)


def get_station_id(session: Session, *, source: str, source_station_id: str) -> int | None:
    """Return the id of a station by its upstream identity, if it exists."""
    statement = select(Station.id).where(
        Station.source == source,
        Station.source_station_id == source_station_id,
    )
    return session.execute(statement).scalar_one_or_none()


def count_stations(session: Session, *, tier: StationTier | None = None) -> int:
    """Count stations, optionally restricted to one tier."""
    statement = select(Station)
    if tier is not None:
        statement = statement.where(Station.tier == tier)
    return len(list(session.execute(statement).scalars()))


def list_stations(session: Session, *, tier: StationTier | None = None) -> list[Station]:
    """Return stations, optionally restricted to one tier."""
    statement = select(Station)
    if tier is not None:
        statement = statement.where(Station.tier == tier)
    return list(session.execute(statement).scalars())


def upsert_pollution_source(
    session: Session,
    *,
    name: str,
    source_type: SourceType,
    coordinates: LonLat,
    emission_prior: float,
    extra: dict[str, object] | None = None,
) -> int:
    """Insert or refresh a registered pollution source.

    Identity is the name, so re-seeding converges rather than duplicating.

    Returns:
        The database id of the source.
    """
    existing = session.execute(
        select(PollutionSource).where(PollutionSource.name == name)
    ).scalar_one_or_none()

    if existing is not None:
        existing.source_type = source_type
        existing.geom = _point_wkt(coordinates)
        existing.h3_cell = point_to_cell(coordinates)
        existing.emission_prior = emission_prior
        existing.extra = extra
        session.flush()
        return int(existing.id)

    created = PollutionSource(
        name=name,
        source_type=source_type,
        geom=_point_wkt(coordinates),
        h3_cell=point_to_cell(coordinates),
        emission_prior=emission_prior,
        extra=extra,
    )
    session.add(created)
    session.flush()
    return int(created.id)


def list_pollution_sources(session: Session) -> list[PollutionSource]:
    """Return every registered pollution source."""
    return list(session.execute(select(PollutionSource)).scalars())
