"""Orchestration for the read-side API.

Loads observations through repositories and runs the pure analysis in ``ml/``
over them. This is the only layer that knows about both a database session and a
detection algorithm; the analysis knows nothing about storage, and the routes
know nothing about either.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.cities import in_city
from app.core.constants import (
    CITY_VIEW_RADIUS_M,
    EXPOSURE_CANDIDATE_HOURS,
    FUSION_MIN_NEIGHBOURS,
    HOURS_PER_DAY,
    METRES_PER_KILOMETRE,
    PILOT_CITY_CENTRES,
    PILOT_CITY_DEFAULT_POLLUTANT,
    PILOT_CITY_LABELS,
)
from app.core.enums import PilotCity, Pollutant
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.core.logging import get_logger
from app.ml.attribution import (
    Attribution,
    CandidateSource,
    WindHour,
    attribute,
    back_trajectory,
    fire_to_candidate,
)
from app.ml.exposure import Advisory, DepartureOption, RouteSample, advise, route_exposure
from app.ml.forecasting import ForecastPoint, forecast_corridor, sample_corridor
from app.ml.hotspot_detection import Hotspot, detect_over_window
from app.repositories import observation_repository, station_repository

logger = get_logger(__name__)

#: Default window, in hours, for hotspot detection over recent history.
DEFAULT_DETECTION_WINDOW_HOURS = 168

#: Neighbouring stations a station needs before it can be judged against its
#: neighbourhood at all. Published so a city with fewer is told why it shows no
#: hotspots, rather than left to read an empty list as clean air.
DETECTION_MIN_NEIGHBOURS = FUSION_MIN_NEIGHBOURS


@dataclass(frozen=True, slots=True)
class StationSnapshot:
    """A station's most recent reading, with the index it implies."""

    station_id: int
    name: str
    coordinates: LonLat
    h3_cell: H3Cell
    observed_at: datetime
    value: float
    unit: str
    aqi: float
    category: str


@dataclass(frozen=True, slots=True)
class CitySummary:
    """A city a view can be scoped to."""

    city: PilotCity
    label: str
    centre: LonLat
    radius_m: float
    default_pollutant: Pollutant


def pilot_cities() -> list[CitySummary]:
    """The cities this deployment covers, in the order they are offered."""
    return [
        CitySummary(
            city=city,
            label=PILOT_CITY_LABELS[city.value],
            centre=PILOT_CITY_CENTRES[city.value],
            radius_m=CITY_VIEW_RADIUS_M,
            default_pollutant=Pollutant(PILOT_CITY_DEFAULT_POLLUTANT[city.value]),
        )
        for city in PilotCity
    ]


@dataclass(frozen=True, slots=True)
class CorridorOutlook:
    """A corridor forecast, with how much of the route it actually covers.

    The covered length is reported because the points alone cannot express it.
    A route whose western six kilometres return nothing looks identical to a
    shorter route, and a consumer that cannot tell them apart would read
    unmonitored ground as clean.
    """

    points: list[ForecastPoint]
    length_m: float


@dataclass(frozen=True, slots=True)
class AttributedHotspot:
    """A detected hotspot together with what may have caused it."""

    hotspot: Hotspot
    station_name: str
    attributions: list[Attribution]
    #: True when the trajectory could not be traced, usually because the air was
    #: calm. Distinguishes "nothing explains this" from "we could not look".
    trajectory_unavailable: bool


def latest_snapshots(
    session: Session, pollutant: Pollutant, city: PilotCity | None = None
) -> list[StationSnapshot]:
    """Every station's most recent reading, with its sub-index, optionally in one city."""
    snapshots: list[StationSnapshot] = []

    for row in observation_repository.latest_reading_per_station(session, pollutant):
        station_id, name, lon, lat, cell, observed_at, value, unit = row
        if not in_city((float(lon), float(lat)), city):
            continue
        sub_index = aqi.sub_index(pollutant, float(value))
        snapshots.append(
            StationSnapshot(
                station_id=int(station_id),
                name=str(name),
                coordinates=(float(lon), float(lat)),
                h3_cell=str(cell),
                observed_at=observed_at,
                value=float(value),
                unit=str(unit),
                aqi=sub_index,
                category=aqi.category(sub_index),
            )
        )

    snapshots.sort(key=lambda snapshot: snapshot.aqi, reverse=True)
    return snapshots


def detect_and_attribute(
    session: Session,
    pollutant: Pollutant,
    *,
    window_hours: int = DEFAULT_DETECTION_WINDOW_HOURS,
    now: datetime | None = None,
    bounded: bool = False,
    city: PilotCity | None = None,
) -> list[AttributedHotspot]:
    """Detect hotspots over a recent window and rank candidate sources for each.

    Args:
        session: Database session.
        pollutant: Pollutant to analyse.
        window_hours: How far back to look.
        now: Reference time, injectable for tests.
        bounded: Stop the window at ``now`` rather than running to the present.
            The live API always means "up to now", so this is off by default; a
            replay of a recorded episode needs it, or observations from after
            the episode would leak in and the result would depend on whatever
            else the database happens to hold.

    Returns:
        Confirmed hotspots, worst first, each with its ranked candidates. An
        empty attribution list is meaningful: it says nothing in the registry
        explains the excess, which points at an unregistered source.
    """
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)

    readings = observation_repository.observed_readings_in_window(
        session, pollutant, since, reference if bounded else None
    )
    names = {reading.station_id: reading.station_name for reading in readings}

    # Detection runs over the whole network and only the result is scoped: a
    # station's neighbours across a city line still set what it should read.
    hotspots = [
        hotspot for hotspot in detect_over_window(readings) if in_city(hotspot.coordinates, city)
    ]
    if not hotspots:
        return []

    wind = _load_wind(session, since)
    sources = _load_sources(session, since)

    attributed: list[AttributedHotspot] = []
    for hotspot in hotspots:
        trajectory = back_trajectory(hotspot.coordinates, hotspot.last_seen_at, wind)
        ranked = attribute(hotspot.coordinates, hotspot.last_seen_at, trajectory, sources)
        attributed.append(
            AttributedHotspot(
                hotspot=hotspot,
                station_name=names.get(hotspot.station_id, "unknown"),
                attributions=ranked,
                trajectory_unavailable=len(trajectory) < 2,
            )
        )

    logger.info(
        "analysis.hotspots_detected",
        pollutant=pollutant.value,
        window_hours=window_hours,
        hotspots=len(attributed),
        with_attribution=sum(1 for item in attributed if item.attributions),
    )
    return attributed


def _load_wind(session: Session, since: datetime) -> dict[datetime, WindHour]:
    """Load the wind field for back-trajectory tracing."""
    return {
        record.observed_at: WindHour(wind_u=record.wind_u, wind_v=record.wind_v)
        for record in observation_repository.weather_in_window(session, since)
    }


def _load_sources(session: Session, since: datetime) -> list[CandidateSource]:
    """Load registered sources and recent fire detections as candidates."""
    sources: list[CandidateSource] = [
        CandidateSource(
            identifier=str(source.id),
            name=source.name,
            source_type=source.source_type,
            coordinates=(float(lon), float(lat)),
            emission_prior=source.emission_prior,
        )
        for source, lon, lat in station_repository.list_sources_with_coordinates(session)
    ]

    for (
        fire_id,
        lon,
        lat,
        observed_at,
        frp_mw,
        confidence,
    ) in observation_repository.fire_detections_in_window(session, since):
        sources.append(
            fire_to_candidate(
                identifier=f"fire-{fire_id}",
                coordinates=(float(lon), float(lat)),
                observed_at=observed_at,
                frp_mw=float(frp_mw),
                confidence=float(confidence),
            )
        )

    return sources


def corridor_outlook(
    session: Session,
    polyline: list[LonLat],
    pollutant: Pollutant,
    horizon_hours: int,
    *,
    history_hours: int = 336,
    now: datetime | None = None,
) -> CorridorOutlook:
    """Forecast a corridor from stored station history.

    Args:
        session: Database session.
        polyline: Ordered ``(lon, lat)`` vertices of the route.
        pollutant: Pollutant to forecast.
        horizon_hours: Lead time.
        history_hours: How much history to build each station's climatology from.
        now: Issue time, injectable for tests.

    Returns:
        Forecast points along the corridor. Stretches with no station in range
        return nothing rather than an interpolation from nothing.
    """
    issued_at = now or datetime.now(UTC)
    since = issued_at - timedelta(hours=history_hours)

    history: dict[int, dict[datetime, float]] = defaultdict(dict)
    positions: dict[int, LonLat] = {}

    for row in observation_repository.readings_in_window(session, pollutant, since):
        station_id, _, lon, lat, _, observed_at, value = row
        station_id = int(station_id)
        positions[station_id] = (float(lon), float(lat))
        history[station_id][observed_at] = float(value)

    return CorridorOutlook(
        points=forecast_corridor(polyline, history, positions, issued_at, horizon_hours),
        # The last sample's distance is the route's full length, which is the
        # denominator for how much of it the network can actually support.
        length_m=sample_corridor(polyline)[-1][1],
    )


def exposure_advisory(
    session: Session,
    polyline: list[LonLat],
    pollutant: Pollutant,
    *,
    history_hours: int = 336,
    now: datetime | None = None,
) -> Advisory:
    """Rank departure times for a route by the exposure each would cost.

    Built on the daily cycle, which is what the climatological forecast actually
    resolves. Each candidate hour is forecast along the whole route, the route
    is integrated with time spent in each segment as the weight, and the hours
    are ranked.

    Returns:
        The ranking, with the recommendation withheld when the spread across the
        day is smaller than the forecast's own error.
    """
    issued_at = now or datetime.now(UTC)
    since = issued_at - timedelta(hours=history_hours)

    history: dict[int, dict[datetime, float]] = defaultdict(dict)
    positions: dict[int, LonLat] = {}

    for row in observation_repository.readings_in_window(session, pollutant, since):
        station_id, _, lon, lat, _, observed_at, value = row
        station_id = int(station_id)
        positions[station_id] = (float(lon), float(lat))
        history[station_id][observed_at] = float(value)

    options: list[DepartureOption] = []
    for hour in EXPOSURE_CANDIDATE_HOURS:
        # Each candidate is the next occurrence of that hour, so every option is
        # a forecast rather than a mix of forecast and hindsight.
        horizon = (hour - issued_at.hour) % HOURS_PER_DAY or HOURS_PER_DAY
        points = forecast_corridor(polyline, history, positions, issued_at, horizon)

        exposure, mean, minutes = route_exposure(
            [
                RouteSample(
                    distance_along_km=point.distance_along_m / METRES_PER_KILOMETRE,
                    value=point.value,
                )
                for point in points
            ]
        )
        options.append(
            DepartureOption(
                hour=hour,
                exposure=exposure,
                mean_concentration=mean,
                travel_minutes=minutes,
            )
        )

    advisory = advise(options)
    logger.info(
        "analysis.exposure_advisory",
        pollutant=pollutant.value,
        actionable=advisory.is_meaningful,
        reduction=round(advisory.reduction, 3),
    )
    return advisory
