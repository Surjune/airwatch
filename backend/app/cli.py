"""Command-line entry points for operational tasks.

Kept thin: each command parses arguments, calls one service, and reports. Every
rule lives in the service layer, so a command and an API route produce identical
behaviour.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.config import get_settings
from app.core.geo import LonLat
from app.core.logging import configure_logging, get_logger
from app.repositories import observation_repository, station_repository
from app.repositories.session import session_scope
from app.services.ingestion_service import IngestionReport, IngestionService

logger = get_logger(__name__)

#: Pilot cities, chosen to span distinct pollution regimes. Coimbatore is
#: deliberately included as the data-poor southern node: it is the one that
#: benefits from federated model sharing, which is the whole argument for it.
PILOT_CITIES: dict[str, tuple[LonLat, tuple[float, float, float, float]]] = {
    # name: (centre (lon, lat), fire bbox (west, south, east, north))
    "delhi": ((77.2090, 28.6139), (76.0, 27.8, 78.2, 29.3)),
    "kanpur": ((80.3319, 26.4499), (79.8, 26.0, 80.9, 27.0)),
    "coimbatore": ((76.9558, 11.0168), (76.4, 10.6, 77.5, 11.5)),
}

#: Exit code used when at least one upstream failed.
_EXIT_PARTIAL_FAILURE = 1


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

    args = parser.parse_args(argv)
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=False)

    if args.command == "ingest":
        report = asyncio.run(_run_ingestion(args.city, args.radius_m, args.skip_fires))
        _print_report(report)
        # A partial failure is a non-zero exit: a scheduled run that half-worked
        # must not look like a clean one.
        return 0 if report.all_succeeded else _EXIT_PARTIAL_FAILURE

    return 0


if __name__ == "__main__":
    sys.exit(main())
