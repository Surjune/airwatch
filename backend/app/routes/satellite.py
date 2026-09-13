"""Satellite tier endpoints.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.enums import PilotCity, SatelliteProduct
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.satellite import SatelliteCellResponse, SatelliteDayResponse, SatelliteResponse
from app.services import satellite_service

router = APIRouter(prefix="/satellite", tags=["satellite"])

_SOURCE = "Sentinel-5P TROPOMI (Copernicus), via Google Earth Engine"

#: Bounds on the history a caller may request, in days.
_MIN_DAYS = 1
_MAX_DAYS = 90


@router.get("", response_model=SatelliteResponse, summary="A Sentinel-5P product over a city")
def city_satellite(
    session: Annotated[Session, Depends(get_db_session)],
    city: PilotCity,
    product: SatelliteProduct = SatelliteProduct.NO2,
    days: Annotated[int, Query(ge=_MIN_DAYS, le=_MAX_DAYS)] = 14,
) -> SatelliteResponse:
    """Daily means over the city, and each coarse cell's latest value."""
    picture = satellite_service.city_picture(session, city, product, days=days)
    return SatelliteResponse(
        city=picture.city,
        product=picture.product,
        unit=picture.unit,
        source=_SOURCE,
        total_cells=picture.total_cells,
        series=[
            SatelliteDayResponse(observed_on=day.observed_on, value=day.value, cells=day.cells)
            for day in picture.series
        ],
        cells=[
            SatelliteCellResponse(
                h3_cell=cell.h3_cell,
                boundary=[Position(longitude=lon, latitude=lat) for lon, lat in cell.boundary],
                observed_on=cell.observed_on,
                value=cell.value,
                pixel_count=cell.pixel_count,
            )
            for cell in picture.cells
        ],
    )
