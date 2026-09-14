"""CAMS regional air-quality model, via Open-Meteo.

The Copernicus Atmosphere Monitoring Service runs a global model of the
atmosphere's chemistry and publishes hourly concentrations and a five-day
forecast. Open-Meteo serves it for any point with no key.

It is a **model**, not an instrument. At a resolution of tens of kilometres it
describes the air over a whole city, not a street; it misses local sources a
monitor would catch; and its error differs by city -- in September 2026 it read
about 0.6x Coimbatore's PM10 monitor and 1.8x Delhi's PM2.5 monitors.
AirWatch therefore stores it in its own table, shows it labelled as modelled,
measures its bias against real monitors, and never feeds it into detection.
What it adds is coverage in time and space where monitors are silent -- which in
Coimbatore is most of the district, most of the time.

Like the weather client, the response is columnar, so arrays are checked for
alignment before rows are rebuilt; a null hour is dropped rather than read as
clean air.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from app.core.constants import CAMS_BASE_URL, CAMS_VARIABLES
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.core.geo import LonLat, validate_lon_lat
from app.core.logging import get_logger
from app.external.base import JsonValue, UpstreamClient

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelHour:
    """One modelled hourly concentration."""

    observed_at: datetime
    pollutant: Pollutant
    #: Concentration in ug/m3, as the model states it.
    value: float


@dataclass(frozen=True, slots=True)
class ModelSeries:
    """The model's hours for one point, and the grid point it snapped to."""

    grid_point: LonLat
    hours: list[ModelHour]


class CamsClient(UpstreamClient):
    """Typed client for Open-Meteo's CAMS air-quality endpoint."""

    provider_name = "CAMS via Open-Meteo"
    base_url = CAMS_BASE_URL

    async def hourly(self, centre: LonLat, *, past_days: int, forecast_days: int) -> ModelSeries:
        """Modelled hourly concentrations at a point, past and forecast.

        Raises:
            UpstreamResponseError: The payload was not the aligned columnar shape
                required, or held a non-numeric value.
            UpstreamError: The request failed.
        """
        lon, lat = validate_lon_lat(*centre)
        payload = await self.get_json(
            "/air-quality",
            params={
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(CAMS_VARIABLES.values()),
                "past_days": past_days,
                "forecast_days": forecast_days,
                "timezone": "UTC",
            },
        )
        series = self._parse(payload)
        logger.info("cams.fetched", hours=len(series.hours), grid_point=series.grid_point)
        return series

    def _parse(self, payload: JsonValue) -> ModelSeries:
        if not isinstance(payload, dict):
            raise UpstreamResponseError(self.provider_name, "CAMS response was not an object.")
        hourly = payload.get("hourly")
        times = hourly.get("time") if isinstance(hourly, dict) else None
        if not isinstance(hourly, dict) or not isinstance(times, list):
            raise UpstreamResponseError(
                self.provider_name, "CAMS response had no hourly time array."
            )
        grid_lat, grid_lon = payload.get("latitude"), payload.get("longitude")
        if not isinstance(grid_lat, int | float) or not isinstance(grid_lon, int | float):
            raise UpstreamResponseError(self.provider_name, "CAMS response had no grid point.")

        hours: list[ModelHour] = []
        for code, variable in CAMS_VARIABLES.items():
            values = hourly.get(variable)
            if not isinstance(values, list) or len(values) != len(times):
                raise UpstreamResponseError(
                    self.provider_name,
                    f"CAMS '{variable}' was missing or misaligned with 'time'.",
                    details={"variable": variable},
                )
            for raw_time, value in zip(times, values, strict=True):
                if value is None:
                    continue
                if isinstance(value, bool) or not isinstance(value, int | float):
                    raise UpstreamResponseError(
                        self.provider_name,
                        f"CAMS '{variable}' held a non-numeric value.",
                        details={"variable": variable},
                    )
                hours.append(
                    ModelHour(
                        observed_at=self._parse_time(str(raw_time)),
                        pollutant=Pollutant(code),
                        value=float(value),
                    )
                )
        return ModelSeries(grid_point=(float(grid_lon), float(grid_lat)), hours=hours)

    def _parse_time(self, raw_time: str) -> datetime:
        """Parse a naive timestamp the request pinned to UTC."""
        try:
            return datetime.fromisoformat(raw_time).replace(tzinfo=UTC)
        except ValueError as error:
            raise UpstreamResponseError(
                self.provider_name, f"CAMS returned an unparseable time: {raw_time!r}."
            ) from error
