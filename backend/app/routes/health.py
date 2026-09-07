"""Health endpoint.

Routes parse the request, call exactly one service, and return the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.config import Settings, get_settings
from app.schemas.health import HealthResponse
from app.services.health_service import build_health_report

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and upstream configuration",
)
def health(settings: Annotated[Settings, Depends(get_settings)]) -> HealthResponse:
    """Report that the service is up and which upstreams are configured."""
    return build_health_report(settings)
