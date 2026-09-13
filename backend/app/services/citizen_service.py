"""Accepting a photograph from a member of the public.

The value of this tier is density: a reference monitor costs ~1 crore and there
are a few hundred in the country, while there are a billion cameras. The risk is
that density arrives without accuracy and gets treated as if it had both.

So the pipeline is arranged to fail towards silence:

* An unusable photograph is **rejected with a reason**, never silently scored.
  Darkness, blur and over-exposure all make clean air look dirty.
* A submission produces a concentration **only if a calibration exists**, fitted
  from this network's own co-located pairs. Otherwise it reports a haze index
  and says plainly that no concentration can be derived yet.
* A device that repeatedly disagrees with nearby monitors **loses trust** and
  stops contributing to the calibration, without being blocked or identified.

The first submissions near stations are therefore the ones that make later
submissions far from stations mean anything. That bootstrapping is the point,
and it is why a report with no derived concentration is still worth storing.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np
from PIL import Image, UnidentifiedImageError
from sqlalchemy.orm import Session

from app.core.constants import (
    CITIZEN_CALIBRATION_MIN_PAIRS,
    CITIZEN_COLOCATION_RADIUS_M,
    CITIZEN_DISAGREEMENT_TOLERANCE,
    CITIZEN_INITIAL_TRUST,
    CITIZEN_MAX_CAPTURE_AGE_HOURS,
    CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR,
    CITIZEN_MIN_TRUST,
    CITIZEN_PHOTO_MAX_BYTES,
    CITIZEN_TRUST_STEP,
    CITIZEN_UNVERIFIED_TRUST,
    HOURS_PER_DAY,
)
from app.core.enums import ComplaintCategory, Pollutant, SubmissionKind
from app.core.exceptions import RateLimitExceededError, ValidationError
from app.core.geo import LonLat, validate_within_india
from app.core.h3_grid import point_to_cell
from app.core.logging import get_logger
from app.core.references import clean_description, format_reference
from app.ml.exif import PhotoProvenance, Verdict, verify
from app.ml.haze_calibration import HazeCalibration, HazeEstimate
from app.ml.haze_calibration import fit as fit_calibration
from app.ml.vision import HazeAnalysis, Rejection, analyse
from app.repositories import citizen_repository
from app.repositories.citizen_repository import CitizenReportRow, NearestReading

logger = get_logger(__name__)

#: Trust a device must hold for its pairs to shape the calibration. Set at the
#: starting value, so a device only stops contributing once it has actually
#: disagreed -- a newcomer is trusted until it gives a reason not to be.
CALIBRATION_MIN_TRUST = CITIZEN_INITIAL_TRUST

#: How far back the public map of submissions looks, in hours.
DEFAULT_REPORT_WINDOW_HOURS = HOURS_PER_DAY

#: Most reports one map request returns.
MAX_REPORTS_RETURNED = 500


@dataclass(frozen=True, slots=True)
class CalibrationStatus:
    """Whether a concentration can be derived from a haze index yet."""

    is_calibrated: bool
    pairs: int
    pairs_needed: int
    #: Leave-one-out error of the fit, when there is one.
    mae: float | None
    explanation: str


@dataclass(frozen=True, slots=True)
class AcceptedReport:
    """A stored submission and everything that could honestly be said about it."""

    report_id: int
    #: What the resident quotes, and downloads their complaint report by.
    complaint_reference: str
    haze_index: float
    h3_cell: str
    captured_at: datetime
    trust_score: float

    #: Present only when a calibration exists. None means the tier measured the
    #: haze but cannot yet state a concentration, which is reported as such
    #: rather than filled in with a plausible figure.
    estimate: HazeEstimate | None
    is_extrapolating: bool

    #: The nearby monitor this was compared with, when one was in range.
    reference: NearestReading | None
    agrees_with_reference: bool | None

    #: What the file's own metadata said about the submission.
    provenance: PhotoProvenance

    calibration: CalibrationStatus


def decode_image(content: bytes) -> np.ndarray:
    """Decode uploaded bytes into an RGB array.

    Raises:
        ValidationError: The upload is empty, oversized, or not an image this
            server can read. Uploaded bytes are untrusted input, so the failure
            is explicit rather than an exception escaping from the decoder.
    """
    if not content:
        raise ValidationError("The uploaded file is empty.")
    if len(content) > CITIZEN_PHOTO_MAX_BYTES:
        raise ValidationError(
            f"The photo is {len(content)} bytes, above the {CITIZEN_PHOTO_MAX_BYTES}-byte limit.",
        )

    try:
        with Image.open(io.BytesIO(content)) as opened:
            # Converting to RGB drops any alpha channel and normalises palette
            # and greyscale images, so the analyser always receives (H, W, 3).
            return np.asarray(opened.convert("RGB"), dtype=np.float64)
    except (UnidentifiedImageError, OSError, ValueError) as error:
        raise ValidationError(
            "The uploaded file could not be read as an image.",
        ) from error


def _validate_capture_time(captured_at: datetime, now: datetime) -> datetime:
    """Reject a capture time that cannot describe current air.

    Raises:
        ValidationError: The photo is from the future, or older than the window
            an episode lasts. A photograph from yesterday is a photograph of
            different air, and accepting it would put stale haze on a live map.
    """
    if captured_at.tzinfo is None:
        raise ValidationError("The capture time must state its timezone.")
    if captured_at > now + timedelta(minutes=1):
        raise ValidationError("The capture time is in the future.")

    age = now - captured_at
    if age > timedelta(hours=CITIZEN_MAX_CAPTURE_AGE_HOURS):
        raise ValidationError(
            f"The photo was taken {age.total_seconds() / 3600:.1f} hours ago, beyond the "
            f"{CITIZEN_MAX_CAPTURE_AGE_HOURS}-hour window in which it still describes "
            "current air.",
        )
    return captured_at


def _enforce_rate_limit(session: Session, device_id: str, now: datetime) -> None:
    """Stop one device flooding the tier.

    Raises:
        RateLimitExceededError: The device has already submitted its hourly allowance.
    """
    recent = citizen_repository.count_reports_since(session, device_id, now - timedelta(hours=1))
    if recent >= CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR:
        raise RateLimitExceededError(
            f"This device has submitted {recent} reports in the last hour, at the limit of "
            f"{CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR}.",
        )


def _next_trust(current: float, agrees: bool | None) -> float:
    """Adjust a device's trust after a submission.

    No comparison was possible means no change: a device should not lose
    standing for taking a photograph somewhere there is no monitor, since that
    is precisely where this tier is most needed.
    """
    if agrees is None:
        return current
    step = CITIZEN_TRUST_STEP if agrees else -CITIZEN_TRUST_STEP
    return float(min(1.0, max(CITIZEN_MIN_TRUST, current + step)))


def _agreement(
    estimate: HazeEstimate | None,
    reference: NearestReading | None,
) -> bool | None:
    """Whether a derived concentration matches the nearby monitor.

    Returns None when there is nothing to compare -- no monitor in range, or no
    calibration with which to derive a comparable number. An uncomparable
    submission is not a disagreement.
    """
    if estimate is None or reference is None or reference.value <= 0:
        return None
    relative = abs(estimate.value - reference.value) / reference.value
    return relative <= CITIZEN_DISAGREEMENT_TOLERANCE


def calibration_status(session: Session) -> tuple[HazeCalibration | None, CalibrationStatus]:
    """The current haze-to-concentration relation, and how to describe it."""
    pairs = citizen_repository.calibration_pairs(session, min_trust=CALIBRATION_MIN_TRUST)
    calibration = fit_calibration(pairs)

    if calibration is None:
        return None, CalibrationStatus(
            is_calibrated=False,
            pairs=len(pairs),
            pairs_needed=CITIZEN_CALIBRATION_MIN_PAIRS,
            mae=None,
            explanation=(
                f"No concentration can be derived from a photograph yet. That needs "
                f"{CITIZEN_CALIBRATION_MIN_PAIRS} submissions taken within "
                f"{CITIZEN_COLOCATION_RADIUS_M / 1000:.0f} km of a reference monitor, "
                f"spanning a range of conditions; there are {len(pairs)} so far. Until "
                "then this tier reports how hazy the air looked, which is what a "
                "photograph can actually establish."
            ),
        )

    return calibration, CalibrationStatus(
        is_calibrated=True,
        pairs=calibration.pairs,
        pairs_needed=CITIZEN_CALIBRATION_MIN_PAIRS,
        mae=calibration.mae,
        explanation=(
            f"Fitted from {calibration.pairs} co-located submissions, with a "
            f"leave-one-out error of {calibration.mae:.1f} ug/m3. That error is wide: a "
            "photograph is a weaker instrument than a monitor, and this estimate should "
            "never be the sole evidence for a decision."
        ),
    )


def submit(
    session: Session,
    *,
    content: bytes,
    coordinates: LonLat,
    captured_at: datetime,
    device_id: str,
    pollutant: Pollutant = Pollutant.PM25,
    category: ComplaintCategory | None = None,
    description: str | None = None,
    now: datetime | None = None,
) -> AcceptedReport | Rejection:
    """Accept a photograph, measure its haze, and store what it yielded.

    Args:
        session: Database session.
        content: The uploaded image bytes.
        coordinates: Where the photo was taken, ``(lon, lat)``.
        captured_at: When the photo was taken, timezone-aware.
        device_id: Opaque per-device identifier, for rate limiting and trust.
        pollutant: Pollutant to compare against a nearby monitor.
        category: What the resident says they saw, if they said.
        description: The resident's own words, trimmed; blank is stored as none.
        now: Reference time, injectable for tests.

    Returns:
        The stored report, or a :class:`Rejection` when the image cannot support
        an estimate. Rejection is a normal outcome and is not an error: every
        way a photograph fails here makes clean air look dirty.

    Raises:
        ValidationError: The upload, position or capture time is unusable.
        RateLimitExceededError: The device is over its hourly allowance.
    """
    reference_time = now or datetime.now(UTC)
    position = validate_within_india(coordinates)
    capture_time = _validate_capture_time(captured_at, reference_time)
    _enforce_rate_limit(session, device_id, reference_time)

    provenance = verify(content, claimed_position=position, claimed_time=capture_time)
    if provenance.verdict is Verdict.CONTRADICTED:
        # The file's own header disagrees with what was claimed about it. That is
        # the one direction EXIF is worth anything in, so it is acted on.
        logger.info("citizen.photo_contradicted", detail=provenance.detail)
        raise ValidationError(provenance.detail)

    analysis = analyse(decode_image(content))
    if isinstance(analysis, Rejection):
        logger.info("citizen.photo_rejected", reason=analysis.reason.value)
        return analysis

    return _store(
        session,
        analysis=analysis,
        position=position,
        capture_time=capture_time,
        device_id=device_id,
        pollutant=pollutant,
        provenance=provenance,
        category=category,
        description=clean_description(description),
    )


def _store(
    session: Session,
    *,
    analysis: HazeAnalysis,
    position: LonLat,
    capture_time: datetime,
    device_id: str,
    pollutant: Pollutant,
    provenance: PhotoProvenance,
    category: ComplaintCategory | None,
    description: str | None,
) -> AcceptedReport:
    """Persist an analysed submission and describe what it supports."""
    reference = citizen_repository.nearest_station_reading(
        session, position, pollutant, capture_time
    )
    calibration, status = calibration_status(session)

    estimate = calibration.estimate(analysis.haze_index) if calibration else None
    extrapolating = (
        calibration.is_extrapolating(analysis.haze_index) if calibration is not None else False
    )
    agrees = _agreement(estimate, reference)

    previous_trust = citizen_repository.latest_trust(session, device_id)
    trust = _next_trust(
        previous_trust if previous_trust is not None else CITIZEN_INITIAL_TRUST, agrees
    )
    if provenance.verdict is Verdict.UNVERIFIABLE:
        # Accepted and shown, but held below the threshold that lets a pair
        # shape the calibration. A submission nothing can corroborate should not
        # move a relation every other estimate is derived from.
        trust = min(trust, CITIZEN_UNVERIFIED_TRUST)

    report_id = citizen_repository.insert_report(
        session,
        CitizenReportRow(
            coordinates=position,
            h3_cell=point_to_cell(position),
            captured_at=capture_time,
            device_id=device_id,
            haze_index=analysis.haze_index,
            transmission=analysis.transmission,
            mean_luminance=analysis.mean_luminance,
            sharpness=analysis.sharpness,
            trust_score=trust,
            reference_station_id=reference.station_id if reference else None,
            reference_value=reference.value if reference else None,
            reference_distance_m=reference.distance_m if reference else None,
            category=category,
            description=description,
            provenance=provenance.verdict.value,
        ),
    )

    logger.info(
        "citizen.report_accepted",
        report_id=report_id,
        haze_index=round(analysis.haze_index, 3),
        calibrated=status.is_calibrated,
        paired=reference is not None,
        provenance=provenance.verdict.value,
        trust=round(trust, 2),
    )

    return AcceptedReport(
        report_id=report_id,
        complaint_reference=format_reference(SubmissionKind.PHOTO, report_id),
        haze_index=analysis.haze_index,
        h3_cell=point_to_cell(position),
        captured_at=capture_time,
        trust_score=trust,
        estimate=estimate,
        is_extrapolating=extrapolating,
        reference=reference,
        agrees_with_reference=agrees,
        provenance=provenance,
        calibration=status,
    )
