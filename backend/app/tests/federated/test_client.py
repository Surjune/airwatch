"""Tests for a city node's side of the federation protocol."""

from __future__ import annotations

import numpy as np
import pytest
from federated.client import CityClient
from federated.node_data import NodeData
from federated.protocol import (
    NODE_KEY,
    PHASE_KEY,
    PROXIMAL_MU_KEY,
    STATISTICS_PHASE,
    TRAIN_PHASE,
    ProtocolError,
    pack_model,
)
from federated.strategy import (
    GlobalScaler,
    add_bias_column,
    aggregate_statistics,
    compute_statistics,
    mean_absolute_error,
)

RNG = np.random.default_rng(20260913)


def make_node(train_rows: int = 40, test_rows: int = 10, features: int = 3) -> NodeData:
    return NodeData(
        name="kanpur",
        x_train=RNG.normal(50.0, 10.0, size=(train_rows, features)),
        y_train=RNG.normal(60.0, 15.0, size=train_rows),
        x_test=RNG.normal(50.0, 10.0, size=(test_rows, features)),
        y_test=RNG.normal(60.0, 15.0, size=test_rows),
        stations=3,
    )


def scaler_for(node: NodeData) -> GlobalScaler:
    return aggregate_statistics([compute_statistics(node.x_train)])


class TestStatisticsRound:
    def test_shares_sums_and_a_count_and_nothing_else(self) -> None:
        node = make_node()

        arrays, count, metrics = CityClient(node).fit([], {PHASE_KEY: STATISTICS_PHASE})

        expected = compute_statistics(node.x_train)
        assert count == expected.count
        assert metrics == {}
        assert len(arrays) == 2
        np.testing.assert_allclose(arrays[0], expected.total)
        np.testing.assert_allclose(arrays[1], expected.total_squares)

    def test_never_sends_arrays_shaped_like_rows(self) -> None:
        # The privacy property in one assertion: every array a node sends in the
        # statistics round has one entry per feature, whatever the row count.
        node = make_node(train_rows=200)

        arrays, _, _ = CityClient(node).fit([], {PHASE_KEY: STATISTICS_PHASE})

        assert all(array.shape == (node.x_train.shape[1],) for array in arrays)


class TestTrainingRound:
    def test_returns_updated_weights_weighted_by_its_training_rows(self) -> None:
        node = make_node()
        start = np.zeros(node.x_train.shape[1] + 1)

        arrays, count, _ = CityClient(node).fit(
            pack_model(start, scaler_for(node)),
            {PHASE_KEY: TRAIN_PHASE, PROXIMAL_MU_KEY: 0.0},
        )

        assert count == len(node.y_train)
        assert arrays[0].shape == start.shape
        assert not np.array_equal(arrays[0], start)

    def test_training_reduces_its_own_error(self) -> None:
        node = make_node()
        scaler = scaler_for(node)
        start = np.zeros(node.x_train.shape[1] + 1)
        features = add_bias_column(scaler.transform(node.x_train))

        arrays, _, _ = CityClient(node).fit(pack_model(start, scaler), {PHASE_KEY: TRAIN_PHASE})

        assert mean_absolute_error(features, node.y_train, arrays[0]) < mean_absolute_error(
            features, node.y_train, start
        )

    def test_a_stronger_proximal_term_keeps_it_nearer_the_global_model(self) -> None:
        node = make_node()
        scaler = scaler_for(node)
        start = np.zeros(node.x_train.shape[1] + 1)
        client = CityClient(node)

        free, _, _ = client.fit(
            pack_model(start, scaler), {PHASE_KEY: TRAIN_PHASE, PROXIMAL_MU_KEY: 0.0}
        )
        anchored, _, _ = client.fit(
            pack_model(start, scaler), {PHASE_KEY: TRAIN_PHASE, PROXIMAL_MU_KEY: 5.0}
        )

        assert np.linalg.norm(anchored[0] - start) < np.linalg.norm(free[0] - start)

    def test_rejects_a_malformed_model(self) -> None:
        with pytest.raises(ProtocolError):
            CityClient(make_node()).fit([np.zeros(4)], {PHASE_KEY: TRAIN_PHASE})


def test_rejects_an_unknown_phase() -> None:
    with pytest.raises(ProtocolError, match="Unknown federation phase"):
        CityClient(make_node()).fit([], {PHASE_KEY: "exfiltrate"})


def test_has_no_model_to_offer_before_the_federation_starts() -> None:
    assert CityClient(make_node()).get_parameters({}) == []


def test_evaluates_on_its_held_out_rows_and_names_only_itself() -> None:
    node = make_node()
    scaler = scaler_for(node)
    weights = RNG.normal(size=node.x_train.shape[1] + 1)

    loss, count, metrics = CityClient(node).evaluate(pack_model(weights, scaler), {})

    expected = mean_absolute_error(
        add_bias_column(scaler.transform(node.x_test)), node.y_test, weights
    )
    assert loss == pytest.approx(expected)
    assert count == len(node.y_test)
    assert metrics == {NODE_KEY: "kanpur"}
