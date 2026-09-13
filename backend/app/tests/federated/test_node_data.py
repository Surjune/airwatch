"""Tests for building a city node's matrices from its own series."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from federated.node_data import actual_near, assign_city, build_node, federated_columns

from app.core.constants import FORECAST_LAG_HOURS_SHORT, PILOT_CITY_CENTRES
from app.ml.forecast_features import FEDERATED_EXCLUDED_PREFIXES, feature_names

START = datetime(2026, 8, 1, tzinfo=UTC)


def hourly_series(hours: int, *, base: float = 60.0) -> dict[datetime, float]:
    return {
        START + timedelta(hours=hour): base + 20.0 * np.sin(2 * np.pi * hour / 24)
        for hour in range(hours)
    }


class TestAssignCity:
    def test_a_station_at_a_centre_belongs_to_that_city(self) -> None:
        for city, centre in PILOT_CITY_CENTRES.items():
            assert assign_city(centre) == city

    def test_a_station_far_from_every_city_belongs_to_none(self) -> None:
        # Mumbai: a real monitoring city, and not a node in this federation.
        assert assign_city((72.8777, 19.0760)) is None


class TestActualNear:
    def test_prefers_the_exact_target_hour(self) -> None:
        history = {START + timedelta(hours=24): 80.0, START + timedelta(hours=24, minutes=30): 99.0}
        assert actual_near(history, START, 24) == 80.0

    def test_accepts_a_reading_inside_the_tolerance(self) -> None:
        history = {START + timedelta(hours=24, minutes=40): 71.0}
        assert actual_near(history, START, 24) == 71.0

    def test_refuses_to_borrow_the_next_hour(self) -> None:
        history = {START + timedelta(hours=25): 71.0}
        assert actual_near(history, START, 24) is None


def test_federated_columns_drop_what_not_every_node_can_compute() -> None:
    columns = federated_columns(feature_names(FORECAST_LAG_HOURS_SHORT))

    assert columns
    assert not any(name.startswith(FEDERATED_EXCLUDED_PREFIXES) for name in columns)


class TestBuildNode:
    columns = federated_columns(feature_names(FORECAST_LAG_HOURS_SHORT))

    def test_splits_in_time_with_every_test_row_after_every_training_row(self) -> None:
        series = {1: hourly_series(24 * 12), 2: hourly_series(24 * 12, base=90.0)}

        node = build_node("delhi", series, self.columns, stations=2)

        assert node is not None
        assert len(node.y_train) > len(node.y_test) > 0
        assert node.x_train.shape[1] == len(self.columns)
        assert not np.isnan(node.x_train).any()

    def test_a_node_with_too_little_history_does_not_participate(self) -> None:
        node = build_node("coimbatore", {1: hourly_series(30)}, self.columns, stations=1)
        assert node is None

    def test_an_empty_city_does_not_participate(self) -> None:
        assert build_node("coimbatore", {}, self.columns, stations=0) is None
