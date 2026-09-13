"""The spoken guide: what each screen is for, read aloud in English, Hindi or Tamil.

A dashboard built for officials is also meant to be used by residents, and the
resident most exposed to bad air is the least likely to read an English
interface. The guide explains each screen in the listener's language, and says
the same thing on screen as a transcript, so it works with the sound off, for
someone hard of hearing, and when the voice cannot be generated.

Speech is synthesised by Sarvam AI one paragraph at a time and stored, so each
paragraph is generated once for every listener after it. That also means the
guide keeps speaking if the key is later removed or Sarvam is down: only a
paragraph nobody has heard yet needs the upstream.

Nothing here claims a measurement. The scripts describe the interface, and their
wording lives in ``app/guides/scripts``, where it can be corrected without code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import (
    SARVAM_TTS_MODEL,
    VOICE_GUIDE_AUDIO_CODEC,
    VOICE_GUIDE_LANGUAGE_CODES,
    VOICE_GUIDE_MEDIA_TYPE,
    VOICE_GUIDE_PACE,
    VOICE_GUIDE_SAMPLE_RATE_HZ,
    VOICE_GUIDE_SPEAKERS,
    VOICE_GUIDE_VERSION_LENGTH,
)
from app.core.enums import GuideLanguage, GuideScreen
from app.core.exceptions import NotFoundError, UpstreamError
from app.core.logging import get_logger
from app.external.sarvam_client import SarvamSpeechClient
from app.guides.catalogue import GuideSection, script_for
from app.repositories import voice_guide_repository
from app.repositories.voice_guide_repository import ClipRow

logger = get_logger(__name__)

#: Credential the voice needs; the text needs none.
_CREDENTIAL = "sarvam_api_key"


@dataclass(frozen=True, slots=True)
class SectionView:
    """One paragraph as served: its words, and the version its audio is filed under."""

    index: int
    heading: str
    text: str
    audio_version: str


@dataclass(frozen=True, slots=True)
class GuideView:
    """The guide for one screen in one language."""

    screen: GuideScreen
    language: GuideLanguage
    title: str
    sections: tuple[SectionView, ...]
    voice_available: bool
    voice: str


@dataclass(frozen=True, slots=True)
class SectionAudio:
    """A paragraph's speech, with the version that identifies these exact words."""

    version: str
    media_type: str
    audio: bytes


@dataclass(frozen=True, slots=True)
class WarmOutcome:
    """What preparing every clip in advance did."""

    already_stored: int
    synthesised: int
    failed: int


def clip_key(language: GuideLanguage, speech: str) -> str:
    """A hash of everything that shapes a clip's sound.

    Any change -- a corrected word, another voice, a new model or pace -- gives a
    new key, so a stored clip can never be served for words it does not say.
    """
    material = "\n".join(
        (
            SARVAM_TTS_MODEL,
            VOICE_GUIDE_SPEAKERS[language.value],
            VOICE_GUIDE_LANGUAGE_CODES[language.value],
            str(VOICE_GUIDE_PACE),
            str(VOICE_GUIDE_SAMPLE_RATE_HZ),
            VOICE_GUIDE_AUDIO_CODEC,
            speech,
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _voice_label(language: GuideLanguage) -> str:
    speaker = VOICE_GUIDE_SPEAKERS[language.value].capitalize()
    return f"Sarvam AI {SARVAM_TTS_MODEL}, voice {speaker}"


def guide(settings: Settings, screen: GuideScreen, language: GuideLanguage) -> GuideView:
    """The transcript for a screen, and whether this deployment can voice it."""
    script = script_for(screen, language)
    return GuideView(
        screen=screen,
        language=language,
        title=script.title,
        sections=tuple(
            SectionView(
                index=index,
                heading=section.heading,
                text=section.text,
                audio_version=clip_key(language, section.speech)[:VOICE_GUIDE_VERSION_LENGTH],
            )
            for index, section in enumerate(script.sections)
        ),
        voice_available=settings.has(_CREDENTIAL),
        voice=_voice_label(language),
    )


def _section(screen: GuideScreen, language: GuideLanguage, index: int) -> GuideSection:
    sections = script_for(screen, language).sections
    if not 0 <= index < len(sections):
        raise NotFoundError("guide section", f"{screen.value}/{language.value}/{index}")
    return sections[index]


async def section_audio(
    session: Session,
    settings: Settings,
    screen: GuideScreen,
    language: GuideLanguage,
    index: int,
) -> SectionAudio:
    """One paragraph's speech, from storage or synthesised and stored now.

    Raises:
        NotFoundError: The screen has no paragraph at that index.
        MissingCredentialError: The clip was never generated and no Sarvam key is
            configured to generate it.
        UpstreamError: Sarvam failed.
    """
    section = _section(screen, language, index)
    key = clip_key(language, section.speech)
    audio = voice_guide_repository.clip_audio(session, key)
    if audio is None:
        async with SarvamSpeechClient(settings.require(_CREDENTIAL)) as client:
            audio = await _synthesise_and_store(session, client, language, key, section.speech)
        logger.info(
            "voice_guide.synthesised", screen=screen.value, language=language.value, index=index
        )
    return SectionAudio(
        version=key[:VOICE_GUIDE_VERSION_LENGTH],
        media_type=VOICE_GUIDE_MEDIA_TYPE,
        audio=audio,
    )


async def _synthesise_and_store(
    session: Session,
    client: SarvamSpeechClient,
    language: GuideLanguage,
    key: str,
    speech: str,
) -> bytes:
    audio = await client.synthesise(
        speech,
        language_code=VOICE_GUIDE_LANGUAGE_CODES[language.value],
        speaker=VOICE_GUIDE_SPEAKERS[language.value],
    )
    voice_guide_repository.store_clip(
        session,
        ClipRow(
            cache_key=key,
            language=language.value,
            model=SARVAM_TTS_MODEL,
            speaker=VOICE_GUIDE_SPEAKERS[language.value],
            audio=audio,
        ),
    )
    return audio


async def warm(session: Session, settings: Settings) -> WarmOutcome:
    """Generate every clip not yet stored, so no listener waits for synthesis.

    Run after a deploy. A paragraph that fails is counted and skipped rather than
    stopping the run: the rest are still worth having, and the failed one is
    simply generated on first listen instead.

    Raises:
        MissingCredentialError: Something needs generating and no key is set.
    """
    pending: list[tuple[GuideLanguage, str, str]] = []
    for language in GuideLanguage:
        for screen in GuideScreen:
            for section in script_for(screen, language).sections:
                pending.append((language, clip_key(language, section.speech), section.speech))

    stored = voice_guide_repository.cached_keys(session, [key for _, key, _ in pending])
    missing = [item for item in pending if item[1] not in stored]
    if not missing:
        return WarmOutcome(already_stored=len(pending), synthesised=0, failed=0)

    synthesised = failed = 0
    async with SarvamSpeechClient(settings.require(_CREDENTIAL)) as client:
        for language, key, speech in missing:
            try:
                await _synthesise_and_store(session, client, language, key, speech)
            except UpstreamError as error:
                failed += 1
                logger.warning(
                    "voice_guide.warm_failed", language=language.value, error=error.message
                )
            else:
                synthesised += 1
    logger.info("voice_guide.warmed", synthesised=synthesised, failed=failed)
    return WarmOutcome(already_stored=len(stored), synthesised=synthesised, failed=failed)
