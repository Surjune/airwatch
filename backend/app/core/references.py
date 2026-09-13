"""Human-readable references for citizen submissions.

A resident quotes a reference to a helpline or pastes it into a grievance form,
so it has to survive being read aloud: a fixed prefix, one letter for the tier,
and a zero-padded number -- ``AW-P-000123`` for a photograph, ``AW-S-000045`` for
a sensor reading. The number is the row id, which is not a secret: the report it
names can only be downloaded by the device that submitted it.
"""

from __future__ import annotations

import re

from app.core.constants import COMPLAINT_REFERENCE_DIGITS, COMPLAINT_REFERENCE_PREFIX
from app.core.enums import SubmissionKind
from app.core.exceptions import ValidationError

_KIND_LETTERS: dict[SubmissionKind, str] = {
    SubmissionKind.PHOTO: "P",
    SubmissionKind.SENSOR: "S",
}

_PATTERN = re.compile(rf"^{COMPLAINT_REFERENCE_PREFIX}-([PS])-(\d+)$")


def clean_description(text: str | None) -> str | None:
    """A resident's description, trimmed, with whitespace runs collapsed.

    Blank means nothing was said, so it is stored as none rather than as an empty
    string a report would print as a quoted blank.
    """
    if text is None:
        return None
    collapsed = " ".join(text.split())
    return collapsed or None


def format_reference(kind: SubmissionKind, submission_id: int) -> str:
    """The reference a resident is given for a submission."""
    letter = _KIND_LETTERS[kind]
    return f"{COMPLAINT_REFERENCE_PREFIX}-{letter}-{submission_id:0{COMPLAINT_REFERENCE_DIGITS}d}"


def parse_reference(reference: str) -> tuple[SubmissionKind, int]:
    """Split a reference back into its tier and id.

    Case and surrounding space are forgiven, because references get retyped by
    hand; anything else malformed is refused rather than guessed at.

    Raises:
        ValidationError: The text is not an AirWatch submission reference.
    """
    match = _PATTERN.match(reference.strip().upper())
    if match is None:
        raise ValidationError(f"{reference!r} is not an AirWatch submission reference.")
    letter, digits = match.groups()
    kind = next(kind for kind, value in _KIND_LETTERS.items() if value == letter)
    return kind, int(digits)
