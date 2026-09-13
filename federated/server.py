"""The federation server: aggregates what city nodes send, and holds no data.

The server never opens a database. It receives per-feature sums in the first
round and model weights after that, which is the whole point: the party doing
the aggregating is never in a position to see a reading, so a state board can
join without handing anything to it that it would refuse to hand to another state.

Membership is fixed in the statistics round. A node that connects later did not
contribute to the scaler every weight assumes, and a node that drops out would
leave an average over a different federation than the one that started; either
stops the run rather than being quietly absorbed.

Run with: npm run fl:server -- --nodes 2
"""

# This entry point reports a round table to a terminal for a person to read.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from flwr.common import (
    EvaluateIns,
    EvaluateRes,
    FitIns,
    FitRes,
    Parameters,
    Scalar,
    ndarrays_to_parameters,
    parameters_to_ndarrays,
)
from flwr.server import ServerConfig, start_server
from flwr.server.client_manager import ClientManager
from flwr.server.client_proxy import ClientProxy
from flwr.server.strategy import Strategy

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "backend"), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.core.constants import (  # noqa: E402
    FL_MIN_AVAILABLE_CLIENTS,
    FL_NODE_WAIT_SECONDS,
    FL_NUM_ROUNDS,
    FL_PROXIMAL_MU,
    FL_SERVER_ADDRESS,
)
from app.core.logging import configure_logging, get_logger  # noqa: E402
from federated.protocol import (  # noqa: E402
    NODE_KEY,
    PHASE_KEY,
    PROXIMAL_MU_KEY,
    STATISTICS_PHASE,
    TRAIN_PHASE,
    pack_model,
)
from federated.strategy import (  # noqa: E402
    FeatureStats,
    GlobalScaler,
    LocalUpdate,
    aggregate_statistics,
    federated_average,
)

logger = get_logger(__name__)

#: Where the final global model is written. Artifacts are not committed.
DEFAULT_OUTPUT = ROOT / "ml" / "artifacts" / "federated_global.npz"

#: The statistics exchange occupies Flower's first round; training follows it.
_STATISTICS_ROUND = 1


@dataclass(slots=True)
class FederationState:
    """What the server knows at any point: the model, and nothing about rows."""

    scaler: GlobalScaler | None = None
    weights: np.ndarray | None = None
    members: frozenset[str] = frozenset()
    #: Held-out error per node after each training round, as the nodes reported it.
    node_errors: dict[int, dict[str, float]] = field(default_factory=dict)
    failure: str | None = None


class CityFederation(Strategy):
    """FedAvg over city nodes, with a statistics round and fixed membership."""

    def __init__(self, *, expected_nodes: int, proximal_mu: float) -> None:
        super().__init__()
        self._expected_nodes = expected_nodes
        self._proximal_mu = proximal_mu
        self.state = FederationState()

    def initialize_parameters(self, client_manager: ClientManager) -> Parameters | None:
        # Empty rather than None: None makes Flower ask one node for its weights,
        # and no node has a model before the scaler exists.
        return ndarrays_to_parameters([])

    def configure_fit(
        self, server_round: int, parameters: Parameters, client_manager: ClientManager
    ) -> list[tuple[ClientProxy, FitIns]]:
        if self.state.failure is not None:
            return []

        if server_round == _STATISTICS_ROUND:
            if not client_manager.wait_for(self._expected_nodes, FL_NODE_WAIT_SECONDS):
                self.state.failure = (
                    f"only {client_manager.num_available()} of {self._expected_nodes} nodes "
                    f"connected within {FL_NODE_WAIT_SECONDS}s"
                )
                return []
            connected = client_manager.all()
            self.state.members = frozenset(connected)
            statistics = FitIns(ndarrays_to_parameters([]), {PHASE_KEY: STATISTICS_PHASE})
            return [(proxy, statistics) for proxy in connected.values()]

        members = self._members(client_manager)
        if members is None:
            return []
        config: dict[str, Scalar] = {PHASE_KEY: TRAIN_PHASE, PROXIMAL_MU_KEY: self._proximal_mu}
        training = FitIns(self._model_parameters(), config)
        return [(proxy, training) for proxy in members]

    def aggregate_fit(
        self,
        server_round: int,
        results: list[tuple[ClientProxy, FitRes]],
        failures: list[tuple[ClientProxy, FitRes] | BaseException],
    ) -> tuple[Parameters | None, dict[str, Scalar]]:
        if failures or len(results) != len(self.state.members):
            self.state.failure = (
                f"round {server_round}: {len(results)} of {len(self.state.members)} nodes "
                f"answered ({len(failures)} failed)"
            )
            return None, {}

        if server_round == _STATISTICS_ROUND:
            stats = []
            for _, result in results:
                total, total_squares = parameters_to_ndarrays(result.parameters)
                stats.append(
                    FeatureStats(
                        count=result.num_examples, total=total, total_squares=total_squares
                    )
                )
            self.state.scaler = aggregate_statistics(stats)
            self.state.weights = np.zeros(len(self.state.scaler.mean) + 1)
            logger.info("fl_scaler_agreed", nodes=len(stats), features=len(self.state.scaler.mean))
        else:
            updates = [
                LocalUpdate(
                    node=proxy.cid,
                    weights=parameters_to_ndarrays(result.parameters)[0],
                    sample_count=result.num_examples,
                )
                for proxy, result in results
            ]
            self.state.weights = federated_average(updates)
            logger.info("fl_round_aggregated", round=server_round - _STATISTICS_ROUND)

        return self._model_parameters(), {}

    def configure_evaluate(
        self, server_round: int, parameters: Parameters, client_manager: ClientManager
    ) -> list[tuple[ClientProxy, EvaluateIns]]:
        if server_round == _STATISTICS_ROUND or self.state.failure is not None:
            return []
        proxies = self._members(client_manager)
        if proxies is None:
            return []
        instruction = EvaluateIns(self._model_parameters(), {})
        return [(proxy, instruction) for proxy in proxies]

    def aggregate_evaluate(
        self,
        server_round: int,
        results: list[tuple[ClientProxy, EvaluateRes]],
        failures: list[tuple[ClientProxy, EvaluateRes] | BaseException],
    ) -> tuple[float | None, dict[str, Scalar]]:
        if not results:
            return None, {}
        self.state.node_errors[server_round - _STATISTICS_ROUND] = {
            str(result.metrics[NODE_KEY]): result.loss for _, result in results
        }
        examples = sum(result.num_examples for _, result in results)
        pooled = sum(result.loss * result.num_examples for _, result in results) / examples
        return pooled, {}

    def evaluate(
        self, server_round: int, parameters: Parameters
    ) -> tuple[float, dict[str, Scalar]] | None:
        # The server holds no data to evaluate on, by design.
        return None

    def _members(self, client_manager: ClientManager) -> list[ClientProxy] | None:
        """The nodes that started the run, or None if any has gone."""
        connected = client_manager.all()
        missing = self.state.members - set(connected)
        if missing:
            self.state.failure = f"{len(missing)} node(s) disconnected mid-run"
            return None
        return [connected[cid] for cid in sorted(self.state.members)]

    def _model_parameters(self) -> Parameters:
        if self.state.weights is None or self.state.scaler is None:
            return ndarrays_to_parameters([])
        return ndarrays_to_parameters(pack_model(self.state.weights, self.state.scaler))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the federation server")
    parser.add_argument("--nodes", type=int, default=FL_MIN_AVAILABLE_CLIENTS)
    parser.add_argument("--rounds", type=int, default=FL_NUM_ROUNDS)
    parser.add_argument("--proximal-mu", type=float, default=FL_PROXIMAL_MU)
    parser.add_argument("--address", default=FL_SERVER_ADDRESS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    if args.nodes < FL_MIN_AVAILABLE_CLIENTS:
        parser.error(
            f"--nodes must be at least {FL_MIN_AVAILABLE_CLIENTS}: one node is not a federation"
        )

    configure_logging(level="INFO", json_output=True)
    strategy = CityFederation(expected_nodes=args.nodes, proximal_mu=args.proximal_mu)
    start_server(
        server_address=args.address,
        config=ServerConfig(num_rounds=args.rounds + _STATISTICS_ROUND),
        strategy=strategy,
    )

    state = strategy.state
    if state.failure is not None or state.weights is None or state.scaler is None:
        print(f"Federation did not complete: {state.failure or 'no model was produced'}.")
        return 1

    nodes = sorted({node for errors in state.node_errors.values() for node in errors})
    print(f"\n{'round':>5}  " + "  ".join(f"{node:>10}" for node in nodes))
    for training_round, errors in sorted(state.node_errors.items()):
        print(f"{training_round:>5}  " + "  ".join(f"{errors[node]:>10.2f}" for node in nodes))
    print("\nHeld-out MAE (ug/m3) of the global model, as each node measured it on its own data.")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.out, weights=state.weights, mean=state.scaler.mean, std=state.scaler.std)
    print(f"Global model written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
