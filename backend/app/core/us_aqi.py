"""Turning a US AQI figure back into a concentration.

The World Air Quality Index Project reports every pollutant on the US EPA scale,
whatever the source published. AirWatch stores concentrations, so a WAQI figure
is mapped back through the same piecewise-linear table it was produced with.

The inversion is exact up to rounding: WAQI publishes whole index points, so a
PM2.5 figure carries up to half a point of error -- about 0.25 ug/m^3 in the
51-100 band and under 1 ug/m^3 in the highest. An index above the top of the
table has no defined concentration and returns None rather than an
extrapolation.
"""

from __future__ import annotations

from typing import Final

from app.core.constants import (
    US_AQI_BREAKPOINTS_PM10,
    WAQI_PM25_BREAKPOINTS,
    AQIBreakpoint,
)
from app.core.enums import Pollutant

#: The table each supported pollutant is read with.
TABLES: Final[dict[Pollutant, tuple[AQIBreakpoint, ...]]] = {
    Pollutant.PM25: WAQI_PM25_BREAKPOINTS,
    Pollutant.PM10: US_AQI_BREAKPOINTS_PM10,
}


def concentration(
    pollutant: Pollutant,
    index: float,
    table: tuple[AQIBreakpoint, ...] | None = None,
) -> float | None:
    """The concentration, in ug/m^3, a US AQI figure stands for.

    Args:
        pollutant: PM2.5 or PM10.
        index: The US AQI figure.
        table: The breakpoints to read with; the pollutant's own by default.

    Returns:
        The concentration, or None for a pollutant with no table, a negative
        index, or one above the table's top.
    """
    bands = table if table is not None else TABLES.get(pollutant)
    if bands is None or index < 0:
        return None
    for conc_low, conc_high, index_low, index_high in bands:
        if index <= index_high:
            # Whole-number tables leave gaps between bands (50 to 51); an index
            # in one belongs to the band above, at its floor.
            position = max(index, index_low) - index_low
            return conc_low + position * (conc_high - conc_low) / (index_high - index_low)
    return None
