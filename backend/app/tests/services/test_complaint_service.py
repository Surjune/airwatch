"""Tests for a resident's complaint list and report.

Two properties matter most: a device can only ever reach its own submissions,
and the report never claims more than was measured -- no concentration from an
uncalibrated photograph, no suggestion an office was already told.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.core.enums import ComplaintCategory, Pollutant, StationTier, SubmissionKind
from app.core.exceptions import NotFoundError, ValidationError
from app.core.h3_grid import point_to_cell
from app.core.references import format_reference
from app.documents.complaint_pdf import ComplaintDocument
from app.repositories import (
    alert_repository,
    citizen_repository,
    citizen_sensor_repository,
    station_repository,
)
from app.repositories.citizen_repository import CitizenReportRow
from app.repositories.citizen_sensor_repository import SensorReadingRow
from app.services import complaint_service

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 13, 15, 0, tzinfo=UTC)

#: Beside SIDCO Kurichi, Coimbatore, in (longitude, latitude).
KURICHI: tuple[float, float] = (76.9790, 10.9425)

DEVICE = "complaint-device-0001"
OTHER_DEVICE = "someone-else-00001"

COIMBATORE_DISTRICT: list[tuple[float, float]] = [
    (76.80, 10.80),
    (77.20, 10.80),
    (77.20, 11.20),
    (76.80, 11.20),
]


def _photo(session: Session, *, device: str = DEVICE, paired: bool = False) -> int:
    station_id = (
        station_repository.upsert_station(
            session,
            source="test",
            source_station_id="kurichi",
            name="SIDCO Kurichi",
            tier=StationTier.REFERENCE,
            coordinates=KURICHI,
        )
        if paired
        else None
    )
    return citizen_repository.insert_report(
        session,
        CitizenReportRow(
            coordinates=KURICHI,
            h3_cell=point_to_cell(KURICHI),
            captured_at=NOW,
            device_id=device,
            haze_index=0.42,
            transmission=0.58,
            mean_luminance=120.0,
            sharpness=80.0,
            trust_score=0.5,
            reference_station_id=station_id,
            reference_value=61.0 if paired else None,
            reference_distance_m=200.0 if paired else None,
            category=ComplaintCategory.OPEN_BURNING,
            description="Smoke behind the bus stand every night",
            provenance="unverifiable",
        ),
    )


def _reading(session: Session, *, device: str = DEVICE) -> int:
    return citizen_sensor_repository.insert_reading(
        session,
        SensorReadingRow(
            coordinates=KURICHI,
            h3_cell=point_to_cell(KURICHI),
            observed_at=NOW,
            device_id=device,
            sensor_model="AirGradient ONE",
            pollutant=Pollutant.PM25,
            value=142.0,
            reference_station_id=None,
            reference_value=None,
            reference_distance_m=None,
            category=ComplaintCategory.INDUSTRIAL_SMOKE,
            description=None,
        ),
    )


def _all_text(document: ComplaintDocument) -> str:
    parts = [document.title, document.disclaimer]
    for section in document.sections:
        parts.append(section.title)
        parts.extend(f"{row.label} {row.value}" for row in section.rows)
        parts.extend(section.paragraphs)
        parts.extend(section.bullets)
        if section.quote:
            parts.append(section.quote)
    return "\n".join(parts)


class TestList:
    def test_lists_only_this_devices_submissions_newest_first(self, session: Session) -> None:
        photo_id = _photo(session)
        reading_id = _reading(session)
        _photo(session, device=OTHER_DEVICE)

        complaints = complaint_service.list_for_device(session, DEVICE)

        references = {complaint.reference for complaint in complaints}
        assert references == {
            format_reference(SubmissionKind.PHOTO, photo_id),
            format_reference(SubmissionKind.SENSOR, reading_id),
        }

    def test_names_the_area_and_the_concern(self, session: Session) -> None:
        _photo(session)

        [complaint] = complaint_service.list_for_device(session, DEVICE)

        assert complaint.area == "Coimbatore"
        assert complaint.category is ComplaintCategory.OPEN_BURNING


class TestReport:
    def test_a_photo_report_quotes_the_resident_and_names_the_authority(
        self, session: Session
    ) -> None:
        alert_repository.upsert_authority(
            session,
            name="Coimbatore district administration",
            jurisdiction=COIMBATORE_DISTRICT,
            escalation_tier=1,
        )
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, paired=True))

        document = complaint_service.document_for(session, reference, DEVICE, now=NOW)
        text = _all_text(document)

        assert document.reference == reference
        assert "Smoke behind the bus stand every night" in text
        assert "Open burning of waste" in text
        assert "Coimbatore district administration" in text
        assert "SIDCO Kurichi" in text

    def test_an_uncalibrated_photo_states_no_concentration(self, session: Session) -> None:
        reference = format_reference(SubmissionKind.PHOTO, _photo(session))

        text = _all_text(complaint_service.document_for(session, reference, DEVICE, now=NOW))

        assert "Not derivable yet" in text
        assert "not stored" in text

    def test_never_implies_an_office_was_already_told(self, session: Session) -> None:
        reference = format_reference(SubmissionKind.SENSOR, _reading(session))

        text = _all_text(complaint_service.document_for(session, reference, DEVICE, now=NOW))

        assert "does not forward an individual complaint automatically" in text
        assert "No reference monitor reported" in text

    def test_says_when_no_jurisdiction_is_registered(self, session: Session) -> None:
        reference = format_reference(SubmissionKind.SENSOR, _reading(session))

        text = _all_text(complaint_service.document_for(session, reference, DEVICE, now=NOW))

        assert "outside the jurisdictions registered" in text

    def test_another_device_cannot_read_it(self, session: Session) -> None:
        reference = format_reference(SubmissionKind.PHOTO, _photo(session))

        with pytest.raises(NotFoundError):
            complaint_service.document_for(session, reference, OTHER_DEVICE, now=NOW)

    def test_a_malformed_reference_is_refused(self, session: Session) -> None:
        with pytest.raises(ValidationError):
            complaint_service.document_for(session, "not-a-reference", DEVICE, now=NOW)

    def test_renders_to_pdf_under_the_canonical_reference(self, session: Session) -> None:
        reading_id = _reading(session)

        canonical, pdf = complaint_service.render_pdf(
            session, f"  aw-s-{reading_id:06d} ", DEVICE, now=NOW
        )

        assert canonical == format_reference(SubmissionKind.SENSOR, reading_id)
        assert pdf.startswith(b"%PDF-")
