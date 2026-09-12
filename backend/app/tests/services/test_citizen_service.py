"""Tests for citizen photo submission.

The property under test throughout is restraint. This tier is the one most
likely to be believed beyond what it can support -- it produces a number from a
phone photograph, and a number from a phone photograph looks exactly like a
number from an instrument once it is on a map.

So the assertions are mostly about what the system refuses to say: no
concentration without a fitted relation, no acceptance of an image whose
failure mode is "clean air looks dirty", and no trust penalty for photographing
somewhere no monitor covers, since that is where the tier is most needed.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from app.core.constants import (
    CITIZEN_CALIBRATION_MIN_PAIRS,
    CITIZEN_INITIAL_TRUST,
    CITIZEN_MAX_CAPTURE_AGE_HOURS,
    CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR,
)
from app.core.enums import Pollutant, StationTier
from app.core.exceptions import RateLimitExceededError, ValidationError
from app.core.h3_grid import point_to_cell
from app.ml.vision import Rejection, RejectionReason
from app.repositories import citizen_repository, observation_repository, station_repository
from app.repositories.citizen_repository import CitizenReportRow
from app.repositories.observation_repository import MeasurementRow
from app.services import citizen_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 4, 2, 9, 0, tzinfo=UTC)

#: Connaught Place, in (longitude, latitude) order.
DELHI: tuple[float, float] = (77.2167, 28.6333)

#: A point far from the seeded station, outside the co-location radius.
REMOTE: tuple[float, float] = (77.4500, 28.9000)

DEVICE = "device-abcdef123456"

RNG = np.random.default_rng(20260912)


def photo_bytes(*, haze: float = 0.0, size: int = 200, blurred: bool = False) -> bytes:
    """A synthetic JPEG with a known amount of airlight composited over it.

    Encoded rather than passed as an array so the whole upload path -- decode,
    channel conversion, analysis -- is exercised.
    """
    noise = RNG.uniform(0.0, 1.0, size=(size, size, 3))
    scene = np.clip(110.0 + 70.0 * (noise - 0.5) * 2.0, 0.0, 255.0)
    if blurred:
        scene = np.full((size, size, 3), 120.0)
    composited = np.clip(scene * (1.0 - haze) + 235.0 * haze, 0.0, 255.0)

    buffer = io.BytesIO()
    Image.fromarray(composited.astype(np.uint8)).save(buffer, format="JPEG", quality=95)
    return buffer.getvalue()


def _seed_station(session: Session, value: float = 120.0) -> int:
    """A reference station at the Delhi point, with a recent reading."""
    station_id = station_repository.upsert_station(
        session,
        source="test",
        source_station_id="citizen-ref",
        name="Reference Monitor",
        tier=StationTier.REFERENCE,
        coordinates=DELHI,
    )
    observation_repository.upsert_measurements(
        session,
        [
            MeasurementRow(
                station_id=station_id,
                observed_at=NOW,
                pollutant=Pollutant.PM25,
                value_raw=value,
                unit="ug/m3",
            )
        ],
    )
    session.flush()
    return station_id


def _seed_calibration(session: Session, count: int = CITIZEN_CALIBRATION_MIN_PAIRS + 5) -> None:
    """Enough co-located pairs, spanning a haze range, to fit a relation."""
    for index in range(count):
        haze = 0.05 + 0.7 * (index / max(1, count - 1))
        citizen_repository.insert_report(
            session,
            CitizenReportRow(
                coordinates=DELHI,
                h3_cell=point_to_cell(DELHI),
                captured_at=NOW - timedelta(minutes=index),
                device_id=f"seed-device-{index:04d}",
                haze_index=haze,
                transmission=1.0 - haze,
                mean_luminance=120.0,
                sharpness=100.0,
                trust_score=CITIZEN_INITIAL_TRUST,
                reference_station_id=None,
                reference_value=20.0 + 300.0 * haze,
                reference_distance_m=500.0,
            ),
        )
    session.flush()


class TestUncalibratedBehaviour:
    def test_measures_haze_but_publishes_no_concentration(self, session: Session) -> None:
        # The central restraint. With no fitted relation there is no defensible
        # conversion, and inventing one would be a fabricated reading.
        _seed_station(session)

        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.4),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.haze_index > 0
        assert result.estimate is None
        assert result.calibration.is_calibrated is False

    def test_explains_what_would_make_a_concentration_possible(self, session: Session) -> None:
        # A null estimate must not read as a bug, so the response says what is
        # missing and how many pairs it would take.
        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.3),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert str(CITIZEN_CALIBRATION_MIN_PAIRS) in result.calibration.explanation
        assert result.calibration.pairs_needed == CITIZEN_CALIBRATION_MIN_PAIRS

    def test_the_submission_is_still_stored(self, session: Session) -> None:
        # Worth keeping even with nothing derivable from it: pairs taken near a
        # monitor now are what let a photo taken far from one mean something later.
        _seed_station(session)
        before = citizen_repository.count_reports(session)

        citizen_service.submit(
            session,
            content=photo_bytes(haze=0.35),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert citizen_repository.count_reports(session) == before + 1


class TestCalibratedBehaviour:
    def test_publishes_a_concentration_with_its_error(self, session: Session) -> None:
        _seed_station(session)
        _seed_calibration(session)

        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.4),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.calibration.is_calibrated is True
        assert result.estimate is not None
        assert result.estimate.value >= 0
        assert result.estimate.uncertainty > 0

    def test_states_the_error_is_wide(self, session: Session) -> None:
        # The explanation has to say that a photograph is a weaker instrument,
        # or a citizen reads the figure as equivalent to a monitor's.
        _seed_calibration(session)
        _, status = citizen_service.calibration_status(session)

        assert status.mae is not None
        assert "never be the sole evidence" in status.explanation


class TestReferenceComparison:
    def test_pairs_a_submission_with_a_nearby_monitor(self, session: Session) -> None:
        station_id = _seed_station(session, value=150.0)

        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.4),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.reference is not None
        assert result.reference.station_id == station_id
        assert result.reference.value == pytest.approx(150.0)

    def test_a_submission_far_from_any_monitor_has_no_comparison(self, session: Session) -> None:
        # The case the tier exists for. No comparison is available, so the
        # submission extends coverage rather than calibrating it.
        _seed_station(session)

        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.4),
            coordinates=REMOTE,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.reference is None
        assert result.agrees_with_reference is None


class TestTrust:
    def test_a_new_device_starts_at_the_initial_trust(self, session: Session) -> None:
        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.3),
            coordinates=REMOTE,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.trust_score == pytest.approx(CITIZEN_INITIAL_TRUST)

    def test_photographing_where_there_is_no_monitor_costs_no_trust(self, session: Session) -> None:
        # A device must not be penalised for contributing exactly where the
        # reference network cannot check it, which is where it is most useful.
        for index in range(3):
            result = citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=REMOTE,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW + timedelta(minutes=index),
            )
            assert not isinstance(result, Rejection)
            assert result.trust_score == pytest.approx(CITIZEN_INITIAL_TRUST)

    def test_a_contradicted_submission_loses_trust(self, session: Session) -> None:
        # The monitor reads very clean while the photo is heavily hazed, so the
        # derived value cannot agree.
        _seed_station(session, value=5.0)
        _seed_calibration(session)

        result = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.75),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert not isinstance(result, Rejection)
        assert result.agrees_with_reference is False
        assert result.trust_score < CITIZEN_INITIAL_TRUST


class TestRejections:
    def test_a_blurred_photograph_is_refused(self, session: Session) -> None:
        result = citizen_service.submit(
            session,
            content=photo_bytes(blurred=True),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert isinstance(result, Rejection)
        assert result.reason is RejectionReason.OUT_OF_FOCUS

    def test_a_refused_photograph_is_not_stored(self, session: Session) -> None:
        before = citizen_repository.count_reports(session)

        citizen_service.submit(
            session,
            content=photo_bytes(blurred=True),
            coordinates=DELHI,
            captured_at=NOW,
            device_id=DEVICE,
            now=NOW,
        )

        assert citizen_repository.count_reports(session) == before


class TestInputValidation:
    def test_rejects_a_file_that_is_not_an_image(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="image"):
            citizen_service.submit(
                session,
                content=b"this is not a JPEG",
                coordinates=DELHI,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_an_empty_upload(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="empty"):
            citizen_service.submit(
                session,
                content=b"",
                coordinates=DELHI,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_a_stale_photograph(self, session: Session) -> None:
        # A photo from yesterday is a photograph of different air, and putting
        # it on a live map would show haze that has already dispersed.
        with pytest.raises(ValidationError, match="hours ago"):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=DELHI,
                captured_at=NOW - timedelta(hours=CITIZEN_MAX_CAPTURE_AGE_HOURS + 1),
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_a_capture_time_in_the_future(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="future"):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=DELHI,
                captured_at=NOW + timedelta(hours=2),
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_a_naive_capture_time(self, session: Session) -> None:
        with pytest.raises(ValidationError, match="timezone"):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=DELHI,
                captured_at=datetime(2026, 4, 2, 9, 0),
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_a_position_outside_india(self, session: Session) -> None:
        with pytest.raises(ValidationError):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=(2.35, 48.86),  # Paris
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW,
            )

    def test_rejects_transposed_coordinates(self, session: Session) -> None:
        # Latitude 77 is a valid number but not a place anyone photographs in
        # India, so the bounding box is what catches a transposed pair.
        with pytest.raises(ValidationError):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=(28.6333, 77.2167),
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW,
            )


class TestRateLimit:
    def test_one_device_cannot_flood_the_tier(self, session: Session) -> None:
        # A dense tier is only useful if a single participant cannot swamp it.
        for index in range(CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=REMOTE,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW + timedelta(seconds=index),
            )

        with pytest.raises(RateLimitExceededError, match="limit"):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=REMOTE,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW,
            )

    def test_the_limit_is_per_device(self, session: Session) -> None:
        for index in range(CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR):
            citizen_service.submit(
                session,
                content=photo_bytes(haze=0.3),
                coordinates=REMOTE,
                captured_at=NOW,
                device_id=DEVICE,
                now=NOW + timedelta(seconds=index),
            )

        other = citizen_service.submit(
            session,
            content=photo_bytes(haze=0.3),
            coordinates=REMOTE,
            captured_at=NOW,
            device_id="device-zzzzzz999999",
            now=NOW,
        )

        assert not isinstance(other, Rejection)
