"""Tests for a resident's complaint list and report.

Two properties matter most: a device can only ever reach its own submissions,
and the report never claims more than was measured -- no concentration from an
uncalibrated photograph, no suggestion an office was already told.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import GEMINI_BASE_URL, GEMINI_MODELS
from app.core.enums import ComplaintCategory, Pollutant, StationTier, SubmissionKind
from app.core.exceptions import NotFoundError, ValidationError
from app.core.h3_grid import point_to_cell
from app.core.references import format_reference
from app.documents.complaint_pdf import ComplaintDocument, Section, Translation
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


#: A Tamil description: "They burn garbage behind the bus stand at 9 every night."
TAMIL = "தினமும் இரவு 9 மணிக்கு பேருந்து நிலையத்தின் பின்னால் குப்பை எரிக்கிறார்கள்"
ENGLISH = "They burn garbage behind the bus stand at 9 every night."

GEMINI_URL = f"{GEMINI_BASE_URL}/models/{GEMINI_MODELS[0]}:generateContent"


def _photo(
    session: Session,
    *,
    device: str = DEVICE,
    paired: bool = False,
    description: str = "Smoke behind the bus stand every night",
) -> int:
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
            description=description,
            provenance="unverifiable",
        ),
    )


def _reading(session: Session, *, device: str = DEVICE, description: str | None = None) -> int:
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
            description=description,
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
        if section.translation:
            parts.extend((section.translation.label, section.translation.text))
    return "\n".join(parts)


def _reported(document: ComplaintDocument) -> Section:
    return next(section for section in document.sections if section.quote)


def _translated(document: ComplaintDocument) -> Translation | None:
    return _reported(document).translation


def gemini_translation(language: str, english: str, *, is_english: bool = False) -> httpx.Response:
    text = json.dumps({"language": language, "is_english": is_english, "english": english})
    return httpx.Response(
        200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
    )


@pytest.fixture
def with_gemini(settings: Settings) -> Settings:
    return settings.model_copy(update={"gemini_api_key": "test-gemini-key"})


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
    async def test_a_photo_report_quotes_the_resident_and_names_the_authority(
        self, session: Session, settings: Settings
    ) -> None:
        alert_repository.upsert_authority(
            session,
            name="Coimbatore district administration",
            jurisdiction=COIMBATORE_DISTRICT,
            escalation_tier=1,
        )
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, paired=True))

        document = await complaint_service.document_for(
            session, settings, reference, DEVICE, now=NOW
        )
        text = _all_text(document)

        assert document.reference == reference
        assert "Smoke behind the bus stand every night" in text
        assert "Open burning of waste" in text
        assert "Coimbatore district administration" in text
        assert "SIDCO Kurichi" in text

    async def test_an_uncalibrated_photo_states_no_concentration(
        self, session: Session, settings: Settings
    ) -> None:
        reference = format_reference(SubmissionKind.PHOTO, _photo(session))

        text = _all_text(
            await complaint_service.document_for(session, settings, reference, DEVICE, now=NOW)
        )

        assert "Not derivable yet" in text
        assert "not stored" in text

    async def test_never_implies_an_office_was_already_told(
        self, session: Session, settings: Settings
    ) -> None:
        reference = format_reference(SubmissionKind.SENSOR, _reading(session))

        text = _all_text(
            await complaint_service.document_for(session, settings, reference, DEVICE, now=NOW)
        )

        assert "does not forward an individual complaint automatically" in text
        assert "No reference monitor reported" in text

    async def test_says_when_no_jurisdiction_is_registered(
        self, session: Session, settings: Settings
    ) -> None:
        reference = format_reference(SubmissionKind.SENSOR, _reading(session))

        text = _all_text(
            await complaint_service.document_for(session, settings, reference, DEVICE, now=NOW)
        )

        assert "outside the jurisdictions registered" in text

    async def test_another_device_cannot_read_it(
        self, session: Session, settings: Settings
    ) -> None:
        reference = format_reference(SubmissionKind.PHOTO, _photo(session))

        with pytest.raises(NotFoundError):
            await complaint_service.document_for(
                session, settings, reference, OTHER_DEVICE, now=NOW
            )

    async def test_a_malformed_reference_is_refused(
        self, session: Session, settings: Settings
    ) -> None:
        with pytest.raises(ValidationError):
            await complaint_service.document_for(
                session, settings, "not-a-reference", DEVICE, now=NOW
            )

    async def test_renders_to_pdf_under_the_canonical_reference(
        self, session: Session, settings: Settings
    ) -> None:
        reading_id = _reading(session)

        canonical, pdf = await complaint_service.render_pdf(
            session, settings, f"  aw-s-{reading_id:06d} ", DEVICE, now=NOW
        )

        assert canonical == format_reference(SubmissionKind.SENSOR, reading_id)
        assert pdf.startswith(b"%PDF-")


class TestTranslation:
    @respx.mock
    async def test_a_tamil_description_is_printed_with_its_english_beneath(
        self, session: Session, with_gemini: Settings
    ) -> None:
        respx.post(GEMINI_URL).mock(return_value=gemini_translation("Tamil", ENGLISH))
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, description=TAMIL))

        document = await complaint_service.document_for(
            session, with_gemini, reference, DEVICE, now=NOW
        )

        assert _reported(document).quote == TAMIL
        translation = _translated(document)
        assert translation is not None
        assert translation.text == ENGLISH
        assert "machine translation from Tamil by Google Gemini" in translation.label
        assert "remain the record" in translation.label

    @respx.mock
    async def test_the_same_words_are_translated_once(
        self, session: Session, with_gemini: Settings
    ) -> None:
        route = respx.post(GEMINI_URL).mock(return_value=gemini_translation("Tamil", ENGLISH))
        references = [
            format_reference(SubmissionKind.PHOTO, _photo(session, description=TAMIL)),
            format_reference(SubmissionKind.SENSOR, _reading(session, description=TAMIL)),
        ]

        for reference in [*references, references[0]]:
            document = await complaint_service.document_for(
                session, with_gemini, reference, DEVICE, now=NOW
            )
            translation = _translated(document)
            assert translation is not None
            assert translation.text == ENGLISH

        assert route.call_count == 1

    @respx.mock
    async def test_an_english_description_is_printed_alone(
        self, session: Session, with_gemini: Settings
    ) -> None:
        route = respx.post(GEMINI_URL).mock(
            return_value=gemini_translation(
                "English", "Smoke behind the bus stand every night", is_english=True
            )
        )
        reference = format_reference(SubmissionKind.PHOTO, _photo(session))

        for _ in range(2):
            document = await complaint_service.document_for(
                session, with_gemini, reference, DEVICE, now=NOW
            )
            assert _translated(document) is None

        # Found to be English once, and not sent again.
        assert route.call_count == 1

    @respx.mock
    async def test_a_translation_that_adds_a_figure_is_discarded(
        self, session: Session, with_gemini: Settings
    ) -> None:
        route = respx.post(GEMINI_URL).mock(
            return_value=gemini_translation("Tamil", "They burn 50 kg of garbage at 9 every night.")
        )
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, description=TAMIL))

        for _ in range(2):
            document = await complaint_service.document_for(
                session, with_gemini, reference, DEVICE, now=NOW
            )
            translation = _translated(document)
            assert translation is not None
            assert "50" not in translation.text
            assert translation.text.startswith("Not shown")

        # Never stored, so the next download asks again.
        assert route.call_count == 2

    @respx.mock
    async def test_a_failed_translation_still_produces_the_report(
        self, session: Session, with_gemini: Settings
    ) -> None:
        for model in GEMINI_MODELS:
            respx.post(f"{GEMINI_BASE_URL}/models/{model}:generateContent").mock(
                return_value=httpx.Response(503, json={"error": "busy"})
            )
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, description=TAMIL))

        document = await complaint_service.document_for(
            session, with_gemini, reference, DEVICE, now=NOW
        )

        translation = _translated(document)
        assert translation is not None
        assert "could not translate this just now" in translation.text
        assert _reported(document).quote == TAMIL

    async def test_without_a_key_a_tamil_description_says_why_it_is_untranslated(
        self, session: Session, settings: Settings
    ) -> None:
        reference = format_reference(SubmissionKind.PHOTO, _photo(session, description=TAMIL))

        document = await complaint_service.document_for(
            session, settings, reference, DEVICE, now=NOW
        )

        translation = _translated(document)
        assert translation is not None
        assert translation.label == "In English"
        assert "not set up" in translation.text

    async def test_without_a_key_latin_text_is_left_alone(
        self, session: Session, settings: Settings
    ) -> None:
        # Hindi in Latin letters, with a dash: text an official can at least read aloud.
        reference = format_reference(
            SubmissionKind.PHOTO,
            _photo(session, description="Bahut dhuan hai — smoke everywhere"),
        )

        document = await complaint_service.document_for(
            session, settings, reference, DEVICE, now=NOW
        )

        assert _translated(document) is None
