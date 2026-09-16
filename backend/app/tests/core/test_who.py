"""Tests for the WHO guideline comparison."""

from __future__ import annotations

import pytest

from app.core.enums import Pollutant
from app.core.who import guideline_24h, multiple_of_guideline


def test_uses_the_2021_levels() -> None:
    assert guideline_24h(Pollutant.PM25) == 15.0
    assert guideline_24h(Pollutant.PM10) == 45.0


def test_co_is_compared_in_milligrams() -> None:
    # CO is stored in mg/m³, and WHO's 24-hour CO level is 4 mg/m³.
    assert multiple_of_guideline(Pollutant.CO, 2.0) == pytest.approx(0.5)


def test_a_day_at_the_guideline_is_a_multiple_of_one() -> None:
    assert multiple_of_guideline(Pollutant.PM25, 15.0) == pytest.approx(1.0)


def test_a_clean_day_is_below_one() -> None:
    assert multiple_of_guideline(Pollutant.PM10, 0.0) == 0.0


@pytest.mark.parametrize("pollutant", [Pollutant.O3, Pollutant.NH3])
def test_pollutants_without_a_24_hour_level_are_not_compared(pollutant: Pollutant) -> None:
    assert guideline_24h(pollutant) is None
    assert multiple_of_guideline(pollutant, 100.0) is None
