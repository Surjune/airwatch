"""The World Air Quality Index Project's API -- a backup route to CPCB's monitors.

AirWatch reads CPCB's monitors through OpenAQ, which relays the concentrations
as published. When that relay stalls, WAQI is often still receiving the same
stations, and this client is how AirWatch reaches them. Two calls are used:

* ``/v2/map/bounds`` lists the stations inside a box, with their positions;
* ``/feed/@{uid}/`` returns one station's latest figures and their sources.

WAQI reports every pollutant as a US AQI figure, not a concentration; the
conversion back is made in ``core/us_aqi``, not here. The token travels as a
query parameter, which the API requires; :meth:`sanitise_path` masks it.

WAQI answers an error with HTTP 200 and ``{"status": "error"}``, so the status
field is checked on every response rather than trusting the HTTP code.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ValidationError

from app.core.constants import WAQI_BASE_URL, WAQI_MIN_REQUEST_INTERVAL_SECONDS
from app.core.exceptions import UpstreamResponseError
from app.core.geo import LonLat, validate_lon_lat
from app.core.logging import get_logger
from app.external.base import JsonValue, UpstreamClient

logger = get_logger(__name__)

_OK = "ok"


class WaqiStation(BaseModel):
    """A station inside a bounding box, as the map listing gives it."""

    uid: int
    name: str
    coordinates: LonLat


class WaqiFeed(BaseModel):
    """One station's latest figures."""

    uid: int
    name: str
    coordinates: LonLat
    #: When the figures were measured, in UTC.
    observed_at: datetime
    #: US AQI figure per pollutant key as WAQI names it ("pm25", "pm10", ...).
    indices: dict[str, float]
    #: Each source's name and URL, joined, for checking who measured it.
    attributions: list[str]


class _BoundsEntry(BaseModel):
    uid: int
    lat: float
    lon: float
    station: dict[str, JsonValue]


class _Value(BaseModel):
    v: float


class _Time(BaseModel):
    iso: str


class _City(BaseModel):
    geo: list[float]
    name: str


class _Attribution(BaseModel):
    name: str = ""
    url: str = ""


class _Feed(BaseModel):
    idx: int
    city: _City
    iaqi: dict[str, _Value] = {}
    time: _Time
    attributions: list[_Attribution] = []


class WaqiClient(UpstreamClient):
    """Typed client for the World Air Quality Index Project's JSON API."""

    provider_name = "World Air Quality Index"
    base_url = WAQI_BASE_URL

    def __init__(self, token: str, **kwargs: object) -> None:
        kwargs.setdefault("min_request_interval_seconds", WAQI_MIN_REQUEST_INTERVAL_SECONDS)
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._token = token

    def sanitise_path(self, path: str) -> str:
        """Mask the token wherever a URL might be logged or echoed."""
        return path.replace(self._token, "***") if self._token else path

    async def stations_in_bounds(
        self, bbox: tuple[float, float, float, float]
    ) -> list[WaqiStation]:
        """Every station inside ``(west, south, east, north)``.

        Raises:
            UpstreamResponseError: The token was refused or the payload malformed.
            UpstreamError: The request failed.
        """
        west, south, east, north = bbox
        payload = await self.get_json(
            "/v2/map/bounds",
            params={
                "latlng": f"{south},{west},{north},{east}",
                "networks": "all",
                "token": self._token,
            },
        )
        stations: list[WaqiStation] = []
        for item in self._data_list(payload):
            try:
                entry = _BoundsEntry.model_validate(item)
                coordinates = validate_lon_lat(entry.lon, entry.lat)
            except (ValidationError, ValueError):
                # One malformed entry is skipped; the rest of the box is still good.
                continue
            stations.append(
                WaqiStation(
                    uid=entry.uid,
                    name=str(entry.station.get("name", "")),
                    coordinates=coordinates,
                )
            )
        logger.info("waqi.bounds_fetched", stations=len(stations))
        return stations

    async def feed(self, uid: int) -> WaqiFeed:
        """One station's latest US AQI figures and their sources.

        Raises:
            UpstreamResponseError: The token or station was refused, or the
                payload was not the expected shape.
            UpstreamError: The request failed.
        """
        payload = await self.get_json(f"/feed/@{uid}/", params={"token": self._token})
        data = self._data(payload)
        try:
            feed = _Feed.model_validate(data)
            latitude, longitude = feed.city.geo[0], feed.city.geo[1]
            coordinates = validate_lon_lat(longitude, latitude)
            measured = datetime.fromisoformat(feed.time.iso)
        except (ValidationError, ValueError, IndexError) as error:
            raise UpstreamResponseError(
                self.provider_name, f"Station {uid}'s feed was not the expected shape."
            ) from error
        if measured.tzinfo is None:
            # Without an offset the hour is ambiguous by up to a day across zones,
            # and a reading filed under the wrong hour is a wrong reading.
            raise UpstreamResponseError(
                self.provider_name, f"Station {uid}'s time carried no time zone."
            )
        observed_at = measured.astimezone(UTC)
        return WaqiFeed(
            uid=feed.idx,
            name=feed.city.name,
            coordinates=coordinates,
            observed_at=observed_at,
            indices={key: value.v for key, value in feed.iaqi.items()},
            attributions=[f"{item.name} {item.url}" for item in feed.attributions],
        )

    def _data(self, payload: JsonValue) -> JsonValue:
        if not isinstance(payload, dict):
            raise UpstreamResponseError(self.provider_name, "The response was not an object.")
        if payload.get("status") != _OK:
            reason = payload.get("data")
            raise UpstreamResponseError(
                self.provider_name,
                f"WAQI refused the request: {reason}.",
                details={"reason": str(reason)},
            )
        return payload.get("data")

    def _data_list(self, payload: JsonValue) -> list[JsonValue]:
        data = self._data(payload)
        if not isinstance(data, list):
            raise UpstreamResponseError(self.provider_name, "The station list was not a list.")
        return data
