"""Open-Meteo client — the meteorological backbone.

Weather is not context here, it is mechanism. The wind field drives the
back-trajectory that names a source; the boundary layer height decides whether a
given emission rate produces a mild or a severe concentration; relative humidity
is the dominant bias term when calibrating low-cost sensors. Open-Meteo needs no
credential, so this is the one upstream that always works on a clean clone.

Two properties of the API shape the client:

* Responses are **columnar**, not row-oriented: ``hourly`` is a dict of equal
  length arrays, one per variable, sharing an index with ``hourly.time``. Rows
  have to be reassembled, and a short array would silently misalign every later
  variable against the wrong hour.
* Wind arrives as **speed and direction**, defaulting to km/h. AirWatch stores
  ``u``/``v`` components in m/s. The unit is requested explicitly rather than
  converted afterwards, because a silent factor of 3.6 in the wind field
  misplaces every back-trajectory it feeds.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.core.constants import (
    OPENMETEO_BASE_URL,
    OPENMETEO_HOURLY_VARIABLES,
    OPENMETEO_MAX_FORECAST_DAYS,
    OPENMETEO_WIND_SPEED_UNIT,
)
from app.core.exceptions import UpstreamResponseError
from app.core.geo import LonLat, validate_lon_lat, wind_components_ms
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: The time array every other hourly array is aligned against.
_TIME_KEY = "time"


class WeatherHour(BaseModel):
    """One hour of meteorology for a point.

    Attributes:
        observed_at: Hour in UTC.
        temperature_c: Air temperature at 2 m, in degrees Celsius.
        relative_humidity_pct: Relative humidity at 2 m, as a percentage. The
            dominant bias term when calibrating low-cost optical sensors, which
            over-read once water uptake swells the particles they size.
        wind_u: Eastward component of the flow at 10 m, in m/s.
        wind_v: Northward component of the flow at 10 m, in m/s.
        pbl_height_m: Boundary layer height in metres — the depth of air the
            emissions mix into.
        precipitation_mm: Precipitation in the hour, in millimetres. Rain scours
            particulates out of the air, so a spike ending at a rain hour is
            washout rather than a source stopping.
    """

    observed_at: datetime
    temperature_c: float
    relative_humidity_pct: float = Field(ge=0.0, le=100.0)
    wind_u: float
    wind_v: float
    pbl_height_m: float | None = None
    precipitation_mm: float = 0.0


class OpenMeteoClient(UpstreamClient):
    """Typed client for the Open-Meteo forecast API."""

    provider_name = "Open-Meteo"
    base_url = OPENMETEO_BASE_URL

    async def forecast(
        self,
        centre: LonLat,
        *,
        forecast_days: int = 3,
        past_days: int = 0,
    ) -> list[WeatherHour]:
        """Fetch hourly meteorology for a point.

        Args:
            centre: ``(lon, lat)`` of the point. Open-Meteo snaps this to its own
                grid, so the returned coordinates differ slightly from those sent.
            forecast_days: Days ahead, capped at the API maximum.
            past_days: Days of recent history to include alongside the forecast,
                which is how a back-trajectory gets the wind field for hours that
                have already happened.

        Returns:
            One entry per hour, chronologically ordered.

        Raises:
            UpstreamResponseError: The payload was not the columnar shape the
                parser requires, or its arrays disagreed in length.
        """
        lon, lat = validate_lon_lat(*centre)
        days = max(1, min(forecast_days, OPENMETEO_MAX_FORECAST_DAYS))

        payload = await self.get_json(
            "/forecast",
            params={
                # Open-Meteo takes latitude and longitude as separate parameters,
                # so there is no (lat, lon) ordering trap here.
                "latitude": lat,
                "longitude": lon,
                "hourly": ",".join(OPENMETEO_HOURLY_VARIABLES),
                "wind_speed_unit": OPENMETEO_WIND_SPEED_UNIT,
                "forecast_days": days,
                "past_days": past_days,
                # UTC in storage; local time is a presentation concern.
                "timezone": "UTC",
            },
        )

        hours = self._parse_hourly(payload)
        logger.info(
            "openmeteo.fetched",
            forecast_days=days,
            past_days=past_days,
            hours=len(hours),
        )
        return hours

    def _parse_hourly(self, payload: object) -> list[WeatherHour]:
        """Reassemble the columnar response into per-hour rows."""
        if not isinstance(payload, dict):
            raise UpstreamResponseError(
                self.provider_name,
                f"Open-Meteo returned {type(payload).__name__}, expected an object.",
            )

        hourly = payload.get("hourly")
        if not isinstance(hourly, dict):
            raise UpstreamResponseError(
                self.provider_name,
                "Open-Meteo response did not contain an 'hourly' object.",
            )

        times = hourly.get(_TIME_KEY)
        if not isinstance(times, list):
            raise UpstreamResponseError(
                self.provider_name,
                "Open-Meteo 'hourly.time' was missing or not an array.",
            )

        columns = self._validate_columns(hourly, expected_length=len(times))

        rows: list[WeatherHour] = []
        for index, raw_time in enumerate(times):
            row = self._build_hour(str(raw_time), columns, index)
            if row is not None:
                rows.append(row)
        return rows

    def _validate_columns(
        self, hourly: dict[str, object], *, expected_length: int
    ) -> dict[str, list[object]]:
        """Check every requested variable is present and correctly aligned.

        A short array is rejected rather than padded. Padding would silently
        shift every later hour's wind against the wrong timestamp, and a
        back-trajectory built on shifted wind names a source with confidence and
        no basis.
        """
        columns: dict[str, list[object]] = {}
        for variable in OPENMETEO_HOURLY_VARIABLES:
            values = hourly.get(variable)
            if not isinstance(values, list):
                raise UpstreamResponseError(
                    self.provider_name,
                    f"Open-Meteo 'hourly.{variable}' was missing or not an array.",
                )
            if len(values) != expected_length:
                raise UpstreamResponseError(
                    self.provider_name,
                    f"Open-Meteo 'hourly.{variable}' has {len(values)} values "
                    f"but 'time' has {expected_length}; the arrays are misaligned.",
                    details={"variable": variable},
                )
            columns[variable] = values
        return columns

    def _build_hour(
        self, raw_time: str, columns: dict[str, list[object]], index: int
    ) -> WeatherHour | None:
        """Build one hour, or None when the essential values are absent.

        Open-Meteo emits ``null`` for a variable it has no value for. An hour
        without wind or temperature cannot support a trajectory or a calibration,
        so it is dropped rather than defaulted to zero — a zero wind reads as
        calm air, which is a physical claim the data does not make.
        """
        temperature = columns["temperature_2m"][index]
        humidity = columns["relative_humidity_2m"][index]
        speed = columns["wind_speed_10m"][index]
        direction = columns["wind_direction_10m"][index]

        temperature_c = self._as_float(temperature, "temperature_2m")
        humidity_pct = self._as_float(humidity, "relative_humidity_2m")
        speed_ms = self._as_float(speed, "wind_speed_10m")
        direction_deg = self._as_float(direction, "wind_direction_10m")

        if (
            temperature_c is None
            or humidity_pct is None
            or speed_ms is None
            or direction_deg is None
        ):
            return None

        # Open-Meteo gives speed and the meteorological "from" direction; AirWatch
        # stores u/v flow components. Speed is already m/s because the request
        # asked for it.
        wind_u, wind_v = wind_components_ms(speed_ms, direction_deg)

        pbl = self._as_float(columns["boundary_layer_height"][index], "boundary_layer_height")
        precipitation = self._as_float(columns["precipitation"][index], "precipitation")

        return WeatherHour(
            observed_at=self._parse_time(raw_time),
            temperature_c=temperature_c,
            relative_humidity_pct=humidity_pct,
            wind_u=wind_u,
            wind_v=wind_v,
            pbl_height_m=pbl,
            precipitation_mm=precipitation if precipitation is not None else 0.0,
        )

    def _as_float(self, value: object, variable: str) -> float | None:
        """Narrow an untyped JSON value to a float, or None when absent.

        Raises:
            UpstreamResponseError: The value was neither null nor numeric. A
                string where a number belongs means the response changed shape,
                and coercing it would put a fabricated number into the wind field.
        """
        if value is None:
            return None
        if isinstance(value, bool):
            # bool is a subclass of int; a boolean here is a shape change, not a
            # measurement.
            raise UpstreamResponseError(
                self.provider_name,
                f"Open-Meteo '{variable}' was a boolean, expected a number.",
            )
        if isinstance(value, int | float):
            return float(value)
        raise UpstreamResponseError(
            self.provider_name,
            f"Open-Meteo '{variable}' was {type(value).__name__}, expected a number.",
            details={"variable": variable},
        )

    def _parse_time(self, raw_time: str) -> datetime:
        """Parse an Open-Meteo timestamp, which carries no timezone suffix.

        The request pins ``timezone=UTC``, so the naive value is UTC and is
        labelled as such rather than left to the server's local zone.
        """
        try:
            return datetime.fromisoformat(raw_time).replace(tzinfo=UTC)
        except ValueError as error:
            raise UpstreamResponseError(
                self.provider_name,
                f"Open-Meteo returned an unparseable timestamp: {raw_time!r}.",
            ) from error
