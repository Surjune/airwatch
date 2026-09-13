"""Tests for the spoken screen guide: transcripts, versions, and stored speech."""

from __future__ import annotations

import base64

import httpx
import pytest
import respx
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import SARVAM_BASE_URL, SARVAM_TTS_PATH, VOICE_GUIDE_VERSION_LENGTH
from app.core.enums import GuideLanguage, GuideScreen
from app.core.exceptions import MissingCredentialError, NotFoundError
from app.guides.catalogue import script_for
from app.repositories import voice_guide_repository
from app.services import voice_guide_service
from app.services.voice_guide_service import clip_key

URL = f"{SARVAM_BASE_URL}{SARVAM_TTS_PATH}"
CLIP = b"\xff\xf3 spoken paragraph"


@pytest.fixture
def voiced(settings: Settings) -> Settings:
    return settings.model_copy(update={"sarvam_api_key": "sk_test_0123456789"})


def sarvam_ok() -> httpx.Response:
    return httpx.Response(200, json={"audios": [base64.b64encode(CLIP).decode()]})


class TestTranscript:
    def test_lists_every_paragraph_with_a_version(self, settings: Settings) -> None:
        view = voice_guide_service.guide(settings, GuideScreen.MAP, GuideLanguage.TAMIL)

        expected = script_for(GuideScreen.MAP, GuideLanguage.TAMIL)
        assert view.title == expected.title
        assert [section.text for section in view.sections] == [
            section.text for section in expected.sections
        ]
        assert all(len(s.audio_version) == VOICE_GUIDE_VERSION_LENGTH for s in view.sections)

    def test_says_when_this_deployment_cannot_speak(
        self, settings: Settings, voiced: Settings
    ) -> None:
        screen, language = GuideScreen.OVERVIEW, GuideLanguage.HINDI

        assert voice_guide_service.guide(settings, screen, language).voice_available is False
        assert voice_guide_service.guide(voiced, screen, language).voice_available is True

    def test_names_the_voice(self, settings: Settings) -> None:
        view = voice_guide_service.guide(settings, GuideScreen.MAP, GuideLanguage.ENGLISH)

        assert "Sarvam" in view.voice


class TestClipKey:
    def test_changes_when_the_words_change(self) -> None:
        assert clip_key(GuideLanguage.HINDI, "नमस्ते") != clip_key(GuideLanguage.HINDI, "नमस्ते।")

    def test_changes_with_the_language_for_the_same_words(self) -> None:
        # The same code-mixed words in another voice are a different clip.
        hindi = clip_key(GuideLanguage.HINDI, "AirWatch")
        assert hindi != clip_key(GuideLanguage.TAMIL, "AirWatch")

    def test_is_stable(self) -> None:
        assert clip_key(GuideLanguage.TAMIL, "வணக்கம்") == clip_key(GuideLanguage.TAMIL, "வணக்கம்")


async def test_a_paragraph_beyond_the_script_is_not_found(settings: Settings) -> None:
    beyond = len(script_for(GuideScreen.ALERTS, GuideLanguage.ENGLISH).sections)

    # Checked before storage is touched, so no database is needed.
    with pytest.raises(NotFoundError):
        await voice_guide_service.section_audio(
            None,  # type: ignore[arg-type]
            settings,
            GuideScreen.ALERTS,
            GuideLanguage.ENGLISH,
            beyond,
        )


@pytest.mark.integration
class TestStoredSpeech:
    @respx.mock
    async def test_is_synthesised_once_and_then_served_from_storage(
        self, session: Session, voiced: Settings
    ) -> None:
        route = respx.post(URL).mock(return_value=sarvam_ok())

        first = await voice_guide_service.section_audio(
            session, voiced, GuideScreen.CITIZEN, GuideLanguage.TAMIL, 1
        )
        second = await voice_guide_service.section_audio(
            session, voiced, GuideScreen.CITIZEN, GuideLanguage.TAMIL, 1
        )

        assert first.audio == second.audio == CLIP
        assert first.version == second.version
        assert route.call_count == 1

    async def test_without_a_key_a_new_paragraph_is_a_typed_error(
        self, session: Session, settings: Settings
    ) -> None:
        with pytest.raises(MissingCredentialError):
            await voice_guide_service.section_audio(
                session, settings, GuideScreen.MAP, GuideLanguage.HINDI, 0
            )

    @respx.mock
    async def test_a_stored_paragraph_still_plays_without_a_key(
        self, session: Session, settings: Settings, voiced: Settings
    ) -> None:
        respx.post(URL).mock(return_value=sarvam_ok())
        await voice_guide_service.section_audio(
            session, voiced, GuideScreen.MAP, GuideLanguage.HINDI, 0
        )

        clip = await voice_guide_service.section_audio(
            session, settings, GuideScreen.MAP, GuideLanguage.HINDI, 0
        )

        assert clip.audio == CLIP

    @respx.mock
    async def test_warming_generates_only_what_is_missing_and_counts_failures(
        self, session: Session, voiced: Settings
    ) -> None:
        refusals = iter([httpx.Response(400, json={"error": {"message": "bad"}})])
        respx.post(URL).mock(side_effect=lambda _request: next(refusals, sarvam_ok()))
        total = sum(
            len(script_for(screen, language).sections)
            for screen in GuideScreen
            for language in GuideLanguage
        )

        outcome = await voice_guide_service.warm(session, voiced)

        assert (outcome.already_stored, outcome.synthesised, outcome.failed) == (0, total - 1, 1)

        again = await voice_guide_service.warm(session, voiced)

        assert (again.already_stored, again.synthesised, again.failed) == (total - 1, 1, 0)

    async def test_warming_with_everything_stored_needs_no_key(
        self, session: Session, settings: Settings
    ) -> None:
        for language in GuideLanguage:
            for screen in GuideScreen:
                for section in script_for(screen, language).sections:
                    voice_guide_repository.store_clip(
                        session,
                        voice_guide_repository.ClipRow(
                            cache_key=clip_key(language, section.speech),
                            language=language.value,
                            model="bulbul:v3",
                            speaker="test",
                            audio=CLIP,
                        ),
                    )

        outcome = await voice_guide_service.warm(session, settings)

        assert outcome.synthesised == 0
        assert outcome.failed == 0


@pytest.mark.integration
class TestRepository:
    def test_storing_the_same_clip_twice_keeps_one(self, session: Session) -> None:
        row = voice_guide_repository.ClipRow(
            cache_key="a" * 64, language="ta", model="bulbul:v3", speaker="kavitha", audio=CLIP
        )
        voice_guide_repository.store_clip(session, row)
        voice_guide_repository.store_clip(session, row)

        assert voice_guide_repository.clip_audio(session, "a" * 64) == CLIP
        assert voice_guide_repository.cached_keys(session, ["a" * 64, "b" * 64]) == {"a" * 64}
