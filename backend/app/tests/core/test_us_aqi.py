"""Tests for turning a US AQI figure back into a concentration."""

from __future__ import annotations

import pytest

from app.core.constants import US_AQI_BREAKPOINTS_PM25_2012, US_AQI_BREAKPOINTS_PM25_2024
from app.core.enums import Pollutant
from app.core.us_aqi import concentration


@pytest.mark.parametrize(
    ("index", "expected"),
    [(0, 0.0), (50, 12.0), (51, 12.1), (100, 35.4), (101, 35.5), (150, 55.4), (500, 500.4)],
)
def test_reads_the_2012_pm25_table_at_its_breakpoints(index: float, expected: float) -> None:
    value = concentration(Pollutant.PM25, index, US_AQI_BREAKPOINTS_PM25_2012)

    assert value == pytest.approx(expected)


@pytest.mark.parametrize(
    ("index", "expected"),
    [(50, 9.0), (51, 9.1), (100, 35.4), (200, 125.4), (500, 325.4)],
)
def test_reads_the_2024_pm25_table_at_its_breakpoints(index: float, expected: float) -> None:
    value = concentration(Pollutant.PM25, index, US_AQI_BREAKPOINTS_PM25_2024)

    assert value == pytest.approx(expected)


def test_the_two_tables_agree_where_they_share_a_band() -> None:
    # 101-150 is 35.5-55.4 ug/m3 in both, which is why that band cannot tell them apart.
    old = concentration(Pollutant.PM25, 132, US_AQI_BREAKPOINTS_PM25_2012)
    new = concentration(Pollutant.PM25, 132, US_AQI_BREAKPOINTS_PM25_2024)

    assert old == pytest.approx(new)
    assert old == pytest.approx(35.5 + 31 * 19.9 / 49)


def test_interpolates_inside_a_band() -> None:
    # Halfway through 51-100 on the 2012 table is halfway through 12.1-35.4.
    value = concentration(Pollutant.PM25, 75.5, US_AQI_BREAKPOINTS_PM25_2012)

    assert value == pytest.approx((12.1 + 35.4) / 2)


def test_an_index_between_whole_number_bands_takes_the_upper_floor() -> None:
    assert concentration(Pollutant.PM25, 50.5, US_AQI_BREAKPOINTS_PM25_2012) == pytest.approx(12.1)


def test_reads_pm10_with_its_own_table() -> None:
    assert concentration(Pollutant.PM10, 100) == pytest.approx(154.0)
    assert concentration(Pollutant.PM10, 51) == pytest.approx(55.0)


@pytest.mark.parametrize("index", [-1, 501, 999])
def test_an_index_off_the_table_has_no_concentration(index: float) -> None:
    assert concentration(Pollutant.PM25, index) is None
    assert concentration(Pollutant.PM10, index) is None


def test_a_gas_is_not_converted() -> None:
    # The US AQI quotes gases in parts per billion at its own reference conditions.
    assert concentration(Pollutant.NO2, 40) is None
