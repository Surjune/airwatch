"""Tests for corridor forecasting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.constants import FORECAST_MAX_HORIZON_HOURS
from app.core.exceptions import ValidationError
from app.core.geo import LonLat, destination_point, haversine_distance_m
from app.ml.forecasting import (
    forecast_corridor,
    forecast_from_history,
    forecast_uncertainty,
    sample_corridor,
)

DELHI: LonLat = (77.2090, 28.6139)
ISSUED_AT = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)


def diurnal_history(
    days: int = 10, *, base: float = 60.0, amplitude: float = 40.0
) -> dict[datetime, float]:
    """A history with a clean daily cycle: worst at 03:00, cleanest at 15:00."""
    history: dict[datetime, float] = {}
    start = ISSUED_AT - timedelta(days=days)
    for hour in range(days * 24):
        at_time = start + timedelta(hours=hour)
        # Peaks overnight when the boundary layer collapses.
        night_factor = 1.0 if at_time.hour in range(0, 7) else -1.0
        history[at_time] = base + amplitude * night_factor * 0.5
    return history


class TestForecastUncertainty:
    def test_is_never_falsely_small(self) -> None:
        # Measured at 15.6 ug/m3 on a temporal holdout. A forecast published
        # without it invites planning against a number routinely a band out.
        assert forecast_uncertainty(24) >= 15.0

    def test_grows_with_lead_time(self) -> None:
        assert forecast_uncertainty(72) > forecast_uncertainty(24)

    def test_grows_only_slightly(self) -> None:
        # The measured error barely grew with lead time, because the diurnal
        # cycle is as predictable three days out as one.
        assert forecast_uncertainty(72) < forecast_uncertainty(24) * 1.5


class TestForecastFromHistory:
    def test_predicts_the_stations_usual_value_for_that_hour(self) -> None:
        history = diurnal_history()
        # 06:00 + 21h = 03:00, inside the overnight peak.
        forecast = forecast_from_history(history, ISSUED_AT, 21)

        assert forecast is not None
        assert forecast.value == pytest.approx(80.0)

    def test_distinguishes_a_clean_hour_from_a_dirty_one(self) -> None:
        history = diurnal_history()
        overnight = forecast_from_history(history, ISSUED_AT, 21)
        afternoon = forecast_from_history(history, ISSUED_AT, 33)

        assert overnight is not None and afternoon is not None
        assert overnight.value > afternoon.value

    def test_reports_the_target_time(self) -> None:
        forecast = forecast_from_history(diurnal_history(), ISSUED_AT, 24)
        assert forecast is not None
        assert forecast.target_time == ISSUED_AT + timedelta(hours=24)

    def test_upper_bound_is_the_precautionary_figure(self) -> None:
        forecast = forecast_from_history(diurnal_history(), ISSUED_AT, 24)
        assert forecast is not None
        assert forecast.upper_bound == pytest.approx(forecast.value + forecast.uncertainty)

    def test_too_little_history_yields_no_forecast(self) -> None:
        # A location with no established pattern gets nothing rather than an
        # invented number.
        sparse = {ISSUED_AT - timedelta(hours=hour): 50.0 for hour in range(5)}
        assert forecast_from_history(sparse, ISSUED_AT, 24) is None

    def test_rejects_a_horizon_beyond_what_was_validated(self) -> None:
        # Serving 96 hours from a model measured to 72 puts a number beyond its
        # evidence in front of a decision.
        with pytest.raises(ValidationError, match="exceeds the validated maximum"):
            forecast_from_history(diurnal_history(), ISSUED_AT, FORECAST_MAX_HORIZON_HOURS + 1)

    def test_rejects_a_non_positive_horizon(self) -> None:
        with pytest.raises(ValidationError, match="must be positive"):
            forecast_from_history(diurnal_history(), ISSUED_AT, 0)


class TestCorridorSampling:
    def test_includes_both_endpoints(self) -> None:
        end = destination_point(DELHI, 90.0, 10_000.0)
        samples = sample_corridor([DELHI, end], spacing_m=2000.0)

        assert samples[0][0] == DELHI
        assert samples[-1][0] == end

    def test_spaces_points_evenly(self) -> None:
        end = destination_point(DELHI, 90.0, 10_000.0)
        samples = sample_corridor([DELHI, end], spacing_m=2000.0)

        gaps = [
            haversine_distance_m(samples[i][0], samples[i + 1][0]) for i in range(len(samples) - 1)
        ]
        assert all(gap == pytest.approx(2000.0, rel=0.05) for gap in gaps)

    def test_distance_along_increases_monotonically(self) -> None:
        end = destination_point(DELHI, 90.0, 10_000.0)
        distances = [distance for _, distance in sample_corridor([DELHI, end], spacing_m=2500.0)]
        assert distances == sorted(distances)

    def test_spacing_stays_even_across_a_corner(self) -> None:
        # Restarting the count at each vertex would bunch points at corners.
        corner = destination_point(DELHI, 90.0, 5000.0)
        end = destination_point(corner, 0.0, 5000.0)
        samples = sample_corridor([DELHI, corner, end], spacing_m=2000.0)

        gaps = [
            samples[i + 1][1] - samples[i][1]
            for i in range(len(samples) - 2)  # the final partial gap is shorter
        ]
        assert all(gap == pytest.approx(2000.0, rel=0.05) for gap in gaps)

    def test_rejects_a_single_vertex(self) -> None:
        with pytest.raises(ValidationError, match="at least two vertices"):
            sample_corridor([DELHI])

    def test_rejects_non_positive_spacing(self) -> None:
        end = destination_point(DELHI, 90.0, 10_000.0)
        with pytest.raises(ValidationError, match="must be positive"):
            sample_corridor([DELHI, end], spacing_m=0.0)


class TestCorridorForecast:
    def test_forecasts_along_a_monitored_corridor(self) -> None:
        end = destination_point(DELHI, 90.0, 6000.0)
        positions = {
            index: destination_point(DELHI, 90.0, offset)
            for index, offset in enumerate((0.0, 3000.0, 6000.0))
        }
        history = {index: diurnal_history() for index in positions}

        forecasts = forecast_corridor([DELHI, end], history, positions, ISSUED_AT, 24)

        assert forecasts
        assert all(forecast.horizon_hours == 24 for forecast in forecasts)
        assert all(forecast.uncertainty > 0 for forecast in forecasts)

    def test_uncertainty_compounds_both_error_sources(self) -> None:
        # Reconstructing an unmonitored place and forecasting it ahead are
        # separate errors, and a corridor point carries both.
        end = destination_point(DELHI, 90.0, 6000.0)
        positions = {
            index: destination_point(DELHI, 90.0, offset)
            for index, offset in enumerate((0.0, 3000.0, 6000.0))
        }
        history = {index: diurnal_history() for index in positions}

        forecasts = forecast_corridor([DELHI, end], history, positions, ISSUED_AT, 24)

        assert forecasts[0].uncertainty > forecast_uncertainty(24)

    def test_an_unmonitored_corridor_produces_no_points(self) -> None:
        # A stretch with no stations in range must render as unknown, not clean.
        far_start = destination_point(DELHI, 0.0, 200_000.0)
        far_end = destination_point(far_start, 90.0, 10_000.0)
        positions = {
            index: destination_point(DELHI, 90.0, offset)
            for index, offset in enumerate((0.0, 3000.0, 6000.0))
        }
        history = {index: diurnal_history() for index in positions}

        assert forecast_corridor([far_start, far_end], history, positions, ISSUED_AT, 24) == []

    def test_no_station_climatology_yields_nothing(self) -> None:
        end = destination_point(DELHI, 90.0, 6000.0)
        positions = {1: DELHI}
        sparse = {1: {ISSUED_AT - timedelta(hours=hour): 50.0 for hour in range(3)}}

        assert forecast_corridor([DELHI, end], sparse, positions, ISSUED_AT, 24) == []

    def test_points_are_ordered_along_the_corridor(self) -> None:
        end = destination_point(DELHI, 90.0, 6000.0)
        positions = {
            index: destination_point(DELHI, 90.0, offset)
            for index, offset in enumerate((0.0, 3000.0, 6000.0))
        }
        history = {index: diurnal_history() for index in positions}

        forecasts = forecast_corridor([DELHI, end], history, positions, ISSUED_AT, 24)

        distances = [forecast.distance_along_m for forecast in forecasts]
        assert distances == sorted(distances)
