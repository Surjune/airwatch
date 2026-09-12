"""Request and response models for citizen photo submission.

The response is shaped around one constraint: a person who submits a photograph
gets an answer back, and that answer must not sound more certain than it is.

So `haze_index` is always present and `estimate` may be null. A null estimate is
not a failure -- it is the system saying it measured how hazy the air looked but
cannot yet convert that into a concentration it would stand behind. The
`calibration` block says why in plain language, which is what stops a null from
reading as a bug.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.analysis import Position


class CalibrationStatusResponse(BaseModel):
    """Whether a photograph can currently yield a concentration."""

    is_calibrated: bool
    pairs: int = Field(
        description="Co-located submissions available to fit the haze-to-concentration relation."
    )
    pairs_needed: int
    mae: float | None = Field(
        default=None,
        description=(
            "Leave-one-out error of the fit, in ug/m3. Measured out of sample "
            "because at this sample size the fit has seen every point it would "
            "otherwise be scored on."
        ),
    )
    explanation: str


class HazeEstimateResponse(BaseModel):
    """A concentration derived from a haze index."""

    value: float
    uncertainty: float
    upper_bound: float = Field(
        description="Value plus uncertainty, which is what a precautionary decision uses."
    )
    is_extrapolating: bool = Field(
        description=(
            "True when the photograph's haze sits outside the range the relation "
            "was fitted across, so the number is an extrapolation."
        )
    )


class ReferenceComparisonResponse(BaseModel):
    """The nearby monitor a submission was checked against."""

    station_id: int
    station_name: str
    value: float
    observed_at: datetime
    distance_m: float
    agrees: bool | None = Field(
        default=None,
        description=(
            "Null when no comparison was possible -- either no calibration exists "
            "or the monitor reported nothing usable. An uncomparable submission "
            "is not a disagreement."
        ),
    )


class SubmissionResponse(BaseModel):
    """What a submitted photograph yielded."""

    report_id: int
    h3_cell: str
    captured_at: datetime

    haze_index: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Atmospheric opacity measured from the photograph, dimensionless. "
            "Zero is perfectly clear air. This is what a camera can actually "
            "establish; everything else here is derived from it."
        ),
    )
    trust_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Weight this device's submissions currently carry.",
    )

    estimate: HazeEstimateResponse | None = Field(
        default=None,
        description=(
            "Null until a calibration exists. Null is an answer, not an error: "
            "an uncalibrated concentration derived from a photograph would be a "
            "fabricated reading."
        ),
    )
    reference: ReferenceComparisonResponse | None = None
    calibration: CalibrationStatusResponse


class RejectionResponse(BaseModel):
    """A photograph that cannot support an estimate, and why."""

    accepted: bool = Field(
        default=False,
        description="Always false. Present so a client can branch on one field.",
    )
    reason: str
    detail: str = Field(
        description=(
            "Written for the person who took the photo. Every rejection here is a "
            "condition that would make clean air look dirty, so refusing is the "
            "safe direction to fail in."
        )
    )


class CitizenReportSummary(BaseModel):
    """One submission on the public map."""

    report_id: int
    position: Position
    h3_cell: str
    captured_at: datetime
    haze_index: float
    trust_score: float
    had_reference: bool = Field(
        description="Whether a monitor was in range, so this submission also calibrates."
    )


class CitizenReportsResponse(BaseModel):
    """Recent submissions, newest first."""

    window_hours: int
    report_count: int
    reports: list[CitizenReportSummary]
    calibration: CalibrationStatusResponse
