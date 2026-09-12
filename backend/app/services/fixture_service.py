"""Exporting and replaying a recorded episode.

Every result this project reports came from live upstreams over a fourteen-day
window. That makes them real and makes them unreproducible: a reader would need
three API keys, a backfill and the same fortnight of weather to see any of it.

A fixture closes that gap. It is a window of the actual observations, recorded
verbatim, with the finding it is expected to produce written into the file
itself. Replaying it loads the window into a database and runs the real
detection over it -- not a recording of the output, the actual code -- and fails
if the episode stops being found.

That makes it a regression test with a public-health meaning rather than a demo.
If a change to fusion, the uncertainty model or the persistence filter quietly
stops the system seeing a 341 ug/m3 excess at a bus terminal, this is what says
so.

The observations are public CPCB and DPCC reference-monitor readings, which is
why they can be committed at all.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Pollutant, SourceType, StationTier
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.repositories import observation_repository, station_repository
from app.repositories.models import Station, WeatherObservation
from app.repositories.observation_repository import MeasurementRow, WeatherRow

logger = get_logger(__name__)

#: Where recorded episodes live.
FIXTURE_DIRECTORY = Path(__file__).resolve().parents[3] / "infra" / "fixtures"

#: Schema version, so a fixture recorded against an older shape fails loudly
#: rather than loading partially.
FIXTURE_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExpectedFinding:
    """What replaying a fixture must produce.

    Carried in the fixture rather than in the replay command, so the file is
    self-describing: whoever reads it can see what it is supposed to demonstrate
    without reading the code that checks it.
    """

    station_name: str
    min_peak_z: float
    min_peak_excess: float
    description: str


@dataclass(frozen=True, slots=True)
class LoadReport:
    """What loading a fixture inserted."""

    stations: int
    measurements: int
    weather: int
    sources: int


def export(
    session: Session,
    *,
    since: datetime,
    until: datetime,
    pollutant: Pollutant,
    expected: ExpectedFinding,
    name: str,
) -> dict[str, Any]:
    """Record a window of observations as a replayable fixture."""
    rows = [
        row
        for row in observation_repository.readings_in_window(session, pollutant, since)
        if row[5] < until
    ]
    station_ids = {int(row[0]) for row in rows}

    stations = [
        station
        for station in session.execute(select(Station)).scalars()
        if station.id in station_ids
    ]
    # Coordinates come from the reading rows rather than a second query: the
    # same rows already carry the station's position, and asking twice would let
    # the two answers drift.
    positions = {int(row[0]): (float(row[2]), float(row[3])) for row in rows}

    weather = list(
        session.execute(
            select(WeatherObservation).where(
                WeatherObservation.observed_at >= since,
                WeatherObservation.observed_at < until,
            )
        ).scalars()
    )

    sources = [
        {
            "name": source.name,
            "source_type": source.source_type.value,
            "coordinates": [lon, lat],
            "emission_prior": source.emission_prior,
        }
        for source, lon, lat in station_repository.list_sources_with_coordinates(session)
    ]

    return {
        "version": FIXTURE_VERSION,
        "name": name,
        "_about": (
            "A recorded window of real CPCB and DPCC reference-monitor observations, "
            "replayable without API keys. Public data, recorded verbatim."
        ),
        "_coordinate_order": "[longitude, latitude], WGS84",
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "pollutant": pollutant.value,
        "expected": {
            "station_name": expected.station_name,
            "min_peak_z": expected.min_peak_z,
            "min_peak_excess": expected.min_peak_excess,
            "description": expected.description,
        },
        "stations": [
            {
                "source": station.source,
                "source_station_id": station.source_station_id,
                "name": station.name,
                "tier": station.tier.value,
                "coordinates": list(positions[station.id]),
            }
            for station in stations
            if station.id in positions
        ],
        "measurements": [
            {
                "source_station_id": _source_id(stations, int(row[0])),
                "observed_at": row[5].isoformat(),
                "value": float(row[6]),
            }
            for row in rows
        ],
        "weather": [
            {
                "h3_cell": record.h3_cell,
                "observed_at": record.observed_at.isoformat(),
                "wind_u": record.wind_u,
                "wind_v": record.wind_v,
                "temperature_c": record.temperature_c,
                "relative_humidity_pct": record.relative_humidity_pct,
                "pbl_height_m": record.pbl_height_m,
                "precipitation_mm": record.precipitation_mm,
            }
            for record in weather
        ],
        "sources": sources,
    }


def _source_id(stations: list[Station], station_id: int) -> str:
    """Map a database id to the upstream identity a fixture is keyed on.

    Fixtures cannot carry database ids: loading into a fresh database assigns new
    ones. The upstream identity is what survives a reload.
    """
    for station in stations:
        if station.id == station_id:
            return station.source_station_id
    return str(station_id)  # pragma: no cover - every row joins a station.


def read_fixture(path: Path) -> dict[str, Any]:
    """Read a fixture, refusing one recorded against a different schema."""
    if not path.exists():
        raise ValidationError(f"No fixture at {path}.", details={"path": str(path)})

    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    version = document.get("version")
    if version != FIXTURE_VERSION:
        raise ValidationError(
            f"Fixture {path.name} is version {version!r}, expected {FIXTURE_VERSION}.",
        )
    return document


def load(session: Session, document: dict[str, Any]) -> LoadReport:
    """Load a fixture into the database.

    Idempotent, like every other write here: replaying the same episode twice
    converges rather than duplicating, so a replay can be run repeatedly while
    debugging without the network drifting under it.
    """
    pollutant = Pollutant(document["pollutant"])

    station_ids: dict[str, int] = {}
    for entry in document["stations"]:
        longitude, latitude = entry["coordinates"]
        station_ids[entry["source_station_id"]] = station_repository.upsert_station(
            session,
            source=entry["source"],
            source_station_id=entry["source_station_id"],
            name=entry["name"],
            tier=StationTier(entry["tier"]),
            coordinates=(float(longitude), float(latitude)),
        )
    session.flush()

    measurements = [
        MeasurementRow(
            station_id=station_ids[entry["source_station_id"]],
            observed_at=datetime.fromisoformat(entry["observed_at"]),
            pollutant=pollutant,
            value_raw=float(entry["value"]),
            unit="ug/m3",
        )
        for entry in document["measurements"]
        if entry["source_station_id"] in station_ids
    ]
    observation_repository.upsert_measurements(session, measurements)

    weather = [
        WeatherRow(
            h3_cell=entry["h3_cell"],
            observed_at=datetime.fromisoformat(entry["observed_at"]),
            wind_u=float(entry["wind_u"]),
            wind_v=float(entry["wind_v"]),
            temperature_c=float(entry["temperature_c"]),
            relative_humidity_pct=float(entry["relative_humidity_pct"]),
            pbl_height_m=entry["pbl_height_m"],
            precipitation_mm=float(entry["precipitation_mm"]),
            is_forecast=False,
        )
        for entry in document["weather"]
    ]
    observation_repository.upsert_weather(session, weather)

    for entry in document.get("sources", []):
        longitude, latitude = entry["coordinates"]
        station_repository.upsert_pollution_source(
            session,
            name=entry["name"],
            source_type=SourceType(entry["source_type"]),
            coordinates=(float(longitude), float(latitude)),
            emission_prior=float(entry["emission_prior"]),
        )
    session.flush()

    logger.info(
        "fixture.loaded",
        name=document.get("name"),
        stations=len(station_ids),
        measurements=len(measurements),
        weather=len(weather),
    )
    return LoadReport(
        stations=len(station_ids),
        measurements=len(measurements),
        weather=len(weather),
        sources=len(document.get("sources", [])),
    )


def expected_finding(document: dict[str, Any]) -> ExpectedFinding:
    """The finding a fixture asserts its window should produce."""
    entry = document["expected"]
    return ExpectedFinding(
        station_name=str(entry["station_name"]),
        min_peak_z=float(entry["min_peak_z"]),
        min_peak_excess=float(entry["min_peak_excess"]),
        description=str(entry["description"]),
    )
