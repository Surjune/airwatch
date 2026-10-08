"""CPCB's live AQI feed, published on data.gov.in.

This is the one source that is current for every CAAQMS station, including
those OpenAQ lags on by days -- Coimbatore's SIDCO Kurichi among them.

**The values are sub-indices, not concentrations.** The dataset ("Real time Air
Quality Index from various locations") reports, per station and pollutant, the
minimum, maximum and average CPCB sub-index over the averaging period. The CO
field settles it: Delhi stations report averages of 40 to 90, which is
impossible for CO as a concentration in either ug/m3 (ambient CO is around a
thousand) or mg/m3 (it is around one), and exactly right as a sub-index. So the
client returns them as indices and nothing downstream converts them back into
concentrations it would have to guess the rounding of.

The credential travels as a query parameter, which base clients never log; the
path sanitiser also masks it in case the portal echoes the request back.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core import cpcb
from app.core.constants import (
    CPCB_AQI_BASE_URL,
    CPCB_AQI_RESOURCE_ID,
    CPCB_MAX_PAGE_LIMIT,
)
from app.core.enums import Pollutant
from app.core.exceptions import InvalidGeometryError, UpstreamResponseError
from app.core.geo import LonLat, validate_lon_lat
from app.core.logging import get_logger
from app.external.base import JsonValue, UpstreamClient

logger = get_logger(__name__)


class CpcbRecord(BaseModel):
    """One station-pollutant row as the portal returns it."""

    country: str
    state: str
    city: str
    station: str
    last_update: str
    latitude: str
    longitude: str
    pollutant_id: str
    min_value: str
    max_value: str
    avg_value: str


class SubIndexReading(BaseModel):
    """A station's CPCB sub-index for one pollutant, parsed and typed."""

    station: str
    city: str
    state: str
    coordinates: LonLat
    pollutant: Pollutant
    reported_at: datetime
    sub_index: float
    sub_index_min: float | None
    sub_index_max: float | None


class CpcbAqiClient(UpstreamClient):
    """Typed client for CPCB's real-time AQI resource on data.gov.in."""

    provider_name = "CPCB (data.gov.in)"
    base_url = CPCB_AQI_BASE_URL

    def __init__(self, api_key: str, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._api_key = api_key

    def sanitise_path(self, path: str) -> str:
        """Mask the key wherever the portal might echo it back."""
        return path.replace(self._api_key, "***") if self._api_key else path

    async def city_sub_indices(self, city: str) -> list[SubIndexReading]:
        """Every station's latest sub-indices in one city, as the portal names it.

        Rows with no value ("NA") are skipped: a missing sub-index means the sensor
        reported nothing, which is not a sub-index of zero.

        Raises:
            UpstreamResponseError: The payload did not match the expected shape.
        """
        payload = await self.get_json(
            f"/resource/{CPCB_AQI_RESOURCE_ID}",
            params={
                "api-key": self._api_key,
                "format": "json",
                "limit": CPCB_MAX_PAGE_LIMIT,
                "filters[city]": city,
            },
        )
        readings = [
            reading
            for record in self._records(payload)
            if (reading := self._parse(record)) is not None
        ]
        logger.info("cpcb.city_fetched", city=city, readings=len(readings))
        return readings

    def _records(self, payload: JsonValue) -> list[CpcbRecord]:
        records = payload.get("records") if isinstance(payload, dict) else None
        if not isinstance(records, list):
            raise UpstreamResponseError(self.provider_name, "The response had no records list.")
        try:
            return [CpcbRecord.model_validate(item) for item in records]
        except ValueError as error:
            raise UpstreamResponseError(
                self.provider_name, f"A record did not match the expected shape: {error}"
            ) from error

    def _parse(self, record: CpcbRecord) -> SubIndexReading | None:
        pollutant = cpcb.pollutant(record.pollutant_id)
        if pollutant is None or record.avg_value.strip() == cpcb.MISSING:
            return None
        try:
            reported_at = cpcb.parse_timestamp(record.last_update)
            coordinates = validate_lon_lat(float(record.longitude), float(record.latitude))
            average = float(record.avg_value)
        except (ValueError, InvalidGeometryError) as error:
            raise UpstreamResponseError(
                self.provider_name, f"Unparseable record for {record.station}: {error}"
            ) from error
        return SubIndexReading(
            station=record.station.strip(),
            city=record.city.strip(),
            state=record.state.strip(),
            coordinates=coordinates,
            pollutant=pollutant,
            reported_at=reported_at,
            sub_index=average,
            sub_index_min=cpcb.optional_value(record.min_value),
            sub_index_max=cpcb.optional_value(record.max_value),
        )
