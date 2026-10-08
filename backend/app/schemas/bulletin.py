"""Response models for CPCB's daily AQI bulletin."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.core.enums import PilotCity, Pollutant


class CityBulletinResponse(BaseModel):
    """A city's line in the newest bulletin that has one."""

    day: date
    averaged_until: datetime = Field(
        description="When the 24-hour average ran to: 4 pm IST on the bulletin's day."
    )
    aqi: int
    category: str
    prominent_pollutants: list[Pollutant]
    stations_reporting: int = Field(description="The city's stations that took part.")
    stations_total: int
    source_url: str = Field(description="The bulletin as CPCB published it.")


class BulletinResponse(BaseModel):
    """A city's figure in CPCB's daily bulletin, or null when none is stored."""

    city: PilotCity
    source: str
    bulletin: CityBulletinResponse | None
