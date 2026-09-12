"""Citizen photo submission endpoints.

Routes parse the request, call exactly one service, and shape the response.
No business rules, no arithmetic, no database access.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from sqlalchemy.orm import Session

from app.ml.vision import Rejection
from app.repositories import citizen_repository
from app.repositories.session import get_db_session
from app.schemas.analysis import Position
from app.schemas.citizen import (
    CalibrationStatusResponse,
    CitizenReportsResponse,
    CitizenReportSummary,
    HazeEstimateResponse,
    ReferenceComparisonResponse,
    RejectionResponse,
    SubmissionResponse,
)
from app.services import citizen_service
from app.services.citizen_service import AcceptedReport, CalibrationStatus

router = APIRouter(prefix="/citizen", tags=["citizen"])

#: Bounds on the window a caller may request for the public map, in hours.
_MIN_WINDOW_HOURS = 1
_MAX_WINDOW_HOURS = 720

#: Shortest device identifier accepted. Long enough that an identifier is not
#: trivially guessable, which is what stops one participant attributing
#: submissions to another device to dodge the rate limit.
_MIN_DEVICE_ID_LENGTH = 8

#: Status returned when a photograph is well formed but cannot support an
#: estimate. Written as a literal rather than taken from Starlette's constants,
#: which renamed this one and deprecated the old spelling.
_UNPROCESSABLE = 422


def _calibration(status_: CalibrationStatus) -> CalibrationStatusResponse:
    return CalibrationStatusResponse(
        is_calibrated=status_.is_calibrated,
        pairs=status_.pairs,
        pairs_needed=status_.pairs_needed,
        mae=status_.mae,
        explanation=status_.explanation,
    )


def _accepted(report: AcceptedReport) -> SubmissionResponse:
    return SubmissionResponse(
        report_id=report.report_id,
        h3_cell=report.h3_cell,
        captured_at=report.captured_at,
        haze_index=report.haze_index,
        trust_score=report.trust_score,
        estimate=(
            HazeEstimateResponse(
                value=report.estimate.value,
                uncertainty=report.estimate.uncertainty,
                upper_bound=report.estimate.upper_bound,
                is_extrapolating=report.is_extrapolating,
            )
            if report.estimate is not None
            else None
        ),
        reference=(
            ReferenceComparisonResponse(
                station_id=report.reference.station_id,
                station_name=report.reference.station_name,
                value=report.reference.value,
                observed_at=report.reference.observed_at,
                distance_m=report.reference.distance_m,
                agrees=report.agrees_with_reference,
            )
            if report.reference is not None
            else None
        ),
        calibration=_calibration(report.calibration),
    )


@router.post(
    "/reports",
    response_model=SubmissionResponse | RejectionResponse,
    summary="Submit a geotagged photograph",
    responses={
        _UNPROCESSABLE: {
            "model": RejectionResponse,
            "description": (
                "The photograph could not support an estimate. Returned with the "
                "reason rather than as a generic failure, because each reason "
                "tells the submitter something different about how to retake it."
            ),
        }
    },
)
async def submit_report(
    session: Annotated[Session, Depends(get_db_session)],
    response: Response,
    photo: Annotated[UploadFile, File(description="A geotagged outdoor photograph.")],
    longitude: Annotated[float, Form(ge=-180.0, le=180.0)],
    latitude: Annotated[float, Form(ge=-90.0, le=90.0)],
    captured_at: Annotated[
        datetime,
        Form(description="When the photo was taken, timezone-aware. Not the upload time."),
    ],
    device_id: Annotated[str, Form(min_length=_MIN_DEVICE_ID_LENGTH, max_length=128)],
) -> SubmissionResponse | RejectionResponse:
    """Measure atmospheric haze in a photograph and store what it yielded.

    Constraints are declared on the form fields themselves so FastAPI checks
    them at the boundary. Validating inside the body instead would raise a
    Pydantic error that is not a request-validation error, and the caller would
    receive an opaque 500 for a request they could have corrected.

    The fields are flat rather than nested under one model, because that is how
    a phone client posts multipart data alongside a file.
    """
    content = await photo.read()

    outcome = citizen_service.submit(
        session,
        content=content,
        coordinates=(longitude, latitude),
        captured_at=captured_at,
        device_id=device_id,
    )

    if isinstance(outcome, Rejection):
        response.status_code = _UNPROCESSABLE
        return RejectionResponse(reason=outcome.reason.value, detail=outcome.detail)

    return _accepted(outcome)


@router.get(
    "/reports",
    response_model=CitizenReportsResponse,
    summary="Recent citizen submissions",
)
def list_reports(
    session: Annotated[Session, Depends(get_db_session)],
    window_hours: Annotated[
        int, Query(ge=_MIN_WINDOW_HOURS, le=_MAX_WINDOW_HOURS)
    ] = citizen_service.DEFAULT_REPORT_WINDOW_HOURS,
) -> CitizenReportsResponse:
    """Submissions over a recent window, newest first."""
    since = datetime.now(UTC) - timedelta(hours=window_hours)
    rows = citizen_repository.recent_reports(
        session, since, limit=citizen_service.MAX_REPORTS_RETURNED
    )
    _, calibration = citizen_service.calibration_status(session)

    return CitizenReportsResponse(
        window_hours=window_hours,
        report_count=len(rows),
        reports=[
            CitizenReportSummary(
                report_id=int(report_id),
                position=Position(longitude=float(lon), latitude=float(lat)),
                h3_cell=str(cell),
                captured_at=captured_at,
                haze_index=float(haze),
                trust_score=float(trust),
                had_reference=reference is not None,
            )
            for report_id, lon, lat, cell, captured_at, haze, trust, reference in rows
        ],
        calibration=_calibration(calibration),
    )


@router.get(
    "/calibration",
    response_model=CalibrationStatusResponse,
    summary="Whether a photograph can yield a concentration yet",
)
def calibration(
    session: Annotated[Session, Depends(get_db_session)],
) -> CalibrationStatusResponse:
    """Report the state of the haze-to-concentration relation."""
    _, status_ = citizen_service.calibration_status(session)
    return _calibration(status_)
