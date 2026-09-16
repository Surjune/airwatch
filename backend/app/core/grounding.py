"""Checking that generated text states only figures it was given.

A language model asked to summarise an alert or translate a complaint will,
occasionally, add a number: a round percentage, a distance it assumed, a
concentration from its training data. In front of an official that is worse
than no text at all, so every figure in generated text must appear verbatim in
the facts the model was handed.

The check is deliberately literal. "74" is grounded if "74" was in the facts;
"74.0" or "seventy-four" are not accepted as the same figure, because a strict
check that occasionally discards a good summary costs nothing, while a lenient
one that lets a wrong figure through costs trust. The one equivalence allowed is
the script a digit is written in: Tamil and Hindi have their own numerals, and
a translation that writes ५० as 50 has kept the figure, not invented one.
"""

from __future__ import annotations

import re
import unicodedata

#: A figure: digits, optionally with one decimal part. Thousands separators are
#: not recognised, so "1,232" is read as the two figures "1" and "232" -- both of
#: which must then be present, which a verbatim "1,232" in the facts guarantees.
_FIGURE = re.compile(r"\d+(?:\.\d+)?")


def _ascii_digits(text: str) -> str:
    """The text with every decimal digit, in any script, written as an ASCII digit."""
    return "".join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in text)


def figures(text: str) -> set[str]:
    """Every figure written in a piece of text, in ASCII digits."""
    return set(_FIGURE.findall(_ascii_digits(text)))


def ungrounded_figures(generated: str, facts: str) -> set[str]:
    """Figures in generated text that do not appear in the facts it was given.

    An empty result means every number the text states can be traced to its
    input. Anything else means the text is not to be shown.
    """
    return figures(generated) - figures(facts)
