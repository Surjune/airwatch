"""AirWatch's live index from the monitors.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import PilotCity
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.live_index import LiveIndexResponse, LiveStationResponse
from app.services import live_index_service

router = APIRouter(prefix="/live-index", tags=["official"])

_BASIS = (
    "Each reference monitor's latest hourly PM2.5 and PM10 on CPCB's scale, the higher of the "
    "two. Worked out by AirWatch, not published by CPCB."
)


@router.get(
    "", response_model=LiveIndexResponse, summary="A live index from each monitor's latest hour"
)
def live_index(
    session: Annotated[Session, Depends(get_db_session)],
    city: PilotCity,
) -> LiveIndexResponse:
    """Each monitor's latest particulate readings in the city, on CPCB's scale."""
    stations = live_index_service.live_for_city(session, city)
    return LiveIndexResponse(
        city=city,
        basis=_BASIS,
        station_count=len(stations),
        stations=[
            LiveStationResponse(
                station_id=station.station_id,
                name=station.name,
                position=Position(
                    longitude=station.coordinates[0], latitude=station.coordinates[1]
                ),
                observed_at=station.observed_at,
                oldest_observed_at=station.oldest_observed_at,
                aqi=station.aqi,
                category=station.category,
                dominant_pollutant=station.dominant_pollutant,
                sub_indices=station.sub_indices,
                origins=station.origins,
            )
            for station in stations
        ],
    )
