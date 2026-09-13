"""A resident's own submissions, and the PDF complaint report for each.

Both endpoints are keyed on the ``X-Device-ID`` header rather than a query
parameter, so the identifier stays out of URLs, proxy logs and browser history.
Routes parse the request, call exactly one service, and shape the response.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response
from sqlalchemy.orm import Session

from app.repositories.session import get_db_session
from app.schemas.complaints import ComplaintsResponse, ComplaintSummaryResponse
from app.services import complaint_service

router = APIRouter(prefix="/citizen/complaints", tags=["citizen"])

#: Identifier bounds, matching the submission endpoints.
_MIN_DEVICE_ID_LENGTH = 8
_MAX_DEVICE_ID_LENGTH = 128
#: Longest reference accepted in a path, well above the formatted length.
_MAX_REFERENCE_LENGTH = 32

DeviceId = Annotated[
    str,
    Header(
        alias="X-Device-ID",
        min_length=_MIN_DEVICE_ID_LENGTH,
        max_length=_MAX_DEVICE_ID_LENGTH,
        description="The anonymous identifier this browser submitted with.",
    ),
]

_NOTE = (
    "Submissions made from this browser. They are tied to an anonymous identifier stored "
    "here, so clearing this site's data starts a new list; nobody else can list or download "
    "them."
)


@router.get("", response_model=ComplaintsResponse, summary="This device's submissions")
def list_complaints(
    session: Annotated[Session, Depends(get_db_session)],
    device_id: DeviceId,
) -> ComplaintsResponse:
    """Every photograph and sensor reading this device submitted, newest first."""
    summaries = complaint_service.list_for_device(session, device_id)
    return ComplaintsResponse(
        complaint_count=len(summaries),
        complaints=[
            ComplaintSummaryResponse(
                reference=summary.reference,
                kind=summary.kind,
                submitted_at=summary.submitted_at,
                observed_at=summary.observed_at,
                category=summary.category,
                area=summary.area,
                headline=summary.headline,
                compared_with_monitor=summary.compared_with_monitor,
            )
            for summary in summaries
        ],
        note=_NOTE,
    )


@router.get(
    "/{reference}/pdf",
    summary="Download the PDF complaint report for one submission",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The report."}},
)
def complaint_pdf(
    session: Annotated[Session, Depends(get_db_session)],
    device_id: DeviceId,
    reference: Annotated[str, Path(max_length=_MAX_REFERENCE_LENGTH)],
) -> Response:
    """The report for a submission this device made; any other device gets a 404."""
    canonical, content = complaint_service.render_pdf(session, reference, device_id)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="airwatch-{canonical}.pdf"',
            "Cache-Control": "no-store",
        },
    )
