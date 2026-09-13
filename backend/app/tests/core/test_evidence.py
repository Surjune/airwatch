"""Tests for the rule deciding whether a model comparison is a finding.

This rule exists because a published claim broke it. "Federation measurably
harmed Kanpur" rested on 23 held-out rows whose bootstrap interval spans zero.
The tests pin both halves of the replacement: an interval that includes zero is
inconclusive however large the point estimate, and a real but tiny difference on
a large holdout is not called an effect either.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.evidence import (
    Effect,
    EffectEstimate,
    classify,
    paired_bootstrap,
    paired_cluster_bootstrap,
)

SEED = 20260913
RNG = np.random.default_rng(SEED)


def _estimate(gain: float, low: float, high: float) -> EffectEstimate:
    return EffectEstimate(gain=gain, low=low, high=high, samples=100)


class TestPairedBootstrap:
    def test_a_consistently_better_candidate_has_an_interval_above_zero(self) -> None:
        baseline = RNG.uniform(10.0, 20.0, size=400)
        candidate = baseline - 2.0

        estimate = paired_bootstrap(baseline, candidate, seed=SEED)

        assert estimate.gain == pytest.approx(2.0)
        assert estimate.low > 0

    def test_identical_models_have_an_interval_around_zero(self) -> None:
        errors = RNG.uniform(5.0, 15.0, size=200)

        estimate = paired_bootstrap(errors, errors.copy(), seed=SEED)

        assert estimate.low <= 0.0 <= estimate.high

    def test_a_small_noisy_holdout_gives_a_wide_interval(self) -> None:
        # The Kanpur case: a visible mean difference on very few rows.
        baseline = RNG.uniform(0.0, 20.0, size=23)
        candidate = baseline + RNG.normal(0.6, 5.0, size=23)

        small = paired_bootstrap(baseline, candidate, seed=SEED)
        large_base = RNG.uniform(0.0, 20.0, size=2300)
        large = paired_bootstrap(
            large_base, large_base + RNG.normal(0.6, 5.0, size=2300), seed=SEED
        )

        assert (small.high - small.low) > (large.high - large.low)

    def test_pairing_is_respected(self) -> None:
        # Rows hard for both models must not widen the interval: the difference
        # per row is constant here, so the interval collapses onto it.
        hardness = RNG.uniform(0.0, 100.0, size=300)

        estimate = paired_bootstrap(hardness + 5.0, hardness + 4.0, seed=SEED)

        assert estimate.low == pytest.approx(1.0)
        assert estimate.high == pytest.approx(1.0)

    def test_the_same_seed_reproduces_the_interval(self) -> None:
        baseline = RNG.uniform(0.0, 10.0, size=50)
        candidate = baseline + RNG.normal(0.0, 2.0, size=50)

        first = paired_bootstrap(baseline, candidate, seed=SEED)
        second = paired_bootstrap(baseline, candidate, seed=SEED)

        assert (first.low, first.high) == (second.low, second.high)

    def test_rejects_unpaired_errors(self) -> None:
        with pytest.raises(ValueError, match="same rows"):
            paired_bootstrap(np.ones(5), np.ones(6), seed=SEED)

    def test_rejects_an_empty_holdout(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            paired_bootstrap(np.array([]), np.array([]), seed=SEED)


class TestClassify:
    def test_an_interval_spanning_zero_is_inconclusive_however_large_the_estimate(self) -> None:
        # Kanpur's published harm: a 6.8% point estimate, interval across zero.
        estimate = _estimate(gain=-0.63, low=-3.36, high=2.19)

        assert classify(estimate, baseline_error=9.21, tolerance=0.02) is Effect.INCONCLUSIVE

    def test_a_clear_large_improvement_is_helped(self) -> None:
        estimate = _estimate(gain=2.0, low=1.2, high=2.8)

        assert classify(estimate, baseline_error=10.0, tolerance=0.02) is Effect.HELPED

    def test_a_clear_large_degradation_is_harmed(self) -> None:
        estimate = _estimate(gain=-2.0, low=-2.8, high=-1.2)

        assert classify(estimate, baseline_error=10.0, tolerance=0.02) is Effect.HARMED

    def test_a_certain_but_tiny_difference_is_no_practical_difference(self) -> None:
        # Delhi's local head: 493 rows make 0.03 ug/m3 statistically certain and
        # still far too small for anyone to act on.
        estimate = _estimate(gain=0.03, low=0.01, high=0.05)

        assert (
            classify(estimate, baseline_error=16.82, tolerance=0.02)
            is Effect.NO_PRACTICAL_DIFFERENCE
        )

    def test_an_interval_touching_zero_is_still_inconclusive(self) -> None:
        estimate = _estimate(gain=1.0, low=0.0, high=2.0)

        assert classify(estimate, baseline_error=10.0, tolerance=0.02) is Effect.INCONCLUSIVE


class TestClusterBootstrap:
    def test_correlated_rows_give_a_wider_interval_than_pretending_independence(self) -> None:
        # Ten stations, each with a persistent station-level effect across 300
        # hours. Row resampling sees 3000 independent draws; the evidence is ten.
        stations = np.repeat(np.arange(10), 300)
        station_effect = RNG.normal(0.5, 3.0, size=10)[stations]
        baseline = RNG.uniform(5.0, 15.0, size=stations.size)
        candidate = baseline - station_effect - RNG.normal(0.0, 0.5, size=stations.size)

        rows = paired_bootstrap(baseline, candidate, seed=SEED)
        clustered = paired_cluster_bootstrap(baseline, candidate, stations, seed=SEED)

        assert (clustered.high - clustered.low) > 3 * (rows.high - rows.low)

    def test_reports_the_cluster_count_as_the_sample(self) -> None:
        stations = np.repeat(np.arange(7), 40)
        errors = RNG.uniform(0.0, 10.0, size=stations.size)

        estimate = paired_cluster_bootstrap(errors, errors - 1.0, stations, seed=SEED)

        assert estimate.samples == 7
        assert estimate.gain == pytest.approx(1.0)

    def test_a_uniform_improvement_is_certain_whatever_the_clustering(self) -> None:
        stations = np.repeat(np.arange(12), 50)
        errors = RNG.uniform(5.0, 15.0, size=stations.size)

        estimate = paired_cluster_bootstrap(errors, errors - 2.0, stations, seed=SEED)

        assert estimate.low == pytest.approx(2.0)
        assert estimate.high == pytest.approx(2.0)

    def test_rejects_mismatched_clusters(self) -> None:
        with pytest.raises(ValueError, match="same rows"):
            paired_cluster_bootstrap(np.ones(4), np.ones(4), np.ones(3), seed=SEED)
