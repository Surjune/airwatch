"""CPCB's sub-indices for Tamil Nadu's monitors, as TNPCB's website republishes them.

TNPCB's AQI page (https://tnpcb.gov.in/aqi.php) carries, for every CAAQMS station
in the state, the figures data.gov.in's feed carries: each pollutant's minimum,
maximum and average CPCB sub-index over the last 24 hours, stamped in IST. The
page says the data is obtained from CPCB. It kept updating hourly while
data.gov.in's API refused connections from 25 September 2026, so it is the one
official live source left for Coimbatore.

There is no API: the figures sit in the page's script as one
``stationsData["<city>"].push({...})`` statement per station, which this client
reads. A change to the page breaks the parse loudly, as a typed error, rather
than quietly returning nothing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from pydantic import BaseModel, Field

from app.core import cpcb
from app.core.constants import TNPCB_AQI_PATH, TNPCB_BASE_URL
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: One station's entry in the page's script.
_STATION_ENTRY = re.compile(r'stationsData\["(?P<city>[^"]+)"\]\.push\((?P<entry>\{.*?\})\);')


class _TnpcbPollutant(BaseModel):
    """One pollutant's figures as the page writes them."""

    label: str = Field(alias="indexId")
    low: str = Field(alias="min")
    high: str = Field(alias="max")
    average: str = Field(alias="avg")


class _TnpcbStation(BaseModel):
    """One station's entry as the page writes it."""

    name: str
    last_update: str = Field(alias="lastUpdate")
    pollutants: list[_TnpcbPollutant]


class TnpcbReading(BaseModel):
    """A station's CPCB sub-index for one pollutant, read from TNPCB's page."""

    station: str
    city: str
    pollutant: Pollutant
    reported_at: datetime
    sub_index: float
    sub_index_min: float | None
    sub_index_max: float | None


class TnpcbClient(UpstreamClient):
    """Typed reader for TNPCB's CAAQMS AQI page."""

    provider_name = "TNPCB (tnpcb.gov.in)"
    base_url = TNPCB_BASE_URL

    async def station_sub_indices(self) -> list[TnpcbReading]:
        """Every Tamil Nadu station's latest sub-indices.

        A pollutant with no average ("NA") is skipped: the sensor reported
        nothing, which is not a sub-index of zero.

        Raises:
            UpstreamResponseError: The page carried no station entries, or one
                did not match the expected shape.
        """
        page = await self.get_text(TNPCB_AQI_PATH, headers={"Accept": "text/html"})
        entries = list(_STATION_ENTRY.finditer(page))
        if not entries:
            raise UpstreamResponseError(
                self.provider_name, "The AQI page carried no station entries."
            )
        readings = [
            reading
            for entry in entries
            for reading in self._parse(entry.group("city"), entry.group("entry"))
        ]
        logger.info("tnpcb.stations_fetched", stations=len(entries), readings=len(readings))
        return readings

    def _parse(self, city: str, raw: str) -> list[TnpcbReading]:
        try:
            station = _TnpcbStation.model_validate(json.loads(raw))
            reported_at = cpcb.parse_timestamp(station.last_update)
        except ValueError as error:
            raise UpstreamResponseError(
                self.provider_name, f"A station entry did not match the expected shape: {error}"
            ) from error

        readings: list[TnpcbReading] = []
        for figures in station.pollutants:
            pollutant = cpcb.pollutant(figures.label)
            average = cpcb.optional_value(figures.average)
            if pollutant is None or average is None:
                continue
            readings.append(
                TnpcbReading(
                    station=station.name.strip(),
                    city=city.strip(),
                    pollutant=pollutant,
                    reported_at=reported_at,
                    sub_index=average,
                    sub_index_min=cpcb.optional_value(figures.low),
                    sub_index_max=cpcb.optional_value(figures.high),
                )
            )
        return readings
