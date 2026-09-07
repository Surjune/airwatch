"""CPCB National AQI arithmetic — the single source of truth.

Nothing else in the codebase may re-derive a sub-index or a category. Import from
here.

The method (CPCB, 2014): compute a sub-index per pollutant by linear
interpolation within its breakpoint band, then report the maximum across
pollutants as the AQI, naming the pollutant that produced it.

Unit trap: every pollutant is in micrograms per cubic metre except CO, which is
in **milligrams** per cubic metre. Callers must convert at the ingestion boundary;
:func:`sub_index` cannot detect the mistake, because 5 mg/m^3 and 5 ug/m^3 are
both plausible-looking numbers.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from app.core.constants import (
    AQI_BREAKPOINTS_CO,
    AQI_BREAKPOINTS_NH3,
    AQI_BREAKPOINTS_NO2,
    AQI_BREAKPOINTS_O3,
    AQI_BREAKPOINTS_PM10,
    AQI_BREAKPOINTS_PM25,
    AQI_BREAKPOINTS_SO2,
    AQI_CATEGORY_BOUNDS,
    AQI_MAX,
    AQIBreakpoint,
)
from app.core.enums import Pollutant
from app.core.exceptions import UnsupportedPollutantError, ValidationError

#: Breakpoint table per pollutant.
BREAKPOINTS: Final[dict[Pollutant, tuple[AQIBreakpoint, ...]]] = {
    Pollutant.PM25: AQI_BREAKPOINTS_PM25,
    Pollutant.PM10: AQI_BREAKPOINTS_PM10,
    Pollutant.NO2: AQI_BREAKPOINTS_NO2,
    Pollutant.SO2: AQI_BREAKPOINTS_SO2,
    Pollutant.O3: AQI_BREAKPOINTS_O3,
    Pollutant.CO: AQI_BREAKPOINTS_CO,
    Pollutant.NH3: AQI_BREAKPOINTS_NH3,
}

#: Averaging period the CPCB method requires per pollutant, in hours. Applying a
#: breakpoint table to the wrong averaging period silently produces a wrong index.
AVERAGING_PERIOD_HOURS: Final[dict[Pollutant, int]] = {
    Pollutant.PM25: 24,
    Pollutant.PM10: 24,
    Pollutant.NO2: 24,
    Pollutant.SO2: 24,
    Pollutant.NH3: 24,
    Pollutant.O3: 8,
    Pollutant.CO: 8,
}

#: Measurement unit per pollutant, for display and for conversion checks.
CONCENTRATION_UNIT: Final[dict[Pollutant, str]] = {
    Pollutant.PM25: "ug/m3",
    Pollutant.PM10: "ug/m3",
    Pollutant.NO2: "ug/m3",
    Pollutant.SO2: "ug/m3",
    Pollutant.O3: "ug/m3",
    Pollutant.NH3: "ug/m3",
    Pollutant.CO: "mg/m3",
}


@dataclass(frozen=True, slots=True)
class AQIResult:
    """An AQI value together with the pollutant responsible for it.

    Attributes:
        value: The index, 0-500.
        dominant_pollutant: Pollutant whose sub-index was highest.
        category: CPCB category name for ``value``.
        sub_indices: Every sub-index that contributed, for transparency in the UI.
        clamped: True when at least one concentration exceeded the top breakpoint
            and was capped at :data:`AQI_MAX`. The reading is then a floor, not an
            estimate, and must be shown as such.
    """

    value: float
    dominant_pollutant: Pollutant
    category: str
    sub_indices: Mapping[Pollutant, float]
    clamped: bool


def sub_index(pollutant: Pollutant, concentration: float) -> float:
    """Compute the CPCB sub-index for one pollutant.

    Args:
        pollutant: Which pollutant the concentration is for.
        concentration: Concentration already averaged over
            :data:`AVERAGING_PERIOD_HOURS` for this pollutant, in the unit given
            by :data:`CONCENTRATION_UNIT` (mg/m^3 for CO, ug/m^3 for the rest).

    Returns:
        The sub-index, 0-500. Concentrations above the top breakpoint are clamped
        to :data:`AQI_MAX`, since the CPCB index is not defined beyond it.

    Raises:
        UnsupportedPollutantError: No breakpoint table exists for the pollutant.
        ValidationError: The concentration is negative or not finite.
    """
    table = BREAKPOINTS.get(pollutant)
    if table is None:
        raise UnsupportedPollutantError(
            f"No CPCB breakpoint table for pollutant {pollutant.value!r}."
        )

    if concentration != concentration:  # NaN is the only value unequal to itself.
        raise ValidationError(f"Concentration for {pollutant.value} is not a number.")
    if concentration < 0:
        raise ValidationError(
            f"Concentration for {pollutant.value} is negative ({concentration}).",
        )

    for conc_low, conc_high, index_low, index_high in table:
        if conc_low <= concentration <= conc_high:
            # Linear interpolation within the band.
            span = conc_high - conc_low
            if span == 0:
                return index_low
            fraction = (concentration - conc_low) / span
            return index_low + fraction * (index_high - index_low)

    # Above the highest breakpoint: the index saturates.
    return AQI_MAX


def is_clamped(pollutant: Pollutant, concentration: float) -> bool:
    """Whether a concentration exceeds the top breakpoint and is being capped."""
    table = BREAKPOINTS.get(pollutant)
    if table is None:
        raise UnsupportedPollutantError(
            f"No CPCB breakpoint table for pollutant {pollutant.value!r}."
        )
    highest_concentration = table[-1][1]
    return concentration > highest_concentration


def category(aqi_value: float) -> str:
    """Return the CPCB category name for an index value.

    Args:
        aqi_value: An AQI, 0-500.

    Raises:
        ValidationError: The value is negative.
    """
    if aqi_value < 0:
        raise ValidationError(f"AQI cannot be negative ({aqi_value}).")

    name = AQI_CATEGORY_BOUNDS[0][1]
    for lower_bound, category_name in AQI_CATEGORY_BOUNDS:
        if aqi_value >= lower_bound:
            name = category_name
        else:
            break
    return name


def overall_aqi(concentrations: Mapping[Pollutant, float]) -> AQIResult:
    """Compute the overall AQI from per-pollutant concentrations.

    Args:
        concentrations: Concentrations already averaged over each pollutant's
            required period, in that pollutant's unit.

    Returns:
        The maximum sub-index, the pollutant responsible, and every contributing
        sub-index.

    Raises:
        ValidationError: No concentrations were supplied. An AQI computed from
            nothing would be indistinguishable from a genuine "Good" reading.
    """
    if not concentrations:
        raise ValidationError("Cannot compute an AQI with no pollutant concentrations.")

    sub_indices = {
        pollutant: sub_index(pollutant, value) for pollutant, value in concentrations.items()
    }
    dominant = max(sub_indices, key=lambda pollutant: sub_indices[pollutant])
    value = sub_indices[dominant]
    clamped = any(
        is_clamped(pollutant, concentration) for pollutant, concentration in concentrations.items()
    )

    return AQIResult(
        value=value,
        dominant_pollutant=dominant,
        category=category(value),
        sub_indices=sub_indices,
        clamped=clamped,
    )
