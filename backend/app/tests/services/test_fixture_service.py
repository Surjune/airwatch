"""Replay of the recorded episode, against an empty database.

This is the test that makes every published result checkable. The headline
finding -- 381 ug/m3 at Anand Vihar where the surrounding network predicted 40 --
was produced from live upstreams over a fortnight, which nobody else can
reproduce without three API keys and the same fortnight of weather.

Here the same observations are loaded from a committed file into a database that
starts empty, and the real detection runs over them. Nothing is replayed from a
recording of the output; if fusion, the uncertainty model or the persistence
filter changes in a way that stops the system seeing a bus terminal running nine
times its neighbourhood, this fails.

That is a regression test with a public-health meaning rather than a demo.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.core.exceptions import ValidationError
from app.repositories import observation_repository, station_repository
from app.services import analysis_service, fixture_service

pytestmark = pytest.mark.integration

#: The recorded episode committed under infra/fixtures.
EVENT = "delhi-anand-vihar-august"


@pytest.fixture
def document() -> dict[str, object]:
    return fixture_service.read_fixture(fixture_service.FIXTURE_DIRECTORY / f"{EVENT}.json")


def _window(document: dict[str, object]) -> tuple[datetime, datetime, int]:
    window = document["window"]
    assert isinstance(window, dict)
    since = datetime.fromisoformat(str(window["since"]))
    until = datetime.fromisoformat(str(window["until"]))
    return since, until, int((until - since).total_seconds() // 3600) + 1


class TestLoading:
    def test_loads_into_an_empty_database(
        self, session: Session, document: dict[str, object]
    ) -> None:
        report = fixture_service.load(session, document)

        assert report.stations > 0
        assert report.measurements > 0
        assert station_repository.count_stations(session) == report.stations
        assert observation_repository.count_measurements(session) == report.measurements

    def test_loading_twice_converges(self, session: Session, document: dict[str, object]) -> None:
        # A replay is run repeatedly while debugging, so it has to be idempotent
        # or the second run would analyse a dataset the first one doubled.
        first = fixture_service.load(session, document)
        fixture_service.load(session, document)

        assert observation_repository.count_measurements(session) == first.measurements

    def test_refuses_a_fixture_from_another_schema(self, tmp_path: Path) -> None:
        # A fixture recorded against an older shape must fail loudly rather than
        # load partially, which would produce a result nobody could account for.
        stale = tmp_path / "stale.json"
        stale.write_text(json.dumps({"version": 0, "name": "stale"}), encoding="utf-8")

        with pytest.raises(ValidationError, match="version"):
            fixture_service.read_fixture(stale)

    def test_refuses_a_fixture_that_is_not_there(self, tmp_path: Path) -> None:
        with pytest.raises(ValidationError, match="No fixture"):
            fixture_service.read_fixture(tmp_path / "absent.json")


class TestReplay:
    def test_the_recorded_episode_is_still_detected(
        self, session: Session, document: dict[str, object]
    ) -> None:
        fixture_service.load(session, document)
        expected = fixture_service.expected_finding(document)
        _, until, hours = _window(document)

        detected = analysis_service.detect_and_attribute(
            session, Pollutant.PM25, window_hours=hours, now=until, bounded=True
        )

        matching = [
            item
            for item in detected
            if expected.station_name.lower() in item.station_name.lower()
            and item.hotspot.peak_z >= expected.min_peak_z
            and item.hotspot.peak_residual >= expected.min_peak_excess
        ]
        assert matching, (
            f"no episode at {expected.station_name} with z >= {expected.min_peak_z} "
            f"and excess >= {expected.min_peak_excess}"
        )

    def test_the_excess_is_the_finding_not_the_concentration(
        self, session: Session, document: dict[str, object]
    ) -> None:
        # The number that locates a source is observed minus expected. A
        # detector that had quietly become a threshold alarm would still report
        # a high concentration here, and would still pass a test that only
        # checked one.
        fixture_service.load(session, document)
        _, until, hours = _window(document)

        detected = analysis_service.detect_and_attribute(
            session, Pollutant.PM25, window_hours=hours, now=until, bounded=True
        )
        worst = detected[0].hotspot

        assert worst.peak_residual > worst.peak_observed / 2
        assert worst.peak_z > 10

    def test_the_terminal_beneath_the_station_is_named(
        self, session: Session, document: dict[str, object]
    ) -> None:
        # Attribution is ranked, never asserted, so this checks that the
        # plausible candidate is offered -- not that it is declared the cause.
        fixture_service.load(session, document)
        _, until, hours = _window(document)

        detected = analysis_service.detect_and_attribute(
            session, Pollutant.PM25, window_hours=hours, now=until, bounded=True
        )
        anand = next(item for item in detected if "Anand Vihar" in item.station_name)

        names = [candidate.source.name for candidate in anand.attributions]
        assert any("Anand Vihar" in name for name in names)
        for candidate in anand.attributions:
            assert 0.0 < candidate.confidence < 1.0

    def test_the_window_is_bounded(self, session: Session, document: dict[str, object]) -> None:
        # Without an upper bound the replay would sweep in whatever else the
        # database held after the episode, and the result would stop being a
        # property of the fixture.
        fixture_service.load(session, document)
        since, until, hours = _window(document)

        detected = analysis_service.detect_and_attribute(
            session, Pollutant.PM25, window_hours=hours, now=until, bounded=True
        )

        for item in detected:
            assert since <= item.hotspot.first_seen_at
            assert item.hotspot.last_seen_at < until
