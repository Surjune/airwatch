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
from app.core.enums import Pollutant
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
from app.ml.forecasting import ForecastPoint, forecast_corridor
from app.ml.fusion_features import StationReading
from app.ml.hotspot_detection import Hotspot, detect_hotspots, score_hour
from app.repositories import observation_repository, station_repository

logger = get_logger(__name__)

#: Default window, in hours, for hotspot detection over recent history.
DEFAULT_DETECTION_WINDOW_HOURS = 168


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
class AttributedHotspot:
    """A detected hotspot together with what may have caused it."""

    hotspot: Hotspot
    station_name: str
    attributions: list[Attribution]
    #: True when the trajectory could not be traced, usually because the air was
    #: calm. Distinguishes "nothing explains this" from "we could not look".
    trajectory_unavailable: bool


def latest_snapshots(session: Session, pollutant: Pollutant) -> list[StationSnapshot]:
    """Every station's most recent reading, with its sub-index."""
    snapshots: list[StationSnapshot] = []

    for row in observation_repository.latest_reading_per_station(session, pollutant):
        station_id, name, lon, lat, cell, observed_at, value, unit = row
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
) -> list[AttributedHotspot]:
    """Detect hotspots over a recent window and rank candidate sources for each.

    Args:
        session: Database session.
        pollutant: Pollutant to analyse.
        window_hours: How far back to look.
        now: Reference time, injectable for tests.

    Returns:
        Confirmed hotspots, worst first, each with its ranked candidates. An
        empty attribution list is meaningful: it says nothing in the registry
        explains the excess, which points at an unregistered source.
    """
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)

    readings_by_hour: dict[datetime, list[StationReading]] = defaultdict(list)
    cells: dict[int, H3Cell] = {}
    names: dict[int, str] = {}

    for row in observation_repository.readings_in_window(session, pollutant, since):
        station_id, name, lon, lat, cell, observed_at, value = row
        station_id = int(station_id)
        cells[station_id] = str(cell)
        names[station_id] = str(name)
        readings_by_hour[observed_at].append(
            StationReading(
                station_id=station_id,
                coordinates=(float(lon), float(lat)),
                value=float(value),
            )
        )

    anomalies = []
    for observed_at, readings in readings_by_hour.items():
        anomalies.extend(score_hour(readings, cells, observed_at))

    hotspots = detect_hotspots(anomalies)
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
) -> list[ForecastPoint]:
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

    return forecast_corridor(polyline, history, positions, issued_at, horizon_hours)
