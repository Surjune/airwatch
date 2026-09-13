"""Tests for summarising household sensors against reference monitors.

The property that matters is that a small sample never presents as a finding: the
statistics are computed and shown, but ``is_established`` stays false until there
are enough pairs to separate a bias from one humid morning.
"""

from __future__ import annotations

import pytest

from app.core.constants import CITIZEN_SENSOR_BIAS_MIN_PAIRS
from app.ml.sensor_colocation import ColocatedPair, relative_difference, summarise


class TestRelativeDifference:
    def test_a_high_reading_is_positive(self) -> None:
        assert relative_difference(150.0, 100.0) == pytest.approx(0.5)

    def test_a_low_reading_is_negative(self) -> None:
        assert relative_difference(80.0, 100.0) == pytest.approx(-0.2)

    def test_a_zero_reference_has_no_ratio(self) -> None:
        # Clean air after rain reads near zero. A ratio against it is undefined,
        # and a huge number would read as a sensor wildly over-reading.
        assert relative_difference(5.0, 0.0) is None


class TestSummarise:
    def test_no_pairs_says_nothing(self) -> None:
        summary = summarise([])

        assert summary.pairs == 0
        assert summary.median_ratio is None
        assert summary.median_difference is None
        assert summary.is_established is False
        assert summary.pairs_needed == CITIZEN_SENSOR_BIAS_MIN_PAIRS

    def test_uses_medians_so_one_kitchen_sensor_cannot_move_the_bias(self) -> None:
        pairs = [ColocatedPair(sensor_value=130.0, reference_value=100.0) for _ in range(4)]
        pairs.append(ColocatedPair(sensor_value=900.0, reference_value=100.0))

        summary = summarise(pairs)

        assert summary.median_ratio == pytest.approx(1.3)
        assert summary.median_difference == pytest.approx(30.0)

    def test_is_not_established_below_the_minimum(self) -> None:
        pairs = [ColocatedPair(120.0, 100.0)] * (CITIZEN_SENSOR_BIAS_MIN_PAIRS - 1)

        assert summarise(pairs).is_established is False

    def test_is_established_at_the_minimum(self) -> None:
        pairs = [ColocatedPair(120.0, 100.0)] * CITIZEN_SENSOR_BIAS_MIN_PAIRS

        assert summarise(pairs).is_established is True

    def test_zero_references_count_towards_the_difference_only(self) -> None:
        summary = summarise([ColocatedPair(4.0, 0.0), ColocatedPair(60.0, 50.0)])

        assert summary.median_ratio == pytest.approx(1.2)
        assert summary.median_difference == pytest.approx(7.0)

    def test_all_zero_references_leave_the_ratio_unknown(self) -> None:
        summary = summarise([ColocatedPair(4.0, 0.0)])

        assert summary.median_ratio is None
        assert summary.median_difference == pytest.approx(4.0)
