"""A city's air now on CPCB's scale, worked out from its monitors' latest readings.

CPCB's official index reaches AirWatch through data.gov.in. When that feed stops
-- its API refused every connection from 25 September 2026 -- the monitors
themselves usually keep reporting, through OpenAQ or the backup feed. This
service puts each monitor's latest PM2.5 and PM10 on CPCB's scale, so the air now
can still be read on the scale residents know.

It is AirWatch's figure, not CPCB's, and differs from CPCB's in two ways the
response states: it uses the latest hour rather than a 24-hour average, as every
other index on the dashboard does, and it covers the particulates only, because
the backup feed carries no gases. The dashboard shows it only while CPCB's own
figure is out of date.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.cities import in_city
from app.core.constants import LIVE_INDEX_COMBINE_HOURS
from app.core.enums import MeasurementOrigin, PilotCity, Pollutant
from app.core.geo import LonLat
from app.core.logging import get_logger
from app.repositories import observation_repository

logger = get_logger(__name__)

#: The pollutants combined: the two every reference monitor and the backup feed report.
_POLLUTANTS = (Pollutant.PM25, Pollutant.PM10)


@dataclass(frozen=True, slots=True)
class LiveStationIndex:
    """One monitor's latest particulate readings, on CPCB's scale."""

    station_id: int
    name: str
    coordinates: LonLat
    #: The newest reading combined here.
    observed_at: datetime
    #: The oldest reading combined here; equal to ``observed_at`` when both
    #: pollutants arrived in the same hour.
    oldest_observed_at: datetime
    #: The higher of the sub-indices.
    aqi: float
    category: str
    dominant_pollutant: Pollutant
    sub_indices: dict[Pollutant, float]
    #: The relays the combined readings came through.
    origins: list[MeasurementOrigin]


@dataclass(frozen=True, slots=True)
class _Reading:
    name: str
    coordinates: LonLat
    pollutant: Pollutant
    observed_at: datetime
    value: float
    origin: MeasurementOrigin


def live_for_city(session: Session, city: PilotCity) -> list[LiveStationIndex]:
    """Each reference monitor's latest index in a city, worst first.

    Every monitor with a reading is returned, however old; the caller decides
    what counts as current, as it does for the monitor list.
    """
    by_station: dict[int, list[_Reading]] = defaultdict(list)
    for pollutant in _POLLUTANTS:
        for row in observation_repository.latest_reading_per_station(session, pollutant):
            station_id, name, lon, lat, _, observed_at, value, _, origin = row
            position = (float(lon), float(lat))
            if not in_city(position, city):
                continue
            by_station[int(station_id)].append(
                _Reading(
                    name=str(name),
                    coordinates=position,
                    pollutant=pollutant,
                    observed_at=observed_at,
                    value=float(value),
                    origin=MeasurementOrigin(origin),
                )
            )

    stations = [_combine(station_id, readings) for station_id, readings in by_station.items()]
    stations.sort(key=lambda station: station.aqi, reverse=True)
    logger.info("live_index.computed", city=city.value, stations=len(stations))
    return stations


def _combine(station_id: int, readings: list[_Reading]) -> LiveStationIndex:
    """One monitor's index from its pollutants' latest readings.

    A pollutant whose latest reading is much older than the other's has stopped
    reporting, and combining it would describe two different hours as one.
    """
    newest = max(reading.observed_at for reading in readings)
    cutoff = newest - timedelta(hours=LIVE_INDEX_COMBINE_HOURS)
    included = [reading for reading in readings if reading.observed_at >= cutoff]
    result = aqi.overall_aqi({reading.pollutant: reading.value for reading in included})
    return LiveStationIndex(
        station_id=station_id,
        name=included[0].name,
        coordinates=included[0].coordinates,
        observed_at=newest,
        oldest_observed_at=min(reading.observed_at for reading in included),
        aqi=result.value,
        category=result.category,
        dominant_pollutant=result.dominant_pollutant,
        sub_indices=dict(result.sub_indices),
        origins=sorted({reading.origin for reading in included}),
    )
