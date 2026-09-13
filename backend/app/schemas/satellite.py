"""Response models for the satellite tier."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from app.core.enums import PilotCity, SatelliteProduct
from app.schemas.analysis import Position


class SatelliteDayResponse(BaseModel):
    """One day's mean across the city's cells."""

    observed_on: date
    value: float
    cells: int = Field(description="Cells with enough valid pixels that day to be averaged.")


class SatelliteCellResponse(BaseModel):
    """One coarse cell's latest value, with its outline."""

    h3_cell: str
    boundary: list[Position]
    observed_on: date
    value: float
    pixel_count: int


class SatelliteResponse(BaseModel):
    """A Sentinel-5P product over one city."""

    city: PilotCity
    product: SatelliteProduct
    unit: str
    source: str = Field(
        description=(
            "Sentinel-5P TROPOMI via Google Earth Engine. A column measurement over "
            "roughly 36 km^2 cells, not a ground concentration."
        )
    )
    series: list[SatelliteDayResponse]
    cells: list[SatelliteCellResponse]
