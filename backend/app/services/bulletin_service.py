"""CPCB's daily AQI bulletin for the pilot cities.

The bulletin is CPCB's own once-a-day statement of each city's air: the average
of its stations over the 24 hours to 4 pm IST. It is not a live figure, and the
dashboard says when it ran to, but it is official and it kept appearing every day
while the hourly feeds were down -- for Kanpur it was the only current official
figure anywhere.

The worker asks for today's bulletin each cycle until it has it, and for
yesterday's while today's is not yet out, so a day costs a few requests rather
than one an hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.orm import Session

from app.core import cpcb
from app.core.constants import (
    CPCB_BULLETIN_BASE_URL,
    CPCB_BULLETIN_HOUR_IST,
    CPCB_BULLETIN_LOOKBACK_DAYS,
    CPCB_BULLETIN_PATH,
    PILOT_CITY_CPCB_NAMES,
)
from app.core.enums import PilotCity, Pollutant
from app.core.exceptions import UpstreamUnavailableError
from app.core.logging import get_logger
from app.external.cpcb_bulletin_client import Bulletin, CpcbBulletinClient
from app.repositories import bulletin_repository
from app.repositories.bulletin_repository import BulletinRow

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BulletinOutcome:
    """What a worker cycle did: the newest bulletin day held, and lines stored now."""

    day: date
    stored: int


@dataclass(frozen=True, slots=True)
class CityBulletin:
    """A pilot city's line in the newest bulletin that has one."""

    city: PilotCity
    day: date
    #: When the bulletin's 24-hour average ran to: 4 pm IST on its day.
    averaged_until: datetime
    aqi: int
    category: str
    prominent_pollutants: list[Pollutant]
    stations_reporting: int
    stations_total: int
    source_url: str


async def ingest(session: Session, *, now: datetime | None = None) -> BulletinOutcome:
    """Store the newest bulletin not yet held, today's or the day before.

    Raises:
        UpstreamUnavailableError: CPCB has published neither, which in a normal
            week does not happen.
        UpstreamResponseError: A bulletin could not be read.
    """
    # UTC -> IST: the bulletin's day is India's calendar day.
    today = (now or datetime.now(UTC)).astimezone(cpcb.IST).date()
    async with CpcbBulletinClient() as client:
        for offset in range(CPCB_BULLETIN_LOOKBACK_DAYS + 1):
            day = today - timedelta(days=offset)
            if bulletin_repository.has_day(session, day):
                return BulletinOutcome(day=day, stored=0)
            bulletin = await client.bulletin(day)
            if bulletin is not None:
                stored = bulletin_repository.upsert_bulletins(session, _pilot_rows(bulletin))
                logger.info("bulletin.ingested", day=day.isoformat(), stored=stored)
                return BulletinOutcome(day=day, stored=stored)
    raise UpstreamUnavailableError(
        CpcbBulletinClient.provider_name,
        f"CPCB has published no AQI bulletin for {today} or the "
        f"{CPCB_BULLETIN_LOOKBACK_DAYS} day(s) before.",
    )


def latest_for_city(session: Session, city: PilotCity) -> CityBulletin | None:
    """A city's line in the newest stored bulletin that has one, or None."""
    row = bulletin_repository.latest_for_city(session, PILOT_CITY_CPCB_NAMES[city.value])
    if row is None:
        return None
    return CityBulletin(
        city=city,
        day=row.day,
        averaged_until=averaged_until(row.day),
        aqi=row.aqi,
        category=row.category,
        prominent_pollutants=list(row.prominent_pollutants),
        stations_reporting=row.stations_reporting,
        stations_total=row.stations_total,
        source_url=source_url(row.day),
    )


def source_url(day: date) -> str:
    """Where CPCB published the bulletin for a day."""
    return CPCB_BULLETIN_BASE_URL + CPCB_BULLETIN_PATH.format(day=day.strftime("%Y%m%d"))


def averaged_until(day: date) -> datetime:
    """The end of a bulletin's 24-hour average: 4 pm IST on its day, in UTC."""
    # IST -> UTC: storage and the API are UTC.
    return datetime.combine(day, time(CPCB_BULLETIN_HOUR_IST), tzinfo=cpcb.IST).astimezone(UTC)


def _pilot_rows(bulletin: Bulletin) -> list[BulletinRow]:
    """The pilot cities' lines, stored under the name CPCB's feeds use for each.

    A city CPCB left out of the day's bulletin -- it lists cities with too few
    stations reporting separately, without an AQI -- simply has no line that day.
    """
    by_name = {city.city.casefold(): city for city in bulletin.cities}
    rows: list[BulletinRow] = []
    for name in PILOT_CITY_CPCB_NAMES.values():
        line = by_name.get(name.casefold())
        if line is None:
            continue
        rows.append(
            BulletinRow(
                city=name,
                day=bulletin.day,
                aqi=line.aqi,
                category=line.category,
                prominent_pollutants=tuple(line.prominent_pollutants),
                stations_reporting=line.stations_reporting,
                stations_total=line.stations_total,
            )
        )
    return rows
