"""CPCB's daily AQI bulletin endpoint.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import PilotCity
from app.repositories.session import get_db_session
from app.schemas.bulletin import BulletinResponse, CityBulletinResponse
from app.services import bulletin_service

router = APIRouter(prefix="/bulletin", tags=["official"])

_SOURCE = "CPCB daily AQI bulletin: each city's 24-hour average to 4 pm IST"


@router.get("", response_model=BulletinResponse, summary="CPCB's daily AQI for a city")
def city_bulletin(
    session: Annotated[Session, Depends(get_db_session)],
    city: PilotCity,
) -> BulletinResponse:
    """The city's line in CPCB's newest daily bulletin that has one."""
    bulletin = bulletin_service.latest_for_city(session, city)
    return BulletinResponse(
        city=city,
        source=_SOURCE,
        bulletin=None
        if bulletin is None
        else CityBulletinResponse(
            day=bulletin.day,
            averaged_until=bulletin.averaged_until,
            aqi=bulletin.aqi,
            category=bulletin.category,
            prominent_pollutants=bulletin.prominent_pollutants,
            stations_reporting=bulletin.stations_reporting,
            stations_total=bulletin.stations_total,
            source_url=bulletin.source_url,
        ),
    )
