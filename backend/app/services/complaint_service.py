"""A resident's own submissions, and the complaint report for each.

A photograph or a sensor reading can carry what the resident saw. This service
lists a device's submissions and words the report for one of them: what was
submitted, what AirWatch measured, how it compared with the nearest monitor, who
is responsible for that ground, and what happens next.

Two constraints shape every sentence:

* **Only the submitting device can read it.** A description can say where
  someone lives. Lookups are by reference *and* device, and a mismatch is
  indistinguishable from a missing reference.
* **It must not overstate.** A photograph measures haze, not PM2.5; a household
  sensor is uncalibrated; neither establishes a cause. AirWatch does not forward
  an individual complaint on its own, and the report says so rather than implying
  an office has already been told.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.cities import in_city
from app.core.constants import (
    CITIZEN_COLOCATION_RADIUS_M,
    CITIZEN_INITIAL_TRUST,
    CITIZEN_REFERENCE_MAX_GAP_MINUTES,
    COMPLAINT_LIST_LIMIT,
    IST_UTC_OFFSET_MINUTES,
    PILOT_CITY_LABELS,
)
from app.core.enums import ComplaintCategory, PilotCity, SubmissionKind, VisibleSource
from app.core.exceptions import NotFoundError
from app.core.geo import LonLat
from app.core.logging import get_logger
from app.core.references import format_reference, parse_reference
from app.documents.complaint_pdf import ComplaintDocument, Row, Section, render
from app.ml.haze_calibration import fit as fit_calibration
from app.ml.sensor_colocation import relative_difference
from app.repositories import alert_repository, citizen_repository, citizen_sensor_repository
from app.repositories.citizen_repository import PhotoReadingRow, StoredPhotoReport
from app.repositories.citizen_sensor_repository import DeviceSensorReading

logger = get_logger(__name__)

_IST = timezone(timedelta(minutes=IST_UTC_OFFSET_MINUTES))

#: Metres in a kilometre, for distances written in km.
_METRES_PER_KM = 1000
#: Percent, for a relative difference written as a percentage.
_PERCENT = 100

CATEGORY_LABELS: dict[ComplaintCategory, str] = {
    ComplaintCategory.OPEN_BURNING: "Open burning of waste",
    ComplaintCategory.INDUSTRIAL_SMOKE: "Smoke or fumes from an industrial unit",
    ComplaintCategory.CONSTRUCTION_DUST: "Dust from construction or demolition",
    ComplaintCategory.VEHICLE_EXHAUST: "Vehicle exhaust or idling traffic",
    ComplaintCategory.CROP_RESIDUE_BURNING: "Burning of crop residue",
    ComplaintCategory.ROAD_DUST: "Dust from unpaved or unswept roads",
    ComplaintCategory.OTHER: "Other",
}

#: How Gemini's reading of a photograph is named on a report.
VISIBLE_SOURCE_LABELS: dict[VisibleSource, str] = {
    VisibleSource.OPEN_BURNING: "Open burning of waste",
    VisibleSource.INDUSTRIAL_SMOKE: "Smoke or fumes from an industrial unit",
    VisibleSource.CONSTRUCTION_DUST: "Dust from construction or demolition",
    VisibleSource.VEHICLE_EXHAUST: "Vehicle exhaust",
    VisibleSource.CROP_RESIDUE_BURNING: "Burning of crop residue",
    VisibleSource.ROAD_DUST: "Road dust",
    VisibleSource.HAZE_WITHOUT_VISIBLE_SOURCE: "Haze, with no source visible in the frame",
    VisibleSource.NONE_VISIBLE: "No visible pollution",
    VisibleSource.NOT_OUTDOOR: "Not a photograph of outdoor air",
}


def _photo_reading_value(reading: PhotoReadingRow | None) -> str:
    if reading is None:
        return "Not read"
    label = VISIBLE_SOURCE_LABELS[reading.visible_source]
    return (
        f"{label} (Google Gemini, {reading.confidence * _PERCENT:.0f}% confidence). "
        f"{reading.observation}"
    )


#: How a jurisdiction's tier is named on a report.
_TIER_LABELS: dict[int, str] = {1: "Responsible first", 2: "Escalation"}

_PROVENANCE_LABELS: dict[str, str] = {
    "consistent": "The photo's own metadata matched the place and time given",
    "unverifiable": "The photo carried no usable metadata (common; apps strip it)",
    "contradicted": "The photo's metadata contradicted the place or time given",
}


@dataclass(frozen=True, slots=True)
class ComplaintSummary:
    """One of a device's submissions, as listed beside its download button."""

    reference: str
    kind: SubmissionKind
    submitted_at: datetime
    observed_at: datetime
    category: ComplaintCategory | None
    area: str
    headline: str
    compared_with_monitor: bool


def _ist(moment: datetime) -> str:
    return moment.astimezone(_IST).strftime("%d %b %Y, %H:%M IST")


def _area(point: LonLat) -> str:
    for city in PilotCity:
        if in_city(point, city):
            return PILOT_CITY_LABELS[city.value]
    return "Outside the pilot cities"


def _photo_headline(photo: StoredPhotoReport) -> str:
    return f"Photograph · haze {photo.haze_index:.2f}"


def _reading_headline(reading: DeviceSensorReading) -> str:
    return f"{reading.sensor_model} · {reading.value:.0f} µg/m³ {_pollutant(reading)}"


def _pollutant(reading: DeviceSensorReading) -> str:
    return "PM2.5" if reading.pollutant.value == "pm25" else "PM10"


def list_for_device(session: Session, device_id: str) -> list[ComplaintSummary]:
    """A device's photographs and sensor readings, newest first."""
    summaries = [
        ComplaintSummary(
            reference=format_reference(SubmissionKind.PHOTO, photo.report_id),
            kind=SubmissionKind.PHOTO,
            submitted_at=photo.submitted_at,
            observed_at=photo.captured_at,
            category=photo.category,
            area=_area(photo.coordinates),
            headline=_photo_headline(photo),
            compared_with_monitor=photo.reference_value is not None,
        )
        for photo in citizen_repository.photos_for_device(
            session, device_id, limit=COMPLAINT_LIST_LIMIT
        )
    ] + [
        ComplaintSummary(
            reference=format_reference(SubmissionKind.SENSOR, reading.reading_id),
            kind=SubmissionKind.SENSOR,
            submitted_at=reading.submitted_at,
            observed_at=reading.observed_at,
            category=reading.category,
            area=_area(reading.coordinates),
            headline=_reading_headline(reading),
            compared_with_monitor=reading.reference_value is not None,
        )
        for reading in citizen_sensor_repository.readings_for_device(
            session, device_id, limit=COMPLAINT_LIST_LIMIT
        )
    ]
    summaries.sort(key=lambda summary: summary.submitted_at, reverse=True)
    return summaries[:COMPLAINT_LIST_LIMIT]


def document_for(
    session: Session, reference: str, device_id: str, *, now: datetime | None = None
) -> ComplaintDocument:
    """Word the complaint report for one of this device's submissions.

    Raises:
        ValidationError: The reference is malformed.
        NotFoundError: No submission has that reference for this device.
    """
    kind, submission_id = parse_reference(reference)
    generated_at = now or datetime.now(UTC)

    if kind is SubmissionKind.PHOTO:
        photo = citizen_repository.photo_for_device(session, submission_id, device_id)
        if photo is None:
            raise NotFoundError("complaint", reference)
        document = _photo_document(session, photo, generated_at)
    else:
        reading = citizen_sensor_repository.reading_for_device(session, submission_id, device_id)
        if reading is None:
            raise NotFoundError("complaint", reference)
        document = _reading_document(session, reading, generated_at)

    logger.info("complaint.report_prepared", reference=document.reference, kind=kind.value)
    return document


def render_pdf(
    session: Session, reference: str, device_id: str, *, now: datetime | None = None
) -> tuple[str, bytes]:
    """The canonical reference and PDF bytes of one of this device's complaint reports."""
    document = document_for(session, reference, device_id, now=now)
    return document.reference, render(document)


def _reported_section(
    kind: SubmissionKind,
    category: ComplaintCategory | None,
    description: str | None,
    observed_at: datetime,
    submitted_at: datetime,
    point: LonLat,
) -> Section:
    lon, lat = point
    what = "A photograph" if kind is SubmissionKind.PHOTO else "A reading from a household sensor"
    return Section(
        title="What you reported",
        rows=(
            Row("Submission", what),
            Row("Concern", CATEGORY_LABELS[category] if category else "Not stated"),
            Row(
                "Observed at" if kind is SubmissionKind.SENSOR else "Photographed at",
                _ist(observed_at),
            ),
            Row("Submitted at", _ist(submitted_at)),
            Row("Location", f"{lat:.5f}° N, {lon:.5f}° E · {_area(point)}"),
        ),
        quote=description,
    )


def _authority_section(session: Session, point: LonLat) -> tuple[Section, str | None]:
    authorities = alert_repository.authorities_at(session, point)
    if not authorities:
        return (
            Section(
                title="Who is responsible for this location",
                paragraphs=(
                    "This location falls outside the jurisdictions registered in AirWatch. "
                    "The district administration and the state pollution control board for "
                    "the area remain the bodies to approach.",
                ),
            ),
            None,
        )
    return (
        Section(
            title="Who is responsible for this location",
            rows=tuple(
                Row(_TIER_LABELS.get(tier, f"Tier {tier}"), name) for name, tier in authorities
            ),
            paragraphs=(
                "From the registered district and state boundaries (OpenStreetMap). Which office "
                "inside each body handles air complaints is for that body to confirm.",
            ),
        ),
        authorities[0][0],
    )


def _next_steps(reference: str, first_authority: str | None, stored_where: str) -> Section:
    lodge_with = first_authority or "the district administration"
    return Section(
        title="What happens next",
        bullets=(
            f"Your submission is stored under {reference} and counted in {stored_where}. "
            "It is kept out of AirWatch's own hotspot estimates, which use reference "
            "monitors only.",
            "AirWatch does not forward an individual complaint automatically. To lodge it "
            f"officially, attach this report to a grievance with {lodge_with}, or with the "
            "state pollution control board, and quote the reference.",
            "If the monitors around you detect an excess persisting for hours, AirWatch routes "
            "an alert to the responsible authority on its own. This report is then supporting "
            "evidence of what residents saw.",
        ),
    )


def _comparison_paragraph(
    station: str | None, value: float | None, distance_m: float | None, sensor_value: float | None
) -> str:
    radius_km = CITIZEN_COLOCATION_RADIUS_M / _METRES_PER_KM
    if station is None or value is None or distance_m is None:
        return (
            f"No reference monitor reported within {radius_km:.0f} km and "
            f"{CITIZEN_REFERENCE_MAX_GAP_MINUTES} minutes of this submission, so it could not be "
            "checked against one. That is the ground the citizen tier exists to cover."
        )
    sentence = (
        f"The nearest reference monitor, {station}, {distance_m / _METRES_PER_KM:.1f} km away, "
        f"reported {value:.0f} µg/m³ within {CITIZEN_REFERENCE_MAX_GAP_MINUTES} minutes."
    )
    if sensor_value is not None:
        difference = relative_difference(sensor_value, value)
        if difference is not None:
            direction = "higher" if difference >= 0 else "lower"
            sentence += (
                f" Your sensor read {abs(difference) * _PERCENT:.0f}% {direction}. Household "
                "optical sensors commonly read high in humid air."
            )
    return sentence


def _photo_document(
    session: Session, photo: StoredPhotoReport, generated_at: datetime
) -> ComplaintDocument:
    reference = format_reference(SubmissionKind.PHOTO, photo.report_id)
    calibration = fit_calibration(
        citizen_repository.calibration_pairs(session, min_trust=CITIZEN_INITIAL_TRUST)
    )
    estimate = calibration.estimate(photo.haze_index) if calibration else None

    rows = [
        Row("Haze index", f"{photo.haze_index:.2f}  (0 is perfectly clear air, 1 fully obscured)"),
        Row(
            "Estimated PM2.5",
            f"{estimate.value:.0f} ± {estimate.uncertainty:.0f} µg/m³, from the calibration as of "
            "this report"
            if estimate
            else "Not derivable yet: too few photographs have been taken beside a monitor",
        ),
        Row("Visible in the photo", _photo_reading_value(photo.photo_reading)),
        Row("Photo metadata", _PROVENANCE_LABELS.get(photo.provenance or "", "Not recorded")),
        Row(
            "Counts towards calibration",
            "Yes"
            if photo.reference_value is not None and photo.trust_score >= CITIZEN_INITIAL_TRUST
            else "No",
        ),
    ]
    authority_section, first_authority = _authority_section(session, photo.coordinates)

    return ComplaintDocument(
        reference=reference,
        title="Complaint report",
        generated_at=generated_at,
        generated_label=f"Generated {_ist(generated_at)} from the record held for this reference",
        sections=(
            _reported_section(
                SubmissionKind.PHOTO,
                photo.category,
                photo.description,
                photo.captured_at,
                photo.submitted_at,
                photo.coordinates,
            ),
            Section(
                title="What AirWatch measured",
                rows=tuple(rows),
                paragraphs=(
                    "The photograph itself is not stored; only what was measured from it. What "
                    "is visible in it was suggested by Google Gemini, an AI model: it describes "
                    "the image, measures nothing, and does not establish a source.",
                ),
            ),
            Section(
                title="Compared with the nearest monitor",
                paragraphs=(
                    _comparison_paragraph(
                        photo.reference_station_name,
                        photo.reference_value,
                        photo.reference_distance_m,
                        None,
                    ),
                ),
            ),
            authority_section,
            _next_steps(reference, first_authority, "the residents' photograph tier"),
        ),
        disclaimer=(
            "A citizen measurement, not a regulatory one. A photograph measures how hazy the air "
            "looked, not the concentration of PM2.5, and haze has causes other than pollution. "
            "This report records what was submitted and measured; it does not establish the "
            "source of any pollution."
        ),
    )


def _reading_document(
    session: Session, reading: DeviceSensorReading, generated_at: datetime
) -> ComplaintDocument:
    reference = format_reference(SubmissionKind.SENSOR, reading.reading_id)
    sub_index = aqi.sub_index(reading.pollutant, reading.value)
    authority_section, first_authority = _authority_section(session, reading.coordinates)

    return ComplaintDocument(
        reference=reference,
        title="Complaint report",
        generated_at=generated_at,
        generated_label=f"Generated {_ist(generated_at)} from the record held for this reference",
        sections=(
            _reported_section(
                SubmissionKind.SENSOR,
                reading.category,
                reading.description,
                reading.observed_at,
                reading.submitted_at,
                reading.coordinates,
            ),
            Section(
                title="What AirWatch recorded",
                rows=(
                    Row("Instrument", reading.sensor_model),
                    Row(
                        "Reading",
                        f"{reading.value:.0f} µg/m³ of {_pollutant(reading)}, as reported",
                    ),
                    Row(
                        "Index it would carry",
                        f"{sub_index:.0f} ({aqi.category(sub_index)}), before any correction",
                    ),
                ),
            ),
            Section(
                title="Compared with the nearest monitor",
                paragraphs=(
                    _comparison_paragraph(
                        reading.reference_station_name,
                        reading.reference_value,
                        reading.reference_distance_m,
                        reading.value,
                    ),
                ),
            ),
            authority_section,
            _next_steps(reference, first_authority, "the residents' sensor tier"),
        ),
        disclaimer=(
            "A citizen measurement, not a regulatory one. A household optical sensor is "
            "uncalibrated and typically over-reads in humid air, so its number is not "
            "comparable with an official monitor's. This report records what was submitted and "
            "measured; it does not establish the source of any pollution."
        ),
    )
