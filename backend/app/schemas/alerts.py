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

from app.core.enums import AlertKind, AlertStatus, Pollutant
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
    peak_expected: float = Field(
        description=(
            "What the surrounding network predicted at that moment. Carried "
            "alongside the observation rather than left to the client to derive, "
            "so every consumer states the comparison the same way."
        )
    )
    peak_excess: float = Field(
        description="How far above the neighbourhood prediction. This is what locates a source."
    )
    peak_z: float = Field(description="Excess in units of the expected error at this location.")

    sent_at: datetime = Field(description="When the alert was recorded.")
    delivered_at: datetime | None = Field(
        default=None,
        description=(
            "When the authority's endpoint accepted it. Null with a non-null "
            "sent_at means the alert exists in the trail but nobody has been "
            "told -- a different finding from an authority that was told and "
            "stayed silent."
        ),
    )
    delivery_error: str | None = Field(
        default=None,
        description="Why delivery failed, when it did. The alert stays queued.",
    )
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution_note: str | None = None
    kind: AlertKind = Field(
        default=AlertKind.LOCAL,
        description=(
            "local: the hotspot is on this authority's ground. coordination: the "
            "hotspot is on a neighbour's ground, and this authority holds its "
            "likeliest upwind source."
        ),
    )
    source_name: str | None = Field(
        default=None, description="For a coordination request, the source to inspect."
    )
    source_confidence: float | None = Field(
        default=None,
        description=(
            "How plausible attribution judged that source, in [0, 1). A ranked "
            "candidate, never an established cause."
        ),
    )


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
    coordination_requests: int = Field(
        default=0,
        description=(
            "Of the alerts raised, how many ask a neighbouring jurisdiction to act "
            "on a source on its ground."
        ),
    )


class DeliveryResponse(BaseModel):
    """What one delivery run achieved."""

    attempted: int
    delivered: int
    failed: int = Field(
        description="Attempts that failed. Those alerts stay queued rather than being lost."
    )
    endpoint_configured: bool = Field(
        description=(
            "False when no endpoint is configured, so nothing was attempted. "
            "Distinct from zero pending: one means nothing to send, the other "
            "means nowhere to send it."
        )
    )
    pending: int = Field(description="Alerts still waiting after this run.")


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
