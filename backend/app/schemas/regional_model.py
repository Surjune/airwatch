"""Response models for the CAMS regional model."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.enums import PilotCity, Pollutant
from app.schemas.analysis import Position


class ModelHourResponse(BaseModel):
    """One modelled hour."""

    observed_at: datetime
    value: float = Field(description="Modelled concentration, ug/m3.")
    is_forecast: bool = Field(description="True for hours after now: the model's forecast.")


class ModelComparisonResponse(BaseModel):
    """How the model compared with the city's reference monitors over the last fortnight."""

    pairs: int = Field(description="Monitor readings paired with the model interpolated to them.")
    pairs_needed: int
    stations: int = Field(description="Reference monitors in the city that contributed pairs.")
    median_ratio: float | None = Field(
        description="Median of model / monitor. Below 1, the model reads low here."
    )
    median_difference: float | None = Field(description="Median of model - monitor, ug/m3.")
    is_established: bool = Field(
        description="Whether there are enough pairs for the ratio to be read as the model's bias."
    )


class RegionalModelResponse(BaseModel):
    """The CAMS regional model over one city."""

    city: PilotCity
    pollutant: Pollutant
    unit: str = "µg/m³"
    source: str
    grid_point: Position | None = Field(
        description="The model grid point the city centre snapped to. Null before first ingest."
    )
    latest: ModelHourResponse | None = Field(
        description="The most recent modelled hour at or before now."
    )
    next_day_peak: float | None = Field(description="Highest modelled hour in the next 24 hours.")
    outlook_peak: float | None = Field(description="Highest modelled hour in the next 72 hours.")
    hours: list[ModelHourResponse] = Field(
        description="Modelled hours from 72 hours ago to 72 hours ahead, oldest first."
    )
    comparison: ModelComparisonResponse
    notice: str = Field(
        description="What a modelled value can and cannot say. Always shown beside the numbers."
    )
