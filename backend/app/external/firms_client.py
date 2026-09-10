"""NASA FIRMS active-fire client — the crop-residue and waste-burning source.

FIRMS supplies the fire detections that turn an attributed hotspot from "a plume
came from the north-west" into "a plume came from a fire detected 40 minutes ago
at these coordinates". VIIRS resolves fires at 375 m, against MODIS at 1 km,
which matters because a single stubble field is well under a MODIS pixel.

Three things about this API shape the client:

* It serves **CSV, not JSON**, so it uses :meth:`UpstreamClient.get_text` and
  parses rows itself.
* The credential goes in the **URL path**, not a header or query parameter. That
  makes the key a leak risk in logs and error envelopes, so
  :meth:`sanitise_path` masks it.
* ``acq_time`` is an integer of the form HHMM with no zero padding, so 718 means
  07:18. Read naively as a number of minutes or as a bare hour, every morning
  detection lands at the wrong time and the back-trajectory traces the wrong
  air mass.
"""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from io import StringIO

from pydantic import BaseModel, Field

from app.core.constants import (
    FIRMS_BASE_URL,
    FIRMS_CONFIDENCE_SCORES,
    FIRMS_DEFAULT_SOURCE,
    FIRMS_MAX_DAY_RANGE,
    FIRMS_MIN_FRP_MW,
)
from app.core.exceptions import UpstreamResponseError, ValidationError
from app.core.geo import validate_lon_lat
from app.core.logging import get_logger
from app.external.base import UpstreamClient

logger = get_logger(__name__)

#: Columns the parser requires. FIRMS adds columns over time, so the client
#: checks for the ones it needs rather than pinning the full header.
_REQUIRED_COLUMNS = frozenset(
    {"latitude", "longitude", "acq_date", "acq_time", "confidence", "frp"}
)

#: Minutes in an hour, for decoding the HHMM acquisition time.
_MINUTES_PER_HOUR = 100

#: Confidence score used when the value is a MODIS-style percentage.
_PERCENT_SCALE = 100.0


class FireDetection(BaseModel):
    """One active-fire pixel.

    Attributes:
        coordinates: ``(lon, lat)`` of the pixel centre.
        observed_at: Acquisition time in UTC.
        confidence: Detection confidence as a fraction in [0, 1], normalised
            from either the VIIRS letter classes or the MODIS percentage.
        frp_mw: Fire radiative power in megawatts — a proxy for how much smoke
            the fire is producing, and the weight used when ranking candidate
            sources for a hotspot.
        brightness_k: Brightness temperature in kelvin, where reported.
        is_daytime: Whether the overpass was on the day side.
        satellite: Reporting platform.
    """

    coordinates: tuple[float, float]
    observed_at: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    frp_mw: float = Field(ge=0.0)
    brightness_k: float | None = None
    is_daytime: bool = True
    satellite: str = ""


class FirmsClient(UpstreamClient):
    """Typed client for the NASA FIRMS area API."""

    provider_name = "NASA FIRMS"
    base_url = FIRMS_BASE_URL

    def __init__(self, map_key: str, **kwargs: object) -> None:
        """Construct the client.

        Args:
            map_key: FIRMS MAP_KEY. Obtained via ``settings.require`` so an
                absent key raises a typed configuration error.
            **kwargs: Forwarded to :class:`UpstreamClient`.
        """
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._map_key = map_key

    def sanitise_path(self, path: str) -> str:
        """Mask the MAP_KEY, which FIRMS requires inside the URL path.

        Without this the key would be written to the log stream on any upstream
        failure, and returned inside the error envelope to every API caller.
        """
        return path.replace(self._map_key, "***")

    async def fires_in_bbox(
        self,
        bbox: tuple[float, float, float, float],
        *,
        day_range: int = 1,
        source: str = FIRMS_DEFAULT_SOURCE,
        min_frp_mw: float = FIRMS_MIN_FRP_MW,
    ) -> list[FireDetection]:
        """Fetch active-fire detections inside a bounding box.

        Args:
            bbox: ``(west, south, east, north)`` in WGS84 degrees — the order
                FIRMS expects, which is also GeoJSON bbox order.
            day_range: Days back from now, capped at the API maximum.
            source: FIRMS product identifier.
            min_frp_mw: Detections weaker than this are dropped as implausible
                plume sources.

        Returns:
            Parsed detections, strongest-first by fire radiative power.

        Raises:
            ValidationError: The bounding box is malformed.
            UpstreamResponseError: The CSV lacked the columns the parser needs.
        """
        west, south, east, north = self._validate_bbox(bbox)
        days = max(1, min(day_range, FIRMS_MAX_DAY_RANGE))

        # The MAP_KEY is a path segment here, not a query parameter. That is the
        # provider's design, not a choice; sanitise_path keeps it out of logs.
        path = f"/area/csv/{self._map_key}/{source}/{west},{south},{east},{north}/{days}"
        body = await self.get_text(path)

        detections = self._parse_csv(body, min_frp_mw=min_frp_mw)
        detections.sort(key=lambda detection: detection.frp_mw, reverse=True)
        logger.info(
            "firms.fetched",
            source=source,
            day_range=days,
            detections=len(detections),
        )
        return detections

    def _validate_bbox(
        self, bbox: tuple[float, float, float, float]
    ) -> tuple[float, float, float, float]:
        """Validate a ``(west, south, east, north)`` box."""
        west, south, east, north = bbox
        validate_lon_lat(west, south)
        validate_lon_lat(east, north)
        if west >= east:
            raise ValidationError(
                f"Bounding box west ({west}) must be less than east ({east}).",
            )
        if south >= north:
            raise ValidationError(
                f"Bounding box south ({south}) must be less than north ({north}).",
            )
        return west, south, east, north

    def _parse_csv(self, body: str, *, min_frp_mw: float) -> list[FireDetection]:
        """Parse the FIRMS CSV body into detections.

        Raises:
            UpstreamResponseError: The header lacked a required column, which
                means the product changed shape and the parse cannot be trusted.
        """
        reader = csv.DictReader(StringIO(body))
        header = set(reader.fieldnames or [])

        if not header:
            # An empty body is not the same as "no fires": FIRMS returns a header
            # row even with zero detections, so a truly empty body is a fault.
            raise UpstreamResponseError(
                self.provider_name,
                "FIRMS returned an empty body; expected at least a CSV header.",
            )

        missing = _REQUIRED_COLUMNS - header
        if missing:
            raise UpstreamResponseError(
                self.provider_name,
                f"FIRMS CSV is missing required columns: {sorted(missing)}.",
                details={"columns": sorted(header)},
            )

        detections: list[FireDetection] = []
        skipped_weak = 0
        skipped_malformed = 0

        for row in reader:
            try:
                detection = self._parse_row(row)
            except (ValueError, KeyError, TypeError):
                # One unreadable row must not discard the whole overpass, but the
                # count is logged so silent decay in data quality is visible.
                skipped_malformed += 1
                continue

            if detection.frp_mw < min_frp_mw:
                skipped_weak += 1
                continue
            detections.append(detection)

        if skipped_malformed or skipped_weak:
            logger.info(
                "firms.rows_skipped",
                malformed=skipped_malformed,
                below_frp_threshold=skipped_weak,
                kept=len(detections),
            )
        return detections

    def _parse_row(self, row: dict[str, str]) -> FireDetection:
        """Parse one CSV row into a detection."""
        lon = float(row["longitude"])
        lat = float(row["latitude"])
        validate_lon_lat(lon, lat)

        brightness = row.get("bright_ti4") or row.get("brightness") or ""

        return FireDetection(
            coordinates=(lon, lat),
            observed_at=self._parse_acquisition_time(row["acq_date"], row["acq_time"]),
            confidence=self._parse_confidence(row["confidence"]),
            frp_mw=float(row["frp"]),
            brightness_k=float(brightness) if brightness else None,
            is_daytime=row.get("daynight", "D").strip().upper() == "D",
            satellite=row.get("satellite", "").strip(),
        )

    @staticmethod
    def _parse_acquisition_time(acq_date: str, acq_time: str) -> datetime:
        """Combine the FIRMS date and HHMM time into a UTC timestamp.

        ``acq_time`` is an unpadded integer of the form HHMM: 718 is 07:18, and
        1830 is 18:30. Treating it as minutes past midnight, or as a bare hour,
        misplaces every morning detection by hours — which in turn hands the
        back-trajectory the wrong air mass and names the wrong source.
        """
        raw = int(acq_time.strip())
        hour, minute = divmod(raw, _MINUTES_PER_HOUR)
        date = datetime.strptime(acq_date.strip(), "%Y-%m-%d").replace(tzinfo=UTC)
        return date.replace(hour=hour, minute=minute)

    @staticmethod
    def _parse_confidence(raw: str) -> float:
        """Normalise VIIRS letter classes or a MODIS percentage to [0, 1].

        VIIRS reports ``l``/``n``/``h``; MODIS reports 0-100. Both products are
        in scope, so both spellings are handled rather than assumed.
        """
        value = raw.strip().lower()
        if value in FIRMS_CONFIDENCE_SCORES:
            return FIRMS_CONFIDENCE_SCORES[value]
        # MODIS-style percentage.
        return min(1.0, max(0.0, float(value) / _PERCENT_SCALE))
