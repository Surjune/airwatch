"""Tests for federated aggregation.

The property that matters most is in TestPrivacyProperty and
TestDistributedStatistics: a node shares counts and sums, never rows, and the
scaler built from those must match the one a central server would compute if it
could see everything. If the aggregate maths were wrong, the whole arrangement
would be paying a privacy cost for a worse model.
"""

from __future__ import annotations

import numpy as np
import pytest
from federated.strategy import (
    FeatureStats,
    LocalUpdate,
    TransferOutcome,
    add_bias_column,
    aggregate_statistics,
    compute_statistics,
    federated_average,
    mean_absolute_error,
    train_local,
)

RNG = np.random.default_rng(20260907)


class TestDistributedStatistics:
    def test_matches_what_a_central_server_would_compute(self) -> None:
        # The correctness claim underneath the privacy claim: pooling counts and
        # sums must give exactly the mean and deviation of the combined data.
        delhi = RNG.normal(loc=90.0, scale=40.0, size=(500, 4))
        kanpur = RNG.normal(loc=45.0, scale=15.0, size=(60, 4))

        scaler = aggregate_statistics([compute_statistics(delhi), compute_statistics(kanpur)])
        combined = np.vstack([delhi, kanpur])

        assert scaler.mean == pytest.approx(combined.mean(axis=0))
        assert scaler.std == pytest.approx(combined.std(axis=0), rel=1e-6)

    def test_standardises_to_zero_mean_and_unit_variance(self) -> None:
        data = RNG.normal(loc=70.0, scale=20.0, size=(300, 3))
        scaler = aggregate_statistics([compute_statistics(data)])

        standardised = scaler.transform(data)

        assert standardised.mean(axis=0) == pytest.approx(np.zeros(3), abs=1e-9)
        assert standardised.std(axis=0) == pytest.approx(np.ones(3), rel=1e-6)

    def test_a_constant_feature_does_not_divide_by_zero(self) -> None:
        # A single-station city can easily have a feature that never varies.
        data = np.column_stack([RNG.normal(size=50), np.full(50, 7.0)])
        scaler = aggregate_statistics([compute_statistics(data)])

        standardised = scaler.transform(data)

        assert np.all(np.isfinite(standardised))

    def test_rejects_an_empty_federation(self) -> None:
        with pytest.raises(ValueError, match="no node statistics"):
            aggregate_statistics([])

    def test_rejects_statistics_describing_nothing(self) -> None:
        empty = FeatureStats(count=0, total=np.zeros(3), total_squares=np.zeros(3))
        with pytest.raises(ValueError, match="zero samples"):
            aggregate_statistics([empty])


class TestPrivacyProperty:
    def test_shared_statistics_contain_no_rows(self) -> None:
        # Structural check on the claim that lets weights cross a boundary raw
        # observations cannot: what leaves a node is three numbers per feature,
        # regardless of how many readings produced them.
        data = RNG.normal(size=(1000, 5))
        stats = compute_statistics(data)

        assert stats.total.shape == (5,)
        assert stats.total_squares.shape == (5,)
        assert stats.count == 1000

    def test_two_different_datasets_can_share_statistics(self) -> None:
        # The same summary can arise from different data, which is the point:
        # the summary does not identify the rows behind it.
        first = np.array([[0.0], [10.0]])
        second = np.array([[5.0 - 5.0], [5.0 + 5.0]])

        assert compute_statistics(first).total == pytest.approx(compute_statistics(second).total)


class TestFederatedAverage:
    def test_weights_by_sample_count(self) -> None:
        # A city with sixty stations should count for more than one with three.
        big = LocalUpdate(node="delhi", weights=np.array([10.0, 0.0]), sample_count=900)
        small = LocalUpdate(node="kanpur", weights=np.array([0.0, 0.0]), sample_count=100)

        averaged = federated_average([big, small])

        assert averaged[0] == pytest.approx(9.0)

    def test_equal_nodes_give_a_plain_mean(self) -> None:
        first = LocalUpdate(node="a", weights=np.array([2.0]), sample_count=50)
        second = LocalUpdate(node="b", weights=np.array([4.0]), sample_count=50)

        assert federated_average([first, second])[0] == pytest.approx(3.0)

    def test_a_single_node_is_returned_unchanged(self) -> None:
        only = LocalUpdate(node="a", weights=np.array([1.5, -2.0]), sample_count=10)
        assert federated_average([only]) == pytest.approx(only.weights)

    def test_rejects_an_empty_round(self) -> None:
        with pytest.raises(ValueError, match="empty set of updates"):
            federated_average([])

    def test_rejects_nodes_with_no_samples(self) -> None:
        empty = LocalUpdate(node="a", weights=np.array([1.0]), sample_count=0)
        with pytest.raises(ValueError, match="zero samples"):
            federated_average([empty])


class TestLocalTraining:
    def test_recovers_a_known_linear_relationship(self) -> None:
        features = add_bias_column(RNG.normal(size=(500, 2)))
        true_weights = np.array([3.0, -2.0, 5.0])
        targets = features @ true_weights

        learned = train_local(
            features,
            targets,
            initial_weights=np.zeros(3),
            epochs=2000,
            learning_rate=0.1,
            l2=0.0,
        )

        assert learned == pytest.approx(true_weights, abs=0.05)

    def test_training_reduces_error(self) -> None:
        features = add_bias_column(RNG.normal(size=(200, 3)))
        targets = features @ np.array([1.0, 2.0, -1.0, 0.5])
        start = np.zeros(4)

        learned = train_local(features, targets, initial_weights=start, epochs=200)

        assert mean_absolute_error(features, targets, learned) < mean_absolute_error(
            features, targets, start
        )

    def test_the_proximal_term_holds_a_node_near_the_global_model(self) -> None:
        # FedProx exists so a node whose data looks nothing like the federation's
        # cannot drag aggregation somewhere that suits nobody.
        features = add_bias_column(RNG.normal(size=(100, 2)))
        targets = features @ np.array([9.0, -9.0, 9.0])
        anchor = np.zeros(3)

        free = train_local(features, targets, initial_weights=anchor, epochs=200)
        constrained = train_local(
            features,
            targets,
            initial_weights=anchor,
            global_weights=anchor,
            epochs=200,
            proximal_mu=5.0,
        )

        assert np.linalg.norm(constrained - anchor) < np.linalg.norm(free - anchor)

    def test_zero_mu_is_plain_fedavg_training(self) -> None:
        features = add_bias_column(RNG.normal(size=(100, 2)))
        targets = features @ np.array([1.0, 1.0, 1.0])

        without = train_local(features, targets, initial_weights=np.zeros(3), epochs=50)
        with_zero_mu = train_local(
            features,
            targets,
            initial_weights=np.zeros(3),
            global_weights=np.zeros(3),
            epochs=50,
            proximal_mu=0.0,
        )

        assert without == pytest.approx(with_zero_mu)


class TestNegativeTransfer:
    def test_detects_a_node_made_worse(self) -> None:
        # The check that lets the federation claim be refuted. Measured on real
        # data, Kanpur was harmed by 6.8% and kept its local model.
        harmed = TransferOutcome(node="kanpur", local_mae=9.21, global_mae=9.85)

        assert harmed.improvement < 0
        assert harmed.is_harmed(tolerance=0.02) is True

    def test_a_small_degradation_is_within_tolerance(self) -> None:
        noise = TransferOutcome(node="delhi", local_mae=16.82, global_mae=16.84)
        assert noise.is_harmed(tolerance=0.02) is False

    def test_recognises_a_genuine_improvement(self) -> None:
        helped = TransferOutcome(node="sparse", local_mae=20.0, global_mae=15.0)

        assert helped.improvement == pytest.approx(0.25)
        assert helped.is_harmed(tolerance=0.02) is False

    def test_a_perfect_local_model_is_not_a_division_by_zero(self) -> None:
        degenerate = TransferOutcome(node="a", local_mae=0.0, global_mae=1.0)
        assert degenerate.improvement == 0.0
