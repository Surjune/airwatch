"""WHO's 2021 air quality guideline levels, and how far a reading is from them.

The CPCB index says how the air compares with India's own standards. WHO's
guideline levels are much stricter -- a PM2.5 day CPCB calls "Satisfactory" can
be four times WHO's level -- and residents meet them in the news, so the
comparison is stated beside the index rather than in place of it.

A 24-hour guideline is compared only with a 24-hour average. Set against an
hourly reading it would overstate every evening peak and understate every
afternoon lull.
"""

from __future__ import annotations

from typing import Final

from app.core.constants import (
    WHO_GUIDELINE_24H_CO,
    WHO_GUIDELINE_24H_NO2,
    WHO_GUIDELINE_24H_PM10,
    WHO_GUIDELINE_24H_PM25,
    WHO_GUIDELINE_24H_SO2,
)
from app.core.enums import Pollutant

#: WHO's 24-hour guideline level per pollutant, in the pollutant's storage unit.
#: Ozone has only an 8-hour level and ammonia none, so neither is listed.
GUIDELINE_24H: Final[dict[Pollutant, float]] = {
    Pollutant.PM25: WHO_GUIDELINE_24H_PM25,
    Pollutant.PM10: WHO_GUIDELINE_24H_PM10,
    Pollutant.NO2: WHO_GUIDELINE_24H_NO2,
    Pollutant.SO2: WHO_GUIDELINE_24H_SO2,
    Pollutant.CO: WHO_GUIDELINE_24H_CO,
}


def guideline_24h(pollutant: Pollutant) -> float | None:
    """WHO's guideline level for a 24-hour average, or None where WHO sets none."""
    return GUIDELINE_24H.get(pollutant)


def multiple_of_guideline(pollutant: Pollutant, daily_mean: float) -> float | None:
    """A 24-hour average as a multiple of WHO's 24-hour guideline level.

    None for a pollutant WHO sets no 24-hour level for. Below 1 means the day's
    average was within the guideline.
    """
    guideline = guideline_24h(pollutant)
    return None if guideline is None else daily_mean / guideline
