"""Checking that generated text states only figures it was given.

A language model asked to summarise an alert will, occasionally, add a number:
a round percentage, a distance it assumed, a concentration from its training
data. In front of an official that is worse than no summary, so every figure in
generated text must appear verbatim in the facts the model was handed.

The check is deliberately literal. "74" is grounded if "74" was in the facts;
"74.0" or "seventy-four" are not accepted as the same figure, because a strict
check that occasionally discards a good summary costs nothing, while a lenient
one that lets a wrong figure through costs trust.
"""

from __future__ import annotations

import re

#: A figure: digits, optionally with one decimal part. Thousands separators are
#: not recognised, so "1,232" is read as the two figures "1" and "232" -- both of
#: which must then be present, which a verbatim "1,232" in the facts guarantees.
_FIGURE = re.compile(r"\d+(?:\.\d+)?")


def figures(text: str) -> set[str]:
    """Every figure written in a piece of text."""
    return set(_FIGURE.findall(text))


def ungrounded_figures(generated: str, facts: str) -> set[str]:
    """Figures in generated text that do not appear in the facts it was given.

    An empty result means every number the text states can be traced to its
    input. Anything else means the text is not to be shown.
    """
    return figures(generated) - figures(facts)
