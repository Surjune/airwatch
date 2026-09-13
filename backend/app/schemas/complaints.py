"""Response models for a resident's own submissions and their complaint reports."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import ComplaintCategory, SubmissionKind


class ComplaintSummaryResponse(BaseModel):
    """One of the requesting device's submissions."""

    reference: str = Field(description="Quote this; the PDF report is downloaded by it.")
    kind: SubmissionKind
    submitted_at: datetime
    observed_at: datetime
    category: ComplaintCategory | None
    area: str = Field(description="The pilot city the submission falls in, if any.")
    headline: str
    compared_with_monitor: bool = Field(
        description="Whether a reference monitor reported close enough in space and time."
    )


class ComplaintsResponse(BaseModel):
    """Every submission this device has made, newest first."""

    complaint_count: int
    complaints: list[ComplaintSummaryResponse]
    note: str
