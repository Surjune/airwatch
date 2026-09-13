"""CPCB official AQI endpoint.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import PilotCity
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.official_aqi import OfficialAqiResponse, OfficialStationResponse
from app.services import official_aqi_service

router = APIRouter(prefix="/official-aqi", tags=["official"])

_SOURCE = "CPCB real-time AQI, published on data.gov.in"


@router.get("", response_model=OfficialAqiResponse, summary="CPCB's latest AQI in a city")
def official_aqi(
    session: Annotated[Session, Depends(get_db_session)],
    city: PilotCity,
) -> OfficialAqiResponse:
    """What CPCB most recently published for each station in the city."""
    stations = official_aqi_service.latest_for_city(session, city)
    return OfficialAqiResponse(
        city=city,
        source=_SOURCE,
        station_count=len(stations),
        stations=[
            OfficialStationResponse(
                station_name=station.station_name,
                position=Position(
                    longitude=station.coordinates[0], latitude=station.coordinates[1]
                ),
                reported_at=station.reported_at,
                sub_indices=station.sub_indices,
                aqi=station.aqi,
                category=station.category,
                dominant_pollutant=station.dominant_pollutant,
            )
            for station in stations
        ],
    )
