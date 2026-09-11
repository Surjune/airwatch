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
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(BACKEND), str(ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from federated.strategy import (  # noqa: E402
    LocalUpdate,
    TransferOutcome,
    add_bias_column,
    aggregate_statistics,
    compute_statistics,
    federated_average,
    mean_absolute_error,
    train_local,
)

from app.core.constants import (  # noqa: E402
    FL_MIN_AVAILABLE_CLIENTS,
    FL_NEGATIVE_TRANSFER_TOLERANCE,
    FL_NUM_ROUNDS,
    FL_PROXIMAL_MU,
    FORECAST_LAG_HOURS_SHORT,
    FORECAST_TEST_FRACTION,
    RANDOM_SEED,
)
from app.core.enums import Pollutant  # noqa: E402
from app.core.geo import haversine_distance_m  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.ml.forecast_features import (  # noqa: E402
    FEDERATED_EXCLUDED_PREFIXES,
    ForecastInputs,
    build_climatology,
    build_features,
    feature_names,
)
from app.repositories.models import Measurement, Station  # noqa: E402
from app.repositories.session import session_scope  # noqa: E402

#: City centres. A station belongs to the nearest centre within the radius.
CITY_CENTRES: dict[str, tuple[float, float]] = {
    "delhi": (77.2090, 28.6139),
    "kanpur": (80.3319, 26.4499),
    "coimbatore": (76.9558, 11.0168),
}

#: Radius, in metres, within which a station is assigned to a city.
_CITY_RADIUS_M = 40_000.0

#: Forecast horizon used for the federated task. One horizon keeps the
#: comparison between local and global models clean.
_HORIZON_HOURS = 24

#: Issue-hour stride, matching the forecast validation.
_ISSUE_STRIDE = 3


_LOCAL_EPOCHS = 30
_LEARNING_RATE = 0.05
_L2 = 0.01


@dataclass(slots=True)
class NodeData:
    """One city's training and test matrices."""

    name: str
    x_train: np.ndarray
    y_train: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    stations: int


def federated_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    """Restrict the feature set to what every node can compute.

    The exclusion list is defined alongside the model in
    ``app.ml.forecast_features`` so the schema this experiment trains on and the
    schema a node publishes in its model card cannot drift apart.
    """
    return tuple(
        name for name in columns if not name.startswith(FEDERATED_EXCLUDED_PREFIXES)
    )


def assign_city(position: tuple[float, float]) -> str | None:
    """Assign a station to the nearest pilot city, if any is close enough."""
    best: tuple[str, float] | None = None
    for city, centre in CITY_CENTRES.items():
        distance = haversine_distance_m(position, centre)
        if distance <= _CITY_RADIUS_M and (best is None or distance < best[1]):
            best = (city, distance)
    return best[0] if best else None


def load_city_series(
    pollutant: Pollutant,
) -> tuple[dict[str, dict[int, dict[datetime, float]]], dict[str, int]]:
    """Load each city's per-station hourly series."""
    by_city: dict[str, dict[int, dict[datetime, float]]] = defaultdict(lambda: defaultdict(dict))
    station_counts: dict[str, int] = defaultdict(int)

    with session_scope() as session:
        positions = {
            station_id: (float(lon), float(lat))
            for station_id, lon, lat in session.execute(
                select(Station.id, Station.geom.ST_X(), Station.geom.ST_Y())
            ).all()
        }
        rows = session.execute(
            select(Measurement.station_id, Measurement.observed_at, Measurement.value_raw).where(
                Measurement.pollutant == pollutant,
                Measurement.is_plausible.is_(True),
            )
        ).all()

    seen: dict[str, set[int]] = defaultdict(set)
    for station_id, observed_at, value in rows:
        position = positions.get(station_id)
        if position is None:
            continue
        city = assign_city(position)
        if city is None:
            continue
        by_city[city][station_id][observed_at] = float(value)
        seen[city].add(station_id)

    for city, station_ids in seen.items():
        station_counts[city] = len(station_ids)

    return by_city, station_counts


def build_node(
    name: str,
    series: dict[int, dict[datetime, float]],
    columns: tuple[str, ...],
    stations: int,
) -> NodeData | None:
    """Build one city's forecast matrices, split temporally."""
    rows: list[tuple[datetime, list[float], float]] = []

    for history in series.values():
        if len(history) < 2:
            continue
        ordered = sorted(history)

        for index in range(0, len(ordered), _ISSUE_STRIDE):
            issued_at = ordered[index]
            known = {when: value for when, value in history.items() if when <= issued_at}
            if not known:
                continue

            target = _actual_near(history, issued_at, _HORIZON_HOURS)
            if target is None:
                continue

            inputs = ForecastInputs(
                history=known,
                climatology=build_climatology(known),
                issue_weather=None,
                target_weather=None,
            )
            features = build_features(inputs, issued_at, _HORIZON_HOURS)
            if features is None:
                continue

            vector = [features[name] for name in columns]
            if any(np.isnan(vector)):
                # A node cannot train on rows with missing lags, and imputing
                # them would put invented history into a federated model that
                # other cities then inherit.
                continue
            rows.append((issued_at, vector, target))

    if len(rows) < 20:
        return None

    rows.sort(key=lambda row: row[0])
    issue_times = sorted({row[0] for row in rows})
    cutoff = issue_times[int(len(issue_times) * (1 - FORECAST_TEST_FRACTION))]

    train = [row for row in rows if row[0] < cutoff]
    test = [row for row in rows if row[0] >= cutoff]
    if not train or not test:
        return None

    return NodeData(
        name=name,
        x_train=np.array([row[1] for row in train]),
        y_train=np.array([row[2] for row in train]),
        x_test=np.array([row[1] for row in test]),
        y_test=np.array([row[2] for row in test]),
        stations=stations,
    )


def _actual_near(
    history: dict[datetime, float], issued_at: datetime, horizon_hours: int
) -> float | None:
    """The observation nearest the target hour, within 45 minutes."""
    target_time = issued_at + timedelta(hours=horizon_hours)
    exact = history.get(target_time)
    if exact is not None:
        return exact
    for observed_at, value in history.items():
        if abs((observed_at - target_time).total_seconds()) <= 2700:
            return value
    return None


def run_federation(nodes: list[NodeData], rounds: int, proximal_mu: float) -> np.ndarray:
    """Run FedAvg across the nodes and return the global weights."""
    scaler = aggregate_statistics([compute_statistics(node.x_train) for node in nodes])
    n_features = nodes[0].x_train.shape[1] + 1  # plus the bias column
    global_weights = np.zeros(n_features)

    for _ in range(rounds):
        updates = []
        for node in nodes:
            features = add_bias_column(scaler.transform(node.x_train))
            weights = train_local(
                features,
                node.y_train,
                initial_weights=global_weights,
                global_weights=global_weights,
                epochs=_LOCAL_EPOCHS,
                learning_rate=_LEARNING_RATE,
                l2=_L2,
                proximal_mu=proximal_mu,
            )
            updates.append(
                LocalUpdate(node=node.name, weights=weights, sample_count=len(node.y_train))
            )
        global_weights = federated_average(updates)

    return global_weights


def train_local_only(node: NodeData, scaler_source: list[NodeData]) -> np.ndarray:
    """Train a node entirely on its own data, as the comparison baseline."""
    scaler = aggregate_statistics([compute_statistics(n.x_train) for n in scaler_source])
    features = add_bias_column(scaler.transform(node.x_train))
    weights: np.ndarray = train_local(
        features,
        node.y_train,
        initial_weights=np.zeros(features.shape[1]),
        epochs=_LOCAL_EPOCHS * FL_NUM_ROUNDS,
        learning_rate=_LEARNING_RATE,
        l2=_L2,
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
    series, station_counts = load_city_series(Pollutant.PM25)

    print(f"shared feature schema: {len(columns)} features every node can compute")
    print("city data available:")
    for city in CITY_CENTRES:
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

    global_weights = run_federation(nodes, args.rounds, args.proximal_mu)
    scaler = aggregate_statistics([compute_statistics(node.x_train) for node in nodes])

    print("\n" + "=" * 78)
    print(
        f"FEDERATED TRANSFER  (pm25, +{_HORIZON_HOURS}h, "
        f"{args.rounds} rounds, mu={args.proximal_mu})"
    )
    print("=" * 78)
    print(
        f"{'node':<12} {'stations':>9} {'train':>7} {'test':>6} "
        f"{'local MAE':>10} {'global MAE':>11} {'change':>9}"
    )
    print("-" * 78)

    outcomes: list[TransferOutcome] = []
    for node in nodes:
        local_weights = train_local_only(node, nodes)
        test_features = add_bias_column(scaler.transform(node.x_test))

        outcome = TransferOutcome(
            node=node.name,
            local_mae=mean_absolute_error(test_features, node.y_test, local_weights),
            global_mae=mean_absolute_error(test_features, node.y_test, global_weights),
        )
        outcomes.append(outcome)
        print(
            f"{node.name:<12} {node.stations:>9} {len(node.y_train):>7} {len(node.y_test):>6} "
            f"{outcome.local_mae:>10.2f} {outcome.global_mae:>11.2f} "
            f"{outcome.improvement * 100:>8.1f}%"
        )

    print()
    harmed = [o for o in outcomes if o.is_harmed(FL_NEGATIVE_TRANSFER_TOLERANCE)]
    helped = [o for o in outcomes if o.improvement > 0]

    for outcome in outcomes:
        verdict = (
            "harmed by federation"
            if outcome.is_harmed(FL_NEGATIVE_TRANSFER_TOLERANCE)
            else ("helped" if outcome.improvement > 0 else "unchanged within tolerance")
        )
        print(f"  {outcome.node:<12} {verdict}")

    print()
    if harmed:
        print(
            f"NEGATIVE TRANSFER: {len(harmed)} node(s) are worse off federated "
            f"({', '.join(o.node for o in harmed)}). They should keep their local model."
        )
    elif helped:
        print(f"Federation helped {len(helped)} of {len(outcomes)} nodes without harming any.")
    else:
        print("Federation neither helped nor harmed any node measurably.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
