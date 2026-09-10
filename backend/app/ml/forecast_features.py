"""Feature construction for the 24-72 hour concentration forecast.

Pure functions over plain data, shared by training and inference so a model is
served the features it was trained on.

The forecast exists to move an alert *before* exposure. A 24-hour AQI published
after the fact tells people what they already breathed; a corridor forecast lets
a school move sports indoors and an authority pre-position an inspection.

Two things about the framing matter more than the model:

**What is known at issue time.** A forecast issued at hour ``t`` for ``t+24``
may use observations up to ``t`` and the *weather forecast* for ``t+24`` --
which is genuinely available, since meteorological forecasts run days ahead.
It may not use pollutant observations after ``t``. Every lag here is measured
backwards from the issue hour for exactly that reason.

**What has to be beaten.** Persistence and diurnal climatology are not
strawmen, they are the honest competition. Urban PM2.5 has a strong daily cycle,
so "the same hour yesterday" is a genuinely good forecast and a model that
cannot beat it is not worth deploying.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from app.core.constants import (
    DAYS_PER_WEEK,
    FORECAST_LAG_HOURS_SHORT,
    FORECAST_MIN_CLIMATOLOGY_OBSERVATIONS,
    HOURS_PER_DAY,
)
from app.ml.fusion_features import WeatherContext

#: Window, in hours, of the trailing average summarising recent conditions.
_RECENT_WINDOW_HOURS: Final[int] = 24

#: How close an observation must be to the requested lag hour to count, in
#: minutes. Indian stations report on IST-aligned bins that fall on :30 past the
#: UTC hour, so an exact-timestamp lookup would miss almost every lag.
_LAG_TOLERANCE_MINUTES: Final[int] = 45


@dataclass(frozen=True, slots=True)
class ForecastInputs:
    """Everything known at issue time for one station.

    Attributes:
        history: Observations keyed by hour, up to and including the issue hour.
            Anything later is a leak and must not be present.
        climatology: Mean concentration by hour of day for this station, or an
            empty mapping when there is too little history to build one.
        issue_weather: Meteorology at the issue hour.
        target_weather: Forecast meteorology at the target hour. Available in
            production because weather forecasts run days ahead.
    """

    history: Mapping[datetime, float]
    climatology: Mapping[int, float]
    issue_weather: WeatherContext | None
    target_weather: WeatherContext | None


def build_climatology(
    history: Mapping[datetime, float],
    *,
    min_observations: int = FORECAST_MIN_CLIMATOLOGY_OBSERVATIONS,
) -> dict[int, float]:
    """Average concentration by hour of day.

    This is the diurnal cycle: traffic peaks, the overnight collapse of the
    boundary layer, the afternoon flush. It is both a feature and one of the
    baselines the model has to beat.

    Args:
        history: Observations keyed by hour.
        min_observations: Fewest observations required overall.

    Returns:
        Hour of day to mean concentration, or an empty mapping when there is too
        little history for the means to describe a daily cycle rather than the
        few days that happened to be observed.
    """
    if len(history) < min_observations:
        return {}

    totals: dict[int, float] = {}
    counts: dict[int, int] = {}
    for observed_at, value in history.items():
        hour = observed_at.hour
        totals[hour] = totals.get(hour, 0.0) + value
        counts[hour] = counts.get(hour, 0) + 1

    return {hour: totals[hour] / counts[hour] for hour in totals}


def _lookup(history: Mapping[datetime, float], at_time: datetime) -> float | None:
    """Find the observation closest to a time, within the lag tolerance."""
    exact = history.get(at_time)
    if exact is not None:
        return exact

    tolerance = timedelta(minutes=_LAG_TOLERANCE_MINUTES)
    best_value: float | None = None
    best_gap = tolerance
    for observed_at, value in history.items():
        gap = abs(observed_at - at_time)
        if gap <= best_gap:
            best_gap = gap
            best_value = value
    return best_value


def feature_names(lags: Sequence[int] = FORECAST_LAG_HOURS_SHORT) -> tuple[str, ...]:
    """Feature names in the order the model receives them.

    Order is part of the contract between training and inference; a silently
    reordered vector produces confident, meaningless forecasts.
    """
    return (
        "current_value",
        *(f"lag_{hours}h" for hours in lags),
        "recent_mean_24h",
        "recent_change_24h",
        "climatology_target_hour",
        "climatology_issue_hour",
        "horizon_hours",
        "target_hour_sin",
        "target_hour_cos",
        "target_weekday_sin",
        "target_weekday_cos",
        "target_wind_u",
        "target_wind_v",
        "target_wind_speed",
        "target_pbl_height_m",
        "target_relative_humidity_pct",
        "target_temperature_c",
        "target_precipitation_mm",
        "issue_wind_speed",
        "issue_pbl_height_m",
    )


def build_features(
    inputs: ForecastInputs,
    issued_at: datetime,
    horizon_hours: int,
    *,
    lags: Sequence[int] = FORECAST_LAG_HOURS_SHORT,
) -> dict[str, float] | None:
    """Build the feature vector for one forecast.

    Args:
        inputs: Everything known at issue time.
        issued_at: The hour the forecast is made, in UTC.
        horizon_hours: How far ahead the forecast reaches.
        lags: Lag hours to include, measured back from the issue hour.

    Returns:
        A feature mapping, or None when the most recent observation is missing.
        Without the current value there is nothing to forecast from, and the
        station is skipped rather than given an invented starting point.
    """
    target_time = issued_at + timedelta(hours=horizon_hours)

    current = _lookup(inputs.history, issued_at)
    if current is None:
        return None

    features: dict[str, float] = {"current_value": current}
    for hours in lags:
        # Lag h is the observation h hours *before* the issue hour. Offsetting
        # these by one would relabel the current value as lag_1h and shift every
        # other lag with it, which no downstream check could detect.
        value = _lookup(inputs.history, issued_at - timedelta(hours=hours))
        features[f"lag_{hours}h"] = value if value is not None else math.nan

    recent = [
        value
        for observed_at, value in inputs.history.items()
        if issued_at - timedelta(hours=_RECENT_WINDOW_HOURS) <= observed_at <= issued_at
    ]
    features["recent_mean_24h"] = sum(recent) / len(recent) if recent else math.nan

    day_ago = _lookup(inputs.history, issued_at - timedelta(hours=HOURS_PER_DAY))
    # Direction of travel over the last day, which separates a station on the way
    # up from one at the same level on the way down.
    features["recent_change_24h"] = current - day_ago if day_ago is not None else math.nan

    features["climatology_target_hour"] = inputs.climatology.get(target_time.hour, math.nan)
    features["climatology_issue_hour"] = inputs.climatology.get(issued_at.hour, math.nan)
    features["horizon_hours"] = float(horizon_hours)

    # Cyclical encoding so hour 23 neighbours hour 0.
    hour_angle = 2 * math.pi * target_time.hour / HOURS_PER_DAY
    weekday_angle = 2 * math.pi * target_time.weekday() / DAYS_PER_WEEK
    features["target_hour_sin"] = math.sin(hour_angle)
    features["target_hour_cos"] = math.cos(hour_angle)
    features["target_weekday_sin"] = math.sin(weekday_angle)
    features["target_weekday_cos"] = math.cos(weekday_angle)

    _add_weather(features, "target", inputs.target_weather)
    _add_issue_weather(features, inputs.issue_weather)

    return features


def _add_weather(features: dict[str, float], prefix: str, weather: WeatherContext | None) -> None:
    """Add the forecast weather at the target hour."""
    if weather is None:
        for suffix in (
            "wind_u",
            "wind_v",
            "wind_speed",
            "pbl_height_m",
            "relative_humidity_pct",
            "temperature_c",
            "precipitation_mm",
        ):
            features[f"{prefix}_{suffix}"] = math.nan
        return

    features[f"{prefix}_wind_u"] = weather.wind_u
    features[f"{prefix}_wind_v"] = weather.wind_v
    features[f"{prefix}_wind_speed"] = math.hypot(weather.wind_u, weather.wind_v)
    # The boundary layer is the single most useful meteorological predictor: it
    # sets the volume the same emissions are diluted into, so a collapse to
    # 100 m at night multiplies concentration without any change in emission.
    features[f"{prefix}_pbl_height_m"] = (
        weather.pbl_height_m if weather.pbl_height_m is not None else math.nan
    )
    features[f"{prefix}_relative_humidity_pct"] = weather.relative_humidity_pct
    features[f"{prefix}_temperature_c"] = weather.temperature_c
    features[f"{prefix}_precipitation_mm"] = 0.0


def _add_issue_weather(features: dict[str, float], weather: WeatherContext | None) -> None:
    """Add the conditions prevailing when the forecast was issued."""
    if weather is None:
        features["issue_wind_speed"] = math.nan
        features["issue_pbl_height_m"] = math.nan
        return
    features["issue_wind_speed"] = math.hypot(weather.wind_u, weather.wind_v)
    features["issue_pbl_height_m"] = (
        weather.pbl_height_m if weather.pbl_height_m is not None else math.nan
    )


def persistence_forecast(inputs: ForecastInputs, issued_at: datetime) -> float | None:
    """Baseline: tomorrow looks like now.

    Weak at 24 hours and beyond for PM2.5, but it costs nothing and any model
    that cannot beat it is not forecasting.
    """
    return _lookup(inputs.history, issued_at)


def climatology_forecast(
    inputs: ForecastInputs, issued_at: datetime, horizon_hours: int
) -> float | None:
    """Baseline: this station's usual value at the target hour of day.

    The competitive baseline. Urban PM2.5 is strongly diurnal, so the daily
    average shape alone is a real forecast rather than a strawman.
    """
    target_time = issued_at + timedelta(hours=horizon_hours)
    return inputs.climatology.get(target_time.hour)
