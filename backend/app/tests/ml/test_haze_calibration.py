"""Tests for the haze-to-concentration calibration.

The behaviour under test is mostly refusal, and that is the point. This is the
gate between "a photograph measured some contrast loss" and "a citizen was told
a PM2.5 figure", and the project's rule is that a wrong number is worse than no
number. So the tests that matter assert that a thin, flat or degenerate sample
produces nothing at all rather than a confident-looking line.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.constants import CITIZEN_CALIBRATION_MIN_PAIRS
from app.ml.haze_calibration import CalibrationPair, fit

RNG = np.random.default_rng(20260912)

#: A plausible relation for generating test samples: clear air near 20 ug/m3,
#: heavy haze near 320. The numbers only have to be self-consistent -- the real
#: relation is whatever the fit finds in real pairs.
TRUE_INTERCEPT = 20.0
TRUE_SLOPE = 300.0


def sample(count: int, *, noise: float = 8.0, spread: float = 0.6) -> list[CalibrationPair]:
    """Pairs drawn from a known linear relation with noise."""
    haze = RNG.uniform(0.1, 0.1 + spread, size=count)
    reference = TRUE_INTERCEPT + TRUE_SLOPE * haze + RNG.normal(0.0, noise, size=count)
    return [
        CalibrationPair(haze_index=float(h), reference_value=float(r))
        for h, r in zip(haze, reference, strict=True)
    ]


class TestRefusal:
    def test_too_few_pairs_yields_no_calibration(self) -> None:
        # A relation fitted from a handful of points would carry an error wider
        # than the range it predicts. Publishing nothing is the honest answer.
        assert fit(sample(CITIZEN_CALIBRATION_MIN_PAIRS - 1)) is None

    def test_the_minimum_sample_is_enough(self) -> None:
        assert fit(sample(CITIZEN_CALIBRATION_MIN_PAIRS)) is not None

    def test_an_empty_sample_yields_no_calibration(self) -> None:
        assert fit([]) is None

    def test_pairs_spanning_no_haze_range_yield_no_calibration(self) -> None:
        # Every photo taken in identical conditions gives the fit no leverage.
        # Extrapolating from a single point would produce confident nonsense.
        flat = [
            CalibrationPair(haze_index=0.30, reference_value=110.0 + float(RNG.normal(0, 5)))
            for _ in range(CITIZEN_CALIBRATION_MIN_PAIRS + 10)
        ]

        assert fit(flat) is None


class TestFittedRelation:
    def test_recovers_a_known_relation(self) -> None:
        calibration = fit(sample(200, noise=4.0))
        assert calibration is not None

        assert calibration.slope == pytest.approx(TRUE_SLOPE, rel=0.15)
        assert calibration.intercept == pytest.approx(TRUE_INTERCEPT, abs=15.0)

    def test_publishes_the_sample_it_was_built_from(self) -> None:
        calibration = fit(sample(80))
        assert calibration is not None

        assert calibration.pairs == 80
        assert calibration.haze_min < calibration.haze_max

    def test_a_noisier_sample_reports_a_larger_error(self) -> None:
        # The error has to track the data, or it is decoration rather than a
        # statement about how far wrong the estimate can be.
        tight = fit(sample(150, noise=3.0))
        loose = fit(sample(150, noise=30.0))
        assert tight is not None
        assert loose is not None

        assert loose.mae > tight.mae

    def test_the_error_is_measured_out_of_sample(self) -> None:
        # Leave-one-out, not in-sample residuals. With a sample this small, the
        # fit has seen every point it would otherwise be scored on, and the
        # in-sample error understates how wrong it is on a new photograph.
        pairs = sample(CITIZEN_CALIBRATION_MIN_PAIRS, noise=20.0)
        calibration = fit(pairs)
        assert calibration is not None

        haze = np.array([pair.haze_index for pair in pairs])
        reference = np.array([pair.reference_value for pair in pairs])
        in_sample = float(
            np.mean(np.abs(calibration.slope * haze + calibration.intercept - reference))
        )

        assert calibration.mae > in_sample


class TestEstimating:
    def test_more_haze_estimates_more_pollution(self) -> None:
        calibration = fit(sample(150))
        assert calibration is not None

        assert calibration.estimate(0.6).value > calibration.estimate(0.2).value

    def test_never_returns_a_negative_concentration(self) -> None:
        # The fit is linear, so a very clear photograph can otherwise produce a
        # negative value, which no consumer should have to reason about.
        calibration = fit(sample(150))
        assert calibration is not None

        assert calibration.estimate(0.0).value >= 0.0

    def test_every_estimate_carries_its_uncertainty(self) -> None:
        calibration = fit(sample(150))
        assert calibration is not None

        estimate = calibration.estimate(0.4)
        assert estimate.uncertainty > 0
        assert estimate.upper_bound == pytest.approx(estimate.value + estimate.uncertainty)

    def test_flags_an_index_outside_the_fitted_range(self) -> None:
        # Evaluating outside the training range is extrapolation, and a consumer
        # has to be told rather than handed a number that looks like the others.
        calibration = fit(sample(150, spread=0.3))
        assert calibration is not None

        assert calibration.is_extrapolating(0.99) is True
        assert calibration.is_extrapolating(0.0) is True
        assert (
            calibration.is_extrapolating((calibration.haze_min + calibration.haze_max) / 2)
            is False
        )
