"""Whether a stored concentration could be real ambient air.

A reading outside physical bounds is stored and flagged, never deleted and never
corrected. Deleting would hide that an upstream is broken; correcting would mean
guessing what the instrument meant, which is fabricating a number. Flagged rows
are excluded from every published estimate by the repository queries.
"""

from __future__ import annotations

from app.core.constants import PLAUSIBLE_CONCENTRATION_RANGE
from app.core.enums import Pollutant


def plausible_range(pollutant: Pollutant) -> tuple[float, float]:
    """The inclusive range a concentration must fall in, in its AQI unit.

    Raises:
        KeyError: The pollutant has no defined range. Every enumerated pollutant
            has one, so this indicates a new pollutant added without its bounds.
    """
    return PLAUSIBLE_CONCENTRATION_RANGE[pollutant.value]


def is_plausible(pollutant: Pollutant, value: float) -> bool:
    """True when ``value``, in the pollutant's AQI unit, could be ambient air."""
    low, high = plausible_range(pollutant)
    return low <= value <= high
