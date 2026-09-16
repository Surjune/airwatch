"""Persistence for English translations of residents' descriptions."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.repositories.models import DescriptionTranslation


@dataclass(frozen=True, slots=True)
class StoredTranslation:
    """A translation as stored."""

    language: str
    is_english: bool
    english: str
    model: str


def translation_for(session: Session, text_sha256: str) -> StoredTranslation | None:
    """The stored translation of the text with this hash, or None if it was never translated."""
    row = session.get(DescriptionTranslation, text_sha256)
    if row is None:
        return None
    return StoredTranslation(
        language=row.language, is_english=row.is_english, english=row.english, model=row.model
    )


def store_translation(
    session: Session,
    text_sha256: str,
    *,
    language: str,
    is_english: bool,
    english: str,
    model: str,
) -> StoredTranslation:
    """Store a translation. Two downloads racing to translate the same text keep the first."""
    statement = insert(DescriptionTranslation).values(
        text_sha256=text_sha256,
        language=language,
        is_english=is_english,
        english=english,
        model=model,
    )
    session.execute(statement.on_conflict_do_nothing(index_elements=["text_sha256"]))
    session.flush()
    stored = translation_for(session, text_sha256)
    if stored is None:  # pragma: no cover - just written in this transaction.
        raise LookupError(f"translation {text_sha256} was not stored")
    return stored
