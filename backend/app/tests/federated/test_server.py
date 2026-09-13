"""Tests for the federation server strategy.

These drive Flower's own round loop -- the same ``Server`` that ``start_server``
runs -- with nodes attached in-process instead of over gRPC. That exercises
every message the strategy sends and receives, and lets the central claim be
checked exactly: training is deterministic, so a run through the transport must
reproduce the in-process federation that produced the published results.
"""

from __future__ import annotations

import numpy as np
import pytest
from federated.client import CityClient
from federated.node_data import NodeData
from federated.server import CityFederation
from federated.strategy import run_in_process
from flwr.common import (
    DisconnectRes,
    EvaluateIns,
    EvaluateRes,
    FitIns,
    FitRes,
    GetParametersIns,
    GetParametersRes,
    GetPropertiesIns,
    GetPropertiesRes,
    ReconnectIns,
)
from flwr.server import Server
from flwr.server.client_manager import SimpleClientManager
from flwr.server.client_proxy import ClientProxy

from app.core.constants import FL_L2, FL_LEARNING_RATE, FL_LOCAL_EPOCHS

RNG = np.random.default_rng(20260913)
ROUNDS = 4
MU = 0.01


class InProcessProxy(ClientProxy):
    """A node attached directly, standing in for the gRPC connection."""

    def __init__(self, cid: str, client: CityClient, *, fail_from_round: int | None = None) -> None:
        super().__init__(cid)
        self._client = client.to_client()
        self._fail_from_round = fail_from_round
        self._fits = 0

    def fit(self, ins: FitIns, timeout: float | None, group_id: int | None) -> FitRes:
        self._fits += 1
        if self._fail_from_round is not None and self._fits >= self._fail_from_round:
            raise ConnectionError("node went away")
        return self._client.fit(ins)

    def evaluate(
        self, ins: EvaluateIns, timeout: float | None, group_id: int | None
    ) -> EvaluateRes:
        return self._client.evaluate(ins)

    def get_parameters(
        self, ins: GetParametersIns, timeout: float | None, group_id: int | None
    ) -> GetParametersRes:
        raise AssertionError("the server must never ask a node for its own model")

    def get_properties(
        self, ins: GetPropertiesIns, timeout: float | None, group_id: int | None
    ) -> GetPropertiesRes:
        raise NotImplementedError

    def reconnect(
        self, ins: ReconnectIns, timeout: float | None, group_id: int | None
    ) -> DisconnectRes:
        return DisconnectRes(reason="")


def make_node(name: str, rows: int, level: float) -> NodeData:
    x_train = RNG.normal(level, 10.0, size=(rows, 3))
    x_test = RNG.normal(level, 10.0, size=(rows // 4, 3))
    coefficients = np.array([0.6, -0.2, 0.1])
    return NodeData(
        name=name,
        x_train=x_train,
        y_train=x_train @ coefficients + RNG.normal(0.0, 2.0, size=rows),
        x_test=x_test,
        y_test=x_test @ coefficients + RNG.normal(0.0, 2.0, size=rows // 4),
        stations=rows // 20,
    )


NODES = [make_node("delhi", 400, 90.0), make_node("kanpur", 40, 45.0)]


def run(proxies: list[InProcessProxy], *, expected_nodes: int) -> CityFederation:
    manager = SimpleClientManager()
    for proxy in proxies:
        manager.register(proxy)
    strategy = CityFederation(expected_nodes=expected_nodes, proximal_mu=MU)
    Server(client_manager=manager, strategy=strategy).fit(num_rounds=ROUNDS + 1, timeout=None)
    return strategy


def proxies_for(nodes: list[NodeData]) -> list[InProcessProxy]:
    return [InProcessProxy(node.name, CityClient(node)) for node in nodes]


class TestEquivalence:
    def test_reproduces_the_in_process_federation(self) -> None:
        strategy = run(proxies_for(NODES), expected_nodes=2)

        expected_weights, expected_scaler = run_in_process(
            [(node.name, node.x_train, node.y_train) for node in NODES],
            rounds=ROUNDS,
            local_epochs=FL_LOCAL_EPOCHS,
            learning_rate=FL_LEARNING_RATE,
            l2=FL_L2,
            proximal_mu=MU,
        )

        state = strategy.state
        assert state.failure is None
        assert state.scaler is not None
        assert state.weights is not None
        np.testing.assert_allclose(state.scaler.mean, expected_scaler.mean, rtol=1e-12)
        np.testing.assert_allclose(state.scaler.std, expected_scaler.std, rtol=1e-12)
        np.testing.assert_allclose(state.weights, expected_weights, rtol=1e-10, atol=1e-12)

    def test_every_node_reports_its_error_after_every_training_round(self) -> None:
        strategy = run(proxies_for(NODES), expected_nodes=2)

        assert sorted(strategy.state.node_errors) == list(range(1, ROUNDS + 1))
        for errors in strategy.state.node_errors.values():
            assert set(errors) == {"delhi", "kanpur"}
            assert all(np.isfinite(value) and value >= 0 for value in errors.values())


class TestMembership:
    def test_stops_rather_than_averaging_over_a_node_that_dropped_out(self) -> None:
        delhi, kanpur = NODES
        proxies = [
            InProcessProxy("delhi", CityClient(delhi)),
            InProcessProxy("kanpur", CityClient(kanpur), fail_from_round=3),
        ]

        strategy = run(proxies, expected_nodes=2)

        assert strategy.state.failure is not None
        assert "1 of 2 nodes answered" in strategy.state.failure

    def test_gives_up_when_too_few_nodes_connect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("federated.server.FL_NODE_WAIT_SECONDS", 0)

        strategy = run(proxies_for(NODES[:1]), expected_nodes=2)

        assert strategy.state.failure is not None
        assert "only 1 of 2 nodes connected" in strategy.state.failure
        assert strategy.state.weights is None
