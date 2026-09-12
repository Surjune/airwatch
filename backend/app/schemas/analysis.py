"""Response models for the analysis endpoints.

Every estimated quantity carries its uncertainty or confidence in the payload
itself. That is not decoration: leave-one-station-out validation put the typical
reconstruction error near 10 µg/m³ and the forecast error near 16, so a client
that renders a bare number renders something misleading. Making the field
required means a consumer has to at least decide to ignore it.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import Pollutant, SourceType


class Position(BaseModel):
    """A WGS84 position, in GeoJSON order."""

    longitude: float = Field(ge=-180.0, le=180.0)
    latitude: float = Field(ge=-90.0, le=90.0)


class StationReadingResponse(BaseModel):
    """A station's most recent reading."""

    station_id: int
    name: str
    position: Position
    h3_cell: str
    observed_at: datetime
    value: float = Field(description="Concentration in the pollutant's storage unit.")
    unit: str
    aqi: float = Field(description="CPCB sub-index for this pollutant alone.")
    category: str = Field(description="CPCB band name for the sub-index.")


class StationsResponse(BaseModel):
    """Latest readings across the network."""

    pollutant: Pollutant
    station_count: int
    readings: list[StationReadingResponse]


class AttributionResponse(BaseModel):
    """A ranked candidate explanation for a hotspot."""

    name: str
    source_type: SourceType
    position: Position
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Plausibility, not proof. Candidates are ranked, never asserted: "
            "naming the wrong operator is worse than naming nobody."
        ),
    )
    distance_m: float
    hours_upwind: float
    explanation: str


class HotspotResponse(BaseModel):
    """A location that stayed dirtier than its neighbourhood predicted."""

    station_id: int
    station_name: str
    position: Position
    h3_cell: str
    first_seen_at: datetime
    last_seen_at: datetime
    duration_hours: float
    intervals: int
    peak_observed: float = Field(description="Highest concentration during the episode.")
    peak_expected: float = Field(
        description="What the surrounding network predicted at that moment."
    )
    peak_excess: float = Field(
        description="Observed minus expected. This is the quantity that locates a source."
    )
    peak_z: float = Field(description="Excess in units of the expected error at this location.")
    attributions: list[AttributionResponse]
    trajectory_unavailable: bool = Field(
        description=(
            "True when the air was calm and no back-trajectory could be traced. "
            "Distinguishes 'nothing explains this' from 'we could not look'."
        )
    )


class HotspotsResponse(BaseModel):
    """Hotspots detected over a recent window."""

    pollutant: Pollutant
    window_hours: int
    hotspot_count: int
    hotspots: list[HotspotResponse]


class ForecastPointResponse(BaseModel):
    """A forecast for one point along a corridor."""

    position: Position
    distance_along_km: float
    target_time: datetime
    value: float
    uncertainty: float = Field(
        description="Expected absolute error, measured on a temporal holdout."
    )
    upper_bound: float = Field(
        description="Value plus uncertainty, which is what a precautionary decision uses."
    )
    category: str


class CorridorForecastResponse(BaseModel):
    """A corridor outlook."""

    pollutant: Pollutant
    horizon_hours: int
    issued_at: datetime
    method: str = Field(
        description=(
            "Which estimator produced this. Climatological, because it beat every "
            "learned model on a temporal holdout."
        )
    )
    corridor_length_km: float = Field(description="Total length of the requested route.")
    covered_length_km: float = Field(
        description=(
            "How much of the route the station network can support. Stretches "
            "beyond this return no forecast and must render as unknown, never "
            "as clean: an interpolation from nothing would be worse than silence."
        )
    )
    point_count: int
    points: list[ForecastPointResponse]
