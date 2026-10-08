"""Tests for the live index worked out from the monitors' latest readings."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.core import aqi
from app.core.constants import LIVE_INDEX_COMBINE_HOURS
from app.core.enums import MeasurementOrigin, PilotCity, Pollutant
from app.core.geo import LonLat
from app.repositories import observation_repository
from app.services import live_index_service

NOW = datetime(2026, 10, 8, 13, 0, tzinfo=UTC)

ANAND_VIHAR: LonLat = (77.3152, 28.6468)
PUSA: LonLat = (77.1475, 28.6397)
#: Kanpur, well outside Delhi's view.
NEHRU_NAGAR_KANPUR: LonLat = (80.3237, 26.4706)

Row = tuple[int, str, float, float, str, datetime, float, str, str]


def row(
    station_id: int,
    position: LonLat,
    value: float,
    *,
    at: datetime = NOW,
    origin: MeasurementOrigin = MeasurementOrigin.OPENAQ,
) -> Row:
    """A row as ``latest_reading_per_station`` returns it."""
    names = {1: "Anand Vihar, New Delhi - DPCC", 2: "Pusa, Delhi - IMD", 3: "Nehru Nagar - UPPCB"}
    return (station_id, names[station_id], *position, "cell", at, value, "ug/m3", origin.value)


def stub_latest(monkeypatch: pytest.MonkeyPatch, rows: dict[Pollutant, list[Row]]) -> None:
    def latest(_session: Any, pollutant: Pollutant, *_: Any, **__: Any) -> list[Row]:
        return rows.get(pollutant, [])

    monkeypatch.setattr(observation_repository, "latest_reading_per_station", latest)


def test_takes_the_higher_sub_index_and_names_its_pollutant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub_latest(
        monkeypatch,
        {
            Pollutant.PM25: [row(1, ANAND_VIHAR, 100.0, origin=MeasurementOrigin.WAQI)],
            Pollutant.PM10: [row(1, ANAND_VIHAR, 150.0, at=NOW - timedelta(hours=1))],
        },
    )

    [station] = live_index_service.live_for_city(object(), PilotCity.DELHI)  # type: ignore[arg-type]

    assert station.aqi == pytest.approx(aqi.sub_index(Pollutant.PM25, 100.0))
    assert station.dominant_pollutant is Pollutant.PM25
    assert station.sub_indices[Pollutant.PM10] == pytest.approx(aqi.sub_index(Pollutant.PM10, 150))
    assert station.category == aqi.category(station.aqi)
    assert station.observed_at == NOW
    assert station.oldest_observed_at == NOW - timedelta(hours=1)
    assert station.origins == [MeasurementOrigin.OPENAQ, MeasurementOrigin.WAQI]


def test_leaves_out_a_pollutant_that_stopped_reporting(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = NOW - timedelta(hours=LIVE_INDEX_COMBINE_HOURS + 1)
    stub_latest(
        monkeypatch,
        {
            Pollutant.PM25: [row(1, ANAND_VIHAR, 40.0)],
            Pollutant.PM10: [row(1, ANAND_VIHAR, 400.0, at=stopped)],
        },
    )

    [station] = live_index_service.live_for_city(object(), PilotCity.DELHI)  # type: ignore[arg-type]

    assert set(station.sub_indices) == {Pollutant.PM25}
    assert station.oldest_observed_at == NOW


def test_lists_the_citys_monitors_only_worst_first(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_latest(
        monkeypatch,
        {
            Pollutant.PM25: [
                row(1, ANAND_VIHAR, 30.0),
                row(2, PUSA, 90.0),
                row(3, NEHRU_NAGAR_KANPUR, 200.0),
            ]
        },
    )

    stations = live_index_service.live_for_city(object(), PilotCity.DELHI)  # type: ignore[arg-type]

    assert [station.station_id for station in stations] == [2, 1]


def test_a_city_with_no_readings_has_no_index(monkeypatch: pytest.MonkeyPatch) -> None:
    stub_latest(monkeypatch, {})

    assert live_index_service.live_for_city(object(), PilotCity.KANPUR) == []  # type: ignore[arg-type]
