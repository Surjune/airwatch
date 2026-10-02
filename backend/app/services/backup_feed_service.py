"""The backup monitor feed: CPCB's monitors through WAQI while OpenAQ is silent.

OpenAQ is how AirWatch reads CPCB's monitors. When its relay stalls -- on 29
September 2026 it stopped relaying every CPCB station in India at once -- the
monitors themselves keep publishing, and the World Air Quality Index Project is
often still receiving them. This service fills the silence from there, under
four rules:

* **Only where OpenAQ is silent.** A station is filled only when its newest
  stored PM2.5 or PM10 reading is more than two hours old, and a WAQI figure
  never overwrites a reading OpenAQ delivered.
* **Only the same instrument.** A WAQI station is used only if it lies within a
  kilometre of an AirWatch reference monitor and credits CPCB as its source, so
  a community sensor beside a monitor can never be stored as one.
* **Converted, and marked as such.** WAQI reports US AQI figures; they are
  turned back into concentrations with the US EPA table and stored with origin
  ``waqi``, which the screens and the API both show.
* **Replaced when OpenAQ returns.** OpenAQ's catch-up fetches the hours it
  missed and removes the converted figures it now covers.

Under WAQI's terms its data may not be redistributed as cached or archived
data, so these readings are kept out of the partner exchange API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi, us_aqi
from app.core.cities import in_city
from app.core.config import Settings
from app.core.constants import (
    CITY_VIEW_RADIUS_M,
    PILOT_CITY_CENTRES,
    WAQI_CPCB_ATTRIBUTION_MARKER,
    WAQI_FALLBACK_AFTER_HOURS,
    WAQI_MATCH_RADIUS_M,
    WAQI_MAX_AGE_HOURS,
    WAQI_POLLUTANTS,
)
from app.core.enums import MeasurementOrigin, PilotCity, Pollutant, StationTier
from app.core.geo import LonLat, haversine_distance_m
from app.core.logging import get_logger
from app.core.plausibility import is_plausible
from app.external.waqi_client import WaqiClient, WaqiStation
from app.repositories import observation_repository, station_repository
from app.repositories.observation_repository import MeasurementRow

logger = get_logger(__name__)

_CREDENTIAL = "waqi_api_token"
_POLLUTANTS = tuple(Pollutant(name) for name in WAQI_POLLUTANTS)

#: Metres per degree of latitude, for the bounding box sent to WAQI.
_METRES_PER_DEGREE = 111_320.0


@dataclass(frozen=True, slots=True)
class BackupOutcome:
    """What one fill of a city did."""

    city: PilotCity
    #: Reference monitors in the city whose PM readings had gone quiet.
    silent_stations: int
    #: Of those, how many WAQI could be matched to.
    matched_stations: int
    #: Readings stored from WAQI.
    stored: int


def city_bbox(city: PilotCity) -> tuple[float, float, float, float]:
    """``(west, south, east, north)`` around a city's view, in degrees."""
    lon, lat = PILOT_CITY_CENTRES[city.value]
    lat_span = CITY_VIEW_RADIUS_M / _METRES_PER_DEGREE
    lon_span = CITY_VIEW_RADIUS_M / (_METRES_PER_DEGREE * math.cos(math.radians(lat)))
    return lon - lon_span, lat - lat_span, lon + lon_span, lat + lat_span


def match_stations(
    candidates: list[WaqiStation], monitors: list[tuple[int, str, LonLat]]
) -> dict[int, WaqiStation]:
    """Pair each monitor with the nearest WAQI station within the match radius.

    One-to-one: a WAQI station nearest to two monitors goes to the closer one,
    so two monitors can never be filled from the same instrument.
    """
    pairs: list[tuple[float, int, WaqiStation]] = []
    for station_id, _, position in monitors:
        for candidate in candidates:
            distance = haversine_distance_m(position, candidate.coordinates)
            if distance <= WAQI_MATCH_RADIUS_M:
                pairs.append((distance, station_id, candidate))
    pairs.sort(key=lambda pair: pair[0])
    matched: dict[int, WaqiStation] = {}
    used: set[int] = set()
    for _, station_id, candidate in pairs:
        if station_id in matched or candidate.uid in used:
            continue
        matched[station_id] = candidate
        used.add(candidate.uid)
    return matched


async def fill_city(
    settings: Settings, session: Session, city: PilotCity, *, now: datetime | None = None
) -> BackupOutcome:
    """Fill a city's silent reference monitors from WAQI.

    Makes no request when every monitor is reporting.

    Raises:
        MissingCredentialError: No WAQI token is configured.
        UpstreamError: WAQI failed or refused the token.
    """
    token = settings.require(_CREDENTIAL)
    reference = now or datetime.now(UTC)
    quiet_before = reference - timedelta(hours=WAQI_FALLBACK_AFTER_HOURS)

    monitors = [
        monitor
        for monitor in station_repository.stations_with_coordinates(
            session, tier=StationTier.REFERENCE
        )
        if in_city(monitor[2], city)
    ]
    newest = observation_repository.newest_by_station(session, _POLLUTANTS, StationTier.REFERENCE)
    silent = [
        monitor
        for monitor in monitors
        if any(
            newest.get((monitor[0], pollutant), datetime.min.replace(tzinfo=UTC)) < quiet_before
            for pollutant in _POLLUTANTS
        )
    ]
    if not silent:
        return BackupOutcome(city=city, silent_stations=0, matched_stations=0, stored=0)

    rows: list[MeasurementRow] = []
    async with WaqiClient(token) as client:
        matched = match_stations(await client.stations_in_bounds(city_bbox(city)), silent)
        for station_id, candidate in matched.items():
            feed = await client.feed(candidate.uid)
            if not any(
                WAQI_CPCB_ATTRIBUTION_MARKER in source.lower() for source in feed.attributions
            ):
                logger.info("backup_feed.not_cpcb", uid=candidate.uid, name=feed.name)
                continue
            if feed.observed_at < reference - timedelta(hours=WAQI_MAX_AGE_HOURS):
                continue
            for pollutant in _POLLUTANTS:
                index = feed.indices.get(pollutant.value)
                last = newest.get((station_id, pollutant))
                if index is None or (last is not None and feed.observed_at <= last):
                    continue
                value = us_aqi.concentration(pollutant, index)
                if value is None:
                    continue
                rows.append(
                    MeasurementRow(
                        station_id=station_id,
                        observed_at=feed.observed_at,
                        pollutant=pollutant,
                        value_raw=value,
                        unit=aqi.CONCENTRATION_UNIT[pollutant],
                        is_plausible=is_plausible(pollutant, value),
                        origin=MeasurementOrigin.WAQI,
                    )
                )

    stored = observation_repository.insert_missing_measurements(session, rows)
    logger.info(
        "backup_feed.filled",
        city=city.value,
        silent_stations=len(silent),
        matched_stations=len(matched),
        stored=stored,
    )
    return BackupOutcome(
        city=city, silent_stations=len(silent), matched_stations=len(matched), stored=stored
    )
