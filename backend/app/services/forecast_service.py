"""Corridor forecasting, 24 to 72 hours ahead.

The point of forecasting here is to move the alert in front of the exposure. An
AQI averaged over 24 hours and published afterwards tells people what they
already breathed. A corridor outlook lets a school move games indoors on
Thursday and an inspection be positioned before the episode rather than after.

**The forecast is climatological, and that is a measured decision.** Against a
temporal holdout on real Delhi data, this station's usual value at the target
hour of day beat gradient boosting at every horizon -- MAE 15.6 against 17.5 at
24 hours, and the gap widened to 72. It also beat persistence outright (22.1),
which says something substantive about the pollutant: Delhi PM2.5 is dominated
by its daily cycle, so what a place is *usually* like at 3pm predicts it better
than what it is doing right now.

That result is why no learned model is served here. Shipping one would mean
publishing worse numbers with more confidence, and the whole argument for this
system is that a wrong number is worse than an honest one.

A corridor is a polyline -- Delhi to Ludhiana, the NH-48 industrial belt -- and
is forecast by sampling points along it, so the output is a strip showing where
along a route and at what hour the air turns.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

from app.core.constants import (
    CORRIDOR_SAMPLE_SPACING_M,
    FORECAST_BASE_UNCERTAINTY_UGM3,
    FORECAST_MAX_HORIZON_HOURS,
    FORECAST_UNCERTAINTY_PER_DAY_UGM3,
    HOURS_PER_DAY,
)
from app.core.exceptions import ValidationError
from app.core.geo import LonLat, destination_point, haversine_distance_m, initial_bearing_deg
from app.core.logging import get_logger
from app.ml.forecast_features import build_climatology
from app.ml.fusion_features import StationReading, estimate_cell

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    """A forecast for one place at one hour."""

    coordinates: LonLat
    #: Distance from the start of the corridor, in metres.
    distance_along_m: float
    target_time: datetime
    horizon_hours: int
    value: float
    uncertainty: float

    @property
    def upper_bound(self) -> float:
        """Plausible high end, which is what a precautionary decision uses."""
        return self.value + self.uncertainty


def forecast_uncertainty(horizon_hours: int) -> float:
    """Expected absolute error of a forecast at a given lead time.

    Fitted to the temporal-holdout validation rather than assumed. The near
    independence from lead time is real and worth noticing: a climatological
    forecast leans on the daily cycle, which is as predictable three days out as
    one.
    """
    days = horizon_hours / HOURS_PER_DAY
    return FORECAST_BASE_UNCERTAINTY_UGM3 + FORECAST_UNCERTAINTY_PER_DAY_UGM3 * days


def forecast_from_history(
    history: Mapping[datetime, float],
    issued_at: datetime,
    horizon_hours: int,
) -> ForecastPoint | None:
    """Forecast one location from its own history.

    Args:
        history: Observations keyed by hour, none later than ``issued_at``.
        issued_at: When the forecast is made, in UTC.
        horizon_hours: Lead time, capped by the validated maximum.

    Returns:
        The forecast, or None when there is too little history for a diurnal
        cycle to exist. Returning None is deliberate: a location with no
        established pattern gets no forecast rather than a fabricated one.

    Raises:
        ValidationError: The horizon is outside the validated range. Serving a
            96-hour forecast from a model measured to 72 would put a number
            beyond its evidence in front of someone making a decision.
    """
    if horizon_hours <= 0:
        raise ValidationError(f"Forecast horizon must be positive, got {horizon_hours}.")
    if horizon_hours > FORECAST_MAX_HORIZON_HOURS:
        raise ValidationError(
            f"Forecast horizon {horizon_hours}h exceeds the validated maximum of "
            f"{FORECAST_MAX_HORIZON_HOURS}h.",
        )

    climatology = build_climatology(history)
    if not climatology:
        return None

    target_time = issued_at + timedelta(hours=horizon_hours)
    value = climatology.get(target_time.hour)
    if value is None:
        return None

    return ForecastPoint(
        coordinates=(0.0, 0.0),
        distance_along_m=0.0,
        target_time=target_time,
        horizon_hours=horizon_hours,
        value=value,
        uncertainty=forecast_uncertainty(horizon_hours),
    )


def sample_corridor(
    polyline: Sequence[LonLat],
    *,
    spacing_m: float = CORRIDOR_SAMPLE_SPACING_M,
) -> list[tuple[LonLat, float]]:
    """Place evenly spaced sample points along a corridor.

    Args:
        polyline: Ordered ``(lon, lat)`` vertices of the route.
        spacing_m: Distance between samples.

    Returns:
        ``(point, distance_from_start_m)`` pairs, including both endpoints.

    Raises:
        ValidationError: Fewer than two vertices, or a non-positive spacing.
    """
    if len(polyline) < 2:
        raise ValidationError("A corridor needs at least two vertices.")
    if spacing_m <= 0:
        raise ValidationError(f"Corridor spacing must be positive, got {spacing_m}.")

    samples: list[tuple[LonLat, float]] = [(polyline[0], 0.0)]
    travelled = 0.0

    for start, end in pairwise(polyline):
        segment_length = haversine_distance_m(start, end)
        if segment_length == 0:
            continue
        bearing = initial_bearing_deg(start, end)

        # Step along this segment, carrying the leftover distance from the
        # previous one so spacing stays even across vertices rather than
        # restarting at every corner.
        offset = spacing_m - (travelled % spacing_m)
        while offset < segment_length:
            samples.append((destination_point(start, bearing, offset), travelled + offset))
            offset += spacing_m
        travelled += segment_length

    samples.append((polyline[-1], travelled))
    return samples


def forecast_corridor(
    polyline: Sequence[LonLat],
    station_history: Mapping[int, Mapping[datetime, float]],
    station_positions: Mapping[int, LonLat],
    issued_at: datetime,
    horizon_hours: int,
    *,
    spacing_m: float = CORRIDOR_SAMPLE_SPACING_M,
) -> list[ForecastPoint]:
    """Forecast concentrations along a corridor.

    Each sample point is forecast by combining nearby stations' climatological
    values for the target hour, weighted by distance in the same way the fused
    surface combines observations. Points the network cannot support are left
    out rather than interpolated from nothing.

    Args:
        polyline: Ordered ``(lon, lat)`` vertices of the route.
        station_history: Observations per station, keyed by hour.
        station_positions: ``(lon, lat)`` per station.
        issued_at: When the forecast is made, in UTC.
        horizon_hours: Lead time.
        spacing_m: Distance between sample points.

    Returns:
        Forecasts ordered from the start of the corridor. Gaps are real: a
        stretch with no stations within range produces no points, and the strip
        must render that as unknown rather than as clean.
    """
    target_time = issued_at + timedelta(hours=horizon_hours)
    uncertainty = forecast_uncertainty(horizon_hours)

    # Each station's expected value at the target hour, from its own history.
    expected: list[StationReading] = []
    for station_id, history in station_history.items():
        position = station_positions.get(station_id)
        if position is None:
            continue
        climatology = build_climatology(history)
        value = climatology.get(target_time.hour)
        if value is None:
            continue
        expected.append(StationReading(station_id=station_id, coordinates=position, value=value))

    if not expected:
        logger.info("forecast.no_station_climatology", target_hour=target_time.hour)
        return []

    forecasts: list[ForecastPoint] = []
    for point, distance_along in sample_corridor(polyline, spacing_m=spacing_m):
        estimate = estimate_cell(point, expected)
        if estimate is None:
            continue
        forecasts.append(
            ForecastPoint(
                coordinates=point,
                distance_along_m=distance_along,
                target_time=target_time,
                horizon_hours=horizon_hours,
                value=estimate.value,
                # Both error sources compound: reconstructing an unmonitored
                # place, and forecasting it ahead.
                uncertainty=uncertainty + estimate.uncertainty,
            )
        )

    logger.info(
        "forecast.corridor_completed",
        horizon_hours=horizon_hours,
        sampled=len(forecasts),
        stations_used=len(expected),
    )
    return forecasts
