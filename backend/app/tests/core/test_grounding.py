"""Tests for checking generated text against the figures it was given."""

from __future__ import annotations

from app.core.grounding import figures, ungrounded_figures

FACTS = (
    "Location: Prashant Garden, Khora\n"
    "Pollutant: PM2.5\n"
    "Measured: 74 µg/m³\n"
    "Predicted from nearby monitors: 20 µg/m³\n"
    "First seen: 10 Sep 2026, 13:00 IST\n"
    "Likely source: Ghazipur landfill, 69% plausible"
)


def test_a_brief_restating_the_facts_is_grounded() -> None:
    brief = (
        "PM2.5 at Prashant Garden read 74 µg/m³ against 20 predicted, first seen "
        "10 Sep 2026, 13:00 IST. Ghazipur landfill is 69% plausible."
    )

    assert ungrounded_figures(brief, FACTS) == set()


def test_an_invented_figure_is_caught() -> None:
    brief = "PM2.5 read 74 µg/m³, about 3 times the prediction, within 5 km of the landfill."

    assert ungrounded_figures(brief, FACTS) == {"3", "5"}


def test_a_rounded_restatement_is_not_accepted_as_the_same_figure() -> None:
    # "74.0" was never written in the facts; a strict check discarding a good brief
    # costs nothing, a lenient one letting a wrong figure through costs trust.
    assert ungrounded_figures("It read 74.0 µg/m³.", FACTS) == {"74.0"}


def test_a_superscript_unit_is_not_a_figure() -> None:
    assert figures("µg/m³") == set()


def test_text_with_no_figures_is_grounded() -> None:
    assert ungrounded_figures("Inspect the landfill for surface fires.", FACTS) == set()
