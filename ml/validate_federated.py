"""Does federating actually help the data-poor city?

The federated argument is that a city with three monitors benefits from a model
shaped partly by a city with sixty, without either handing over raw data. That
is a claim, and this measures it.

The comparison for each node is its own local model against the federated
global one, on its own held-out data. A node made worse is reported as harmed
rather than averaged into a favourable headline -- the whole point of the check
is that it can return "federation did not help", and Phases 2 and 4 have already
shown that the plausible-sounding method is not always the better one.

Nodes are the pilot cities, assigned by proximity to their centre. Delhi is the
data-rich node; Kanpur is the sparse one that federation is supposed to rescue.

Run with: npm run fl:validate
"""

# This script reports to a terminal; the printed table is its product.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(BACKEND), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from federated.node_data import (  # noqa: E402
    NodeData,
    build_node,
    federated_columns,
    load_city_series,
)
from federated.strategy import (  # noqa: E402
    add_bias_column,
    aggregate_statistics,
    compute_statistics,
    fine_tune,
    refit_intercept,
    run_in_process,
    train_local,
)

from app.core.constants import (  # noqa: E402
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    FL_FINE_TUNE_EPOCHS,
    FL_HORIZON_HOURS,
    FL_L2,
    FL_LEARNING_RATE,
    FL_LOCAL_EPOCHS,
    FL_MIN_AVAILABLE_CLIENTS,
    FL_NUM_ROUNDS,
    FL_PROXIMAL_MU,
    FORECAST_LAG_HOURS_SHORT,
    MODEL_COMPARISON_TOLERANCE,
    PILOT_CITY_CENTRES,
    RANDOM_SEED,
    VALIDATION_DATA_UNTIL,
)
from app.core.enums import Pollutant  # noqa: E402
from app.core.evidence import Effect, EffectEstimate, classify, paired_bootstrap  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.ml.forecast_features import feature_names  # noqa: E402


def train_local_only(node: NodeData, scaler_source: list[NodeData]) -> np.ndarray:
    """Train a node entirely on its own data, as the comparison baseline."""
    scaler = aggregate_statistics([compute_statistics(n.x_train) for n in scaler_source])
    features = add_bias_column(scaler.transform(node.x_train))
    weights: np.ndarray = train_local(
        features,
        node.y_train,
        initial_weights=np.zeros(features.shape[1]),
        epochs=FL_LOCAL_EPOCHS * FL_NUM_ROUNDS,
        learning_rate=FL_LEARNING_RATE,
        l2=FL_L2,
    )
    return weights


def main() -> int:
    parser = argparse.ArgumentParser(description="Federated transfer validation")
    parser.add_argument("--rounds", type=int, default=FL_NUM_ROUNDS)
    parser.add_argument("--proximal-mu", type=float, default=FL_PROXIMAL_MU)
    args = parser.parse_args()

    configure_logging(level="WARNING", json_output=False)
    np.random.seed(RANDOM_SEED)

    columns = federated_columns(feature_names(FORECAST_LAG_HOURS_SHORT))
    series, station_counts = load_city_series(Pollutant.PM25, until=VALIDATION_DATA_UNTIL)

    print(f"shared feature schema: {len(columns)} features every node can compute")
    print("city data available:")
    for city in PILOT_CITY_CENTRES:
        readings = sum(len(h) for h in series.get(city, {}).values())
        print(f"  {city:<12} stations={station_counts.get(city, 0):>3}  readings={readings:>6}")

    nodes: list[NodeData] = []
    for city, city_series in series.items():
        node = build_node(city, city_series, columns, station_counts.get(city, 0))
        if node is None:
            print(f"\n  {city}: too little usable data to participate")
            continue
        nodes.append(node)

    print(f"\nparticipating nodes: {[node.name for node in nodes]}")
    if len(nodes) < FL_MIN_AVAILABLE_CLIENTS:
        print(f"Need at least {FL_MIN_AVAILABLE_CLIENTS} nodes to federate; aborting.")
        return 1

    global_weights, scaler = run_in_process(
        [(node.name, node.x_train, node.y_train) for node in nodes],
        rounds=args.rounds,
        local_epochs=FL_LOCAL_EPOCHS,
        learning_rate=FL_LEARNING_RATE,
        l2=FL_L2,
        proximal_mu=args.proximal_mu,
    )

    print()
    print("=" * 78)
    print(
        f"FEDERATED TRANSFER  (pm25, +{FL_HORIZON_HOURS}h, "
        f"{args.rounds} rounds, mu={args.proximal_mu}, fine-tune {FL_FINE_TUNE_EPOCHS} epochs)"
    )
    print("=" * 78)
    print(
        f"{'node':<12} {'stations':>9} {'train':>7} {'test':>6} "
        f"{'local':>8} {'global':>8} {'fine-tuned':>11} {'local head':>11}"
    )
    print("-" * 78)

    comparisons: list[tuple[str, str, float, float, EffectEstimate, Effect]] = []
    for node in nodes:
        train_features = add_bias_column(scaler.transform(node.x_train))
        test_features = add_bias_column(scaler.transform(node.x_test))

        candidates = {
            "local": train_local_only(node, nodes),
            "global": global_weights,
            "fine-tuned": fine_tune(
                global_weights,
                train_features,
                node.y_train,
                epochs=FL_FINE_TUNE_EPOCHS,
                learning_rate=FL_LEARNING_RATE,
                l2=FL_L2,
                proximal_mu=args.proximal_mu,
            ),
            "local head": refit_intercept(global_weights, train_features, node.y_train),
        }
        errors = {
            name: np.abs(test_features @ weights - node.y_test)
            for name, weights in candidates.items()
        }
        local_mae = float(errors["local"].mean())

        print(
            f"{node.name:<12} {node.stations:>9} {len(node.y_train):>7} {len(node.y_test):>6} "
            f"{local_mae:>8.2f} {errors['global'].mean():>8.2f} "
            f"{errors['fine-tuned'].mean():>11.2f} {errors['local head'].mean():>11.2f}"
        )

        for name in ("global", "fine-tuned", "local head"):
            estimate = paired_bootstrap(errors["local"], errors[name], seed=RANDOM_SEED)
            effect = classify(
                estimate, baseline_error=local_mae, tolerance=MODEL_COMPARISON_TOLERANCE
            )
            comparisons.append(
                (node.name, name, local_mae, float(errors[name].mean()), estimate, effect)
            )

    # Every candidate against the node's own model, with a paired bootstrap
    # interval over the held-out rows. A verdict of helped or harmed requires the
    # interval to exclude zero and the effect to clear the practical tolerance;
    # anything else is reported as what it is.
    print()
    print("=" * 78)
    print(
        f"AGAINST EACH NODE'S OWN MODEL  (paired bootstrap, "
        f"{BOOTSTRAP_RESAMPLES} resamples, {BOOTSTRAP_CONFIDENCE:.0%} interval)"
    )
    print("=" * 78)
    print(f"{'node':<10} {'candidate':<11} {'gain ug/m3':>11} {'interval':>19}  verdict")
    print("-" * 78)
    for node_name, name, _, _, estimate, effect in comparisons:
        print(
            f"{node_name:<10} {name:<11} {estimate.gain:>+11.3f} "
            f"[{estimate.low:>+7.3f}, {estimate.high:>+7.3f}]  {effect.value}"
        )

    print()
    established = [c for c in comparisons if c[5] in (Effect.HELPED, Effect.HARMED)]
    if established:
        for node_name, name, _, _, _, effect in established:
            print(f"ESTABLISHED: {name} {effect.value} {node_name}.")
    else:
        print(
            "No candidate is established as helping or harming any node. The differences "
            "above are point estimates the held-out data cannot distinguish from zero, or "
            "real differences too small to act on."
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
