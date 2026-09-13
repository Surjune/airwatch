"""Request and response models for citizen sensor readings.

Every response carries ``is_calibrated: false`` on the reading itself, not only
in documentation, because the consumer that matters is a map legend. A number
from a household sensor and a number from a ₹1-crore monitor look identical
once drawn, and the flag is what lets a client draw them differently.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.core.enums import PilotCity, Pollutant
from app.schemas.analysis import Position

#: Shortest device identifier accepted, matching photo submissions.
_MIN_DEVICE_ID_LENGTH = 8

#: Bounds on the free-text instrument name: long enough for "AirGradient ONE
#: (indoor)", short enough that the field cannot carry a paragraph.
_MIN_SENSOR_MODEL_LENGTH = 2
_MAX_SENSOR_MODEL_LENGTH = 80


class SensorReadingRequest(BaseModel):
    """One reading from a household particulate sensor."""

    longitude: Annotated[float, Field(ge=-180.0, le=180.0)]
    latitude: Annotated[float, Field(ge=-90.0, le=90.0)]
    pollutant: Literal[Pollutant.PM25, Pollutant.PM10] = Field(
        description="Household sensors count particles, so only PM2.5 and PM10 are accepted."
    )
    value_ugm3: Annotated[float, Field(ge=0.0, description="The reading as displayed, in ug/m3.")]
    observed_at: datetime = Field(
        description="When the sensor measured, timezone-aware. Not the upload time."
    )
    device_id: Annotated[str, Field(min_length=_MIN_DEVICE_ID_LENGTH, max_length=128)]
    sensor_model: Annotated[
        str,
        Field(
            min_length=_MIN_SENSOR_MODEL_LENGTH,
            max_length=_MAX_SENSOR_MODEL_LENGTH,
            description="What the instrument is, for example 'AirGradient ONE'.",
        ),
    ]


class ReferencePairResponse(BaseModel):
    """The reference reading a citizen sensor reading was compared with."""

    station_name: str
    value: float
    observed_at: datetime
    distance_m: float
    relative_difference: float | None = Field(
        default=None,
        description=(
            "(sensor - reference) / reference. Null when the monitor read zero, "
            "where a ratio is undefined rather than enormous."
        ),
    )


class ColocationResponse(BaseModel):
    """What the tier's co-located pairs say about its bias so far."""

    pairs: int
    pairs_needed: int
    median_ratio: float | None = Field(
        default=None, description="Median sensor / reference. Above 1 means sensors read high."
    )
    median_difference: float | None = Field(
        default=None, description="Median sensor - reference, in ug/m3."
    )
    is_established: bool
    explanation: str


class SensorReadingAccepted(BaseModel):
    """What happened to a submitted reading."""

    reading_id: int
    h3_cell: str
    observed_at: datetime
    pollutant: Pollutant
    value_ugm3: float
    raw_aqi: float = Field(
        description="The CPCB sub-index this raw value would carry, before any correction."
    )
    is_calibrated: Literal[False] = False
    reference: ReferencePairResponse | None = Field(
        default=None,
        description="Null when no reference monitor reported within range and time.",
    )
    colocation: ColocationResponse


class SensorReadingSummary(BaseModel):
    """One reading in the public list."""

    reading_id: int
    position: Position
    h3_cell: str
    observed_at: datetime
    sensor_model: str
    value_ugm3: float
    raw_aqi: float
    raw_category: str
    is_calibrated: Literal[False] = False
    reference_station_name: str | None
    reference_value: float | None
    reference_distance_m: float | None


class SensorReadingsResponse(BaseModel):
    """Recent citizen sensor readings, with the tier's measured bias."""

    pollutant: Pollutant
    city: PilotCity | None
    window_hours: int
    reading_count: int
    readings: list[SensorReadingSummary]
    colocation: ColocationResponse
    note: str = Field(description="Why these readings are shown but excluded from every estimate.")
