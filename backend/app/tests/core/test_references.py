"""Tests for citizen submission references."""

from __future__ import annotations

import pytest

from app.core.enums import SubmissionKind
from app.core.exceptions import ValidationError
from app.core.references import clean_description, format_reference, parse_reference


class TestCleanDescription:
    def test_trims_and_collapses_whitespace(self) -> None:
        assert clean_description("  smoke \n\n from   the kiln ") == "smoke from the kiln"

    def test_blank_is_nothing_said(self) -> None:
        assert clean_description("   ") is None
        assert clean_description(None) is None

    def test_keeps_non_latin_text_intact(self) -> None:
        assert clean_description(" குப்பை எரிப்பு ") == "குப்பை எரிப்பு"


class TestFormat:
    def test_a_photograph(self) -> None:
        assert format_reference(SubmissionKind.PHOTO, 123) == "AW-P-000123"

    def test_a_sensor_reading(self) -> None:
        assert format_reference(SubmissionKind.SENSOR, 45) == "AW-S-000045"

    def test_ids_beyond_the_padding_are_not_truncated(self) -> None:
        assert format_reference(SubmissionKind.PHOTO, 1_234_567) == "AW-P-1234567"


class TestParse:
    @pytest.mark.parametrize(
        ("kind", "submission_id"),
        [(SubmissionKind.PHOTO, 1), (SubmissionKind.SENSOR, 999_999)],
    )
    def test_round_trips(self, kind: SubmissionKind, submission_id: int) -> None:
        assert parse_reference(format_reference(kind, submission_id)) == (kind, submission_id)

    def test_forgives_case_and_spaces_from_retyping(self) -> None:
        assert parse_reference("  aw-s-000012 ") == (SubmissionKind.SENSOR, 12)

    @pytest.mark.parametrize("text", ["", "AW-X-000001", "AW-P-", "XX-P-000001", "AW-P-12a"])
    def test_refuses_anything_else(self, text: str) -> None:
        with pytest.raises(ValidationError):
            parse_reference(text)
