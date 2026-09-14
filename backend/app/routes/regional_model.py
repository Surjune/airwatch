"""CAMS regional model endpoint.

Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import PilotCity, Pollutant
from app.repositories.model_repository import ModelRow
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.regional_model import (
    ModelComparisonResponse,
    ModelHourResponse,
    RegionalModelResponse,
)
from app.services import regional_model_service

router = APIRouter(prefix="/regional-model", tags=["sources"])

_SOURCE = "CAMS global atmospheric composition forecast (Copernicus), via Open-Meteo"

_NOTICE = (
    "Modelled, not measured. The model averages over tens of kilometres, so it describes the "
    "air over the city rather than any street, misses local sources a monitor would catch, "
    "and is compared with this city's monitors before its number should be read. It is never "
    "used for hotspot detection or the corridor forecast."
)


def _hour(row: ModelRow) -> ModelHourResponse:
    return ModelHourResponse(
        observed_at=row.observed_at, value=row.value, is_forecast=row.is_forecast
    )


@router.get(
    "",
    response_model=RegionalModelResponse,
    summary="The CAMS regional model over a city, with its bias against the monitors",
)
def regional_model(
    session: Annotated[Session, Depends(get_db_session)],
    city: PilotCity,
    pollutant: Pollutant = Pollutant.PM25,
) -> RegionalModelResponse:
    """Modelled hours around now, peaks ahead, and how the model compared with monitors."""
    view = regional_model_service.city_view(session, city, pollutant)
    comparison = view.comparison
    return RegionalModelResponse(
        city=view.city,
        pollutant=view.pollutant,
        source=_SOURCE,
        grid_point=(
            Position(longitude=view.grid_point[0], latitude=view.grid_point[1])
            if view.grid_point
            else None
        ),
        latest=_hour(view.latest) if view.latest else None,
        next_day_peak=view.next_day_peak,
        outlook_peak=view.outlook_peak,
        hours=[_hour(hour) for hour in view.hours],
        comparison=ModelComparisonResponse(
            pairs=comparison.pairs,
            pairs_needed=comparison.pairs_needed,
            stations=view.compared_stations,
            median_ratio=comparison.median_ratio,
            median_difference=comparison.median_difference,
            is_established=comparison.is_established,
        ),
        notice=_NOTICE,
    )
