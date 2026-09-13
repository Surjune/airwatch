"""The scheduled worker: keep the data current and the alert chain moving.

Everything else in the system is a response to something having been fetched.
Without a schedule the map goes stale within a day -- the federation dashboard
already says "stale here" for Delhi -- and a hotspot that develops overnight is
not detected until someone remembers to run ingestion by hand. For a system whose
point is collapsing detection-to-response time, that is the whole failure mode.

One cycle is: ingest every pilot city, detect and route alerts, attempt
delivery. The worker is an entry point, like the CLI and the routes, so it is the
layer allowed to call several services in sequence.

**Every step is isolated.** An OpenAQ outage for Kanpur must not stop Delhi being
ingested, and a failed ingestion must not stop detection running over the data
already held -- that data is still the best available picture, and silencing
detection because one upstream is down would trade a partial view for none.
Each step's outcome is recorded, and the cycle reports failure if any step
failed, so a scheduler watching the exit code still sees it.

Run it as a long-lived process with ``npm run worker``, or one cycle at a time
from cron or Windows Task Scheduler with ``npm run worker:once``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.core.config import Settings, get_settings
from app.core.constants import (
    PILOT_CITY_CENTRES,
    PILOT_CITY_FIRE_BOXES,
    PILOT_CITY_RADIUS_M,
    SATELLITE_INGEST_HOUR_UTC,
    SATELLITE_WORKER_LOOKBACK_DAYS,
    WORKER_DETECTION_WINDOW_HOURS,
    WORKER_INTERVAL_MINUTES,
)
from app.core.enums import PilotCity, Pollutant
from app.core.exceptions import AirWatchError
from app.core.logging import configure_logging, get_logger
from app.external.s5p_client import Sentinel5PClient
from app.repositories.session import session_scope
from app.services import (
    alert_delivery_service,
    alert_service,
    official_aqi_service,
    satellite_service,
)
from app.services.ingestion_service import IngestionService

logger = get_logger(__name__)

#: Seconds in a minute, for turning the configured interval into a sleep.
_SECONDS_PER_MINUTE = 60

#: Exit code when any step of a cycle failed.
_EXIT_STEP_FAILED = 1


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """What one step of a cycle did."""

    name: str
    succeeded: bool
    summary: str


@dataclass(slots=True)
class CycleReport:
    """Everything one cycle did, in the order it did it."""

    started_at: datetime
    steps: list[StepOutcome] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        return all(step.succeeded for step in self.steps)


def _run_step(report: CycleReport, name: str, action: Callable[[], str]) -> None:
    """Run one step, recording its outcome whatever happens.

    Typed application errors are the expected failures -- an upstream down, a
    credential missing -- and are recorded as such. Anything else is also caught,
    because the alternative is one unexpected error ending the worker and every
    later cycle with it; it is logged with its traceback so it is not lost.
    """
    try:
        summary = action()
    except AirWatchError as error:
        logger.warning("worker.step_failed", step=name, code=error.code, message=error.message)
        report.steps.append(StepOutcome(name, False, f"{error.code}: {error.message}"))
    except Exception as error:
        logger.exception("worker.step_crashed", step=name)
        report.steps.append(StepOutcome(name, False, f"unexpected {type(error).__name__}"))
    else:
        report.steps.append(StepOutcome(name, True, summary))


def run_cycle(settings: Settings, *, now: datetime | None = None) -> CycleReport:
    """Run one full cycle: ingest, detect and route, deliver."""
    report = CycleReport(started_at=now or datetime.now(UTC))
    # Fires are fetched only when a key is configured. Without one the step
    # would fail every hour, drowning the failures that actually need attention.
    fetch_fires = settings.has("firms_map_key")

    for city, centre in PILOT_CITY_CENTRES.items():

        def ingest(centre: tuple[float, float] = centre, city: str = city) -> str:
            service = IngestionService(settings)
            outcome = asyncio.run(
                service.ingest_all(
                    centre,
                    radius_m=PILOT_CITY_RADIUS_M,
                    fire_bbox=PILOT_CITY_FIRE_BOXES[city] if fetch_fires else None,
                )
            )
            failed = [result.source for result in outcome.results if not result.succeeded]
            if failed:
                raise _PartialIngestionError(failed, outcome.total_records)
            return f"{outcome.total_records} records"

        _run_step(report, f"ingest:{city}", ingest)

    # CPCB's live feed is fetched only when a data.gov.in key is configured, for
    # the same reason as fires: a step that cannot succeed must not fail hourly.
    if settings.has("cpcb_api_key"):
        for city in PilotCity:

            def official(city: PilotCity = city) -> str:
                with session_scope() as session:
                    stored = asyncio.run(official_aqi_service.ingest_city(settings, session, city))
                return f"{stored} sub-indices"

            _run_step(report, f"official:{city.value}", official)

    if _satellite_due(settings, report.started_at):
        for city in PilotCity:

            def satellite(city: PilotCity = city) -> str:
                client = Sentinel5PClient(settings)
                with session_scope() as session:
                    summary = satellite_service.ingest_city(
                        session,
                        city,
                        client.daily_cell_means,
                        days=SATELLITE_WORKER_LOOKBACK_DAYS,
                    )
                return f"{summary.stored} cell-days"

            _run_step(report, f"satellite:{city.value}", satellite)

    def dispatch() -> str:
        with session_scope() as session:
            outcome = alert_service.dispatch(
                session, Pollutant.PM25, window_hours=WORKER_DETECTION_WINDOW_HOURS
            )
        return (
            f"{outcome.detected} detected, {len(outcome.raised)} raised, "
            f"{outcome.suppressed} suppressed, {outcome.unrouted} unrouted"
        )

    _run_step(report, "dispatch", dispatch)

    def deliver() -> str:
        with session_scope() as session:
            outcome = asyncio.run(alert_delivery_service.deliver_pending(session, settings))
        if not outcome.endpoint_configured:
            # Not a failure of this cycle: nowhere to send is a configuration
            # state, reported every cycle rather than raised as an error.
            return "no endpoint configured; nothing sent"
        if outcome.failed:
            raise _DeliveryFailedError(outcome.failed, outcome.delivered)
        return f"{outcome.delivered} delivered"

    _run_step(report, "deliver", deliver)

    logger.info(
        "worker.cycle_completed",
        succeeded=report.all_succeeded,
        steps={step.name: step.succeeded for step in report.steps},
    )
    return report


def _satellite_due(settings: Settings, now: datetime) -> bool:
    """Whether this cycle should fetch satellite data: configured, and the daily hour."""
    configured = all(
        settings.has(name)
        for name in ("gee_service_account_email", "gee_private_key_path", "gee_project_id")
    )
    return configured and now.hour == SATELLITE_INGEST_HOUR_UTC


class _PartialIngestionError(AirWatchError):
    """Some upstreams for a city failed while others succeeded."""

    code = "partial_ingestion"

    def __init__(self, sources: list[str], stored: int) -> None:
        super().__init__(f"{', '.join(sources)} failed; {stored} records stored from the rest.")


class _DeliveryFailedError(AirWatchError):
    """Some alerts could not be delivered and stay queued."""

    code = "delivery_failed"

    def __init__(self, failed: int, delivered: int) -> None:
        super().__init__(f"{failed} alerts failed to deliver and stay queued; {delivered} sent.")


def _print(report: CycleReport) -> None:
    """Render a cycle for a person reading a terminal or a scheduler log."""
    print(f"\ncycle started {report.started_at.isoformat()}")
    for step in report.steps:
        mark = "ok    " if step.succeeded else "FAILED"
        print(f"  {mark} {step.name:<18} {step.summary}")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="airwatch-worker", description=__doc__.splitlines()[0])
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle and exit, for cron or Windows Task Scheduler",
    )
    parser.add_argument("--interval-minutes", type=int, default=WORKER_INTERVAL_MINUTES)
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.environment != "development")

    if args.once:
        report = run_cycle(settings)
        _print(report)
        return 0 if report.all_succeeded else _EXIT_STEP_FAILED

    logger.info("worker.started", interval_minutes=args.interval_minutes)
    while True:
        started = time.monotonic()
        _print(run_cycle(settings))
        # Sleep the remainder of the interval rather than a fixed period, so a
        # slow cycle does not push every later one further out of step.
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval_minutes * _SECONDS_PER_MINUTE - elapsed))


if __name__ == "__main__":
    sys.exit(main())
