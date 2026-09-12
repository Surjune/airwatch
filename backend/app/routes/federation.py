"""Federation dashboard endpoint.

Routes parse the request, call exactly one service, and shape the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.repositories.session import get_db_session
from app.schemas.federation import (
    FederationStatusResponse,
    NodeCoverageResponse,
    TransferResultResponse,
)
from app.services import federation_service

router = APIRouter(prefix="/federation", tags=["federation"])


@router.get(
    "/status",
    response_model=FederationStatusResponse,
    summary="Node coverage, and whether federating helped",
)
def status(
    session: Annotated[Session, Depends(get_db_session)],
    pollutant: Pollutant = Pollutant.PM25,
) -> FederationStatusResponse:
    """Report live monitoring coverage and the measured transfer result."""
    current = federation_service.status(session, pollutant)

    return FederationStatusResponse(
        reporting_window_hours=current.reporting_window_hours,
        summary=current.summary,
        coverage=[
            NodeCoverageResponse(
                node=node.node,
                stations=node.stations,
                reporting_stations=node.reporting_stations,
                silent_stations=node.silent_stations,
                readings=node.readings,
                latest_reading_at=node.latest_reading_at,
                is_unmonitored=node.is_unmonitored,
                is_stale=node.is_stale,
            )
            for node in current.coverage
        ],
        transfer=[
            TransferResultResponse(
                node=result.node,
                local_mae=result.local_mae,
                global_mae=result.global_mae,
                improvement=result.improvement,
                is_harmed=result.is_harmed,
                recommendation=result.recommendation,
                train_rows=result.train_rows,
                test_rows=result.test_rows,
            )
            for result in current.transfer
        ],
    )
