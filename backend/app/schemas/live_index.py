"""Response models for AirWatch's live index from the monitors."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import MeasurementOrigin, PilotCity, Pollutant
from app.schemas.analysis import Position


class LiveStationResponse(BaseModel):
    """One monitor's latest particulate readings on CPCB's scale."""

    station_id: int
    name: str
    position: Position
    observed_at: datetime = Field(description="The newest reading combined here.")
    oldest_observed_at: datetime = Field(
        description="The oldest reading combined here. A pollutant more than three hours older "
        "than the newest is left out as not currently reporting."
    )
    aqi: float = Field(
        description=(
            "The higher of the PM2.5 and PM10 sub-indices, each from the monitor's latest hourly "
            "reading. AirWatch's figure, not CPCB's: CPCB averages 24 hours and adds gases."
        )
    )
    category: str
    dominant_pollutant: Pollutant
    sub_indices: dict[Pollutant, float]
    origins: list[MeasurementOrigin] = Field(
        description="The relays the combined readings came through."
    )


class LiveIndexResponse(BaseModel):
    """Every reference monitor's latest index in a city, worst first, however old."""

    city: PilotCity
    basis: str
    station_count: int
    stations: list[LiveStationResponse]
