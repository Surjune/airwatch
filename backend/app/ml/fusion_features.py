"""Feature construction for the fused concentration surface.

Pure functions over plain data: no database, no model, no I/O. Training and
inference both call this, which is what guarantees the features a model was
trained on are the features it is served.

The estimate being learned is: *given every other station's reading this hour,
plus the weather, what is the concentration here?* Answering that well is what
lets the system speak about the 99.9% of a city that has no monitor — and
leave-one-station-out validation measures exactly how well, by hiding a real
station and comparing the estimate against what it actually recorded.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from app.core.constants import (
    DAYS_PER_WEEK,
    FUSION_BASE_UNCERTAINTY_UGM3,
    FUSION_DENSITY_RADII_M,
    FUSION_DISTANCE_UNCERTAINTY_PER_KM,
    FUSION_MAX_SENSOR_DISTANCE_M,
    FUSION_MIN_NEIGHBOURS,
    FUSION_NEAREST_K,
    FUSION_SPREAD_UNCERTAINTY_COEFFICIENT,
    HOURS_PER_DAY,
    IDW_POWER,
)
from app.core.geo import LonLat, haversine_distance_m, wind_speed_ms

#: Distance below which a neighbour is treated as co-located with the target,
#: guarding the inverse-distance weight against division by zero.
_MIN_SEPARATION_M: Final[float] = 1.0

#: Metres in a kilometre, for the distance term of the uncertainty model.
_METRES_PER_KM: Final[float] = 1000.0


@dataclass(frozen=True, slots=True)
class StationReading:
    """One station's reading at the hour being estimated."""

    station_id: int
    coordinates: LonLat
    value: float


@dataclass(frozen=True, slots=True)
class WeatherContext:
    """Meteorology for the hour being estimated.

    Currently sampled at the city centre rather than per cell, so these vary in
    time but not in space. They therefore help the model learn *when*
    concentrations rise, not *where* — the spatial signal comes entirely from the
    neighbour features.
    """

    wind_u: float
    wind_v: float
    temperature_c: float
    relative_humidity_pct: float
    pbl_height_m: float | None


#: Feature names, in the order the model receives them. Order is part of the
#: contract between training and inference: a silently reordered vector produces
#: confident, meaningless predictions.
FEATURE_NAMES: Final[tuple[str, ...]] = (
    "idw_estimate",
    "nearest_value",
    "nearest_distance_m",
    "neighbour_mean_k",
    "neighbour_std_k",
    "neighbour_count_2km",
    "neighbour_count_5km",
    "hour_sin",
    "hour_cos",
    "weekday_sin",
    "weekday_cos",
    "wind_u",
    "wind_v",
    "wind_speed",
    "temperature_c",
    "relative_humidity_pct",
    "pbl_height_m",
)


def inverse_distance_estimate(
    target: LonLat,
    neighbours: Sequence[StationReading],
    *,
    max_distance_m: float = FUSION_MAX_SENSOR_DISTANCE_M,
    power: float = IDW_POWER,
) -> float | None:
    """Inverse-distance-weighted estimate at a point.

    The classical interpolation, kept as a standalone function because it is the
    baseline the learned model has to beat. If fusion cannot outperform this,
    the model is adding complexity and no accuracy, and should be dropped.

    Args:
        target: ``(lon, lat)`` of the point being estimated.
        neighbours: Readings from other stations this hour.
        max_distance_m: Neighbours beyond this contribute nothing.
        power: Inverse-distance exponent.

    Returns:
        The weighted estimate, or None when no neighbour is close enough.
    """
    numerator = 0.0
    denominator = 0.0

    for neighbour in neighbours:
        distance = haversine_distance_m(target, neighbour.coordinates)
        if distance > max_distance_m:
            continue
        weight = 1.0 / (max(distance, _MIN_SEPARATION_M) ** power)
        numerator += weight * neighbour.value
        denominator += weight

    if denominator == 0.0:
        return None
    return numerator / denominator


def build_features(
    target: LonLat,
    neighbours: Sequence[StationReading],
    observed_at: datetime,
    weather: WeatherContext | None,
    *,
    max_distance_m: float = FUSION_MAX_SENSOR_DISTANCE_M,
    min_neighbours: int = FUSION_MIN_NEIGHBOURS,
) -> dict[str, float] | None:
    """Build the feature vector for one cell-hour.

    Args:
        target: ``(lon, lat)`` of the cell being estimated.
        neighbours: Every *other* station's reading for this hour. The target's
            own reading must not appear here; including it would leak the answer
            into the features and produce a validation score that means nothing.
        observed_at: The hour being estimated, in UTC.
        weather: Meteorology for the hour, or None when unavailable.
        max_distance_m: Neighbours beyond this are ignored.
        min_neighbours: Fewest usable neighbours required.

    Returns:
        A feature mapping keyed by :data:`FEATURE_NAMES`, or None when too few
        neighbours are in range to support an estimate.
    """
    in_range = [
        (haversine_distance_m(target, neighbour.coordinates), neighbour) for neighbour in neighbours
    ]
    in_range = [(distance, n) for distance, n in in_range if distance <= max_distance_m]

    if len(in_range) < min_neighbours:
        # Refusing is the point: an estimate from one or two distant stations is
        # a guess, and the system must not present it as a measurement.
        return None

    in_range.sort(key=lambda pair: pair[0])
    nearest_distance, nearest = in_range[0]

    idw = inverse_distance_estimate(target, [n for _, n in in_range], max_distance_m=max_distance_m)
    if idw is None:  # pragma: no cover - in_range is non-empty here.
        return None

    k_nearest = [neighbour.value for _, neighbour in in_range[:FUSION_NEAREST_K]]
    neighbour_mean = sum(k_nearest) / len(k_nearest)
    variance = sum((value - neighbour_mean) ** 2 for value in k_nearest) / len(k_nearest)

    counts = [
        float(sum(1 for distance, _ in in_range if distance <= radius))
        for radius in FUSION_DENSITY_RADII_M
    ]

    # Cyclical encoding so hour 23 sits next to hour 0 rather than 23 units away.
    hour_angle = 2 * math.pi * observed_at.hour / HOURS_PER_DAY
    weekday_angle = 2 * math.pi * observed_at.weekday() / DAYS_PER_WEEK

    features: dict[str, float] = {
        "idw_estimate": idw,
        "nearest_value": nearest.value,
        "nearest_distance_m": nearest_distance,
        "neighbour_mean_k": neighbour_mean,
        "neighbour_std_k": math.sqrt(variance),
        "neighbour_count_2km": counts[0],
        "neighbour_count_5km": counts[1],
        "hour_sin": math.sin(hour_angle),
        "hour_cos": math.cos(hour_angle),
        "weekday_sin": math.sin(weekday_angle),
        "weekday_cos": math.cos(weekday_angle),
    }

    if weather is not None:
        features["wind_u"] = weather.wind_u
        features["wind_v"] = weather.wind_v
        features["wind_speed"] = wind_speed_ms(weather.wind_u, weather.wind_v)
        features["temperature_c"] = weather.temperature_c
        features["relative_humidity_pct"] = weather.relative_humidity_pct
        # NaN rather than zero: a missing boundary layer is unknown, not ground
        # level, and gradient-boosted trees handle NaN as a genuine "no value"
        # branch instead of learning a spurious relationship at zero.
        features["pbl_height_m"] = (
            weather.pbl_height_m if weather.pbl_height_m is not None else math.nan
        )
    else:
        for name in (
            "wind_u",
            "wind_v",
            "wind_speed",
            "temperature_c",
            "relative_humidity_pct",
            "pbl_height_m",
        ):
            features[name] = math.nan

    return features


def features_to_vector(features: dict[str, float]) -> list[float]:
    """Flatten a feature mapping into the model's expected column order."""
    return [features[name] for name in FEATURE_NAMES]


@dataclass(frozen=True, slots=True)
class FusedEstimate:
    """A concentration estimate for a cell, with the honesty attached.

    Attributes:
        value: Estimated concentration in the pollutant's storage unit.
        uncertainty: Expected absolute error, in the same unit. Not decoration:
            leave-one-station-out validation put the typical error near
            10 ug/m3 even under good conditions, and above 24 where neighbouring
            monitors disagree. A surface that renders both at the same
            confidence is lying by omission.
        neighbour_count: Stations that contributed.
        nearest_distance_m: Distance to the closest contributing station.
        neighbour_spread: Standard deviation among the nearest few, which is the
            best available warning that a cell is poorly constrained.
    """

    value: float
    uncertainty: float
    neighbour_count: int
    nearest_distance_m: float
    neighbour_spread: float


def estimate_cell(
    target: LonLat,
    neighbours: Sequence[StationReading],
    *,
    max_distance_m: float = FUSION_MAX_SENSOR_DISTANCE_M,
    min_neighbours: int = FUSION_MIN_NEIGHBOURS,
) -> FusedEstimate | None:
    """Estimate the concentration at a cell, with its uncertainty.

    Uses inverse-distance weighting rather than a learned model. That is an
    empirical decision, not a placeholder: under leave-one-station-out validation
    on real Delhi data, gradient boosting was 10.8% *worse* than plain IDW
    (MAE 12.7 against 11.5). With 36 stations the model learns each site's
    idiosyncrasies instead of a spatial relationship that transfers to ground the
    network does not cover. Shipping it anyway would mean publishing worse
    numbers with more confidence.

    Args:
        target: ``(lon, lat)`` of the cell being estimated.
        neighbours: Readings from stations this hour.
        max_distance_m: Stations beyond this contribute nothing.
        min_neighbours: Fewest contributing stations required.

    Returns:
        The estimate, or None when too few stations are in range. Returning None
        is deliberate: a cell nothing supports must be drawn as unknown, not as
        clean.
    """
    in_range = sorted(
        (
            (haversine_distance_m(target, neighbour.coordinates), neighbour)
            for neighbour in neighbours
        ),
        key=lambda pair: pair[0],
    )
    in_range = [(distance, n) for distance, n in in_range if distance <= max_distance_m]

    if len(in_range) < min_neighbours:
        return None

    value = inverse_distance_estimate(
        target, [n for _, n in in_range], max_distance_m=max_distance_m
    )
    if value is None:  # pragma: no cover - in_range is non-empty here.
        return None

    nearest_distance = in_range[0][0]
    k_nearest = [neighbour.value for _, neighbour in in_range[:FUSION_NEAREST_K]]
    mean = sum(k_nearest) / len(k_nearest)
    spread = math.sqrt(sum((v - mean) ** 2 for v in k_nearest) / len(k_nearest))

    uncertainty = (
        FUSION_BASE_UNCERTAINTY_UGM3
        + FUSION_SPREAD_UNCERTAINTY_COEFFICIENT * spread
        + FUSION_DISTANCE_UNCERTAINTY_PER_KM * (nearest_distance / _METRES_PER_KM)
    )

    return FusedEstimate(
        value=value,
        uncertainty=uncertainty,
        neighbour_count=len(in_range),
        nearest_distance_m=nearest_distance,
        neighbour_spread=spread,
    )
