"""Response models for CPCB's official AQI feed."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import PilotCity, Pollutant
from app.schemas.analysis import Position


class OfficialStationResponse(BaseModel):
    """One station's latest official figures."""

    station_name: str
    position: Position
    reported_at: datetime
    sub_indices: dict[Pollutant, float] = Field(
        description=(
            "CPCB sub-index per pollutant: each pollutant's latest, from the station's last "
            "three hours of reports, because the feed publishes pollutants staggered by an hour."
        )
    )
    oldest_reported_at: datetime = Field(
        description="When the oldest sub-index combined here was published."
    )
    aqi: float | None = Field(
        description=(
            "The highest sub-index, stated only when CPCB would state one: at least three "
            "pollutants reported, one of them PM2.5 or PM10."
        )
    )
    category: str | None
    dominant_pollutant: Pollutant | None


class OfficialAqiResponse(BaseModel):
    """CPCB's latest published AQI for every station in a city."""

    city: PilotCity
    source: str
    station_count: int
    stations: list[OfficialStationResponse]
