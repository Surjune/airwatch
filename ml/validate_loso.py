"""Leave-one-station-out validation of the fused concentration surface.

The headline credibility check. The premise of the whole project is that a dense
estimate can be reconstructed for places with no monitor. This tests exactly
that, on real data: hide one real CPCB station entirely, estimate its cell from
the remaining network, and compare against what that station actually recorded.

Two properties make the result honest:

* **The held-out station never appears in its own features.** Its readings are
  removed from the neighbour set for every hour it is being predicted, so the
  answer cannot leak into the question.
* **The held-out station never appears in training either.** A model that had
  seen this station's readings at other hours would have learned its personal
  bias, and the score would flatter the method.

The learned model is compared against plain inverse-distance weighting. If it
cannot beat IDW, it is complexity with no accuracy and should be dropped; the
report says so either way.

Run with: npm run ml:validate-loso
"""

# This script reports to a terminal; the printed table is its product, and
# routing it through the structured logger would make it less legible.
# ruff: noqa: T201

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import lightgbm as lgb
import numpy as np
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.constants import (  # noqa: E402
    BOOTSTRAP_CONFIDENCE,
    BOOTSTRAP_RESAMPLES,
    MODEL_COMPARISON_TOLERANCE,
    RANDOM_SEED,
    VALIDATION_DATA_UNTIL,
)
from app.core.enums import Pollutant, StationTier  # noqa: E402
from app.core.evidence import Effect, classify, paired_cluster_bootstrap  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.ml.fusion_features import (  # noqa: E402
    FEATURE_NAMES,
    StationReading,
    WeatherContext,
    build_features,
)
from app.repositories.models import Measurement, Station, WeatherObservation  # noqa: E402
from app.repositories.session import session_scope  # noqa: E402

#: LightGBM settings. Deliberately small: the training set is thousands of rows,
#: not millions, and a deeper model would memorise the network rather than learn
#: the spatial relationship that has to generalise to unmonitored ground.
_MODEL_PARAMS: dict[str, object] = {
    "objective": "regression",
    "metric": "mae",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 40,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "verbosity": -1,
    "seed": RANDOM_SEED,
}

#: Boosting rounds. Fixed rather than early-stopped, because an early-stopping
#: split carved out of the training stations would leak across folds.
_NUM_BOOST_ROUNDS = 300

#: Stations with fewer usable hours than this are not scored. A fold built from
#: a handful of hours produces a metric dominated by which hours they happened
#: to be.
_MIN_HOURS_PER_STATION = 24


@dataclass(frozen=True, slots=True)
class Sample:
    """One cell-hour: the features, the truth, and which station was hidden."""

    station_id: int
    observed_at: datetime
    features: dict[str, float]
    actual: float


@dataclass(frozen=True, slots=True)
class Metrics:
    """Error of a set of predictions against the truth."""

    mae: float
    rmse: float
    r2: float
    count: int

    def render(self, label: str) -> str:
        return (
            f"{label:<28} MAE {self.mae:>7.2f}   RMSE {self.rmse:>7.2f}   "
            f"R2 {self.r2:>6.3f}   n={self.count}"
        )


def evaluate(actual: np.ndarray, predicted: np.ndarray) -> Metrics:
    """Compute error metrics for a set of predictions."""
    errors = predicted - actual
    mae = float(np.mean(np.abs(errors)))
    rmse = float(np.sqrt(np.mean(errors**2)))
    total_variance = float(np.sum((actual - actual.mean()) ** 2))
    residual = float(np.sum(errors**2))
    # R2 is undefined when the truth has no variance; report 0 rather than
    # dividing by zero and printing a nonsensical figure.
    r2 = 1.0 - residual / total_variance if total_variance > 0 else 0.0
    return Metrics(mae=mae, rmse=rmse, r2=r2, count=len(actual))


def load_observations(
    pollutant: Pollutant,
) -> tuple[dict[datetime, list[StationReading]], dict[datetime, WeatherContext]]:
    """Load every stored reading for a pollutant, grouped by hour."""
    by_hour: dict[datetime, list[StationReading]] = defaultdict(list)
    weather_by_hour: dict[datetime, WeatherContext] = {}

    with session_scope() as session:
        rows = session.execute(
            select(
                Measurement.observed_at,
                Measurement.station_id,
                Measurement.value_raw,
                Station.geom,
            )
            .join(Station, Station.id == Measurement.station_id)
            .where(
                Station.tier == StationTier.REFERENCE,
                Measurement.pollutant == pollutant,
                Measurement.is_plausible.is_(True),
                Measurement.observed_at < VALIDATION_DATA_UNTIL,
            )
        ).all()

        # Coordinates come back as WKB; ask PostGIS for them as numbers instead.
        coordinates = {
            station_id: (float(lon), float(lat))
            for station_id, lon, lat in session.execute(
                select(
                    Station.id,
                    Station.geom.ST_X(),
                    Station.geom.ST_Y(),
                )
            ).all()
        }

        for observed_at, station_id, value, _ in rows:
            position = coordinates.get(station_id)
            if position is None:
                continue
            by_hour[observed_at].append(
                StationReading(station_id=station_id, coordinates=position, value=float(value))
            )

        for weather in session.execute(
            select(WeatherObservation).where(WeatherObservation.observed_at < VALIDATION_DATA_UNTIL)
        ).scalars():
            weather_by_hour[weather.observed_at] = WeatherContext(
                wind_u=weather.wind_u,
                wind_v=weather.wind_v,
                temperature_c=weather.temperature_c,
                relative_humidity_pct=weather.relative_humidity_pct,
                pbl_height_m=weather.pbl_height_m,
            )

    return by_hour, weather_by_hour


def build_samples(
    by_hour: dict[datetime, list[StationReading]],
    weather_by_hour: dict[datetime, WeatherContext],
) -> list[Sample]:
    """Build one sample per station-hour, holding that station out of its own features."""
    samples: list[Sample] = []

    for observed_at, readings in by_hour.items():
        if len(readings) <= 1:
            continue
        weather = _nearest_weather(observed_at, weather_by_hour)

        for target in readings:
            # The held-out station is removed from its own neighbour set. Leaving
            # it in would let the model read the answer off the features.
            neighbours = [r for r in readings if r.station_id != target.station_id]
            features = build_features(target.coordinates, neighbours, observed_at, weather)
            if features is None:
                continue
            samples.append(
                Sample(
                    station_id=target.station_id,
                    observed_at=observed_at,
                    features=features,
                    actual=target.value,
                )
            )

    return samples


def _nearest_weather(
    observed_at: datetime, weather_by_hour: dict[datetime, WeatherContext]
) -> WeatherContext | None:
    """Find the weather record for an hour.

    Indian stations report on IST-aligned bins that fall on :30 past the UTC
    hour, while the weather is on the UTC hour, so an exact match usually fails
    and the closest record within the hour is used instead.
    """
    exact = weather_by_hour.get(observed_at)
    if exact is not None:
        return exact
    for candidate, weather in weather_by_hour.items():
        if abs((candidate - observed_at).total_seconds()) <= 1800:
            return weather
    return None


@dataclass(frozen=True, slots=True)
class PooledErrors:
    """Per-row absolute errors across every fold, with the station each came from."""

    model: np.ndarray
    baseline: np.ndarray
    stations: np.ndarray


def run_loso(
    samples: list[Sample], *, residual: bool
) -> tuple[Metrics, Metrics, list[tuple[str, Metrics]], PooledErrors]:
    """Run leave-one-station-out validation.

    Args:
        samples: Every station-hour, each already holding its own station out of
            its features.
        residual: When True the model learns the *correction to IDW* rather than
            the concentration itself, and the prediction is
            ``idw_estimate + predicted_residual``.

            This matters more than it looks. Weather here is sampled at one point
            and so is identical across stations within an hour, which means the
            time and weather features together effectively name the hour. Given
            the absolute concentration as a target, the trees can score well on
            training stations by memorising each hour's city-wide level -- and
            that is precisely the thing that cannot generalise to ground the
            network does not cover. Predicting the residual removes that option:
            the level is supplied by IDW, and the model can only add spatial
            correction on top.

    Returns:
        Pooled model metrics, pooled IDW baseline metrics, per-station model
        metrics for the worst folds, and the per-row errors a comparison between
        the two needs.
    """
    by_station: dict[int, list[Sample]] = defaultdict(list)
    for sample in samples:
        by_station[sample.station_id].append(sample)

    eligible = {
        station_id: rows
        for station_id, rows in by_station.items()
        if len(rows) >= _MIN_HOURS_PER_STATION
    }

    feature_index = {name: position for position, name in enumerate(FEATURE_NAMES)}
    all_predictions: list[float] = []
    all_actual: list[float] = []
    all_baseline: list[float] = []
    all_stations: list[int] = []
    per_station: list[tuple[int, Metrics]] = []

    for held_out, test_rows in eligible.items():
        train_rows = [s for s in samples if s.station_id != held_out]
        if not train_rows:
            continue

        x_train = np.array([[s.features[name] for name in FEATURE_NAMES] for s in train_rows])
        y_train = np.array([s.actual for s in train_rows])
        x_test = np.array([[s.features[name] for name in FEATURE_NAMES] for s in test_rows])
        y_test = np.array([s.actual for s in test_rows])

        train_baseline = x_train[:, feature_index["idw_estimate"]]
        baseline = x_test[:, feature_index["idw_estimate"]]

        target = y_train - train_baseline if residual else y_train

        model = lgb.train(
            _MODEL_PARAMS,
            lgb.Dataset(x_train, label=target, feature_name=list(FEATURE_NAMES)),
            num_boost_round=_NUM_BOOST_ROUNDS,
        )
        raw_prediction = model.predict(x_test)
        predicted = baseline + raw_prediction if residual else raw_prediction

        all_predictions.extend(predicted)
        all_actual.extend(y_test)
        all_baseline.extend(baseline)
        all_stations.extend([held_out] * len(y_test))
        per_station.append((held_out, evaluate(y_test, np.asarray(predicted))))

    actual = np.array(all_actual)
    model_metrics = evaluate(actual, np.array(all_predictions))
    baseline_metrics = evaluate(actual, np.array(all_baseline))

    names = _station_names([station_id for station_id, _ in per_station])
    worst = sorted(per_station, key=lambda pair: pair[1].mae, reverse=True)[:5]
    labelled = [(names.get(station_id, str(station_id)), metrics) for station_id, metrics in worst]
    pooled = PooledErrors(
        model=np.abs(np.array(all_predictions) - actual),
        baseline=np.abs(np.array(all_baseline) - actual),
        stations=np.array(all_stations),
    )
    return model_metrics, baseline_metrics, labelled, pooled


def _station_names(station_ids: list[int]) -> dict[int, str]:
    """Look up station names for the report."""
    if not station_ids:
        return {}
    with session_scope() as session:
        return {
            int(station_id): str(name)
            for station_id, name in session.execute(
                select(Station.id, Station.name).where(Station.id.in_(station_ids))
            ).all()
        }


def report_error_conditions(samples: list[Sample]) -> None:
    """Show how IDW error varies with the conditions the estimate was made under.

    A negative modelling result is still useful if the error is *predictable*.
    Knowing that estimates degrade with distance to the nearest station, and with
    disagreement among neighbours, is what lets the surface publish an honest
    uncertainty instead of a uniform one -- and what keeps a poorly-supported
    cell from being displayed with the same confidence as a well-supported one.
    """
    rows = [
        (
            sample.features["nearest_distance_m"],
            sample.features["neighbour_std_k"],
            abs(sample.features["idw_estimate"] - sample.actual),
        )
        for sample in samples
    ]
    if not rows:
        return

    print("")
    print("IDW absolute error by distance to the nearest other station:")
    print(f"  {'distance':<18} {'mean |error|':>13} {'n':>8}")
    edges = [(0, 3000), (3000, 6000), (6000, 10000), (10000, 10**9)]
    for low, high in edges:
        bucket = [error for distance, _, error in rows if low <= distance < high]
        if not bucket:
            continue
        label = f"{low // 1000}-{high // 1000} km" if high < 10**9 else f"{low // 1000}+ km"
        print(f"  {label:<18} {sum(bucket) / len(bucket):>13.2f} {len(bucket):>8}")

    print("")
    print("IDW absolute error by disagreement among the 3 nearest stations:")
    print(f"  {'neighbour spread':<18} {'mean |error|':>13} {'n':>8}")
    spread_edges = [(0, 5), (5, 15), (15, 30), (30, 10**9)]
    for low, high in spread_edges:
        bucket = [error for _, spread, error in rows if low <= spread < high]
        if not bucket:
            continue
        label = f"{low}-{high} ug/m3" if high < 10**9 else f"{low}+ ug/m3"
        print(f"  {label:<18} {sum(bucket) / len(bucket):>13.2f} {len(bucket):>8}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Leave-one-station-out fusion validation")
    parser.add_argument(
        "--pollutant",
        choices=[member.value for member in Pollutant],
        default=Pollutant.PM25.value,
    )
    parser.add_argument(
        "--mode",
        choices=["absolute", "residual", "both"],
        default="both",
        help="Whether the model predicts the concentration, the correction to IDW, or both",
    )
    args = parser.parse_args()
    configure_logging(level="WARNING", json_output=False)

    pollutant = Pollutant(args.pollutant)
    by_hour, weather_by_hour = load_observations(pollutant)
    print(f"loaded {sum(len(v) for v in by_hour.values())} readings across {len(by_hour)} hours")
    print(f"weather hours available: {len(weather_by_hour)}")

    samples = build_samples(by_hour, weather_by_hour)
    stations = {s.station_id for s in samples}
    print(f"built {len(samples)} samples across {len(stations)} stations\n")

    if not samples:
        print("No samples could be built. Run `npm run backfill` first.")
        return 1

    modes = ["absolute", "residual"] if args.mode == "both" else [args.mode]
    outcomes: dict[str, Metrics] = {}
    pooled: dict[str, PooledErrors] = {}
    baseline_metrics: Metrics | None = None
    worst: list[tuple[str, Metrics]] = []

    for mode in modes:
        outcomes[mode], baseline_metrics, worst, pooled[mode] = run_loso(
            samples, residual=(mode == "residual")
        )

    if baseline_metrics is None:  # pragma: no cover - modes is never empty.
        return 1

    print("=" * 78)
    print(f"LEAVE-ONE-STATION-OUT VALIDATION  ({pollutant.value}, ug/m3)")
    print("=" * 78)
    print(baseline_metrics.render("IDW baseline"))
    for mode, metrics in outcomes.items():
        print(metrics.render(f"LightGBM ({mode})"))

    # Each learned model against IDW, with the interval resampling whole held-out
    # stations. Rows from one station are not independent -- a station that is
    # hard to reconstruct is hard every hour -- so the effective sample is the
    # station count, not the row count.
    print()
    print(
        f"AGAINST IDW  (station-level bootstrap, {BOOTSTRAP_RESAMPLES} resamples, "
        f"{BOOTSTRAP_CONFIDENCE:.0%} interval; positive gain means the model is better)"
    )
    verdicts: dict[str, Effect] = {}
    for mode, errors in pooled.items():
        estimate = paired_cluster_bootstrap(
            errors.baseline, errors.model, errors.stations, seed=RANDOM_SEED
        )
        verdicts[mode] = classify(
            estimate, baseline_error=baseline_metrics.mae, tolerance=MODEL_COMPARISON_TOLERANCE
        )
        print(
            f"  LightGBM ({mode:<8})  gain {estimate.gain:+.3f} ug/m3  "
            f"[{estimate.low:+.3f}, {estimate.high:+.3f}]  over {estimate.samples} stations  "
            f"{verdicts[mode].value}"
        )

    print()
    if any(effect is Effect.HELPED for effect in verdicts.values()):
        print("A learned model is established as better than IDW.")
    elif all(effect is Effect.HARMED for effect in verdicts.values()):
        # Reported plainly rather than buried. A model that loses to
        # interpolation is complexity with no accuracy, and shipping it anyway
        # would mean publishing worse numbers with more confidence.
        print("Every learned model is established as worse than IDW. Ship IDW.")
    else:
        print(
            "No learned model is established as better than IDW. Ship IDW: without "
            "evidence of a gain, the simpler estimator is the one to trust."
        )

    best = min(outcomes.values(), key=lambda metrics: metrics.mae)

    report_error_conditions(samples)

    print("\nworst folds by MAE (hardest stations to reconstruct):")
    for name, metrics in worst:
        print(f"  {metrics.mae:>7.2f}  {name[:52]}")

    print(f"\nInterpretation: on unseen ground the estimate is within ~{best.mae:.0f}")
    print("ug/m3 of truth. CPCB's Moderate band alone spans 30 ug/m3 of PM2.5.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
