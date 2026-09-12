"""Tests for the read-side orchestration layer.

The service is the only place that knows about both a database session and a
detection algorithm, so these tests stub the repositories and assert on the
translation: rows in, analysis out, ordering and framing correct.

Repositories are stubbed rather than mocked against a live database because the
behaviour under test is the wiring, not the SQL. The SQL has its own integration
tests in ``tests/repositories/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core.enums import Pollutant, SourceType
from app.core.geo import LonLat
from app.core.h3_grid import point_to_cell
from app.repositories import observation_repository, station_repository
from app.services import analysis_service

#: A fixed hour so no test depends on the wall clock.
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)

#: Five stations inside a few kilometres of central Delhi. Fusion needs at least
#: three neighbours within range to predict a location at all, so a smaller
#: cluster would exercise the "cannot be estimated" path instead of detection.
STATION_POSITIONS: dict[int, LonLat] = {
    1: (77.200, 28.600),
    2: (77.220, 28.600),
    3: (77.200, 28.615),
    4: (77.185, 28.590),
    5: (77.215, 28.612),
}

STATION_NAMES: dict[int, str] = {
    1: "Anand Vihar",
    2: "Mandir Marg",
    3: "Punjabi Bagh",
    4: "R K Puram",
    5: "Shadipur",
}

#: What an unremarkable station reads in this synthetic city, in ug/m3.
BACKGROUND_UGM3 = 40.0

#: What the planted hotspot reads. Far enough above the background that the
#: z-score clears the threshold without being tuned to sit just over it.
HOTSPOT_UGM3 = 400.0


@dataclass(frozen=True)
class FakeWeather:
    """Stands in for a WeatherObservation row."""

    observed_at: datetime
    wind_u: float
    wind_v: float


@dataclass(frozen=True)
class FakeSource:
    """Stands in for a PollutionSource row."""

    id: int
    name: str
    source_type: SourceType
    emission_prior: float


def reading_rows(
    hours: int = 4,
    *,
    dirty_station: int | None = 1,
) -> list[tuple[int, str, float, float, str, datetime, float]]:
    """Build the rows ``readings_in_window`` would return.

    Args:
        hours: How many hourly intervals to generate.
        dirty_station: Station that reads at hotspot level, or ``None`` for a
            uniformly unremarkable network.
    """
    rows: list[tuple[int, str, float, float, str, datetime, float]] = []
    for hour in range(hours):
        observed_at = NOW - timedelta(hours=hours - 1 - hour)
        for station_id, (lon, lat) in STATION_POSITIONS.items():
            value = HOTSPOT_UGM3 if station_id == dirty_station else BACKGROUND_UGM3
            rows.append(
                (
                    station_id,
                    STATION_NAMES[station_id],
                    lon,
                    lat,
                    point_to_cell((lon, lat)),
                    observed_at,
                    value,
                )
            )
    return rows


def wind_hours(hours: int = 12) -> list[FakeWeather]:
    """A steady easterly wind field covering the detection window.

    ``wind_u`` is negative because the components say where the air is *going*,
    and air arriving from the east travels west. Without a usable wind field
    attribution correctly refuses to name anything, so a test about ranking has
    to supply one.
    """
    return [
        FakeWeather(observed_at=NOW - timedelta(hours=hour), wind_u=-2.0, wind_v=0.0)
        for hour in range(hours)
    ]


def latest_rows() -> list[tuple[int, str, float, float, str, datetime, float, str]]:
    """Build the rows ``latest_reading_per_station`` would return."""
    return [
        (
            station_id,
            STATION_NAMES[station_id],
            lon,
            lat,
            point_to_cell((lon, lat)),
            NOW,
            HOTSPOT_UGM3 if station_id == 1 else BACKGROUND_UGM3,
            "ug/m3",
        )
        for station_id, (lon, lat) in STATION_POSITIONS.items()
    ]


@pytest.fixture
def stub_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace every repository call the service makes with an empty result.

    Individual tests override the one they care about, so a test that forgets to
    stub something gets an empty list rather than a connection attempt.
    """
    monkeypatch.setattr(observation_repository, "latest_reading_per_station", lambda *a, **k: [])
    monkeypatch.setattr(observation_repository, "readings_in_window", lambda *a, **k: [])
    monkeypatch.setattr(observation_repository, "weather_in_window", lambda *a, **k: [])
    monkeypatch.setattr(observation_repository, "fire_detections_in_window", lambda *a, **k: [])
    monkeypatch.setattr(station_repository, "list_sources_with_coordinates", lambda *a, **k: [])


class TestLatestSnapshots:
    def test_orders_worst_first(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # An operator opening the list is looking for where to send someone, so
        # the ordering is part of the contract rather than a presentation detail.
        monkeypatch.setattr(
            observation_repository, "latest_reading_per_station", lambda *a, **k: latest_rows()
        )

        snapshots = analysis_service.latest_snapshots(_session(), Pollutant.PM25)

        assert snapshots[0].station_id == 1
        assert snapshots == sorted(snapshots, key=lambda s: s.aqi, reverse=True)

    def test_attaches_the_cpcb_sub_index_and_band(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        monkeypatch.setattr(
            observation_repository, "latest_reading_per_station", lambda *a, **k: latest_rows()
        )

        worst = analysis_service.latest_snapshots(_session(), Pollutant.PM25)[0]

        # 400 ug/m3 of PM2.5 is far into the top CPCB band.
        assert worst.category == "Severe"
        assert worst.aqi > 400

    def test_an_empty_network_is_an_empty_list(self, stub_repositories: None) -> None:
        assert analysis_service.latest_snapshots(_session(), Pollutant.PM25) == []


class TestDetectAndAttribute:
    def test_finds_a_planted_hotspot(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        monkeypatch.setattr(
            observation_repository, "readings_in_window", lambda *a, **k: reading_rows()
        )

        detected = analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=24, now=NOW
        )

        assert [item.hotspot.station_id for item in detected] == [1]
        assert detected[0].station_name == "Anand Vihar"

    def test_reports_the_excess_rather_than_the_concentration(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # The quantity that locates a source is observed minus expected. A test
        # asserting only on the observed value would pass for a detector that
        # simply thresholded concentration.
        monkeypatch.setattr(
            observation_repository, "readings_in_window", lambda *a, **k: reading_rows()
        )

        hotspot = analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=24, now=NOW
        )[0].hotspot

        assert hotspot.peak_observed == pytest.approx(HOTSPOT_UGM3)
        assert hotspot.peak_residual > HOTSPOT_UGM3 - BACKGROUND_UGM3 - 1
        assert hotspot.peak_z > 3.0

    def test_a_uniformly_dirty_city_produces_no_hotspot(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # The central claim of the whole detector: a bad day everywhere is not a
        # hotspot anywhere, because observation and prediction move together.
        rows = [
            (station_id, name, lon, lat, cell, observed_at, HOTSPOT_UGM3)
            for station_id, name, lon, lat, cell, observed_at, _ in reading_rows(dirty_station=None)
        ]
        monkeypatch.setattr(observation_repository, "readings_in_window", lambda *a, **k: rows)

        assert (
            analysis_service.detect_and_attribute(
                _session(), Pollutant.PM25, window_hours=24, now=NOW
            )
            == []
        )

    def test_a_single_dirty_hour_does_not_persist_into_a_hotspot(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # One anomalous reading is far more likely to be a glitch than a source.
        rows = reading_rows(hours=1)
        monkeypatch.setattr(observation_repository, "readings_in_window", lambda *a, **k: rows)

        assert (
            analysis_service.detect_and_attribute(
                _session(), Pollutant.PM25, window_hours=24, now=NOW
            )
            == []
        )

    def test_no_wind_field_marks_the_trajectory_unavailable(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # "We could not look" must stay distinguishable from "nothing explains
        # this". Collapsing them would let a calm night read as an all-clear.
        monkeypatch.setattr(
            observation_repository, "readings_in_window", lambda *a, **k: reading_rows()
        )

        detected = analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=24, now=NOW
        )

        assert detected[0].trajectory_unavailable is True
        assert detected[0].attributions == []

    def test_ranks_a_nearby_registered_source(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        monkeypatch.setattr(
            observation_repository, "readings_in_window", lambda *a, **k: reading_rows()
        )
        monkeypatch.setattr(
            observation_repository, "weather_in_window", lambda *a, **k: wind_hours()
        )
        monkeypatch.setattr(
            station_repository,
            "list_sources_with_coordinates",
            lambda *a, **k: [
                (
                    FakeSource(
                        id=7,
                        name="Anand Vihar ISBT",
                        source_type=SourceType.ROAD_SEGMENT,
                        emission_prior=0.9,
                    ),
                    77.2015,
                    28.6008,
                )
            ],
        )

        detected = analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=24, now=NOW
        )

        names = [candidate.source.name for candidate in detected[0].attributions]
        assert "Anand Vihar ISBT" in names

    def test_confidence_never_reaches_certainty(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # Naming the wrong operator is worse than naming nobody, so a candidate
        # is ranked, never asserted.
        monkeypatch.setattr(
            observation_repository, "readings_in_window", lambda *a, **k: reading_rows()
        )
        monkeypatch.setattr(
            observation_repository, "weather_in_window", lambda *a, **k: wind_hours()
        )
        monkeypatch.setattr(
            station_repository,
            "list_sources_with_coordinates",
            lambda *a, **k: [
                (
                    FakeSource(
                        id=7,
                        name="Anand Vihar ISBT",
                        source_type=SourceType.ROAD_SEGMENT,
                        emission_prior=1.0,
                    ),
                    77.2001,
                    28.6001,
                )
            ],
        )

        detected = analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=24, now=NOW
        )

        for candidate in detected[0].attributions:
            assert 0.0 < candidate.confidence < 1.0

    def test_passes_the_window_through_to_the_repository(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        seen: dict[str, Any] = {}

        def capture(
            _session: Any,
            pollutant: Pollutant,
            since: datetime,
            until: datetime | None = None,
        ) -> list[Any]:
            seen["pollutant"] = pollutant
            seen["since"] = since
            seen["until"] = until
            return []

        monkeypatch.setattr(observation_repository, "readings_in_window", capture)

        analysis_service.detect_and_attribute(_session(), Pollutant.PM10, window_hours=6, now=NOW)

        assert seen["pollutant"] is Pollutant.PM10
        assert seen["since"] == NOW - timedelta(hours=6)
        # Unbounded by default: the live API always means "up to now", and
        # capping the window there would hide the most recent hours.
        assert seen["until"] is None

    def test_a_bounded_window_stops_at_the_reference_time(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # Replaying a recorded episode needs the upper bound, or observations
        # from after the episode leak in and the result stops being a property
        # of the recording.
        seen: dict[str, Any] = {}

        def capture(
            _session: Any,
            pollutant: Pollutant,
            since: datetime,
            until: datetime | None = None,
        ) -> list[Any]:
            seen["until"] = until
            return []

        monkeypatch.setattr(observation_repository, "readings_in_window", capture)

        analysis_service.detect_and_attribute(
            _session(), Pollutant.PM25, window_hours=6, now=NOW, bounded=True
        )

        assert seen["until"] == NOW


class TestCorridorOutlook:
    def test_forecasts_along_a_route_covered_by_stations(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        monkeypatch.setattr(
            observation_repository,
            "readings_in_window",
            lambda *a, **k: reading_rows(hours=72),
        )

        outlook = analysis_service.corridor_outlook(
            _session(),
            [(77.185, 28.590), (77.220, 28.615)],
            Pollutant.PM25,
            horizon_hours=24,
            now=NOW,
        )

        assert outlook.points
        assert all(point.uncertainty > 0 for point in outlook.points)
        assert outlook.length_m > 0

    def test_a_corridor_with_no_stations_in_range_returns_nothing(
        self, monkeypatch: pytest.MonkeyPatch, stub_repositories: None
    ) -> None:
        # A stretch nothing supports must render as unknown, never as clean.
        monkeypatch.setattr(
            observation_repository,
            "readings_in_window",
            lambda *a, **k: reading_rows(hours=72),
        )

        outlook = analysis_service.corridor_outlook(
            _session(),
            [(72.80, 19.00), (72.85, 19.05)],  # Mumbai, far from the test network
            Pollutant.PM25,
            horizon_hours=24,
            now=NOW,
        )

        # No points, but a real length: the route exists, nothing supports it.
        # A consumer that saw only an empty list could not tell those apart.
        assert outlook.points == []
        assert outlook.length_m > 0

    def test_an_empty_history_forecasts_nothing(self, stub_repositories: None) -> None:
        outlook = analysis_service.corridor_outlook(
            _session(),
            [(77.185, 28.590), (77.220, 28.615)],
            Pollutant.PM25,
            horizon_hours=24,
            now=NOW,
        )

        assert outlook.points == []


def _session() -> Any:
    """A stand-in session.

    The service never touches it -- every repository call is stubbed -- so the
    object only has to be passed along unchanged. Constructing a real
    ``Session`` would open a connection pool for no reason.
    """
    return object()
