"""Tests for the CPCB AQI arithmetic, exercised at its edges."""

from __future__ import annotations

import math

import pytest

from app.core import aqi
from app.core.constants import AQI_MAX
from app.core.enums import Pollutant
from app.core.exceptions import ValidationError


class TestSubIndex:
    @pytest.mark.parametrize(
        ("concentration", "expected"),
        [
            (0.0, 0.0),  # bottom of the scale
            (30.0, 50.0),  # exact breakpoint, Good/Satisfactory boundary
            (60.0, 100.0),  # Satisfactory/Moderate boundary
            (90.0, 200.0),
            (120.0, 300.0),
            (250.0, 400.0),  # first matching band wins at a shared edge
            (500.0, 500.0),  # top of the scale
        ],
    )
    def test_pm25_breakpoint_edges(self, concentration: float, expected: float) -> None:
        assert aqi.sub_index(Pollutant.PM25, concentration) == pytest.approx(expected)

    def test_interpolates_linearly_within_a_band(self) -> None:
        # 45 ug/m3 sits halfway through the 30-60 band, which maps to 51-100.
        assert aqi.sub_index(Pollutant.PM25, 45.0) == pytest.approx(75.5)

    def test_saturates_above_the_top_breakpoint(self) -> None:
        # The CPCB index is not defined past 500 ug/m3 of PM2.5.
        assert aqi.sub_index(Pollutant.PM25, 900.0) == AQI_MAX

    def test_co_uses_its_own_milligram_scale(self) -> None:
        # 1.0 mg/m3 is the Good/Satisfactory boundary for CO. The same numeric
        # value read as PM2.5 would be near zero, which is why the unit is
        # carried explicitly rather than inferred.
        assert aqi.sub_index(Pollutant.CO, 1.0) == pytest.approx(50.0)
        assert aqi.sub_index(Pollutant.PM25, 1.0) < 5.0

    def test_rejects_negative_concentration(self) -> None:
        with pytest.raises(ValidationError, match="negative"):
            aqi.sub_index(Pollutant.PM25, -1.0)

    def test_rejects_nan(self) -> None:
        with pytest.raises(ValidationError, match="not a number"):
            aqi.sub_index(Pollutant.PM25, math.nan)


class TestIsClamped:
    def test_false_within_range(self) -> None:
        assert aqi.is_clamped(Pollutant.PM25, 250.0) is False

    def test_true_above_top_breakpoint(self) -> None:
        assert aqi.is_clamped(Pollutant.PM25, 501.0) is True


class TestCategory:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0.0, "Good"),
            (50.0, "Good"),
            (51.0, "Satisfactory"),
            (100.0, "Satisfactory"),
            (101.0, "Moderate"),
            (200.0, "Moderate"),
            (201.0, "Poor"),
            (300.0, "Poor"),
            (301.0, "Very Poor"),
            (400.0, "Very Poor"),
            (401.0, "Severe"),
            (500.0, "Severe"),
        ],
    )
    def test_boundaries(self, value: float, expected: str) -> None:
        assert aqi.category(value) == expected

    def test_rejects_negative(self) -> None:
        with pytest.raises(ValidationError):
            aqi.category(-1.0)


class TestOverallAQI:
    def test_reports_the_maximum_sub_index_and_names_it(self) -> None:
        result = aqi.overall_aqi(
            {
                Pollutant.PM25: 45.0,  # -> 75.5
                Pollutant.NO2: 20.0,  # -> 25.0
            }
        )
        assert result.dominant_pollutant is Pollutant.PM25
        assert result.value == pytest.approx(75.5)
        assert result.category == "Satisfactory"
        assert set(result.sub_indices) == {Pollutant.PM25, Pollutant.NO2}
        assert result.clamped is False

    def test_a_secondary_pollutant_can_dominate(self) -> None:
        # Clean particulates, severe ozone: the index must follow the ozone.
        result = aqi.overall_aqi(
            {
                Pollutant.PM25: 10.0,
                Pollutant.O3: 300.0,
            }
        )
        assert result.dominant_pollutant is Pollutant.O3

    def test_flags_clamping_so_the_ui_can_show_a_floor_not_an_estimate(self) -> None:
        result = aqi.overall_aqi({Pollutant.PM25: 900.0})
        assert result.value == AQI_MAX
        assert result.clamped is True

    def test_minimum_risk(self) -> None:
        result = aqi.overall_aqi({Pollutant.PM25: 0.0})
        assert result.value == 0.0
        assert result.category == "Good"

    def test_refuses_to_invent_an_index_from_no_data(self) -> None:
        # An AQI computed from nothing would be indistinguishable from a genuine
        # "Good" reading, which is exactly the failure mode this project exists
        # to remove.
        with pytest.raises(ValidationError, match="no pollutant concentrations"):
            aqi.overall_aqi({})


class TestUnitConversion:
    """The CO trap: OpenAQ sends ug/m3, the CPCB CO table is in mg/m3."""

    def test_converts_co_micrograms_to_milligrams(self) -> None:
        assert aqi.to_aqi_unit(Pollutant.CO, 1200.0, "ug/m3") == pytest.approx(1.2)

    def test_leaves_a_value_already_in_the_target_unit_alone(self) -> None:
        assert aqi.to_aqi_unit(Pollutant.CO, 1.2, "mg/m3") == pytest.approx(1.2)
        assert aqi.to_aqi_unit(Pollutant.PM25, 45.0, "ug/m3") == pytest.approx(45.0)

    def test_converts_milligrams_up_for_a_microgram_pollutant(self) -> None:
        assert aqi.to_aqi_unit(Pollutant.PM25, 0.045, "mg/m3") == pytest.approx(45.0)

    def test_skipping_the_conversion_would_fabricate_a_severe_reading(self) -> None:
        # 1200 ug/m3 of CO is an ordinary 1.2 mg/m3. Fed to the table raw it
        # saturates the index, inventing an emergency out of a normal day.
        raw = aqi.sub_index(Pollutant.CO, 1200.0)
        converted = aqi.sub_index(Pollutant.CO, aqi.to_aqi_unit(Pollutant.CO, 1200.0, "ug/m3"))
        assert raw == AQI_MAX
        assert converted < 100.0

    def test_rejects_an_unknown_unit(self) -> None:
        with pytest.raises(ValidationError, match="Cannot convert"):
            aqi.to_aqi_unit(Pollutant.PM25, 1.0, "ppb")
