"""Command-line entry points for operational tasks.

Kept thin: each command parses arguments, calls one service, and reports. Every
rule lives in the service layer, so a command and an API route produce identical
behaviour.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime

from app.core.config import get_settings
from app.core.constants import BACKFILL_DAYS, PILOT_CITY_CENTRES, PILOT_CITY_FIRE_BOXES
from app.core.enums import PilotCity, Pollutant
from app.core.geo import LonLat
from app.core.logging import configure_logging, get_logger
from app.repositories import observation_repository, station_repository
from app.repositories.session import session_scope
from app.services import (
    alert_delivery_service,
    alert_service,
    analysis_service,
    fixture_service,
    official_aqi_service,
    plausibility_service,
    satellite_service,
    seed_service,
)
from app.services.alert_service import DEFAULT_DISPATCH_WINDOW_HOURS
from app.services.ingestion_service import IngestionReport, IngestionService, SourceResult

logger = get_logger(__name__)

#: Pilot cities, chosen to span distinct pollution regimes. Coimbatore is
#: deliberately included as the data-poor southern node: it is the one that
#: benefits from federated model sharing, which is the whole argument for it.
PILOT_CITIES: dict[str, tuple[LonLat, tuple[float, float, float, float]]] = {
    name: (centre, PILOT_CITY_FIRE_BOXES[name]) for name, centre in PILOT_CITY_CENTRES.items()
}

#: Exit code used when at least one upstream failed.
_EXIT_PARTIAL_FAILURE = 1

#: Most hotspots and candidates a replay lists, so the output stays readable.
_REPLAY_MAX_LISTED = 5
_REPLAY_MAX_CANDIDATES = 2


def _print_report(report: IngestionReport) -> None:
    """Render an ingestion report for a human reading a terminal."""
    duration = (report.finished_at - report.started_at).total_seconds()
    print(f"\ningestion completed in {duration:.1f}s")
    print(f"{'source':<14} {'status':<10} {'records':>8}  detail")
    print("-" * 72)
    for result in report.results:
        status = "ok" if result.succeeded else "FAILED"
        detail = "" if result.succeeded else f"{result.error_code}: {result.error_message}"
        print(f"{result.source:<14} {status:<10} {result.records:>8}  {detail}")

    with session_scope() as session:
        print("\nstored totals")
        print(f"  stations     : {station_repository.count_stations(session)}")
        print(f"  measurements : {observation_repository.count_measurements(session)}")
        print(f"  weather hours: {observation_repository.count_weather(session)}")
        print(f"  fires        : {observation_repository.count_fire_detections(session)}")
        latest = observation_repository.latest_measurement_at(session)
        if latest is not None:
            print(f"  latest reading: {latest.isoformat()}")


async def _run_ingestion(city: str, radius_m: int, skip_fires: bool) -> IngestionReport:
    """Ingest one pilot city."""
    centre, fire_bbox = PILOT_CITIES[city]
    service = IngestionService(get_settings())
    return await service.ingest_all(
        centre,
        radius_m=radius_m,
        fire_bbox=None if skip_fires else fire_bbox,
    )


async def _run_backfill(city: str, pollutant: Pollutant, days: int) -> SourceResult:
    """Backfill hourly history for one pilot city."""
    centre, _ = PILOT_CITIES[city]
    service = IngestionService(get_settings())
    return await service.backfill_history(centre, pollutant=pollutant, days=days)


def _replay(event: str) -> int:
    """Load a recorded episode and check the system still finds it.

    Returns a non-zero exit code when the expected finding is absent. That is
    the point of the command: it is a regression test with a public-health
    meaning, not a demo. If a change quietly stops the system seeing a large
    excess at a monitored location, this is what says so.
    """
    path = fixture_service.FIXTURE_DIRECTORY / f"{event}.json"
    document = fixture_service.read_fixture(path)
    expected = fixture_service.expected_finding(document)

    with session_scope() as session:
        report = fixture_service.load(session, document)
        window = document["window"]
        since = datetime.fromisoformat(window["since"])
        until = datetime.fromisoformat(window["until"])
        hours = int((until - since).total_seconds() // 3600) + 1

        detected = analysis_service.detect_and_attribute(
            session,
            Pollutant(document["pollutant"]),
            window_hours=hours,
            now=until,
            bounded=True,
        )

    print("")
    print(f"replayed {event}")
    print(f"  loaded       : {report.stations} stations, {report.measurements} readings")
    print(f"  window       : {window['since']} to {window['until']}")
    print(f"  expecting    : {expected.description}")
    print("")
    print(f"detected {len(detected)} hotspot(s):")
    for item in detected[:_REPLAY_MAX_LISTED]:
        hotspot = item.hotspot
        expected_value = hotspot.peak_observed - hotspot.peak_residual
        print(
            f"  {item.station_name}: {hotspot.peak_observed:.0f} ug/m3 where the network "
            f"predicted {expected_value:.0f} (excess {hotspot.peak_residual:.0f}, "
            f"z={hotspot.peak_z:.1f}, {hotspot.intervals} intervals)"
        )
        for candidate in item.attributions[:_REPLAY_MAX_CANDIDATES]:
            print(
                f"      candidate: {candidate.source.name} ({candidate.confidence:.0%} plausible)"
            )

    match = [
        item
        for item in detected
        if expected.station_name.lower() in item.station_name.lower()
        and item.hotspot.peak_z >= expected.min_peak_z
        and item.hotspot.peak_residual >= expected.min_peak_excess
    ]

    print("")
    if match:
        print(f"PASS: the expected episode at {expected.station_name} was found.")
        return 0

    print(
        f"FAIL: no episode at {expected.station_name} with z >= {expected.min_peak_z} "
        f"and excess >= {expected.min_peak_excess} ug/m3."
    )
    return _EXIT_PARTIAL_FAILURE


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = argparse.ArgumentParser(prog="airwatch", description="AirWatch operational tasks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Fetch from every upstream and store the results")
    ingest.add_argument(
        "--city",
        choices=sorted(PILOT_CITIES),
        default="delhi",
        help="Pilot city to ingest (default: delhi)",
    )
    ingest.add_argument(
        "--radius-m",
        type=int,
        default=25_000,
        help="Station search radius in metres (default: 25000)",
    )
    ingest.add_argument(
        "--skip-fires",
        action="store_true",
        help="Skip FIRMS, for when no MAP_KEY is configured",
    )

    backfill = subparsers.add_parser(
        "backfill", help="Pull hourly history so fusion has a time series to learn from"
    )
    backfill.add_argument("--city", choices=sorted(PILOT_CITIES), default="delhi")
    backfill.add_argument(
        "--pollutant",
        choices=[member.value for member in Pollutant],
        default=Pollutant.PM25.value,
    )
    backfill.add_argument("--days", type=int, default=BACKFILL_DAYS)

    official = subparsers.add_parser(
        "official-aqi", help="Fetch CPCB's live AQI for a city from data.gov.in"
    )
    official.add_argument("--city", choices=sorted(PILOT_CITIES), default="coimbatore")

    satellite = subparsers.add_parser(
        "satellite", help="Fetch Sentinel-5P daily column means from Earth Engine"
    )
    satellite.add_argument("--city", choices=sorted(PILOT_CITIES), default="coimbatore")

    subparsers.add_parser(
        "reflag",
        help="Re-apply the plausibility bounds to every stored reading",
    )

    subparsers.add_parser(
        "seed",
        help="Load the source and authority registries from infra/seed",
    )

    dispatch = subparsers.add_parser(
        "dispatch", help="Detect hotspots and route alerts to the responsible authorities"
    )
    dispatch.add_argument(
        "--pollutant",
        choices=[member.value for member in Pollutant],
        default=Pollutant.PM25.value,
    )
    dispatch.add_argument("--window-hours", type=int, default=DEFAULT_DISPATCH_WINDOW_HOURS)

    subparsers.add_parser(
        "deliver",
        help="Send recorded alerts to the configured authority endpoint",
    )

    record = subparsers.add_parser(
        "record-fixture", help="Record a window of observations as a replayable episode"
    )
    record.add_argument("--name", required=True, help="Fixture name, used as the filename")
    record.add_argument("--since", required=True, help="ISO timestamp, inclusive")
    record.add_argument("--until", required=True, help="ISO timestamp, exclusive")
    record.add_argument("--station", required=True, help="Station the episode is expected at")
    record.add_argument("--min-z", type=float, required=True)
    record.add_argument("--min-excess", type=float, required=True)
    record.add_argument("--description", required=True)

    replay = subparsers.add_parser(
        "replay", help="Load a recorded episode and assert the system still finds it"
    )
    replay.add_argument("--event", required=True, help="Fixture name under infra/fixtures")

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=False)

    if args.command == "official-aqi":
        with session_scope() as session:
            stored = asyncio.run(
                official_aqi_service.ingest_city(settings, session, PilotCity(args.city))
            )
            stations = official_aqi_service.latest_for_city(session, PilotCity(args.city))
        print("")
        print(f"official AQI {args.city}: {stored} sub-indices stored")
        for station in stations:
            figure = f"AQI {station.aqi:.0f}" if station.aqi is not None else "no AQI stated"
            print(f"  {station.station_name:<48} {figure:<14} {station.reported_at.isoformat()}")
        return 0

    if args.command == "satellite":
        with session_scope() as session:
            summary = satellite_service.ingest_with_earth_engine(
                settings, session, PilotCity(args.city)
            )
        print("")
        print(f"satellite {summary.city.value}: {summary.stored} cell-days stored")
        for product, days in summary.days_observed.items():
            print(f"  {product.value:<14} observed on {days} of {summary.days} days")
        return 0

    if args.command == "reflag":
        with session_scope() as session:
            flagged = plausibility_service.reassess(session)
        print("")
        for pollutant, count in flagged.items():
            print(f"{pollutant.value:<5} flagged implausible: {count}")
        return 0

    if args.command == "seed":
        with session_scope() as session:
            seeded = seed_service.load_all(session)
        print("")
        print(f"pollution sources: {seeded.sources}")
        print(f"authorities      : {seeded.authorities}")
        return 0

    if args.command == "dispatch":
        with session_scope() as session:
            outcome = alert_service.dispatch(
                session,
                Pollutant(args.pollutant),
                window_hours=args.window_hours,
            )
        print("")
        print(f"hotspots detected : {outcome.detected}")
        print(f"alerts raised     : {len(outcome.raised)}")
        print(f"  to neighbours   : {outcome.coordination_requests}")
        print(f"suppressed        : {outcome.suppressed}")
        # An unrouted hotspot is a gap in the authority registry, not a quiet
        # day, so it is reported rather than left implicit in the difference.
        print(f"unrouted          : {outcome.unrouted}")
        return 0

    if args.command == "deliver":
        with session_scope() as session:
            delivery = asyncio.run(alert_delivery_service.deliver_pending(session, settings))
            still_pending = alert_delivery_service.pending_count(session)
        print("")
        if not delivery.endpoint_configured:
            # Nowhere to send is not the same as nothing to send, and a run that
            # reported success here would be claiming an authority was told.
            print("no ALERT_WEBHOOK_URL configured; nothing was sent")
            print(f"alerts waiting  : {still_pending}")
            return _EXIT_PARTIAL_FAILURE
        print(f"attempted       : {delivery.attempted}")
        print(f"delivered       : {delivery.delivered}")
        print(f"failed          : {delivery.failed}")
        print(f"still waiting   : {still_pending}")
        return 0 if delivery.failed == 0 else _EXIT_PARTIAL_FAILURE

    if args.command == "record-fixture":
        with session_scope() as session:
            document = fixture_service.export(
                session,
                since=datetime.fromisoformat(args.since),
                until=datetime.fromisoformat(args.until),
                pollutant=Pollutant.PM25,
                name=args.name,
                expected=fixture_service.ExpectedFinding(
                    station_name=args.station,
                    min_peak_z=args.min_z,
                    min_peak_excess=args.min_excess,
                    description=args.description,
                ),
            )
        fixture_service.FIXTURE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        target = fixture_service.FIXTURE_DIRECTORY / f"{args.name}.json"
        target.write_text(json.dumps(document, indent=2), encoding="utf-8")
        print("")
        print(f"recorded {target.name}")
        print(f"  stations    : {len(document['stations'])}")
        print(f"  measurements: {len(document['measurements'])}")
        print(f"  weather     : {len(document['weather'])}")
        return 0

    if args.command == "replay":
        return _replay(args.event)

    if args.command == "backfill":
        result = asyncio.run(_run_backfill(args.city, Pollutant(args.pollutant), args.days))
        status = "ok" if result.succeeded else "FAILED"
        print("")
        print(f"{result.source}: {status}, {result.records} hourly readings stored")
        if not result.succeeded:
            print(f"  {result.error_code}: {result.error_message}")
        with session_scope() as session:
            print(
                f"  measurements now stored: {observation_repository.count_measurements(session)}"
            )
        return 0 if result.succeeded else _EXIT_PARTIAL_FAILURE

    if args.command == "ingest":
        report = asyncio.run(_run_ingestion(args.city, args.radius_m, args.skip_fires))
        _print_report(report)
        # A partial failure is a non-zero exit: a scheduled run that half-worked
        # must not look like a clean one.
        return 0 if report.all_succeeded else _EXIT_PARTIAL_FAILURE

    return 0


if __name__ == "__main__":
    sys.exit(main())
