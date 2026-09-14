"""The CAMS regional model: hourly air quality over each city, and how far to trust it.

Coimbatore is the reason this exists. OpenAQ lists four reference monitors in
the district; three stopped reporting months ago and the fourth arrives days
late. Between CPCB's once-an-hour index and those gaps, most hours in the city
had no concentration at all. The CAMS global model fills every hour, past and
forecast, for every pilot city.

It is shown as what it is. Each view carries a comparison with the reference
monitors in the same city over the last fortnight -- the median ratio of model
to monitor, over interpolated hourly pairs -- so a reader sees whether the model
runs high or low here before reading its number. And it stays out of everything
analytical: detection, fusion and forecasting read measurements only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.cities import in_city
from app.core.constants import (
    CAMS_FORECAST_DAYS,
    CAMS_PAST_DAYS,
    CAMS_VIEW_HOURS,
    HOURS_PER_DAY,
    PILOT_CITY_CENTRES,
)
from app.core.enums import PilotCity, Pollutant
from app.core.geo import LonLat
from app.core.logging import get_logger
from app.external.cams_client import CamsClient
from app.ml.model_comparison import compare
from app.ml.sensor_colocation import ColocationSummary
from app.repositories import model_repository, observation_repository
from app.repositories.model_repository import ModelRow

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class RegionalModelView:
    """A city's modelled hours around now, and the model's measured bias there."""

    city: PilotCity
    pollutant: Pollutant
    grid_point: LonLat | None
    hours: list[ModelRow]
    latest: ModelRow | None
    next_day_peak: float | None
    outlook_peak: float | None
    comparison: ColocationSummary
    #: Reference monitors in the city that contributed pairs.
    compared_stations: int


async def ingest_city(session: Session, city: PilotCity, *, now: datetime | None = None) -> int:
    """Fetch a fortnight of model history and four days of forecast for a city, and store it.

    Raises:
        UpstreamError: Open-Meteo failed or returned an unusable payload.
    """
    reference = now or datetime.now(UTC)
    async with CamsClient() as client:
        series = await client.hourly(
            PILOT_CITY_CENTRES[city.value],
            past_days=CAMS_PAST_DAYS,
            forecast_days=CAMS_FORECAST_DAYS,
        )
    stored = model_repository.upsert_hours(
        session,
        [
            ModelRow(
                city=city.value,
                pollutant=hour.pollutant,
                observed_at=hour.observed_at,
                value=hour.value,
                is_forecast=hour.observed_at > reference,
                grid_point=series.grid_point,
            )
            for hour in series.hours
        ],
    )
    logger.info("regional_model.ingested", city=city.value, stored=stored)
    return stored


def city_view(
    session: Session, city: PilotCity, pollutant: Pollutant, *, now: datetime | None = None
) -> RegionalModelView:
    """The model around now for a city, its peaks ahead, and its bias against the monitors."""
    reference = now or datetime.now(UTC)
    since = reference - timedelta(days=CAMS_PAST_DAYS)
    horizon = reference + timedelta(hours=CAMS_VIEW_HOURS)
    stored = model_repository.hours_between(session, city.value, pollutant, since, horizon)

    past = [hour for hour in stored if hour.observed_at <= reference]
    ahead = [hour for hour in stored if hour.observed_at > reference]
    next_day = reference + timedelta(hours=HOURS_PER_DAY)

    readings = [
        reading
        for reading in observation_repository.observed_readings_in_window(session, pollutant, since)
        if in_city(reading.coordinates, city)
    ]
    comparison = compare(
        {hour.observed_at: hour.value for hour in past},
        [(reading.observed_at, reading.value) for reading in readings],
    )

    return RegionalModelView(
        city=city,
        pollutant=pollutant,
        grid_point=stored[0].grid_point if stored else None,
        hours=[
            hour
            for hour in stored
            if hour.observed_at >= reference - timedelta(hours=CAMS_VIEW_HOURS)
        ],
        latest=past[-1] if past else None,
        next_day_peak=max(
            (hour.value for hour in ahead if hour.observed_at <= next_day), default=None
        ),
        outlook_peak=max((hour.value for hour in ahead), default=None),
        comparison=comparison,
        compared_stations=len({reading.station_id for reading in readings}),
    )
