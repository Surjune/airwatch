"""Reading a photograph's own account of where and when it was taken.

**EXIF is not proof.** It is a few bytes in a file header, editable with any
text editor, and stripped outright by most messaging apps before a photo ever
reaches a browser. Treating its presence as authentication would be security
theatre, and treating its absence as fraud would reject the majority of honest
submissions.

It is useful in exactly one direction. When metadata is present *and contradicts
the submitted claim*, that is evidence against the claim: a photograph whose own
header says it was taken in another city, or three days ago, is not describing
the air someone is claiming it describes. A contradiction is actionable;
agreement is weak corroboration; absence says nothing at all.

So this module reports one of three verdicts and lets the service decide what
each is worth. The asymmetry is the whole design: an unverifiable submission is
accepted and marked, a contradicted one is refused.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from PIL import ExifTags, Image, UnidentifiedImageError

from app.core.constants import EXIF_POSITION_TOLERANCE_M, EXIF_TIME_TOLERANCE_MINUTES
from app.core.geo import LonLat, haversine_distance_m
from app.core.logging import get_logger

logger = get_logger(__name__)

#: EXIF stores its capture time in this format, with no timezone.
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"

#: Hemisphere markers in the GPS block. Latitude south and longitude west are
#: stored as positive magnitudes with a separate reference, so the sign has to
#: be reapplied or every southern photo lands in the northern hemisphere.
_NEGATIVE_HEMISPHERES = frozenset({"S", "W"})

#: Minutes and seconds per degree, for converting a GPS sexagesimal triple.
_MINUTES_PER_DEGREE = 60.0
_SECONDS_PER_DEGREE = 3600.0

#: Number of components in a GPS coordinate triple.
_GPS_TRIPLE_LENGTH = 3


class Verdict(StrEnum):
    """What the file's own metadata says about the submitted claim."""

    #: Metadata present and consistent with the claim.
    CONSISTENT = "consistent"

    #: Metadata present and contradicting the claim. Actionable.
    CONTRADICTED = "contradicted"

    #: No usable metadata. Says nothing either way, which is the common case.
    UNVERIFIABLE = "unverifiable"


@dataclass(frozen=True, slots=True)
class PhotoProvenance:
    """What the file claims about itself, and whether it matches the submission."""

    verdict: Verdict

    #: Position recorded in the file, if any.
    coordinates: LonLat | None

    #: Capture time recorded in the file, if any. Naive in EXIF; assumed UTC,
    #: which is why the tolerance is generous rather than tight.
    captured_at: datetime | None

    #: Distance between the file's position and the submitted one, when both
    #: exist. Reported so a reviewer can see how far apart they were.
    position_difference_m: float | None

    #: Explanation, written for whoever has to act on a contradiction.
    detail: str


def _to_degrees(triple: object) -> float | None:
    """Convert an EXIF sexagesimal GPS triple to decimal degrees."""
    if not isinstance(triple, (tuple, list)) or len(triple) != _GPS_TRIPLE_LENGTH:
        return None
    try:
        degrees, minutes, seconds = (float(part) for part in triple)
    except (TypeError, ValueError):
        return None
    return degrees + minutes / _MINUTES_PER_DEGREE + seconds / _SECONDS_PER_DEGREE


def _gps_coordinates(gps: dict[str, object]) -> LonLat | None:
    """Extract ``(lon, lat)`` from a decoded GPS block."""
    latitude = _to_degrees(gps.get("GPSLatitude"))
    longitude = _to_degrees(gps.get("GPSLongitude"))
    if latitude is None or longitude is None:
        return None

    if str(gps.get("GPSLatitudeRef", "N")).upper() in _NEGATIVE_HEMISPHERES:
        latitude = -latitude
    if str(gps.get("GPSLongitudeRef", "E")).upper() in _NEGATIVE_HEMISPHERES:
        longitude = -longitude

    return (longitude, latitude)


def _capture_time(exif: dict[str, object]) -> datetime | None:
    """Extract the original capture time, preferring it over the file's mtime."""
    for tag in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
        raw = exif.get(tag)
        if not isinstance(raw, str):
            continue
        try:
            return datetime.strptime(raw, _EXIF_DATETIME_FORMAT).replace(tzinfo=UTC)
        except ValueError:
            continue
    return None


def read(content: bytes) -> tuple[LonLat | None, datetime | None]:
    """Extract position and capture time from a photograph's metadata.

    Returns ``(None, None)`` for any file without usable metadata, including one
    that cannot be opened at all. A malformed header is not an error here: the
    image itself is validated elsewhere, and this step only ever adds
    information.
    """
    try:
        with Image.open(io.BytesIO(content)) as opened:
            raw = opened.getexif()
    except (UnidentifiedImageError, OSError, ValueError):
        return None, None

    if not raw:
        return None, None

    decoded: dict[str, object] = {
        ExifTags.TAGS.get(tag, str(tag)): value for tag, value in raw.items()
    }

    gps_block: dict[str, object] = {}
    try:
        gps_raw = raw.get_ifd(ExifTags.IFD.GPSInfo)
    except (KeyError, ValueError, OSError):
        gps_raw = {}
    if gps_raw:
        gps_block = {ExifTags.GPSTAGS.get(tag, str(tag)): value for tag, value in gps_raw.items()}

    # The capture time lives in the Exif IFD on most cameras, not the root.
    try:
        exif_ifd = raw.get_ifd(ExifTags.IFD.Exif)
    except (KeyError, ValueError, OSError):
        exif_ifd = {}
    for tag, value in exif_ifd.items():
        decoded.setdefault(ExifTags.TAGS.get(tag, str(tag)), value)

    return _gps_coordinates(gps_block), _capture_time(decoded)


def verify(
    content: bytes,
    *,
    claimed_position: LonLat,
    claimed_time: datetime,
    position_tolerance_m: int = EXIF_POSITION_TOLERANCE_M,
    time_tolerance_minutes: int = EXIF_TIME_TOLERANCE_MINUTES,
) -> PhotoProvenance:
    """Check a photograph's metadata against what the submitter claimed.

    Args:
        content: The uploaded image bytes.
        claimed_position: Position the submitter supplied, ``(lon, lat)``.
        claimed_time: Capture time the submitter supplied.
        position_tolerance_m: How far the two positions may differ. Generous,
            because consumer GPS drifts by hundreds of metres beside tall
            buildings and a tight bound would reject honest submissions.
        time_tolerance_minutes: How far the two times may differ.

    Returns:
        A verdict with the reasoning. ``UNVERIFIABLE`` is the expected result
        for most uploads and is not a failure.
    """
    position, captured_at = read(content)

    if position is None and captured_at is None:
        return PhotoProvenance(
            verdict=Verdict.UNVERIFIABLE,
            coordinates=None,
            captured_at=None,
            position_difference_m=None,
            detail=(
                "The photo carries no location or capture metadata, which is normal: "
                "most apps strip it. The submission is accepted but cannot be "
                "corroborated, so it does not contribute to calibration."
            ),
        )

    difference_m: float | None = None
    if position is not None:
        difference_m = haversine_distance_m(position, claimed_position)
        if difference_m > position_tolerance_m:
            return PhotoProvenance(
                verdict=Verdict.CONTRADICTED,
                coordinates=position,
                captured_at=captured_at,
                position_difference_m=difference_m,
                detail=(
                    f"The photo's own location is {difference_m / 1000:.1f} km from the "
                    "position submitted with it. A photograph cannot describe air it was "
                    "not taken in."
                ),
            )

    if captured_at is not None:
        gap = abs(captured_at - claimed_time)
        if gap > timedelta(minutes=time_tolerance_minutes):
            return PhotoProvenance(
                verdict=Verdict.CONTRADICTED,
                coordinates=position,
                captured_at=captured_at,
                position_difference_m=difference_m,
                detail=(
                    f"The photo's own capture time is {gap.total_seconds() / 3600:.1f} "
                    "hours from the time submitted with it. Air quality changes within "
                    "hours, so the two cannot describe the same conditions."
                ),
            )

    return PhotoProvenance(
        verdict=Verdict.CONSISTENT,
        coordinates=position,
        captured_at=captured_at,
        position_difference_m=difference_m,
        detail="The photo's own metadata matches the submission.",
    )
