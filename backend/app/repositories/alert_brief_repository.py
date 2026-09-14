"""Persistence for Gemini-written alert briefs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.repositories.models import AlertBrief


@dataclass(frozen=True, slots=True)
class StoredBrief:
    """A brief as stored."""

    alert_id: int
    summary: str
    suggested_action: str
    model: str
    created_at: datetime


def brief_for(session: Session, alert_id: int) -> StoredBrief | None:
    """The stored brief for an alert, or None if none has been written."""
    brief = session.get(AlertBrief, alert_id)
    if brief is None:
        return None
    return StoredBrief(
        alert_id=brief.alert_id,
        summary=brief.summary,
        suggested_action=brief.suggested_action,
        model=brief.model,
        created_at=brief.created_at,
    )


def store_brief(
    session: Session, *, alert_id: int, summary: str, suggested_action: str, model: str
) -> StoredBrief:
    """Store a brief. Two readers racing to the same new brief keep the first."""
    statement = insert(AlertBrief).values(
        alert_id=alert_id, summary=summary, suggested_action=suggested_action, model=model
    )
    session.execute(statement.on_conflict_do_nothing(index_elements=["alert_id"]))
    session.flush()
    stored = brief_for(session, alert_id)
    if stored is None:  # pragma: no cover - just written in this transaction.
        raise LookupError(f"brief for alert {alert_id} was not stored")
    return stored
