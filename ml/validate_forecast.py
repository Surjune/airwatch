"""Validation of the 24-72 hour concentration forecast.

Answers one question: does a learned forecast beat the two baselines that cost
nothing? Phase 2 already produced a model that lost to plain interpolation, so
the harness is built to detect that outcome rather than to confirm a hope.

**Persistence** forecasts the current value unchanged. **Climatology** forecasts
this station's usual value at the target hour of day. Neither is a strawman:
urban PM2.5 is strongly diurnal, so the daily shape alone is a real forecast.

The split is temporal, not random. A random split would place hours from the
same afternoon on both sides, and autocorrelation would let the model read the
answer off its own neighbours -- yielding an excellent score that says nothing
about forecasting anything. Training uses the earliest days and testing the
latest, which is the only arrangement that mirrors deployment.

One caveat is recorded rather than hidden: target-hour weather here comes from
Open-Meteo's record of what actually happened, whereas a live forecast would use
predicted weather carrying its own error. The figures below are therefore an
optimistic bound on weather-driven skill.

Run with: npm run ml:validate-forecast
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

import lightgbm as lgb
import numpy as np
from sqlalchemy import select

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.core.constants import (  # noqa: E402
    BOOTSTRAP_CONFIDENCE,
    FORECAST_HORIZONS_HOURS,
    FORECAST_LAG_HOURS_SHORT,
    FORECAST_TEST_FRACTION,
    MODEL_COMPARISON_TOLERANCE,
    RANDOM_SEED,
    VALIDATION_DATA_UNTIL,
)
from app.core.enums import Pollutant  # noqa: E402
from app.core.evidence import classify, paired_cluster_bootstrap  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.ml.forecast_features import (  # noqa: E402
    ForecastInputs,
    build_climatology,
    build_features,
    climatology_forecast,
    feature_names,
    persistence_forecast,
)
from app.ml.fusion_features import WeatherContext  # noqa: E402
from app.repositories.models import Measurement, Station, WeatherObservation  # noqa: E402
from app.repositories.session import session_scope  # noqa: E402

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

_NUM_BOOST_ROUNDS = 300

#: Issue hours are sampled rather than taken every hour. Consecutive issue hours
#: produce almost identical feature rows, which inflates the row count without
#: adding information and lets the model over-weight whichever days are densest.
_ISSUE_HOUR_STRIDE = 3


@dataclass(frozen=True, slots=True)
class Sample:
    """One forecast: what was known, what was predicted from it, what happened."""

    station_id: int
    issued_at: datetime
    horizon_hours: int
    features: dict[str, float]
    actual: float
    persistence: float
    climatology: float | None


@dataclass(frozen=True, slots=True)
class Metrics:
    mae: float
    rmse: float
    count: int

    def render(self, label: str) -> str:
        return f"{label:<26} MAE {self.mae:>7.2f}   RMSE {self.rmse:>7.2f}   n={self.count}"


def evaluate(actual: np.ndarray, predicted: np.ndarray) -> Metrics:
    errors = predicted - actual
    return Metrics(
        mae=float(np.mean(np.abs(errors))),
        rmse=float(np.sqrt(np.mean(errors**2))),
        count=len(actual),
    )


def load_series(
    pollutant: Pollutant,
) -> tuple[dict[int, dict[datetime, float]], dict[datetime, WeatherContext], dict[int, str]]:
    """Load each station's hourly series, plus the weather record."""
    series: dict[int, dict[datetime, float]] = defaultdict(dict)
    weather: dict[datetime, WeatherContext] = {}

    with session_scope() as session:
        rows = session.execute(
            select(Measurement.station_id, Measurement.observed_at, Measurement.value_raw).where(
                Measurement.pollutant == pollutant,
                Measurement.is_plausible.is_(True),
                Measurement.observed_at < VALIDATION_DATA_UNTIL,
            )
        ).all()
        for station_id, observed_at, value in rows:
            series[station_id][observed_at] = float(value)

        for record in session.execute(
            select(WeatherObservation).where(
                WeatherObservation.observed_at < VALIDATION_DATA_UNTIL
            )
        ).scalars():
            weather[record.observed_at] = WeatherContext(
                wind_u=record.wind_u,
                wind_v=record.wind_v,
                temperature_c=record.temperature_c,
                relative_humidity_pct=record.relative_humidity_pct,
                pbl_height_m=record.pbl_height_m,
            )

        names = {
            int(station_id): str(name)
            for station_id, name in session.execute(select(Station.id, Station.name)).all()
        }

    return series, weather, names


def _weather_near(
    at_time: datetime, weather: dict[datetime, WeatherContext]
) -> WeatherContext | None:
    """Weather within half an hour of a time, since bins do not align."""
    exact = weather.get(at_time)
    if exact is not None:
        return exact
    for candidate, record in weather.items():
        if abs((candidate - at_time).total_seconds()) <= 1800:
            return record
    return None


def build_samples(
    series: dict[int, dict[datetime, float]],
    weather: dict[datetime, WeatherContext],
    horizons: tuple[int, ...],
) -> list[Sample]:
    """Build one sample per station, issue hour and horizon."""
    samples: list[Sample] = []

    for station_id, history in series.items():
        if len(history) < 2:
            continue
        ordered = sorted(history)
        climatology = build_climatology(history)

        for index in range(0, len(ordered), _ISSUE_HOUR_STRIDE):
            issued_at = ordered[index]

            # Only observations up to the issue hour may be visible. Slicing
            # this is the whole integrity of the exercise: one later value in
            # scope turns forecasting into reading the answer.
            known = {when: value for when, value in history.items() if when <= issued_at}
            if not known:
                continue

            inputs = ForecastInputs(
                history=known,
                climatology=build_climatology(known) or climatology,
                issue_weather=_weather_near(issued_at, weather),
                target_weather=None,
            )

            for horizon in horizons:
                target_time = issued_at + timedelta(hours=horizon)
                actual = _actual_at(history, target_time)
                if actual is None:
                    continue

                target_inputs = ForecastInputs(
                    history=known,
                    climatology=inputs.climatology,
                    issue_weather=inputs.issue_weather,
                    target_weather=_weather_near(target_time, weather),
                )
                features = build_features(target_inputs, issued_at, horizon)
                if features is None:
                    continue

                baseline = persistence_forecast(target_inputs, issued_at)
                if baseline is None:
                    continue

                samples.append(
                    Sample(
                        station_id=station_id,
                        issued_at=issued_at,
                        horizon_hours=horizon,
                        features=features,
                        actual=actual,
                        persistence=baseline,
                        climatology=climatology_forecast(target_inputs, issued_at, horizon),
                    )
                )

    return samples


def _actual_at(history: dict[datetime, float], target_time: datetime) -> float | None:
    """The observation closest to the target hour, within 45 minutes."""
    exact = history.get(target_time)
    if exact is not None:
        return exact
    for observed_at, value in history.items():
        if abs((observed_at - target_time).total_seconds()) <= 2700:
            return value
    return None


def split_temporally(
    samples: list[Sample], test_fraction: float
) -> tuple[list[Sample], list[Sample]]:
    """Split by issue time, training on the earliest and testing on the latest."""
    if not samples:
        return [], []
    issue_times = sorted({sample.issued_at for sample in samples})
    cutoff = issue_times[int(len(issue_times) * (1 - test_fraction))]
    train = [s for s in samples if s.issued_at < cutoff]
    test = [s for s in samples if s.issued_at >= cutoff]
    return train, test


def evaluate_horizon(train: list[Sample], test: list[Sample], columns: tuple[str, ...]) -> None:
    """Train on the earlier period and report every method against the later one.

    Two framings are tried. The absolute model predicts the concentration; the
    residual model predicts the departure from this station's climatology and
    adds it back.

    The residual framing is the physically motivated one: concentration is
    roughly a climatological daily pattern modulated by the weather, and the
    modulation -- a collapsed boundary layer making an ordinary Tuesday twice as
    bad -- is exactly what climatology cannot express and a weather-fed model
    should. Learning the departure lets the model spend its capacity there
    instead of relearning a daily cycle the baseline already supplies.
    """
    if not train or not test:
        print("  insufficient data for this horizon")
        return

    x_train = np.array([[s.features[name] for name in columns] for s in train])
    y_train = np.array([s.actual for s in train])
    x_test = np.array([[s.features[name] for name in columns] for s in test])
    y_test = np.array([s.actual for s in test])

    persistence_metrics = evaluate(y_test, np.array([s.persistence for s in test]))
    print(f"  {persistence_metrics.render('persistence')}")

    climatology_rows = [s for s in test if s.climatology is not None]
    if climatology_rows:
        climatology_metrics = evaluate(
            np.array([s.actual for s in climatology_rows]),
            np.array([s.climatology for s in climatology_rows]),
        )
        print(f"  {climatology_metrics.render('climatology')}")
        best_baseline = min(persistence_metrics.mae, climatology_metrics.mae)
    else:
        best_baseline = persistence_metrics.mae

    outcomes: dict[str, Metrics] = {}
    has_climatology = np.array([s.climatology is not None for s in test])
    # Absolute errors on the rows every method can be scored on, so each
    # comparison against climatology is paired row for row.
    paired_errors: dict[str, np.ndarray] = {}
    if climatology_rows:
        truth_rows = np.array([s.actual for s in climatology_rows])
        paired_errors["climatology"] = np.abs(
            np.array([float(s.climatology or 0.0) for s in climatology_rows]) - truth_rows
        )
        paired_errors["persistence"] = np.abs(
            np.array([s.persistence for s in climatology_rows]) - truth_rows
        )
    station_ids = np.array([s.station_id for s in climatology_rows])

    for mode in ("absolute", "residual"):
        if mode == "residual":
            # Only rows where both sides have a climatology can be reframed.
            usable_train = [s for s in train if s.climatology is not None]
            usable_test = [s for s in test if s.climatology is not None]
            if not usable_train or not usable_test:
                continue
            xs_train = np.array([[s.features[n] for n in columns] for s in usable_train])
            ys_train = np.array([s.actual - float(s.climatology or 0.0) for s in usable_train])
            xs_test = np.array([[s.features[n] for n in columns] for s in usable_test])
            truth = np.array([s.actual for s in usable_test])
            offsets = np.array([float(s.climatology or 0.0) for s in usable_test])
        else:
            xs_train, ys_train, xs_test = x_train, y_train, x_test
            truth = y_test
            offsets = np.zeros_like(y_test)

        model = lgb.train(
            _MODEL_PARAMS,
            lgb.Dataset(xs_train, label=ys_train, feature_name=list(columns)),
            num_boost_round=_NUM_BOOST_ROUNDS,
        )
        predicted = offsets + np.asarray(model.predict(xs_test))
        outcomes[mode] = evaluate(truth, predicted)
        print(f"  {outcomes[mode].render(f'LightGBM ({mode})')}")
        if climatology_rows:
            # The residual model is scored only on climatology rows already; the
            # absolute model is narrowed to them so the pairing holds.
            on_rows = predicted if mode == "residual" else predicted[has_climatology]
            paired_errors[f"LightGBM ({mode})"] = np.abs(on_rows - truth_rows)

    if "climatology" not in paired_errors:
        return

    # Every other method against climatology, resampling whole stations: a
    # station's forecasts share its climate and its sensor, so the effective
    # sample is the station count rather than the row count.
    print(
        f"  against climatology  (station-level bootstrap, {BOOTSTRAP_CONFIDENCE:.0%} "
        "interval; positive gain means better than climatology)"
    )
    for name, errors in paired_errors.items():
        if name == "climatology":
            continue
        estimate = paired_cluster_bootstrap(
            paired_errors["climatology"], errors, station_ids, seed=RANDOM_SEED
        )
        effect = classify(
            estimate,
            baseline_error=float(paired_errors["climatology"].mean()),
            tolerance=MODEL_COMPARISON_TOLERANCE,
        )
        print(
            f"    {name:<22} gain {estimate.gain:+.3f}  "
            f"[{estimate.low:+.3f}, {estimate.high:+.3f}]  over {estimate.samples} stations  "
            f"{effect.value}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Forecast validation against baselines")
    parser.add_argument(
        "--pollutant",
        choices=[member.value for member in Pollutant],
        default=Pollutant.PM25.value,
    )
    args = parser.parse_args()
    configure_logging(level="WARNING", json_output=False)

    pollutant = Pollutant(args.pollutant)
    series, weather, _ = load_series(pollutant)
    print(f"stations with a series : {len(series)}")
    print(f"weather hours          : {len(weather)}")

    samples = build_samples(series, weather, FORECAST_HORIZONS_HOURS)
    print(f"forecast samples       : {len(samples)}\n")

    if not samples:
        print("No samples could be built. Run `npm run backfill` first.")
        return 1

    columns = feature_names(FORECAST_LAG_HOURS_SHORT)

    print("=" * 78)
    print(f"FORECAST VALIDATION  ({pollutant.value}, ug/m3, temporal holdout)")
    print("=" * 78)

    for horizon in FORECAST_HORIZONS_HOURS:
        at_horizon = [s for s in samples if s.horizon_hours == horizon]
        train, test = split_temporally(at_horizon, FORECAST_TEST_FRACTION)
        print(f"\n{horizon}h horizon   (train {len(train)}, test {len(test)})")
        evaluate_horizon(train, test, columns)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
