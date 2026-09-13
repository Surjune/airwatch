"""Tests for the scheduled worker.

The property that matters is isolation. The worker exists so a hotspot that
develops overnight is detected without anyone running anything by hand, and that
only holds if one failing upstream cannot take the rest of the cycle down with
it. A Kanpur outage silencing Delhi's detection would recreate the exact gap the
worker was added to close.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app import worker
from app.core.config import Settings
from app.core.constants import PILOT_CITY_CENTRES
from app.core.exceptions import UpstreamUnavailableError
from app.services import alert_delivery_service, alert_service, official_aqi_service
from app.services.ingestion_service import IngestionReport, SourceResult

NOW = datetime(2026, 9, 13, 3, 0, tzinfo=UTC)


@dataclass
class Calls:
    """What the stubbed services were asked to do."""

    ingested: list[tuple[float, float]] = field(default_factory=list)
    fire_boxes: list[object] = field(default_factory=list)
    dispatched: int = 0
    delivered: int = 0


@dataclass(frozen=True)
class FakeDispatch:
    detected: int = 1
    raised: tuple[object, ...] = (object(),)
    suppressed: int = 0
    unrouted: int = 0


@dataclass(frozen=True)
class FakeDelivery:
    attempted: int = 0
    delivered: int = 0
    failed: int = 0
    endpoint_configured: bool = False


def _report(*, failed_sources: tuple[str, ...] = ()) -> IngestionReport:
    results = [
        SourceResult(source="openaq", succeeded="openaq" not in failed_sources, records=10),
        SourceResult(source="open-meteo", succeeded="open-meteo" not in failed_sources, records=24),
    ]
    return IngestionReport(started_at=NOW, finished_at=NOW, results=results)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch, settings: Settings) -> Calls:
    """Stub every service the worker drives, recording each call."""
    recorded = Calls()

    class FakeIngestion:
        def __init__(self, _settings: Settings) -> None: ...

        async def ingest_all(
            self, centre: tuple[float, float], *, radius_m: int, fire_bbox: object = None
        ) -> IngestionReport:
            recorded.ingested.append(centre)
            recorded.fire_boxes.append(fire_bbox)
            return _report()

    def fake_dispatch(*_args: Any, **_kwargs: Any) -> FakeDispatch:
        recorded.dispatched += 1
        return FakeDispatch()

    async def fake_deliver(*_args: Any, **_kwargs: Any) -> FakeDelivery:
        recorded.delivered += 1
        return FakeDelivery()

    @contextmanager
    def fake_session() -> Any:
        yield object()

    monkeypatch.setattr(worker, "IngestionService", FakeIngestion)
    # ``main`` resolves settings itself; without this it would read the developer's
    # own .env and run whichever optional sources happen to be configured there.
    monkeypatch.setattr(worker, "get_settings", lambda: settings)
    monkeypatch.setattr(worker, "session_scope", fake_session)
    monkeypatch.setattr(alert_service, "dispatch", fake_dispatch)
    monkeypatch.setattr(alert_delivery_service, "deliver_pending", fake_deliver)
    return recorded


class TestCycle:
    def test_ingests_every_pilot_city_then_dispatches_then_delivers(
        self, settings: Settings, calls: Calls
    ) -> None:
        report = worker.run_cycle(settings, now=NOW)

        assert len(calls.ingested) == len(PILOT_CITY_CENTRES)
        assert calls.dispatched == 1
        assert calls.delivered == 1
        assert [step.name for step in report.steps][-2:] == ["dispatch", "deliver"]
        assert report.all_succeeded is True

    def test_no_endpoint_is_reported_but_is_not_a_failure(
        self, settings: Settings, calls: Calls
    ) -> None:
        # Nowhere to send is a configuration state. Failing every hour on it
        # would bury the failures that actually need someone's attention.
        report = worker.run_cycle(settings, now=NOW)

        deliver = next(step for step in report.steps if step.name == "deliver")
        assert deliver.succeeded is True
        assert "no endpoint" in deliver.summary


class TestOptionalSources:
    def test_official_and_satellite_steps_are_skipped_when_unconfigured(
        self, settings: Settings, calls: Calls
    ) -> None:
        report = worker.run_cycle(settings, now=NOW.replace(hour=12))

        names = [step.name for step in report.steps]
        assert not any(name.startswith(("official:", "satellite:")) for name in names)

    def test_official_aqi_is_fetched_for_every_city_when_a_key_exists(
        self, settings: Settings, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        fetched: list[str] = []

        async def fake_official(_settings: Settings, _session: object, city: Any) -> int:
            fetched.append(city.value)
            return 7

        monkeypatch.setattr(official_aqi_service, "ingest_city", fake_official)
        keyed = settings.model_copy(update={"cpcb_api_key": "test-key"})

        report = worker.run_cycle(keyed, now=NOW)

        assert sorted(fetched) == sorted(PILOT_CITY_CENTRES)
        assert all(step.succeeded for step in report.steps if step.name.startswith("official:"))

    @pytest.mark.parametrize(("hour", "due"), [(12, True), (13, False), (3, False)])
    def test_satellite_runs_once_a_day_when_configured(
        self, settings: Settings, hour: int, due: bool
    ) -> None:
        configured = settings.model_copy(
            update={
                "gee_service_account_email": "svc@project.iam.gserviceaccount.com",
                "gee_private_key_path": "C:/keys/key.json",
                "gee_project_id": "project",
            }
        )
        assert worker._satellite_due(configured, NOW.replace(hour=hour)) is due
        assert worker._satellite_due(settings, NOW.replace(hour=hour)) is False


class TestFires:
    def test_fires_are_skipped_without_a_key(self, settings: Settings, calls: Calls) -> None:
        worker.run_cycle(settings, now=NOW)

        assert all(box is None for box in calls.fire_boxes)

    def test_fires_are_fetched_for_each_city_when_a_key_exists(
        self, configured_settings: Settings, calls: Calls
    ) -> None:
        worker.run_cycle(configured_settings, now=NOW)

        assert all(box is not None for box in calls.fire_boxes)
        assert len(set(calls.fire_boxes)) == len(PILOT_CITY_CENTRES)


class TestIsolation:
    def test_one_city_failing_does_not_stop_the_others(
        self, settings: Settings, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        failing = PILOT_CITY_CENTRES["kanpur"]

        class FlakyIngestion:
            def __init__(self, _settings: Settings) -> None: ...

            async def ingest_all(
                self, centre: tuple[float, float], *, radius_m: int, fire_bbox: object = None
            ) -> IngestionReport:
                calls.ingested.append(centre)
                if centre == failing:
                    raise UpstreamUnavailableError("openaq", "OpenAQ could not be reached.")
                return _report()

        monkeypatch.setattr(worker, "IngestionService", FlakyIngestion)

        report = worker.run_cycle(settings, now=NOW)

        assert len(calls.ingested) == len(PILOT_CITY_CENTRES)
        kanpur = next(step for step in report.steps if step.name == "ingest:kanpur")
        assert kanpur.succeeded is False
        assert report.all_succeeded is False

    def test_failed_ingestion_still_lets_detection_run(
        self, settings: Settings, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The data already held is still the best available picture. Silencing
        # detection because an upstream is down would trade a partial view for none.
        class DownIngestion:
            def __init__(self, _settings: Settings) -> None: ...

            async def ingest_all(self, *_args: Any, **_kwargs: Any) -> IngestionReport:
                raise UpstreamUnavailableError("openaq", "down")

        monkeypatch.setattr(worker, "IngestionService", DownIngestion)

        worker.run_cycle(settings, now=NOW)

        assert calls.dispatched == 1
        assert calls.delivered == 1

    def test_a_partial_ingestion_is_recorded_as_a_failure(
        self, settings: Settings, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # One source down while the others succeed must still surface: a
        # scheduler reading only the exit code has to see it.
        class PartialIngestion:
            def __init__(self, _settings: Settings) -> None: ...

            async def ingest_all(self, *_args: Any, **_kwargs: Any) -> IngestionReport:
                return _report(failed_sources=("openaq",))

        monkeypatch.setattr(worker, "IngestionService", PartialIngestion)

        report = worker.run_cycle(settings, now=NOW)

        ingest_steps = [step for step in report.steps if step.name.startswith("ingest:")]
        assert all(not step.succeeded for step in ingest_steps)
        assert "openaq failed" in ingest_steps[0].summary

    def test_an_unexpected_crash_is_contained(
        self, settings: Settings, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # An unanticipated error must not end the worker and every later cycle.
        def broken_dispatch(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("bug")

        monkeypatch.setattr(alert_service, "dispatch", broken_dispatch)

        report = worker.run_cycle(settings, now=NOW)

        dispatch = next(step for step in report.steps if step.name == "dispatch")
        assert dispatch.succeeded is False
        assert "RuntimeError" in dispatch.summary
        assert calls.delivered == 1


class TestExitCode:
    def test_once_exits_non_zero_when_a_step_failed(
        self, calls: Calls, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def broken_dispatch(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("bug")

        monkeypatch.setattr(alert_service, "dispatch", broken_dispatch)

        assert worker.main(["--once"]) == 1

    def test_once_exits_zero_on_a_clean_cycle(self, calls: Calls) -> None:
        assert worker.main(["--once"]) == 0
