"""Request and response models for the alert console.

The response deliberately carries both what was measured and what was expected.
An alert that said only "412 ug/m3" would send an inspector to whichever
location had the highest number, which on a bad day is everywhere. Saying "412
where 78 was expected" sends them to the one place with something to find.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from app.core.enums import AlertStatus, Pollutant
from app.schemas.analysis import Position


class AlertResponse(BaseModel):
    """One alert with the context needed to act on it."""

    alert_id: int
    status: AlertStatus
    authority_id: int
    authority_name: str

    hotspot_id: int
    station_name: str | None = Field(
        default=None,
        description=(
            "Null when the episode was detected on ground no station covers, "
            "which is the case the fused surface exists to reach."
        ),
    )
    position: Position
    pollutant: Pollutant

    first_seen_at: datetime
    last_seen_at: datetime

    peak_observed: float = Field(description="Highest concentration during the episode.")
    peak_excess: float = Field(
        description="How far above the neighbourhood prediction. This is what locates a source."
    )
    peak_z: float = Field(description="Excess in units of the expected error at this location.")

    sent_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class AlertsResponse(BaseModel):
    """The alert inbox."""

    alert_count: int
    alerts: list[AlertResponse]


class DispatchResponse(BaseModel):
    """What one dispatch run did."""

    detected: int
    raised: int
    suppressed: int = Field(
        description=(
            "Episodes already in flight with the same authority. A source that "
            "burns for eight hours is one event, not eight alerts."
        )
    )
    unrouted: int = Field(
        description=(
            "Hotspots inside no registered jurisdiction. Reported rather than "
            "dropped: an incomplete authority registry must not read as a quiet day."
        )
    )


class ResolveRequest(BaseModel):
    """Closing an alert requires saying what was found."""

    note: Annotated[str, Field(min_length=1, max_length=1024)] = Field(
        description=(
            "What was found or done. Required: a resolution with no explanation "
            "records that someone clicked a button, which is not the same as "
            "recording that something was done."
        )
    )

    @field_validator("note")
    @classmethod
    def _reject_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A resolution note cannot be blank.")
        return value


class SlaBreachResponse(BaseModel):
    """An alert that has outlived the time its authority had to respond."""

    alert_id: int
    authority_id: int
    stage: str = Field(description="Which deadline elapsed: acknowledgement or resolution.")
    overdue_hours: float


class SlaBreachesResponse(BaseModel):
    """Alerts past their response deadline, longest overdue first."""

    breach_count: int
    breaches: list[SlaBreachResponse]
