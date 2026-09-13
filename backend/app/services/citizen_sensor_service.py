"""Accepting a reading from a citizen's own air-quality sensor.

The problem this tier answers is density. Coimbatore, a city of about 2.5
million, has one reference monitor in range and its PM2.5 sensor is down, while
a household sensor costs a few thousand rupees. The risk is the usual one for a
cheap instrument: its number looks exactly like a monitor's once it is on a map,
and it is systematically high in humid air.

So a reading is:

* **checked at the boundary** -- a household sensor measures particles, so only
  PM2.5 and PM10 are accepted; a value outside physical bounds is refused with a
  reason rather than stored, because at this tier it is a typing error, not an
  instrument fault worth keeping;
* **stored as reported**, never corrected by a factor nobody has measured;
* **paired with the nearest reference monitor** reading in space and time, by the
  same rule that pairs a photograph, so the network accumulates the evidence a
  correction would need; and
* **kept out of every analysis**. Detection, fusion and forecasting read the
  reference tier only. This tier is shown, compared and counted, not used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.cities import in_city
from app.core.constants import (
    CITIZEN_COLOCATION_RADIUS_M,
    CITIZEN_SENSOR_MAX_AGE_HOURS,
    CITIZEN_SENSOR_MAX_READINGS_PER_DEVICE_PER_HOUR,
    CITIZEN_SENSOR_POLLUTANTS,
    HOURS_PER_DAY,
)
from app.core.enums import PilotCity, Pollutant
from app.core.exceptions import RateLimitExceededError, ValidationError
from app.core.geo import LonLat, validate_within_india
from app.core.h3_grid import point_to_cell
from app.core.logging import get_logger
from app.core.plausibility import is_plausible, plausible_range
from app.ml.sensor_colocation import ColocationSummary, relative_difference, summarise
from app.repositories import citizen_repository, citizen_sensor_repository
from app.repositories.citizen_repository import NearestReading
from app.repositories.citizen_sensor_repository import SensorReadingRow, StoredSensorReading

logger = get_logger(__name__)

#: How far back the public list of readings looks, in hours.
DEFAULT_READING_WINDOW_HOURS = HOURS_PER_DAY

#: Most readings one list request returns.
MAX_READINGS_RETURNED = 500


@dataclass(frozen=True, slots=True)
class AcceptedReading:
    """A stored reading and everything that can honestly be said about it."""

    reading_id: int
    h3_cell: str
    observed_at: datetime
    pollutant: Pollutant
    value: float
    #: The CPCB sub-index the raw value would carry. Uncalibrated, and labelled so
    #: wherever it is shown.
    raw_aqi: float
    reference: NearestReading | None
    #: (sensor - reference) / reference, when a comparison was possible.
    relative_difference: float | None
    colocation: ColocationSummary


@dataclass(frozen=True, slots=True)
class PublishedReading:
    """A stored reading with the sub-index its raw value would carry."""

    reading: StoredSensorReading
    raw_aqi: float
    raw_category: str


def _validate(pollutant: Pollutant, value: float, observed_at: datetime, now: datetime) -> None:
    """Refuse a reading that cannot describe current ambient air.

    Raises:
        ValidationError: With a reason the submitter can act on.
    """
    if pollutant.value not in CITIZEN_SENSOR_POLLUTANTS:
        raise ValidationError(
            f"A household sensor reading must be PM2.5 or PM10, not {pollutant.value}. "
            "Consumer gas sensors drift too far to be compared with a monitor."
        )
    if not is_plausible(pollutant, value):
        low, high = plausible_range(pollutant)
        raise ValidationError(
            f"{value:g} ug/m3 is outside the {low:g}-{high:g} ug/m3 range ambient "
            f"{pollutant.value} can reach. Check the number was copied correctly."
        )
    if observed_at.tzinfo is None:
        raise ValidationError("The observation time must state its timezone.")
    if observed_at > now + timedelta(minutes=1):
        raise ValidationError("The observation time is in the future.")
    if now - observed_at > timedelta(hours=CITIZEN_SENSOR_MAX_AGE_HOURS):
        raise ValidationError(
            f"The reading is older than {CITIZEN_SENSOR_MAX_AGE_HOURS} hours, so it describes "
            "different air from the network's current picture."
        )


def _enforce_rate_limit(session: Session, device_id: str, now: datetime) -> None:
    """Stop one device flooding the tier.

    Raises:
        RateLimitExceededError: The device has used its hourly allowance.
    """
    recent = citizen_sensor_repository.count_readings_since(
        session, device_id, now - timedelta(hours=1)
    )
    if recent >= CITIZEN_SENSOR_MAX_READINGS_PER_DEVICE_PER_HOUR:
        raise RateLimitExceededError(
            f"This device has submitted {recent} readings in the last hour, at the limit of "
            f"{CITIZEN_SENSOR_MAX_READINGS_PER_DEVICE_PER_HOUR}."
        )


def colocation(session: Session, pollutant: Pollutant) -> ColocationSummary:
    """What the pairs collected so far say about how far sensors read from monitors."""
    return summarise(citizen_sensor_repository.colocated_pairs(session, pollutant))


def submit(
    session: Session,
    *,
    coordinates: LonLat,
    pollutant: Pollutant,
    value: float,
    observed_at: datetime,
    device_id: str,
    sensor_model: str,
    now: datetime | None = None,
) -> AcceptedReading:
    """Validate, pair and store one sensor reading.

    Args:
        session: Database session.
        coordinates: Where the sensor is, ``(lon, lat)``.
        pollutant: PM2.5 or PM10.
        value: The reading as the sensor reported it, in ug/m3.
        observed_at: When the sensor measured, timezone-aware.
        device_id: Opaque per-device identifier.
        sensor_model: What the instrument is, as the submitter describes it.
        now: Reference time, injectable for tests.

    Raises:
        ValidationError: The position, pollutant, value or time is unusable.
        RateLimitExceededError: The device is over its hourly allowance.
    """
    reference_time = now or datetime.now(UTC)
    position = validate_within_india(coordinates)
    _validate(pollutant, value, observed_at, reference_time)
    _enforce_rate_limit(session, device_id, reference_time)

    reference = citizen_repository.nearest_station_reading(
        session, position, pollutant, observed_at
    )
    cell = point_to_cell(position)
    reading_id = citizen_sensor_repository.insert_reading(
        session,
        SensorReadingRow(
            coordinates=position,
            h3_cell=cell,
            observed_at=observed_at,
            device_id=device_id,
            sensor_model=sensor_model.strip(),
            pollutant=pollutant,
            value=value,
            reference_station_id=reference.station_id if reference else None,
            reference_value=reference.value if reference else None,
            reference_distance_m=reference.distance_m if reference else None,
        ),
    )
    difference = relative_difference(value, reference.value) if reference is not None else None

    logger.info(
        "citizen_sensor.reading_accepted",
        reading_id=reading_id,
        pollutant=pollutant.value,
        paired=reference is not None,
        relative_difference=None if difference is None else round(difference, 3),
    )

    return AcceptedReading(
        reading_id=reading_id,
        h3_cell=cell,
        observed_at=observed_at,
        pollutant=pollutant,
        value=value,
        raw_aqi=aqi.sub_index(pollutant, value),
        reference=reference,
        relative_difference=difference,
        colocation=colocation(session, pollutant),
    )


def recent(
    session: Session,
    pollutant: Pollutant,
    *,
    window_hours: int = DEFAULT_READING_WINDOW_HOURS,
    city: PilotCity | None = None,
    now: datetime | None = None,
) -> tuple[list[PublishedReading], ColocationSummary]:
    """Readings over a recent window, optionally in one city, with the tier's bias so far."""
    since = (now or datetime.now(UTC)) - timedelta(hours=window_hours)
    published: list[PublishedReading] = []
    for reading in citizen_sensor_repository.recent_readings(
        session, pollutant, since, limit=MAX_READINGS_RETURNED
    ):
        if not in_city(reading.coordinates, city):
            continue
        sub_index = aqi.sub_index(pollutant, reading.value)
        published.append(
            PublishedReading(
                reading=reading, raw_aqi=sub_index, raw_category=aqi.category(sub_index)
            )
        )
    return published, colocation(session, pollutant)


def colocation_explanation(summary: ColocationSummary) -> str:
    """Say in plain language what the bias figures do and do not establish."""
    radius_km = CITIZEN_COLOCATION_RADIUS_M / 1000
    if summary.pairs == 0:
        return (
            "No reading has been taken close enough to a reference monitor to compare yet. "
            f"A reading within {radius_km:.0f} km of one, while it is reporting, is what lets "
            "this tier's bias be measured."
        )
    if not summary.is_established:
        return (
            f"{summary.pairs} of the {summary.pairs_needed} co-located readings needed. The "
            "figures are shown, but that many pairs cannot yet separate a real bias from the "
            "difference between one humid morning and one dry afternoon."
        )
    return (
        f"Measured from {summary.pairs} readings taken within {radius_km:.0f} km of a reference "
        "monitor. Readings are still shown as reported; the ratio is what a correction would "
        "be fitted from, not a correction already applied."
    )
