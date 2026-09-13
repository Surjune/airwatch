"""Citizen sensor reading endpoints.

Routes parse the request, call exactly one service, and shape the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.enums import PilotCity, Pollutant
from app.ml.sensor_colocation import ColocationSummary
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.citizen_sensor import (
    ColocationResponse,
    ReferencePairResponse,
    SensorReadingAccepted,
    SensorReadingRequest,
    SensorReadingsResponse,
    SensorReadingSummary,
)
from app.services import citizen_sensor_service

router = APIRouter(prefix="/citizen/sensor-readings", tags=["citizen"])

#: Bounds on the window a caller may request, in hours.
_MIN_WINDOW_HOURS = 1
_MAX_WINDOW_HOURS = 720

_NOTE = (
    "Readings from household sensors, shown exactly as reported. They are not used "
    "in hotspot detection, the fused surface or forecasts, which read reference "
    "monitors only: a low-cost optical sensor over-reads in humid air, and until its "
    "bias is measured against a monitor a high reading cannot be told apart from a "
    "real local source."
)


def _colocation(summary: ColocationSummary) -> ColocationResponse:
    return ColocationResponse(
        pairs=summary.pairs,
        pairs_needed=summary.pairs_needed,
        median_ratio=summary.median_ratio,
        median_difference=summary.median_difference,
        is_established=summary.is_established,
        explanation=citizen_sensor_service.colocation_explanation(summary),
    )


@router.post(
    "",
    response_model=SensorReadingAccepted,
    summary="Submit a reading from a household air-quality sensor",
)
def submit_reading(
    session: Annotated[Session, Depends(get_db_session)],
    body: SensorReadingRequest,
) -> SensorReadingAccepted:
    """Store a reading as reported and compare it with the nearest reference monitor."""
    accepted = citizen_sensor_service.submit(
        session,
        coordinates=(body.longitude, body.latitude),
        pollutant=body.pollutant,
        value=body.value_ugm3,
        observed_at=body.observed_at,
        device_id=body.device_id,
        sensor_model=body.sensor_model,
    )

    return SensorReadingAccepted(
        reading_id=accepted.reading_id,
        h3_cell=accepted.h3_cell,
        observed_at=accepted.observed_at,
        pollutant=accepted.pollutant,
        value_ugm3=accepted.value,
        raw_aqi=accepted.raw_aqi,
        reference=(
            ReferencePairResponse(
                station_name=accepted.reference.station_name,
                value=accepted.reference.value,
                observed_at=accepted.reference.observed_at,
                distance_m=accepted.reference.distance_m,
                relative_difference=accepted.relative_difference,
            )
            if accepted.reference is not None
            else None
        ),
        colocation=_colocation(accepted.colocation),
    )


@router.get(
    "",
    response_model=SensorReadingsResponse,
    summary="Recent readings from household sensors",
)
def list_readings(
    session: Annotated[Session, Depends(get_db_session)],
    pollutant: Pollutant = Pollutant.PM25,
    window_hours: Annotated[
        int, Query(ge=_MIN_WINDOW_HOURS, le=_MAX_WINDOW_HOURS)
    ] = citizen_sensor_service.DEFAULT_READING_WINDOW_HOURS,
    city: PilotCity | None = None,
) -> SensorReadingsResponse:
    """Readings over a recent window, newest first, with the tier's bias so far."""
    readings, summary = citizen_sensor_service.recent(
        session, pollutant, window_hours=window_hours, city=city
    )

    return SensorReadingsResponse(
        pollutant=pollutant,
        city=city,
        window_hours=window_hours,
        reading_count=len(readings),
        readings=[
            SensorReadingSummary(
                reading_id=item.reading.reading_id,
                position=Position(
                    longitude=item.reading.coordinates[0], latitude=item.reading.coordinates[1]
                ),
                h3_cell=item.reading.h3_cell,
                observed_at=item.reading.observed_at,
                sensor_model=item.reading.sensor_model,
                value_ugm3=item.reading.value,
                raw_aqi=item.raw_aqi,
                raw_category=item.raw_category,
                reference_station_name=item.reading.reference_station_name,
                reference_value=item.reading.reference_value,
                reference_distance_m=item.reading.reference_distance_m,
            )
            for item in readings
        ],
        colocation=_colocation(summary),
        note=_NOTE,
    )
