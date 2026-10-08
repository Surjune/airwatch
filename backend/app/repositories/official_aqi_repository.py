"""Persistence for CPCB's published sub-indices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import OfficialRelay, Pollutant
from app.core.geo import LonLat
from app.repositories.models import OfficialSubIndex


@dataclass(frozen=True, slots=True)
class OfficialRow:
    """One published sub-index, ready to store."""

    station_name: str
    city: str
    state: str
    coordinates: LonLat
    pollutant: Pollutant
    reported_at: datetime
    sub_index: float
    sub_index_min: float | None
    sub_index_max: float | None
    relay: OfficialRelay = OfficialRelay.DATA_GOV_IN


@dataclass(frozen=True, slots=True)
class StoredSubIndex:
    """A stored sub-index, with its position unpacked."""

    station_name: str
    coordinates: LonLat
    pollutant: Pollutant
    reported_at: datetime
    sub_index: float
    sub_index_min: float | None
    sub_index_max: float | None
    relay: OfficialRelay


def upsert_sub_indices(session: Session, rows: Sequence[OfficialRow]) -> int:
    """Store published sub-indices; a re-fetch of the same hour replaces the stored one."""
    if not rows:
        return 0
    statement = insert(OfficialSubIndex).values(
        [
            {
                "station_name": row.station_name,
                "city": row.city,
                "state": row.state,
                "geom": f"SRID=4326;POINT({row.coordinates[0]} {row.coordinates[1]})",
                "pollutant": row.pollutant,
                "reported_at": row.reported_at,
                "sub_index": row.sub_index,
                "sub_index_min": row.sub_index_min,
                "sub_index_max": row.sub_index_max,
                "relay": row.relay.value,
            }
            for row in rows
        ]
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_official_station_pollutant_time",
        set_={
            "sub_index": statement.excluded.sub_index,
            "sub_index_min": statement.excluded.sub_index_min,
            "sub_index_max": statement.excluded.sub_index_max,
            "relay": statement.excluded.relay,
        },
    )
    session.execute(statement)
    return len(rows)


def latest_for_city(session: Session, city: str) -> list[StoredSubIndex]:
    """Each station's most recent sub-index per pollutant in a city."""
    statement = (
        select(
            OfficialSubIndex.station_name,
            OfficialSubIndex.geom.ST_X(),
            OfficialSubIndex.geom.ST_Y(),
            OfficialSubIndex.pollutant,
            OfficialSubIndex.reported_at,
            OfficialSubIndex.sub_index,
            OfficialSubIndex.sub_index_min,
            OfficialSubIndex.sub_index_max,
            OfficialSubIndex.relay,
        )
        .where(OfficialSubIndex.city == city)
        .distinct(OfficialSubIndex.station_name, OfficialSubIndex.pollutant)
        .order_by(
            OfficialSubIndex.station_name,
            OfficialSubIndex.pollutant,
            OfficialSubIndex.reported_at.desc(),
        )
    )
    return [
        StoredSubIndex(
            station_name=str(name),
            coordinates=(float(lon), float(lat)),
            pollutant=pollutant,
            reported_at=reported_at,
            sub_index=float(value),
            sub_index_min=low,
            sub_index_max=high,
            relay=OfficialRelay(relay),
        )
        for name, lon, lat, pollutant, reported_at, value, low, high, relay in session.execute(
            statement
        ).all()
    ]


def positions_by_station(session: Session) -> dict[str, LonLat]:
    """Where each station CPCB has published for stands, by its name.

    TNPCB's website names its stations as CPCB does but gives no coordinates, so
    a station is placed where CPCB's own feed last put it.
    """
    statement = (
        select(
            OfficialSubIndex.station_name,
            OfficialSubIndex.geom.ST_X(),
            OfficialSubIndex.geom.ST_Y(),
        )
        .distinct(OfficialSubIndex.station_name)
        .order_by(OfficialSubIndex.station_name, OfficialSubIndex.reported_at.desc())
    )
    return {
        str(name): (float(lon), float(lat)) for name, lon, lat in session.execute(statement).all()
    }
