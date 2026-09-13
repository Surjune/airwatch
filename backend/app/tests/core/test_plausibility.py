"""Tests for the physical plausibility bounds on stored concentrations."""

from __future__ import annotations

import pytest

from app.core import aqi
from app.core.enums import Pollutant
from app.core.plausibility import is_plausible, plausible_range


@pytest.mark.parametrize("pollutant", list(Pollutant))
def test_every_pollutant_has_bounds(pollutant: Pollutant) -> None:
    low, high = plausible_range(pollutant)
    assert 0.0 <= low < high


@pytest.mark.parametrize("pollutant", list(Pollutant))
def test_bounds_are_inclusive(pollutant: Pollutant) -> None:
    low, high = plausible_range(pollutant)
    assert is_plausible(pollutant, low)
    assert is_plausible(pollutant, high)


def test_a_severe_delhi_hour_is_never_filtered() -> None:
    # Filtering what is unhealthy rather than what is impossible would erase
    # exactly the episodes the system exists to find.
    assert is_plausible(Pollutant.PM25, 700.0)
    assert is_plausible(Pollutant.PM10, 1400.0)


def test_negative_concentrations_are_flagged() -> None:
    assert not is_plausible(Pollutant.PM25, -3.0)
    assert not is_plausible(Pollutant.NO2, -0.1)


def test_saturated_readings_are_flagged() -> None:
    assert not is_plausible(Pollutant.PM25, 99999.0)


def test_carbon_monoxide_reported_in_ppm_but_labelled_ppb_is_flagged() -> None:
    # The failure seen on live Delhi stations: 1.2 is a normal urban CO level in
    # ppm, but the upstream declares ppb, so conversion yields a value a
    # thousand times too small to be air.
    mislabelled = aqi.to_aqi_unit(Pollutant.CO, 1.2, "ppb")
    correctly_labelled = aqi.to_aqi_unit(Pollutant.CO, 1.2, "ppm")

    assert not is_plausible(Pollutant.CO, mislabelled)
    assert is_plausible(Pollutant.CO, correctly_labelled)
