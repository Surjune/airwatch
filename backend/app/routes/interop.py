"""Interoperability endpoints for exchange between city nodes.

Routes parse the request, call exactly one service, and return the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.enums import Pollutant
from app.repositories.session import get_db_session
from app.schemas.interop import (
    HotspotCollection,
    ModelCatalogue,
    NodeCapabilities,
    ObservationCollection,
)
from app.services import interop_service

router = APIRouter(prefix="/interop", tags=["interop"])

#: Bounds on the span a partner may request in one call.
_MIN_WINDOW_HOURS = 1


@router.get(
    "/capabilities",
    response_model=NodeCapabilities,
    summary="What this node offers a partner",
)
def capabilities(
    settings: Annotated[Settings, Depends(get_settings)],
) -> NodeCapabilities:
    """Describe this node so a partner can integrate without prior arrangement."""
    return interop_service.capabilities(settings)


@router.get(
    "/observations",
    response_model=ObservationCollection,
    summary="Station observations as GeoJSON",
)
def observations(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    pollutant: Pollutant = Pollutant.PM25,
    window_hours: Annotated[
        int,
        Query(ge=_MIN_WINDOW_HOURS, le=interop_service.MAX_OBSERVATION_WINDOW_HOURS),
    ] = interop_service.DEFAULT_OBSERVATION_WINDOW_HOURS,
) -> ObservationCollection:
    """Recent observations in an OGC SensorThings-shaped GeoJSON envelope."""
    return interop_service.observations(session, settings, pollutant, window_hours=window_hours)


@router.get(
    "/hotspots",
    response_model=HotspotCollection,
    summary="Detected episodes as GeoJSON",
)
def hotspots(
    session: Annotated[Session, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    pollutant: Pollutant = Pollutant.PM25,
    window_hours: Annotated[
        int,
        Query(ge=_MIN_WINDOW_HOURS, le=interop_service.MAX_OBSERVATION_WINDOW_HOURS),
    ] = interop_service.DEFAULT_OBSERVATION_WINDOW_HOURS,
) -> HotspotCollection:
    """Episodes this node has detected, with observed, expected and excess."""
    return interop_service.hotspots(session, settings, pollutant, window_hours=window_hours)


@router.get(
    "/models",
    response_model=ModelCatalogue,
    summary="Model cards for every estimator this node runs",
)
def models(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ModelCatalogue:
    """Publish what this node runs, how it was validated, and where it fails."""
    return interop_service.models(settings)
