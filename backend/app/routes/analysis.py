"""Read-side analysis endpoints.

Routes parse the request, call exactly one service, and shape the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core import aqi
from app.core.constants import FORECAST_MAX_HORIZON_HOURS
from app.core.enums import Pollutant
from app.core.exceptions import ValidationError
from app.core.geo import LonLat, validate_lon_lat
from app.repositories.session import get_db_session
from app.schemas.analysis import (
    AttributionResponse,
    CorridorForecastResponse,
    ForecastPointResponse,
    HotspotResponse,
    HotspotsResponse,
    Position,
    StationReadingResponse,
    StationsResponse,
)
from app.services import analysis_service

router = APIRouter(tags=["analysis"])

#: Bounds on the detection window a caller may request, in hours.
_MIN_WINDOW_HOURS = 1
_MAX_WINDOW_HOURS = 720

#: Fewest vertices a corridor needs.
_MIN_CORRIDOR_VERTICES = 2

#: Distances are stored in metres and presented in kilometres.
_METRES_PER_KM = 1000.0


def _position(coordinates: LonLat) -> Position:
    lon, lat = coordinates
    return Position(longitude=lon, latitude=lat)


@router.get(
    "/stations",
    response_model=StationsResponse,
    summary="Latest reading at every station",
)
def list_stations(
    session: Annotated[Session, Depends(get_db_session)],
    pollutant: Pollutant = Pollutant.PM25,
) -> StationsResponse:
    """Return the most recent reading for each station, worst first."""
    snapshots = analysis_service.latest_snapshots(session, pollutant)
    return StationsResponse(
        pollutant=pollutant,
        station_count=len(snapshots),
        readings=[
            StationReadingResponse(
                station_id=snapshot.station_id,
                name=snapshot.name,
                position=_position(snapshot.coordinates),
                h3_cell=snapshot.h3_cell,
                observed_at=snapshot.observed_at,
                value=snapshot.value,
                unit=snapshot.unit,
                aqi=snapshot.aqi,
                category=snapshot.category,
            )
            for snapshot in snapshots
        ],
    )


@router.get(
    "/hotspots",
    response_model=HotspotsResponse,
    summary="Locations dirtier than their neighbourhood predicts",
)
def list_hotspots(
    session: Annotated[Session, Depends(get_db_session)],
    pollutant: Pollutant = Pollutant.PM25,
    window_hours: Annotated[
        int, Query(ge=_MIN_WINDOW_HOURS, le=_MAX_WINDOW_HOURS)
    ] = analysis_service.DEFAULT_DETECTION_WINDOW_HOURS,
) -> HotspotsResponse:
    """Detect hotspots over a recent window and rank candidate sources."""
    detected = analysis_service.detect_and_attribute(session, pollutant, window_hours=window_hours)

    return HotspotsResponse(
        pollutant=pollutant,
        window_hours=window_hours,
        hotspot_count=len(detected),
        hotspots=[
            HotspotResponse(
                station_id=item.hotspot.station_id,
                station_name=item.station_name,
                position=_position(item.hotspot.coordinates),
                h3_cell=item.hotspot.h3_cell,
                first_seen_at=item.hotspot.first_seen_at,
                last_seen_at=item.hotspot.last_seen_at,
                duration_hours=item.hotspot.duration_hours,
                intervals=item.hotspot.intervals,
                peak_observed=item.hotspot.peak_observed,
                peak_expected=item.hotspot.peak_observed - item.hotspot.peak_residual,
                peak_excess=item.hotspot.peak_residual,
                peak_z=item.hotspot.peak_z,
                trajectory_unavailable=item.trajectory_unavailable,
                attributions=[
                    AttributionResponse(
                        name=candidate.source.name,
                        source_type=candidate.source.source_type,
                        position=_position(candidate.source.coordinates),
                        confidence=candidate.confidence,
                        distance_m=candidate.distance_m,
                        hours_upwind=candidate.hours_upwind,
                        explanation=candidate.explanation,
                    )
                    for candidate in item.attributions
                ],
            )
            for item in detected
        ],
    )


@router.get(
    "/forecast/corridor",
    response_model=CorridorForecastResponse,
    summary="Concentration outlook along a route",
)
def corridor_forecast(
    session: Annotated[Session, Depends(get_db_session)],
    points: Annotated[
        str,
        Query(
            description=(
                "Corridor vertices as lon,lat pairs separated by semicolons, "
                "for example '77.03,28.59;77.21,28.61;77.32,28.65'."
            )
        ),
    ],
    pollutant: Pollutant = Pollutant.PM25,
    horizon_hours: Annotated[int, Query(ge=1, le=FORECAST_MAX_HORIZON_HOURS)] = 24,
) -> CorridorForecastResponse:
    """Forecast concentrations along a corridor."""
    polyline = _parse_polyline(points)
    issued_at = datetime.now(UTC)

    outlook = analysis_service.corridor_outlook(
        session, polyline, pollutant, horizon_hours, now=issued_at
    )
    forecasts = outlook.points

    return CorridorForecastResponse(
        pollutant=pollutant,
        horizon_hours=horizon_hours,
        issued_at=issued_at,
        method="diurnal climatology, distance-weighted across nearby stations",
        corridor_length_km=outlook.length_m / _METRES_PER_KM,
        covered_length_km=(
            (forecasts[-1].distance_along_m - forecasts[0].distance_along_m) / _METRES_PER_KM
            if forecasts
            else 0.0
        ),
        point_count=len(forecasts),
        points=[
            ForecastPointResponse(
                position=_position(point.coordinates),
                distance_along_km=point.distance_along_m / _METRES_PER_KM,
                target_time=point.target_time,
                value=point.value,
                uncertainty=point.uncertainty,
                upper_bound=point.upper_bound,
                category=aqi.category(aqi.sub_index(pollutant, point.value)),
            )
            for point in forecasts
        ],
    )


def _parse_polyline(raw: str) -> list[LonLat]:
    """Parse a semicolon-separated list of lon,lat pairs.

    Raises:
        ValidationError: The string is malformed or describes fewer than two
            vertices. Coordinates arriving over the wire are untrusted, so each
            pair is range-checked rather than trusted to be sane.
    """
    vertices: list[LonLat] = []

    for part in raw.split(";"):
        piece = part.strip()
        if not piece:
            continue
        fields = piece.split(",")
        if len(fields) != 2:
            raise ValidationError(
                f"Corridor vertex {piece!r} is not a 'lon,lat' pair.",
            )
        try:
            lon, lat = float(fields[0]), float(fields[1])
        except ValueError as error:
            raise ValidationError(
                f"Corridor vertex {piece!r} does not contain two numbers.",
            ) from error
        vertices.append(validate_lon_lat(lon, lat))

    if len(vertices) < _MIN_CORRIDOR_VERTICES:
        raise ValidationError(
            f"A corridor needs at least {_MIN_CORRIDOR_VERTICES} vertices, got {len(vertices)}.",
        )
    return vertices
