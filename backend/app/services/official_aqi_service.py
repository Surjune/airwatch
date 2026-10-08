"""CPCB's official, current AQI for each station in a city.

The analysis runs on hourly concentrations from OpenAQ, which lag some stations
by days. This service stores what CPCB itself published most recently, so a
reader sees the official figure for their city now -- Coimbatore included -- and
can check AirWatch against it.

CPCB's figures are read from data.gov.in for every city and, for Tamil Nadu's
stations, from TNPCB's website too, which kept publishing them while
data.gov.in's API was down. Each stored figure records which it came through.

The station AQI is computed the way CPCB does: the highest sub-index, and only
when at least three pollutants are reported with PM2.5 or PM10 among them.
Otherwise no AQI is stated, and the sub-indices are shown on their own.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.config import Settings
from app.core.constants import (
    AQI_MIN_POLLUTANTS,
    OFFICIAL_SUB_INDEX_MAX_AGE_HOURS,
    PILOT_CITY_CPCB_NAMES,
    TNPCB_STATE,
)
from app.core.enums import OfficialRelay, PilotCity, Pollutant, StationTier
from app.core.geo import LonLat
from app.core.logging import get_logger
from app.external.cpcb_client import CpcbAqiClient, SubIndexReading
from app.external.tnpcb_client import TnpcbClient
from app.repositories import official_aqi_repository, station_repository
from app.repositories.official_aqi_repository import OfficialRow

logger = get_logger(__name__)

#: Pollutants of which at least one must be present for CPCB to state an AQI.
_PARTICULATES = frozenset({Pollutant.PM25, Pollutant.PM10})


@dataclass(frozen=True, slots=True)
class StationAqi:
    """One station's latest official sub-indices, and its AQI where CPCB would state one."""

    station_name: str
    coordinates: LonLat
    reported_at: datetime
    sub_indices: dict[Pollutant, float]
    aqi: float | None
    category: str | None
    dominant_pollutant: Pollutant | None
    #: When the oldest sub-index combined here was published. Equal to
    #: ``reported_at`` when every pollutant arrived in the newest update.
    oldest_reported_at: datetime
    #: Where the newest sub-index was read.
    relay: OfficialRelay


def station_aqi(
    sub_indices: Mapping[Pollutant, float],
) -> tuple[float | None, Pollutant | None]:
    """The overall AQI and the pollutant setting it, by CPCB's rule.

    Returns ``(None, None)`` when fewer than :data:`AQI_MIN_POLLUTANTS` are
    reported or neither particulate is among them: CPCB states no AQI then, and
    a maximum over two gases would understate the air.
    """
    if len(sub_indices) < AQI_MIN_POLLUTANTS or not _PARTICULATES & sub_indices.keys():
        return None, None
    dominant = max(sub_indices, key=lambda pollutant: sub_indices[pollutant])
    return sub_indices[dominant], dominant


async def ingest_city(settings: Settings, session: Session, city: PilotCity) -> int:
    """Fetch and store CPCB's current sub-indices for a city.

    Raises:
        MissingCredentialError: No data.gov.in key is configured.
        UpstreamError: The portal failed or returned an unexpected shape.
    """
    api_key = settings.require("cpcb_api_key")
    async with CpcbAqiClient(api_key) as client:
        readings = await client.city_sub_indices(PILOT_CITY_CPCB_NAMES[city.value])
    stored = official_aqi_repository.upsert_sub_indices(session, [_row(r) for r in readings])
    logger.info("official_aqi.city_ingested", city=city.value, stored=stored)
    return stored


async def ingest_tnpcb(session: Session) -> int:
    """Fetch and store the sub-indices TNPCB's website publishes for the pilot cities.

    TNPCB gives no coordinates, so each station is placed where CPCB's own feed
    last put it, or failing that where OpenAQ puts the monitor of the same name.
    A station found in neither is left out and logged: an official figure shown
    in the wrong place would mislead more than one not shown.

    Raises:
        UpstreamError: The page could not be fetched or no longer has the
            expected shape.
    """
    async with TnpcbClient() as client:
        readings = await client.station_sub_indices()
    pilot_names = {PILOT_CITY_CPCB_NAMES[city.value] for city in PilotCity}
    wanted = [reading for reading in readings if reading.city in pilot_names]

    positions = {
        name: position
        for _, name, position in station_repository.stations_with_coordinates(
            session, tier=StationTier.REFERENCE
        )
    }
    positions.update(official_aqi_repository.positions_by_station(session))

    rows: list[OfficialRow] = []
    unplaced: set[str] = set()
    for reading in wanted:
        position = positions.get(reading.station)
        if position is None:
            unplaced.add(reading.station)
            continue
        rows.append(
            OfficialRow(
                station_name=reading.station,
                city=reading.city,
                state=TNPCB_STATE,
                coordinates=position,
                pollutant=reading.pollutant,
                reported_at=reading.reported_at,
                sub_index=reading.sub_index,
                sub_index_min=reading.sub_index_min,
                sub_index_max=reading.sub_index_max,
                relay=OfficialRelay.TNPCB,
            )
        )
    if unplaced:
        logger.warning("official_aqi.tnpcb_stations_unplaced", stations=sorted(unplaced))
    stored = official_aqi_repository.upsert_sub_indices(session, rows)
    logger.info("official_aqi.tnpcb_ingested", stored=stored)
    return stored


def latest_for_city(session: Session, city: PilotCity) -> list[StationAqi]:
    """Each station's latest official sub-indices in a city, worst AQI first."""
    by_station: dict[str, list[official_aqi_repository.StoredSubIndex]] = defaultdict(list)
    for row in official_aqi_repository.latest_for_city(session, PILOT_CITY_CPCB_NAMES[city.value]):
        by_station[row.station_name].append(row)

    stations: list[StationAqi] = []
    for name, rows in by_station.items():
        # The feed staggers a station's pollutants across consecutive updates, so
        # each pollutant's latest sub-index from the last few hours is combined.
        # Anything older is a pollutant that is not currently reporting.
        latest = max(row.reported_at for row in rows)
        cutoff = latest - timedelta(hours=OFFICIAL_SUB_INDEX_MAX_AGE_HOURS)
        included = [row for row in rows if row.reported_at >= cutoff]
        newest = max(included, key=lambda row: row.reported_at)
        current = {row.pollutant: row.sub_index for row in included}
        overall, dominant = station_aqi(current)
        stations.append(
            StationAqi(
                station_name=name,
                coordinates=rows[0].coordinates,
                reported_at=latest,
                sub_indices=current,
                aqi=overall,
                category=aqi.category(overall) if overall is not None else None,
                dominant_pollutant=dominant,
                oldest_reported_at=min(row.reported_at for row in included),
                relay=newest.relay,
            )
        )

    stations.sort(key=lambda station: station.aqi if station.aqi is not None else -1, reverse=True)
    return stations


def _row(reading: SubIndexReading) -> OfficialRow:
    return OfficialRow(
        station_name=reading.station,
        city=reading.city,
        state=reading.state,
        coordinates=reading.coordinates,
        pollutant=reading.pollutant,
        reported_at=reading.reported_at,
        sub_index=reading.sub_index,
        sub_index_min=reading.sub_index_min,
        sub_index_max=reading.sub_index_max,
    )
