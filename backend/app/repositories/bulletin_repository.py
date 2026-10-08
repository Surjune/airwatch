"""Persistence for CPCB's daily AQI bulletin."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.repositories.models import CpcbBulletin


@dataclass(frozen=True, slots=True)
class BulletinRow:
    """One city's line in a day's bulletin."""

    city: str
    day: date
    aqi: int
    category: str
    prominent_pollutants: tuple[Pollutant, ...]
    stations_reporting: int
    stations_total: int


def upsert_bulletins(session: Session, rows: Sequence[BulletinRow]) -> int:
    """Store bulletin lines; a re-read of the same day replaces the stored one."""
    if not rows:
        return 0
    statement = insert(CpcbBulletin).values(
        [
            {
                "city": row.city,
                "day": row.day,
                "aqi": row.aqi,
                "category": row.category,
                "prominent_pollutants": [pollutant.value for pollutant in row.prominent_pollutants],
                "stations_reporting": row.stations_reporting,
                "stations_total": row.stations_total,
            }
            for row in rows
        ]
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_bulletin_city_day",
        set_={
            "aqi": statement.excluded.aqi,
            "category": statement.excluded.category,
            "prominent_pollutants": statement.excluded.prominent_pollutants,
            "stations_reporting": statement.excluded.stations_reporting,
            "stations_total": statement.excluded.stations_total,
        },
    )
    session.execute(statement)
    return len(rows)


def has_day(session: Session, day: date) -> bool:
    """Whether any city's line is stored for a day."""
    statement = select(CpcbBulletin.id).where(CpcbBulletin.day == day).limit(1)
    return session.execute(statement).first() is not None


def latest_for_city(session: Session, city: str) -> BulletinRow | None:
    """A city's line in the newest bulletin that has one, or None."""
    statement = (
        select(CpcbBulletin)
        .where(CpcbBulletin.city == city)
        .order_by(CpcbBulletin.day.desc())
        .limit(1)
    )
    stored = session.execute(statement).scalar_one_or_none()
    if stored is None:
        return None
    return BulletinRow(
        city=stored.city,
        day=stored.day,
        aqi=stored.aqi,
        category=stored.category,
        prominent_pollutants=tuple(Pollutant(value) for value in stored.prominent_pollutants),
        stations_reporting=stored.stations_reporting,
        stations_total=stored.stations_total,
    )
