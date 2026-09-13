"""Persistence for synthesised voice-guide clips."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.repositories.models import VoiceGuideClip


@dataclass(frozen=True, slots=True)
class ClipRow:
    """A clip ready to store."""

    cache_key: str
    language: str
    model: str
    speaker: str
    audio: bytes


def clip_audio(session: Session, cache_key: str) -> bytes | None:
    """The stored audio for a key, or None when it has not been synthesised."""
    return session.scalar(select(VoiceGuideClip.audio).where(VoiceGuideClip.cache_key == cache_key))


def cached_keys(session: Session, cache_keys: list[str]) -> set[str]:
    """Which of the given keys already have a clip."""
    if not cache_keys:
        return set()
    rows = session.scalars(
        select(VoiceGuideClip.cache_key).where(VoiceGuideClip.cache_key.in_(cache_keys))
    )
    return set(rows)


def store_clip(session: Session, row: ClipRow) -> None:
    """Store a clip. Two listeners racing to the same new clip store it once."""
    statement = insert(VoiceGuideClip).values(
        cache_key=row.cache_key,
        language=row.language,
        model=row.model,
        speaker=row.speaker,
        audio=row.audio,
    )
    session.execute(statement.on_conflict_do_nothing(index_elements=["cache_key"]))
    session.flush()
