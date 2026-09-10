"""Tests for fusion feature construction and the fused estimate."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from app.core.constants import FUSION_DENSITY_RADII_M, FUSION_MAX_SENSOR_DISTANCE_M
from app.core.geo import LonLat, destination_point
from app.ml.fusion_features import (
    FEATURE_NAMES,
    StationReading,
    WeatherContext,
    build_features,
    estimate_cell,
    features_to_vector,
    inverse_distance_estimate,
)

DELHI: LonLat = (77.2090, 28.6139)
OBSERVED_AT = datetime(2026, 9, 8, 14, 0, tzinfo=UTC)

WEATHER = WeatherContext(
    wind_u=3.0,
    wind_v=4.0,
    temperature_c=31.0,
    relative_humidity_pct=52.0,
    pbl_height_m=820.0,
)


def station_at(
    distance_m: float, bearing_deg: float, value: float, station_id: int = 1
) -> StationReading:
    """A station a given distance and bearing from Delhi."""
    return StationReading(
        station_id=station_id,
        coordinates=destination_point(DELHI, bearing_deg, distance_m),
        value=value,
    )


def ring(values: list[float], distance_m: float = 2000.0) -> list[StationReading]:
    """Stations evenly spaced around the target at one distance."""
    step = 360.0 / len(values)
    return [
        station_at(distance_m, index * step, value, station_id=index + 1)
        for index, value in enumerate(values)
    ]


class TestInverseDistanceEstimate:
    def test_equidistant_neighbours_give_their_mean(self) -> None:
        estimate = inverse_distance_estimate(DELHI, ring([10.0, 20.0, 30.0, 40.0]))
        assert estimate == pytest.approx(25.0, rel=1e-3)

    def test_nearer_stations_dominate(self) -> None:
        neighbours = [
            station_at(500.0, 0.0, 100.0, station_id=1),
            station_at(4000.0, 180.0, 10.0, station_id=2),
        ]
        estimate = inverse_distance_estimate(DELHI, neighbours)
        assert estimate is not None
        # Inverse-square weighting puts the estimate close to the near station.
        assert estimate > 90.0

    def test_ignores_stations_beyond_the_cutoff(self) -> None:
        far = [station_at(50_000.0, 0.0, 500.0, station_id=1)]
        assert inverse_distance_estimate(DELHI, far) is None

    def test_returns_none_with_no_neighbours(self) -> None:
        # Distinct from returning zero, which would read as clean air.
        assert inverse_distance_estimate(DELHI, []) is None

    def test_a_colocated_station_does_not_divide_by_zero(self) -> None:
        same_place = [StationReading(station_id=1, coordinates=DELHI, value=77.0)]
        assert inverse_distance_estimate(DELHI, same_place) == pytest.approx(77.0)


class TestBuildFeatures:
    def test_produces_every_declared_feature(self) -> None:
        features = build_features(DELHI, ring([40.0, 50.0, 60.0, 70.0]), OBSERVED_AT, WEATHER)
        assert features is not None
        assert set(features) == set(FEATURE_NAMES)

    def test_vector_follows_the_declared_column_order(self) -> None:
        # Order is the contract between training and inference; a reordered
        # vector produces confident nonsense.
        features = build_features(DELHI, ring([40.0, 50.0, 60.0, 70.0]), OBSERVED_AT, WEATHER)
        assert features is not None
        vector = features_to_vector(features)
        assert vector[0] == features["idw_estimate"]
        assert len(vector) == len(FEATURE_NAMES)

    def test_refuses_when_too_few_neighbours_are_in_range(self) -> None:
        # An estimate from one or two stations is a guess, and must not be
        # presented with the same confidence as a supported one.
        assert build_features(DELHI, ring([40.0, 50.0]), OBSERVED_AT, WEATHER) is None

    def test_refuses_when_every_neighbour_is_out_of_range(self) -> None:
        distant = [
            station_at(40_000.0, angle, 50.0, station_id=i) for i, angle in enumerate((0, 120, 240))
        ]
        assert build_features(DELHI, distant, OBSERVED_AT, WEATHER) is None

    def test_counts_neighbours_by_distance_band(self) -> None:
        neighbours = [
            station_at(800.0, 0.0, 50.0, station_id=1),
            station_at(1500.0, 90.0, 50.0, station_id=2),
            station_at(4000.0, 180.0, 50.0, station_id=3),
        ]
        features = build_features(DELHI, neighbours, OBSERVED_AT, WEATHER)
        assert features is not None
        assert features["neighbour_count_2km"] == 2
        assert features["neighbour_count_5km"] == 3

    def test_density_radii_can_actually_differ(self) -> None:
        # Guards the bug this pairing had. The outer radius may equal the cutoff
        # -- that count is simply the total in range, which is informative -- but
        # every inner radius must sit strictly inside it, or the counts are
        # identical by construction and the feature carries no signal at all.
        assert min(FUSION_DENSITY_RADII_M) < FUSION_MAX_SENSOR_DISTANCE_M
        assert max(FUSION_DENSITY_RADII_M) <= FUSION_MAX_SENSOR_DISTANCE_M
        assert len(set(FUSION_DENSITY_RADII_M)) == len(FUSION_DENSITY_RADII_M)
        assert list(FUSION_DENSITY_RADII_M) == sorted(FUSION_DENSITY_RADII_M)

    def test_spread_is_zero_when_neighbours_agree(self) -> None:
        features = build_features(DELHI, ring([50.0, 50.0, 50.0, 50.0]), OBSERVED_AT, WEATHER)
        assert features is not None
        assert features["neighbour_std_k"] == pytest.approx(0.0)

    def test_spread_grows_when_neighbours_disagree(self) -> None:
        agree = build_features(DELHI, ring([50.0, 50.0, 50.0, 50.0]), OBSERVED_AT, WEATHER)
        disagree = build_features(DELHI, ring([10.0, 90.0, 20.0, 80.0]), OBSERVED_AT, WEATHER)
        assert agree is not None and disagree is not None
        assert disagree["neighbour_std_k"] > agree["neighbour_std_k"]


class TestTimeEncoding:
    def test_hour_encoding_is_cyclical(self) -> None:
        # Hour 23 must sit next to hour 0, not 23 units away.
        late = build_features(DELHI, ring([50.0] * 4), OBSERVED_AT.replace(hour=23), WEATHER)
        midnight = build_features(DELHI, ring([50.0] * 4), OBSERVED_AT.replace(hour=0), WEATHER)
        noon = build_features(DELHI, ring([50.0] * 4), OBSERVED_AT.replace(hour=12), WEATHER)
        assert late is not None and midnight is not None and noon is not None

        def distance(a: dict[str, float], b: dict[str, float]) -> float:
            return math.hypot(a["hour_sin"] - b["hour_sin"], a["hour_cos"] - b["hour_cos"])

        assert distance(late, midnight) < distance(midnight, noon)


class TestMissingWeather:
    def test_absent_weather_becomes_nan_not_zero(self) -> None:
        # Zero wind asserts calm air and zero humidity asserts a desert; both are
        # claims the data does not make. NaN lets a tree branch on "unknown".
        features = build_features(DELHI, ring([50.0] * 4), OBSERVED_AT, None)
        assert features is not None
        assert math.isnan(features["wind_u"])
        assert math.isnan(features["relative_humidity_pct"])

    def test_absent_boundary_layer_becomes_nan(self) -> None:
        weather = WeatherContext(
            wind_u=1.0,
            wind_v=1.0,
            temperature_c=30.0,
            relative_humidity_pct=40.0,
            pbl_height_m=None,
        )
        features = build_features(DELHI, ring([50.0] * 4), OBSERVED_AT, weather)
        assert features is not None
        assert math.isnan(features["pbl_height_m"])
        # The rest of the hour is still usable.
        assert not math.isnan(features["wind_u"])


class TestFusedEstimate:
    def test_returns_value_and_uncertainty(self) -> None:
        estimate = estimate_cell(DELHI, ring([40.0, 50.0, 60.0, 70.0]))
        assert estimate is not None
        assert estimate.value == pytest.approx(55.0, rel=1e-2)
        assert estimate.uncertainty > 0

    def test_uncertainty_grows_when_neighbours_disagree(self) -> None:
        # The relationship measured in leave-one-station-out validation: error
        # rose from 9.9 to 24.5 ug/m3 as neighbour spread rose.
        agreeing = estimate_cell(DELHI, ring([50.0, 50.0, 50.0, 50.0]))
        disagreeing = estimate_cell(DELHI, ring([5.0, 95.0, 10.0, 90.0]))
        assert agreeing is not None and disagreeing is not None
        assert disagreeing.uncertainty > agreeing.uncertainty

    def test_uncertainty_grows_with_distance(self) -> None:
        near = estimate_cell(DELHI, ring([50.0] * 4, distance_m=1000.0))
        far = estimate_cell(DELHI, ring([50.0] * 4, distance_m=4500.0))
        assert near is not None and far is not None
        assert far.uncertainty > near.uncertainty

    def test_uncertainty_is_never_falsely_small(self) -> None:
        # Even perfectly agreeing neighbours carry real error: Delhi PM2.5 is
        # hyperlocal, and validation put the floor near 10 ug/m3.
        estimate = estimate_cell(DELHI, ring([50.0] * 6, distance_m=500.0))
        assert estimate is not None
        assert estimate.uncertainty >= 9.0

    def test_reports_its_support(self) -> None:
        estimate = estimate_cell(DELHI, ring([40.0, 50.0, 60.0]))
        assert estimate is not None
        assert estimate.neighbour_count == 3
        assert estimate.nearest_distance_m == pytest.approx(2000.0, rel=1e-2)

    def test_returns_none_for_an_unsupported_cell(self) -> None:
        # An unsupported cell must render as unknown, never as clean.
        assert estimate_cell(DELHI, ring([50.0, 50.0])) is None


class TestNoSelfLeakage:
    def test_a_target_in_its_own_neighbour_set_would_leak(self) -> None:
        """Documents why the validation removes the held-out station.

        Included as a test because it is the single mistake that would make the
        headline metric meaningless while still looking plausible.
        """
        truth = 250.0
        others = ring([40.0, 45.0, 42.0, 44.0])

        honest = estimate_cell(DELHI, others)
        leaked = estimate_cell(
            DELHI, [*others, StationReading(station_id=99, coordinates=DELHI, value=truth)]
        )

        assert honest is not None and leaked is not None
        # With itself included the estimate is essentially the answer.
        assert leaked.value == pytest.approx(truth, rel=0.05)
        assert abs(honest.value - truth) > 100.0
