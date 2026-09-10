"""OpenAQ v3 client — the primary reference-tier source.

OpenAQ aggregates CPCB and state pollution-control-board stations for India, so
it delivers the Tier 1 ground truth that calibrates everything else. Ninety-odd
stations sit within 25 km of Delhi alone.

Two shapes of the API drive the design here and are not obvious from the docs:

* ``datetimeLast`` is an object ``{"utc": ..., "local": ...}``, not a string, and
  it is ``null`` for stations that have never reported. Some Delhi stations last
  reported in 2018 and sit in the same response as live ones, so recency has to
  be filtered explicitly or decade-old air quietly enters the fused surface.
* The ``/latest`` endpoint returns a value and a ``sensorsId`` but **no
  parameter**. Which pollutant a reading belongs to is only knowable by joining
  back to the sensor list from ``/locations``. A client that skipped that join
  would have to guess, and a PM2.5 value recorded as NO2 is invisible corruption.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Self

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.core.constants import (
    OPENAQ_BASE_URL,
    OPENAQ_MAX_PAGE_LIMIT,
    OPENAQ_MAX_RADIUS_M,
    OPENAQ_MIN_REQUEST_INTERVAL_SECONDS,
    STATION_STALE_AFTER_DAYS,
)
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.core.geo import LonLat, validate_lon_lat
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: OpenAQ parameter names mapped to the pollutants AirWatch models. Anything
#: absent here (bc, um003, pressure, ...) is skipped rather than rejected: an
#: unmodelled parameter is not an error, it is simply not part of the CPCB AQI.
_PARAMETER_TO_POLLUTANT: dict[str, Pollutant] = {
    "pm25": Pollutant.PM25,
    "pm10": Pollutant.PM10,
    "no2": Pollutant.NO2,
    "so2": Pollutant.SO2,
    "o3": Pollutant.O3,
    "co": Pollutant.CO,
    "nh3": Pollutant.NH3,
}

#: OpenAQ unit spellings normalised to the ASCII forms core/aqi.py converts with.
_UNIT_NORMALISATION: dict[str, str] = {
    "µg/m³": "ug/m3",
    "ug/m3": "ug/m3",
    "mg/m³": "mg/m3",
    "mg/m3": "mg/m3",
    "ppm": "ppm",
    "ppb": "ppb",
}


class OpenAQDateTime(BaseModel):
    """A timestamp pair. Only ``utc`` is stored; local time is presentational."""

    utc: datetime
    local: str | None = None


class OpenAQParameter(BaseModel):
    """A measured quantity as OpenAQ describes it."""

    id: int
    name: str
    units: str
    display_name: str | None = Field(default=None, alias="displayName")


class OpenAQSensor(BaseModel):
    """One sensor at a location, measuring exactly one parameter."""

    id: int
    name: str
    parameter: OpenAQParameter


class OpenAQCoordinates(BaseModel):
    """A position as OpenAQ delivers it, in (latitude, longitude) order."""

    latitude: float
    longitude: float

    def to_lon_lat(self) -> LonLat:
        """Convert to AirWatch's ``(lon, lat)`` order.

        OpenAQ is one of the two places the project takes coordinates in the
        opposite order, so the flip is made explicit here rather than assumed.
        """
        return validate_lon_lat(self.longitude, self.latitude)


class OpenAQProvider(BaseModel):
    """Who operates the station. For India this is usually CPCB or a state board."""

    id: int
    name: str


class OpenAQLocation(BaseModel):
    """A monitoring station and the sensors it carries."""

    id: int
    name: str
    timezone: str | None = None
    coordinates: OpenAQCoordinates
    sensors: list[OpenAQSensor] = Field(default_factory=list)
    provider: OpenAQProvider | None = None
    is_monitor: bool = Field(default=True, alias="isMonitor")
    is_mobile: bool = Field(default=False, alias="isMobile")
    datetime_first: OpenAQDateTime | None = Field(default=None, alias="datetimeFirst")
    datetime_last: OpenAQDateTime | None = Field(default=None, alias="datetimeLast")

    @property
    def last_reading_at(self) -> datetime | None:
        """UTC timestamp of the most recent reading, if the station has any."""
        return self.datetime_last.utc if self.datetime_last else None

    def is_active(self, *, as_of: datetime, stale_after_days: int) -> bool:
        """Whether the station reported recently enough to be worth ingesting."""
        last = self.last_reading_at
        if last is None:
            return False
        return last >= as_of - timedelta(days=stale_after_days)

    def pollutant_by_sensor_id(self) -> dict[int, tuple[Pollutant, str]]:
        """Map each sensor id to the pollutant and normalised unit it reports.

        This is the join the ``/latest`` endpoint requires: it returns a
        ``sensorsId`` and a value but never says which pollutant they describe.
        Sensors measuring anything outside the CPCB AQI set are omitted.
        """
        mapping: dict[int, tuple[Pollutant, str]] = {}
        for sensor in self.sensors:
            pollutant = _PARAMETER_TO_POLLUTANT.get(sensor.parameter.name.lower())
            if pollutant is None:
                continue
            unit = _UNIT_NORMALISATION.get(sensor.parameter.units, sensor.parameter.units)
            mapping[sensor.id] = (pollutant, unit)
        return mapping


class OpenAQLatestValue(BaseModel):
    """One reading from the ``/latest`` endpoint, before the pollutant join."""

    value: float
    sensors_id: int = Field(alias="sensorsId")
    locations_id: int = Field(alias="locationsId")
    datetime_observed: OpenAQDateTime = Field(alias="datetime")
    coordinates: OpenAQCoordinates | None = None


class OpenAQReading(BaseModel):
    """A reading joined to its pollutant — what the ingestion service consumes."""

    location_id: int
    sensor_id: int
    pollutant: Pollutant
    value: float
    unit: str
    observed_at: datetime
    coordinates: tuple[float, float]


class OpenAQClient(UpstreamClient):
    """Typed client for the OpenAQ v3 API."""

    provider_name = "OpenAQ"
    base_url = OPENAQ_BASE_URL

    def __init__(self, api_key: str, **kwargs: object) -> None:
        """Construct the client.

        Args:
            api_key: OpenAQ key. Callers obtain it via ``settings.require`` so an
                absent key raises a typed configuration error rather than
                producing an unauthenticated request.
            **kwargs: Forwarded to :class:`UpstreamClient`.
        """
        # A city-wide run makes one call per active station, so pacing is the
        # default rather than something a caller has to remember to ask for.
        kwargs.setdefault("min_request_interval_seconds", OPENAQ_MIN_REQUEST_INTERVAL_SECONDS)
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    @classmethod
    def from_api_key(cls, api_key: str) -> Self:
        """Build a client with default transport settings."""
        return cls(api_key)

    def _auth_headers(self) -> dict[str, str]:
        return {"X-API-Key": self._api_key}

    async def list_locations(
        self,
        centre: LonLat,
        *,
        radius_m: int = OPENAQ_MAX_RADIUS_M,
        limit: int = 100,
    ) -> list[OpenAQLocation]:
        """List monitoring stations within a radius of a point.

        Args:
            centre: ``(lon, lat)`` centre of the search.
            radius_m: Search radius in metres, capped at OpenAQ's own maximum.
            limit: Maximum stations to return, capped at OpenAQ's page limit.

        Returns:
            Every station OpenAQ reports, active or not. Filter with
            :meth:`OpenAQLocation.is_active` before ingesting.

        Raises:
            UpstreamResponseError: The payload did not match the expected shape.
        """
        lon, lat = validate_lon_lat(*centre)
        payload = await self.get_json(
            "/locations",
            params={
                # OpenAQ expects "latitude,longitude" -- the reverse of the
                # (lon, lat) order used everywhere else in AirWatch.
                "coordinates": f"{lat},{lon}",
                "radius": min(radius_m, OPENAQ_MAX_RADIUS_M),
                "limit": min(limit, OPENAQ_MAX_PAGE_LIMIT),
            },
            headers=self._auth_headers(),
        )
        return [self._parse(OpenAQLocation, item) for item in self._results(payload)]

    async def latest_readings(
        self,
        location: OpenAQLocation,
        *,
        as_of: datetime | None = None,
        stale_after_days: int = STATION_STALE_AFTER_DAYS,
    ) -> list[OpenAQReading]:
        """Fetch the latest reading per sensor at a station, joined to pollutants.

        A live station commonly carries two generations of sensor for the same
        pollutant — one reporting now, one decommissioned years ago — and
        ``/latest`` returns the final value of both. At R K Puram that means a
        2026 PM2.5 of 37 arriving beside a 2018 PM2.5 of 201. Both are literally
        the "latest" value for their sensor, so recency has to be enforced per
        reading; filtering per station is not enough.

        Args:
            location: A station previously returned by :meth:`list_locations`.
                Its sensor list supplies the pollutant join that ``/latest``
                omits, so a bare location id is not enough.
            as_of: Reference time, defaulting to now. Injectable for tests.
            stale_after_days: Readings older than this are dropped.

        Returns:
            One reading per sensor whose pollutant AirWatch models and whose
            observation is recent. Sensors measuring anything else are skipped.

        Raises:
            UpstreamResponseError: The payload did not match the expected shape.
        """
        sensor_map = location.pollutant_by_sensor_id()
        reference = as_of or datetime.now(UTC)
        cutoff = reference - timedelta(days=stale_after_days)

        payload = await self.get_json(
            f"/locations/{location.id}/latest",
            headers=self._auth_headers(),
        )

        readings: list[OpenAQReading] = []
        stale_dropped = 0
        for item in self._results(payload):
            latest = self._parse(OpenAQLatestValue, item)
            mapped = sensor_map.get(latest.sensors_id)
            if mapped is None:
                # A sensor for an unmodelled parameter, or one absent from the
                # location record. Skipped rather than guessed at.
                continue
            if latest.datetime_observed.utc < cutoff:
                # A decommissioned sensor's final reading. Ingesting it would
                # record years-old air as the current value for this cell.
                stale_dropped += 1
                continue
            pollutant, unit = mapped
            coordinates = (
                latest.coordinates.to_lon_lat()
                if latest.coordinates
                else location.coordinates.to_lon_lat()
            )
            readings.append(
                OpenAQReading(
                    location_id=latest.locations_id,
                    sensor_id=latest.sensors_id,
                    pollutant=pollutant,
                    value=latest.value,
                    unit=unit,
                    observed_at=latest.datetime_observed.utc,
                    coordinates=coordinates,
                )
            )

        if stale_dropped:
            logger.info(
                "openaq.stale_readings_dropped",
                location_id=location.id,
                dropped=stale_dropped,
                kept=len(readings),
                stale_after_days=stale_after_days,
            )
        return readings

    def active_locations(
        self,
        locations: list[OpenAQLocation],
        *,
        as_of: datetime | None = None,
        stale_after_days: int = STATION_STALE_AFTER_DAYS,
    ) -> list[OpenAQLocation]:
        """Filter out stations that stopped reporting.

        Args:
            locations: Stations as returned by :meth:`list_locations`.
            as_of: Reference time, defaulting to now. Injectable so the filter is
                deterministic under test.
            stale_after_days: Age beyond which a station counts as dormant.
        """
        reference = as_of or datetime.now(UTC)
        return [
            location
            for location in locations
            if location.is_active(as_of=reference, stale_after_days=stale_after_days)
        ]

    def _results(self, payload: object) -> list[object]:
        """Extract the ``results`` array from an OpenAQ envelope."""
        if not isinstance(payload, dict) or "results" not in payload:
            raise UpstreamResponseError(
                self.provider_name,
                "OpenAQ response did not contain a 'results' array.",
            )
        results = payload["results"]
        if not isinstance(results, list):
            raise UpstreamResponseError(
                self.provider_name,
                f"OpenAQ 'results' was {type(results).__name__}, expected a list.",
            )
        return results

    def _parse[ModelT: BaseModel](self, model: type[ModelT], item: object) -> ModelT:
        """Validate one record, converting a schema drift into a typed error."""
        try:
            return model.model_validate(item)
        except PydanticValidationError as error:
            # A silently dropped record would understate pollution, so a shape
            # change has to be loud.
            raise UpstreamResponseError(
                self.provider_name,
                f"OpenAQ record did not match the expected {model.__name__} shape.",
                details={"errors": error.errors(include_url=False)[:3]},
            ) from error
