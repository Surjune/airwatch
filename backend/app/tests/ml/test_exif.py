"""Tests for photo provenance checking.

The asymmetry is the thing being tested. EXIF is editable and routinely
stripped, so it can never authenticate a submission -- but when it is present
and contradicts the claim, that contradiction is real evidence. Absence must
therefore be accepted and a contradiction refused, and getting those two the
wrong way round would either reject most honest submissions or accept a photo
taken in another city.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from PIL import Image
from PIL.TiffImagePlugin import IFDRational

from app.core.constants import EXIF_POSITION_TOLERANCE_M, EXIF_TIME_TOLERANCE_MINUTES
from app.ml.exif import Verdict, read, verify

NOW = datetime(2026, 5, 4, 10, 30, tzinfo=UTC)

#: Connaught Place, in (longitude, latitude) order.
DELHI: tuple[float, float] = (77.2167, 28.6333)

#: Far enough away that no GPS drift explains the difference.
MUMBAI: tuple[float, float] = (72.8777, 19.0760)

RNG = np.random.default_rng(20260912)


def _rational(value: float) -> tuple[IFDRational, IFDRational, IFDRational]:
    """Render decimal degrees as the sexagesimal triple EXIF stores.

    Written as IFDRational rather than plain tuples because that is what
    Pillow's TIFF writer serialises; nested tuples are rejected at save time.
    """
    magnitude = abs(value)
    degrees = int(magnitude)
    minutes_float = (magnitude - degrees) * 60
    minutes = int(minutes_float)
    seconds = (minutes_float - minutes) * 60
    return (
        IFDRational(degrees, 1),
        IFDRational(minutes, 1),
        IFDRational(round(seconds * 1000), 1000),
    )


def photo(
    *,
    position: tuple[float, float] | None = None,
    captured_at: datetime | None = None,
) -> bytes:
    """A small JPEG, optionally carrying GPS and capture-time metadata."""
    noise = RNG.uniform(0.0, 1.0, size=(120, 120, 3))
    scene = np.clip(110.0 + 70.0 * (noise - 0.5) * 2.0, 0.0, 255.0)
    image = Image.fromarray(scene.astype(np.uint8))

    exif = image.getexif()
    if captured_at is not None:
        # 0x9003 is DateTimeOriginal, written into the Exif IFD as a camera does.
        exif.get_ifd(0x8769)[0x9003] = captured_at.strftime("%Y:%m:%d %H:%M:%S")
    if position is not None:
        longitude, latitude = position
        gps = exif.get_ifd(0x8825)
        gps[1] = "N" if latitude >= 0 else "S"
        gps[2] = _rational(latitude)
        gps[3] = "E" if longitude >= 0 else "W"
        gps[4] = _rational(longitude)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", exif=exif)
    return buffer.getvalue()


class TestReading:
    def test_recovers_a_written_position(self) -> None:
        position, _ = read(photo(position=DELHI))

        assert position is not None
        assert position[0] == pytest.approx(DELHI[0], abs=0.001)
        assert position[1] == pytest.approx(DELHI[1], abs=0.001)

    def test_recovers_a_written_capture_time(self) -> None:
        _, captured = read(photo(captured_at=NOW))

        assert captured is not None
        assert captured.replace(tzinfo=None) == NOW.replace(tzinfo=None)

    def test_a_photo_with_no_metadata_yields_nothing(self) -> None:
        assert read(photo()) == (None, None)

    def test_a_file_that_is_not_an_image_yields_nothing(self) -> None:
        # Never raises: the image itself is validated elsewhere, and this step
        # only ever adds information.
        assert read(b"not an image") == (None, None)

    def test_southern_and_western_hemispheres_keep_their_sign(self) -> None:
        # Stored as positive magnitudes with a separate reference, so a dropped
        # sign would put every southern photo in the wrong hemisphere.
        southwest = (-43.2, -22.9)
        position, _ = read(photo(position=southwest))

        assert position is not None
        assert position[0] < 0
        assert position[1] < 0


class TestVerdicts:
    def test_matching_metadata_is_consistent(self) -> None:
        result = verify(
            photo(position=DELHI, captured_at=NOW),
            claimed_position=DELHI,
            claimed_time=NOW,
        )

        assert result.verdict is Verdict.CONSISTENT

    def test_absent_metadata_is_unverifiable_not_a_failure(self) -> None:
        # The common case. Most apps strip EXIF, and rejecting on absence would
        # reject the majority of honest submissions.
        result = verify(photo(), claimed_position=DELHI, claimed_time=NOW)

        assert result.verdict is Verdict.UNVERIFIABLE
        assert "normal" in result.detail

    def test_a_photo_taken_in_another_city_is_contradicted(self) -> None:
        result = verify(
            photo(position=MUMBAI, captured_at=NOW),
            claimed_position=DELHI,
            claimed_time=NOW,
        )

        assert result.verdict is Verdict.CONTRADICTED
        assert result.position_difference_m is not None
        assert result.position_difference_m > EXIF_POSITION_TOLERANCE_M

    def test_a_photo_from_another_time_is_contradicted(self) -> None:
        result = verify(
            photo(position=DELHI, captured_at=NOW - timedelta(hours=6)),
            claimed_position=DELHI,
            claimed_time=NOW,
        )

        assert result.verdict is Verdict.CONTRADICTED
        assert "capture time" in result.detail

    def test_gps_drift_within_tolerance_is_accepted(self) -> None:
        # Consumer GPS drifts by hundreds of metres beside tall buildings, and a
        # tight bound would reject honest submissions.
        nearby = (DELHI[0] + 0.004, DELHI[1] + 0.004)
        result = verify(
            photo(position=nearby, captured_at=NOW),
            claimed_position=DELHI,
            claimed_time=NOW,
        )

        assert result.verdict is Verdict.CONSISTENT

    def test_a_clock_off_by_minutes_is_accepted(self) -> None:
        result = verify(
            photo(
                position=DELHI,
                captured_at=NOW - timedelta(minutes=EXIF_TIME_TOLERANCE_MINUTES - 5),
            ),
            claimed_position=DELHI,
            claimed_time=NOW,
        )

        assert result.verdict is Verdict.CONSISTENT

    def test_position_alone_can_establish_consistency(self) -> None:
        result = verify(photo(position=DELHI), claimed_position=DELHI, claimed_time=NOW)

        assert result.verdict is Verdict.CONSISTENT
        assert result.captured_at is None

    def test_every_verdict_explains_itself(self) -> None:
        # A contradiction has to be actionable by whoever reads it.
        for image, claimed in (
            (photo(), DELHI),
            (photo(position=DELHI), DELHI),
            (photo(position=MUMBAI), DELHI),
        ):
            result = verify(image, claimed_position=claimed, claimed_time=NOW)
            assert len(result.detail) > 20
