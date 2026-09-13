"""The PDF a resident downloads for a complaint they submitted.

Layout only. Every sentence on the page is prepared by ``complaint_service``,
which knows what can honestly be said about a submission; this module decides
where it goes and how it looks, and imports nothing above ``core``.

The document is built to be attached to an official grievance: a reference on
every page, dates in IST, the responsible bodies named, and a plain statement of
what a citizen measurement can and cannot establish. Fonts are embedded Noto,
with Tamil and Devanagari as fallbacks and text shaping on, because a
description written in Tamil must print as Tamil, not as empty boxes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import XPos, YPos

#: Embedded fonts, SIL Open Font Licence (see fonts/OFL.txt).
FONT_DIR = Path(__file__).parent / "fonts"

#: A4 page margins, in millimetres.
_MARGIN_MM = 18
#: Width of the label column in a key-value row, in millimetres.
_LABEL_COLUMN_MM = 48
#: Line height for body text, in millimetres.
_LINE_MM = 4.9

#: Ink, muted ink and hairline colours, matching the web interface's tokens.
_INK = (28, 27, 23)
_MUTED = (87, 84, 74)
_SUBTLE = (138, 133, 119)
_RULE = (220, 214, 200)
_PAPER = (244, 241, 234)
_SIGNAL = (194, 74, 28)

#: The six CPCB band colours, drawn as the rule under the masthead, as on screen.
_BAND_COLOURS = (
    (59, 162, 114),
    (139, 195, 74),
    (226, 185, 59),
    (224, 123, 57),
    (209, 73, 91),
    (139, 38, 53),
)


@dataclass(frozen=True, slots=True)
class Row:
    """One labelled line in a section."""

    label: str
    value: str


@dataclass(frozen=True, slots=True)
class Section:
    """A numbered section: optional rows, then paragraphs."""

    title: str
    rows: tuple[Row, ...] = ()
    paragraphs: tuple[str, ...] = ()
    bullets: tuple[str, ...] = ()
    #: Set in the resident's own words, visually quoted.
    quote: str | None = None


@dataclass(frozen=True, slots=True)
class ComplaintDocument:
    """Everything the page shows, already worded."""

    reference: str
    title: str
    generated_at: datetime
    generated_label: str
    sections: tuple[Section, ...]
    disclaimer: str


class _Page(FPDF):
    """An A4 page with the AirWatch masthead and a reference in the footer."""

    def __init__(self, reference: str) -> None:
        super().__init__(format="A4")
        self._reference = reference
        self.set_margins(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM)
        self.set_auto_page_break(auto=True, margin=_MARGIN_MM + 4)
        for family, stem in (
            ("Noto", "NotoSans"),
            ("NotoTamil", "NotoSansTamil"),
            ("NotoDevanagari", "NotoSansDevanagari"),
        ):
            self.add_font(family, "", str(FONT_DIR / f"{stem}-Regular.ttf"))
            self.add_font(family, "B", str(FONT_DIR / f"{stem}-Bold.ttf"))
        self.set_fallback_fonts(["NotoTamil", "NotoDevanagari"])
        self.set_text_shaping(True)

    def header(self) -> None:
        self.set_font("Noto", "B", 15)
        self.set_text_color(*_INK)
        self.cell(0, 8, "AirWatch", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.set_font("Noto", "", 8.5)
        self.set_text_color(*_SUBTLE)
        self.cell(0, 8, "Citizen air-quality complaint report", align="R")
        self.ln(10)
        band_width = (self.w - 2 * _MARGIN_MM) / len(_BAND_COLOURS)
        for index, colour in enumerate(_BAND_COLOURS):
            self.set_fill_color(*colour)
            self.rect(_MARGIN_MM + index * band_width, self.get_y(), band_width, 1.2, style="F")
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-_MARGIN_MM + 2)
        self.set_draw_color(*_RULE)
        self.line(_MARGIN_MM, self.get_y() - 2, self.w - _MARGIN_MM, self.get_y() - 2)
        self.set_font("Noto", "", 7.5)
        self.set_text_color(*_SUBTLE)
        self.cell(0, 5, f"Reference {self._reference}", new_x=XPos.LMARGIN, new_y=YPos.TOP)
        self.cell(0, 5, f"Page {self.page_no()} of {{nb}}", align="R")


def _section(pdf: _Page, number: int, section: Section) -> None:
    pdf.ln(1.5)
    pdf.set_draw_color(*_INK)
    pdf.line(_MARGIN_MM, pdf.get_y(), pdf.w - _MARGIN_MM, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Noto", "", 9)
    pdf.set_text_color(*_SIGNAL)
    pdf.cell(9, 6, f"{number:02d}")
    pdf.set_font("Noto", "B", 12)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 6, section.title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)

    value_width = pdf.w - 2 * _MARGIN_MM - _LABEL_COLUMN_MM
    for row in section.rows:
        top = pdf.get_y()
        pdf.set_font("Noto", "", 9)
        pdf.set_text_color(*_MUTED)
        pdf.multi_cell(_LABEL_COLUMN_MM, _LINE_MM, row.label, new_x=XPos.RIGHT, new_y=YPos.TOP)
        pdf.set_font("Noto", "", 10)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(value_width, _LINE_MM, row.value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_y(max(pdf.get_y(), top + _LINE_MM) + 0.6)

    if section.quote:
        pdf.ln(1)
        top = pdf.get_y()
        pdf.set_x(_MARGIN_MM + 4)
        pdf.set_font("Noto", "", 10.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, _LINE_MM + 0.6, section.quote, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_draw_color(*_SIGNAL)
        pdf.set_line_width(0.6)
        pdf.line(_MARGIN_MM + 1, top, _MARGIN_MM + 1, pdf.get_y())
        pdf.set_line_width(0.2)
        pdf.ln(1.5)

    for paragraph in section.paragraphs:
        pdf.set_font("Noto", "", 9.5)
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, _LINE_MM, paragraph, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(1)

    for bullet in section.bullets:
        pdf.set_font("Noto", "", 9.5)
        pdf.set_text_color(*_SIGNAL)
        pdf.cell(5, _LINE_MM, "•")
        pdf.set_text_color(*_INK)
        pdf.multi_cell(0, _LINE_MM, bullet, align="L", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(0.6)


def render(document: ComplaintDocument) -> bytes:
    """Lay the document out on A4 and return the PDF bytes."""
    pdf = _Page(document.reference)
    pdf.alias_nb_pages()
    pdf.set_title(f"AirWatch complaint report {document.reference}")
    pdf.set_author("AirWatch")
    pdf.set_creation_date(document.generated_at)
    pdf.add_page()

    pdf.set_font("Noto", "B", 20)
    pdf.set_text_color(*_INK)
    pdf.cell(0, 10, document.title, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Noto", "B", 13)
    pdf.set_text_color(*_SIGNAL)
    pdf.cell(0, 7, document.reference, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(*_SUBTLE)
    pdf.cell(0, 5, document.generated_label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    for number, section in enumerate(document.sections, start=1):
        _section(pdf, number, section)

    pdf.ln(2)
    pdf.set_fill_color(*_PAPER)
    pdf.set_draw_color(*_RULE)
    pdf.set_font("Noto", "", 8.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(
        0,
        4.6,
        document.disclaimer,
        align="L",
        border=1,
        fill=True,
        padding=3,
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )

    return bytes(pdf.output())
