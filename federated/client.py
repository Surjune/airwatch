"""A city node: trains on its own data and shares only statistics and weights.

Each city runs this as its own process. It loads its own observations, answers
the server's rounds, and at no point sends a reading, a station or a location --
only per-feature sums in the first round, model weights after that, and its own
held-out error when asked.

Run with: npm run fl:node -- --city kanpur
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from flwr.client import NumPyClient, start_client
from flwr.common import NDArrays, Scalar

ROOT = Path(__file__).resolve().parents[1]
for _path in (str(ROOT / "backend"), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from app.core.constants import (  # noqa: E402
    FL_L2,
    FL_LEARNING_RATE,
    FL_LOCAL_EPOCHS,
    FL_SERVER_ADDRESS,
    FORECAST_LAG_HOURS_SHORT,
    PILOT_CITY_CENTRES,
    VALIDATION_DATA_UNTIL,
)
from app.core.enums import Pollutant  # noqa: E402
from app.core.logging import configure_logging, get_logger  # noqa: E402
from app.ml.forecast_features import feature_names  # noqa: E402
from federated.node_data import (  # noqa: E402
    NodeData,
    build_node,
    federated_columns,
    load_city_series,
)
from federated.protocol import (  # noqa: E402
    NODE_KEY,
    PHASE_KEY,
    PROXIMAL_MU_KEY,
    STATISTICS_PHASE,
    TRAIN_PHASE,
    ProtocolError,
    unpack_model,
)
from federated.strategy import (  # noqa: E402
    add_bias_column,
    compute_statistics,
    mean_absolute_error,
    train_local,
)

logger = get_logger(__name__)


class CityClient(NumPyClient):
    """One node's side of the protocol, over data it already holds."""

    def __init__(self, node: NodeData) -> None:
        self._node = node

    def get_parameters(self, config: dict[str, Scalar]) -> NDArrays:
        """A node has no model of its own to offer before the federation starts."""
        return []

    def fit(
        self, parameters: NDArrays, config: dict[str, Scalar]
    ) -> tuple[NDArrays, int, dict[str, Scalar]]:
        """Answer a statistics round or a training round.

        Raises:
            ProtocolError: The round named no phase this node understands.
        """
        phase = config.get(PHASE_KEY)
        if phase == STATISTICS_PHASE:
            stats = compute_statistics(self._node.x_train)
            logger.info("fl_node_statistics", node=self._node.name, rows=stats.count)
            return [stats.total, stats.total_squares], stats.count, {}

        if phase == TRAIN_PHASE:
            weights, scaler = unpack_model(parameters)
            updated = train_local(
                add_bias_column(scaler.transform(self._node.x_train)),
                self._node.y_train,
                initial_weights=weights,
                global_weights=weights,
                epochs=FL_LOCAL_EPOCHS,
                learning_rate=FL_LEARNING_RATE,
                l2=FL_L2,
                proximal_mu=float(config.get(PROXIMAL_MU_KEY, 0.0)),
            )
            logger.info("fl_node_trained", node=self._node.name, rows=len(self._node.y_train))
            return [updated], len(self._node.y_train), {}

        raise ProtocolError(f"Unknown federation phase: {phase!r}.")

    def evaluate(
        self, parameters: NDArrays, config: dict[str, Scalar]
    ) -> tuple[float, int, dict[str, Scalar]]:
        """Score the global model on this node's held-out data."""
        weights, scaler = unpack_model(parameters)
        error = mean_absolute_error(
            add_bias_column(scaler.transform(self._node.x_test)), self._node.y_test, weights
        )
        return error, len(self._node.y_test), {NODE_KEY: self._node.name}


def load_node(city: str, *, pinned: bool) -> NodeData | None:
    """Build this city's matrices from its own observations only."""
    columns = federated_columns(feature_names(FORECAST_LAG_HOURS_SHORT))
    series, station_counts = load_city_series(
        Pollutant.PM25, until=VALIDATION_DATA_UNTIL if pinned else None, only=city
    )
    return build_node(city, series.get(city, {}), columns, station_counts.get(city, 0))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one federated city node")
    parser.add_argument("--city", required=True, choices=sorted(PILOT_CITY_CENTRES))
    parser.add_argument("--server", default=FL_SERVER_ADDRESS)
    parser.add_argument(
        "--pinned",
        action="store_true",
        help="use only data before the validation cutoff, to reproduce published results",
    )
    args = parser.parse_args(argv)

    configure_logging(level="INFO", json_output=True)

    node = load_node(args.city, pinned=args.pinned)
    if node is None:
        logger.error("fl_node_insufficient_data", node=args.city)
        return 1

    logger.info(
        "fl_node_ready",
        node=node.name,
        stations=node.stations,
        train_rows=len(node.y_train),
        test_rows=len(node.y_test),
    )
    start_client(server_address=args.server, client=CityClient(node).to_client(), insecure=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
