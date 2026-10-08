"""CPCB's daily AQI bulletin.

Every afternoon CPCB publishes one PDF giving each city's AQI: the average of
its stations over the 24 hours to 4 pm IST, the pollutants that set it, and how
many of the city's stations took part. It is CPCB's own statement of the day's
air, and it kept appearing every day while data.gov.in's API and OpenAQ's relay
were down, so it is the one current official figure for Kanpur.

The PDF is a table, read here line by line from its text. A bulletin whose
heading does not name the day asked for, or with no city rows at all, is a typed
error rather than an empty day.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from http import HTTPStatus

from pydantic import BaseModel
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core import cpcb
from app.core.constants import CPCB_BULLETIN_BASE_URL, CPCB_BULLETIN_PATH
from app.core.enums import Pollutant
from app.core.exceptions import UpstreamResponseError
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: The heading naming the bulletin's day: "Air Quality Index on Oct 08, 2026 @ 4 PM".
_HEADING = re.compile(r"Air Quality Index on (?P<day>[A-Z][a-z]{2} \d{2}, \d{4})")
_HEADING_DAY_FORMAT = "%b %d, %Y"

#: One city's row: serial number, city, category, AQI, prominent pollutants, and
#: stations taking part out of the city's total -- "137 Kanpur Good 44 PM2.5, NO2 2/4".
#: "Very Poor" is tried before "Poor" so the city name never swallows "Very".
_ROW = re.compile(
    r"^\s*\d+\s+(?P<city>.+?)\s+"
    r"(?P<category>Very Poor|Good|Satisfactory|Moderate|Poor|Severe)\s+"
    r"(?P<aqi>\d{1,3})\s+(?P<pollutants>.+?)\s+"
    r"(?P<reporting>\d+)\s*/\s*(?P<total>\d+)\s*$"
)


class BulletinCity(BaseModel):
    """One city's line in the bulletin."""

    city: str
    aqi: int
    category: str
    prominent_pollutants: list[Pollutant]
    stations_reporting: int
    stations_total: int


class Bulletin(BaseModel):
    """A day's bulletin: the day it covers, and every city it states an AQI for."""

    day: date
    cities: list[BulletinCity]


class CpcbBulletinClient(UpstreamClient):
    """Typed reader for CPCB's daily AQI bulletin."""

    provider_name = "CPCB daily AQI bulletin (cpcb.gov.in)"
    base_url = CPCB_BULLETIN_BASE_URL

    async def bulletin(self, day: date) -> Bulletin | None:
        """The bulletin for one day, or None when CPCB has not published it yet.

        Raises:
            UpstreamResponseError: The document was not a readable bulletin for
                that day.
        """
        path = CPCB_BULLETIN_PATH.format(day=day.strftime("%Y%m%d"))
        try:
            document = await self.get_bytes(path, headers={"Accept": "application/pdf"})
        except UpstreamResponseError as error:
            if error.details.get("status_code") == HTTPStatus.NOT_FOUND:
                return None
            raise
        bulletin = self._parse(document, day)
        logger.info("cpcb_bulletin.fetched", day=day.isoformat(), cities=len(bulletin.cities))
        return bulletin

    def _parse(self, document: bytes, day: date) -> Bulletin:
        try:
            pages = PdfReader(io.BytesIO(document)).pages
            text = "\n".join(page.extract_text() for page in pages)
        except (PyPdfError, ValueError) as error:
            raise UpstreamResponseError(
                self.provider_name, f"The bulletin for {day} could not be read: {error}"
            ) from error

        heading = _HEADING.search(text)
        if heading is None:
            raise UpstreamResponseError(self.provider_name, f"The bulletin for {day} has no date.")
        stated = datetime.strptime(heading.group("day"), _HEADING_DAY_FORMAT).date()
        if stated != day:
            raise UpstreamResponseError(
                self.provider_name, f"The bulletin asked for as {day} is dated {stated}."
            )

        cities = [city for line in text.splitlines() if (city := _city(line)) is not None]
        if not cities:
            raise UpstreamResponseError(
                self.provider_name, f"The bulletin for {day} has no city rows."
            )
        return Bulletin(day=day, cities=cities)


def _city(line: str) -> BulletinCity | None:
    """A city's row, or None for any other line of the document."""
    match = _ROW.match(line)
    if match is None:
        return None
    prominent = [
        pollutant
        for label in match.group("pollutants").split(",")
        if (pollutant := cpcb.pollutant(label)) is not None
    ]
    return BulletinCity(
        city=match.group("city").strip(),
        aqi=int(match.group("aqi")),
        category=match.group("category"),
        prominent_pollutants=prominent,
        stations_reporting=int(match.group("reporting")),
        stations_total=int(match.group("total")),
    )
