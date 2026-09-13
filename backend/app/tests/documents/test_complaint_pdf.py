"""Tests for laying out the complaint report PDF.

The layout cannot be asserted pixel by pixel, so these check what would make the
document useless if it broke: it is a PDF, it survives long and non-Latin text a
resident may write, and its reference and pages are what the footer says.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from app.documents.complaint_pdf import ComplaintDocument, Row, Section, render

GENERATED = datetime(2026, 9, 13, 15, 10, tzinfo=UTC)


def _document(
    *, quote: str | None = "Smoke from the kiln after dark.", paragraphs: int = 1
) -> ComplaintDocument:
    return ComplaintDocument(
        reference="AW-P-000007",
        title="Complaint report",
        generated_at=GENERATED,
        generated_label="Generated 13 Sep 2026, 20:40 IST",
        sections=(
            Section(
                title="What you reported",
                rows=(Row("Concern", "Open burning of waste"), Row("Location", "10.94° N")),
                quote=quote,
            ),
            Section(
                title="What happens next",
                paragraphs=tuple(
                    "A long paragraph about next steps. " * 12 for _ in range(paragraphs)
                ),
                bullets=("Quote the reference.",),
            ),
        ),
        disclaimer="A citizen measurement, not a regulatory one.",
    )


def _page_count(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


class TestRender:
    def test_produces_a_pdf(self) -> None:
        pdf = render(_document())

        assert pdf.startswith(b"%PDF-")
        assert pdf.rstrip().endswith(b"%%EOF")

    def test_prints_a_tamil_and_hindi_description(self) -> None:
        # A resident in Coimbatore may write in Tamil. Without the fallback fonts
        # and shaping this raises, or prints empty boxes.
        pdf = render(_document(quote="குப்பை எரிப்பு every night — बहुत धुआँ"))

        assert pdf.startswith(b"%PDF-")
        assert b"NotoSansTamil" in pdf
        assert b"NotoSansDevanagari" in pdf

    def test_a_submission_without_a_description_still_renders(self) -> None:
        assert render(_document(quote=None)).startswith(b"%PDF-")

    def test_long_content_flows_onto_further_pages(self) -> None:
        assert _page_count(render(_document(paragraphs=1))) == 1
        assert _page_count(render(_document(paragraphs=30))) > 1

    def test_is_titled_with_its_reference(self) -> None:
        # The document title is what a mail client or file browser shows, so a
        # report forwarded as an attachment still identifies itself.
        assert b"AirWatch complaint report AW-P-000007" in render(_document())
