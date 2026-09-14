"""Tests for comparing a regional model with the monitors inside its cell."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.ml.model_comparison import compare, model_at

T0 = datetime(2026, 9, 14, 4, 0, tzinfo=UTC)
MODEL = {T0: 20.0, T0 + timedelta(hours=1): 40.0, T0 + timedelta(hours=2): 60.0}


class TestModelAt:
    def test_an_hour_on_the_model_grid_is_taken_as_is(self) -> None:
        assert model_at(MODEL, T0 + timedelta(hours=1)) == 40.0

    def test_a_half_past_reading_gets_the_midpoint_of_the_hours_either_side(self) -> None:
        # Monitors report at half past in UTC; taking the nearer hour would shift
        # every pair by half an hour of the daily cycle.
        assert model_at(MODEL, T0 + timedelta(minutes=30)) == pytest.approx(30.0)

    def test_no_value_without_a_model_hour_on_both_sides(self) -> None:
        assert model_at(MODEL, T0 + timedelta(hours=2, minutes=30)) is None
        assert model_at(MODEL, T0 - timedelta(minutes=30)) is None


class TestCompare:
    def test_a_model_reading_half_the_monitors_has_a_ratio_of_a_half(self) -> None:
        readings = [(T0 + timedelta(minutes=30), 60.0), (T0 + timedelta(hours=1), 80.0)]

        summary = compare(MODEL, readings, min_pairs=2)

        assert summary.pairs == 2
        assert summary.median_ratio == pytest.approx(0.5)
        assert summary.median_difference == pytest.approx(-35.0)
        assert summary.is_established is True

    def test_a_short_record_is_reported_but_not_established(self) -> None:
        summary = compare(MODEL, [(T0, 40.0)], min_pairs=24)

        assert summary.pairs == 1
        assert summary.is_established is False

    def test_readings_the_model_does_not_cover_make_no_pairs(self) -> None:
        summary = compare(MODEL, [(T0 + timedelta(days=3), 50.0)])

        assert summary.pairs == 0
        assert summary.median_ratio is None
