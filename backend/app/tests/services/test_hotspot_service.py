"""Tests for hidden hotspot detection.

The property that matters most is in TestCitywideEpisode: a bad day everywhere
must produce no hotspots at all. Anything that flags on a citywide episode has
reinvented the threshold detector this module exists to replace.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.geo import LonLat, destination_point
from app.core.h3_grid import H3Cell, point_to_cell
from app.ml.fusion_features import StationReading
from app.services.hotspot_service import (
    CellAnomaly,
    detect_hotspots,
    filter_by_contiguity,
    score_hour,
)

DELHI: LonLat = (77.2090, 28.6139)
START = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)


def network(values: dict[int, float], distance_m: float = 2500.0) -> list[StationReading]:
    """A ring of stations around Delhi, one per supplied value."""
    step = 360.0 / len(values)
    return [
        StationReading(
            station_id=station_id,
            coordinates=destination_point(DELHI, index * step, distance_m),
            value=value,
        )
        for index, (station_id, value) in enumerate(values.items())
    ]


def cells_for(readings: list[StationReading]) -> dict[int, H3Cell]:
    return {r.station_id: point_to_cell(r.coordinates) for r in readings}


def anomaly(
    station_id: int,
    observed_at: datetime,
    observed: float,
    expected: float,
    uncertainty: float = 10.0,
) -> CellAnomaly:
    return CellAnomaly(
        station_id=station_id,
        h3_cell=point_to_cell(DELHI),
        coordinates=DELHI,
        observed_at=observed_at,
        observed=observed,
        expected=expected,
        uncertainty=uncertainty,
    )


class TestCitywideEpisode:
    """A bad day everywhere is not a hotspot anywhere."""

    def test_uniformly_severe_air_produces_no_anomaly(self) -> None:
        # Every station at 250 ug/m3: catastrophic air, but no location is worse
        # than its neighbourhood, so there is nothing to dispatch anyone to.
        readings = network(dict.fromkeys(range(1, 9), 250.0))
        anomalies = score_hour(readings, cells_for(readings), START)

        assert anomalies
        assert all(abs(a.z_score) < 1.0 for a in anomalies)
        assert detect_hotspots(anomalies) == []

    def test_severity_alone_never_triggers_detection(self) -> None:
        clean = network(dict.fromkeys(range(1, 9), 15.0))
        filthy = network(dict.fromkeys(range(1, 9), 400.0))

        clean_scores = [a.z_score for a in score_hour(clean, cells_for(clean), START)]
        filthy_scores = [a.z_score for a in score_hour(filthy, cells_for(filthy), START)]

        # A 26x difference in concentration, and the detector treats them alike.
        assert max(abs(z) for z in clean_scores) < 1.0
        assert max(abs(z) for z in filthy_scores) < 1.0


class TestLocalExcess:
    def test_one_station_far_above_its_neighbours_is_flagged(self) -> None:
        values = dict.fromkeys(range(1, 8), 40.0)
        values[8] = 400.0
        readings = network(values)

        anomalies = score_hour(readings, cells_for(readings), START)
        flagged = [a for a in anomalies if a.z_score >= 3.0]

        assert [a.station_id for a in flagged] == [8]

    def test_a_cleaner_station_is_not_a_hotspot(self) -> None:
        # Negative residuals are interesting but they are not a pollution source,
        # and alerting on them would waste an inspector's time.
        values = dict.fromkeys(range(1, 8), 200.0)
        values[8] = 20.0
        readings = network(values)

        anomalies = score_hour(readings, cells_for(readings), START)
        assert detect_hotspots(anomalies) == []

    def test_excess_is_reported_against_the_neighbourhood_not_zero(self) -> None:
        values = dict.fromkeys(range(1, 8), 100.0)
        values[8] = 300.0
        readings = network(values)

        flagged = next(
            a for a in score_hour(readings, cells_for(readings), START) if a.station_id == 8
        )
        # The excess is ~200 over a neighbourhood of ~100, not 300 over nothing.
        assert flagged.residual == pytest.approx(200.0, rel=0.1)
        assert flagged.expected == pytest.approx(100.0, rel=0.1)


class TestSelfExclusion:
    def test_a_station_does_not_predict_itself(self) -> None:
        # If the target were included in its own neighbour set, its own extreme
        # value would drag the prediction toward itself and no hotspot would
        # ever be found.
        values = dict.fromkeys(range(1, 8), 40.0)
        values[8] = 400.0
        readings = network(values)

        flagged = next(
            a for a in score_hour(readings, cells_for(readings), START) if a.station_id == 8
        )
        assert flagged.expected < 100.0


class TestPersistence:
    def test_a_single_flagged_hour_is_rejected(self) -> None:
        # Far more likely a sensor glitch than a source.
        assert detect_hotspots([anomaly(1, START, 200.0, 40.0)]) == []

    def test_two_consecutive_hours_confirm_a_hotspot(self) -> None:
        hotspots = detect_hotspots(
            [
                anomaly(1, START, 200.0, 40.0),
                anomaly(1, START + timedelta(hours=1), 190.0, 45.0),
            ]
        )
        assert len(hotspots) == 1
        assert hotspots[0].intervals == 2

    def test_a_long_gap_splits_one_run_into_separate_episodes(self) -> None:
        hotspots = detect_hotspots(
            [
                anomaly(1, START, 200.0, 40.0),
                anomaly(1, START + timedelta(hours=1), 200.0, 40.0),
                # Twelve hours later: a new event, not the same one continuing.
                anomaly(1, START + timedelta(hours=13), 200.0, 40.0),
                anomaly(1, START + timedelta(hours=14), 200.0, 40.0),
            ]
        )
        assert len(hotspots) == 2

    def test_reports_peak_and_mean_separately(self) -> None:
        hotspots = detect_hotspots(
            [
                anomaly(1, START, 100.0, 40.0),
                anomaly(1, START + timedelta(hours=1), 300.0, 40.0),
            ]
        )
        assert len(hotspots) == 1
        assert hotspots[0].peak_residual == pytest.approx(260.0)
        assert hotspots[0].mean_residual == pytest.approx(160.0)
        assert hotspots[0].duration_hours == pytest.approx(1.0)


class TestUncertaintyScaling:
    def test_a_poorly_constrained_cell_needs_a_larger_excess(self) -> None:
        # The same 50 ug/m3 excess is decisive where neighbours agree and
        # unremarkable where they do not.
        confident = anomaly(1, START, 90.0, 40.0, uncertainty=10.0)
        uncertain = anomaly(2, START, 90.0, 40.0, uncertainty=50.0)

        assert confident.z_score == pytest.approx(5.0)
        assert uncertain.z_score == pytest.approx(1.0)
        assert detect_hotspots([confident, confident]) != []
        assert detect_hotspots([uncertain, uncertain]) == []


class TestUnsupportedLocations:
    def test_a_station_with_too_few_neighbours_is_omitted(self) -> None:
        # Omitted rather than scored as normal: an unsupported location is
        # unknown, not clean.
        readings = network({1: 40.0, 2: 400.0})
        assert score_hour(readings, cells_for(readings), START) == []


class TestContiguity:
    def test_an_isolated_flagged_cell_is_dropped(self) -> None:
        far_apart = [
            point_to_cell(DELHI),
            point_to_cell(destination_point(DELHI, 90.0, 20_000.0)),
        ]
        assert filter_by_contiguity(far_apart) == set()

    def test_touching_cells_are_kept(self) -> None:
        from app.core.h3_grid import grid_ring

        centre = point_to_cell(DELHI)
        adjacent = grid_ring(centre, 1)[0]

        kept = filter_by_contiguity([centre, adjacent])

        assert kept == {centre, adjacent}
