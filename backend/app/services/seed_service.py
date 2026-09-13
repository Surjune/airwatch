"""Loading the source and authority registries from checked-in JSON.

Both files are explicitly illustrative. A real deployment replaces them with the
consented-unit inventory a state board holds and the jurisdiction geometry the
state publishes. They exist so attribution has candidates to rank and alerts
have somewhere to route, rather than those pillars appearing to work only
because nothing was ever loaded into them.

Loading is idempotent: identity is the name, so re-seeding updates rather than
duplicating. That matters because a duplicated authority would mean the same
hotspot alerting two rows that represent one real body.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import SourceType
from app.core.exceptions import ValidationError
from app.core.geo import LonLat, validate_within_india
from app.core.logging import get_logger
from app.repositories import alert_repository, station_repository

logger = get_logger(__name__)

#: Where the checked-in registries live, relative to the repository root.
SEED_DIRECTORY = Path(__file__).resolve().parents[3] / "infra" / "seed"

SOURCES_FILE = SEED_DIRECTORY / "delhi_sources.json"
AUTHORITIES_FILE = SEED_DIRECTORY / "authorities.json"

#: Fewest vertices a jurisdiction ring needs to enclose any area at all.
_MIN_RING_VERTICES = 3


@dataclass(frozen=True, slots=True)
class SeedReport:
    """What one seed run loaded."""

    sources: int
    authorities: int


def _read(path: Path) -> dict[str, Any]:
    """Read a seed file, or fail with a message naming the missing path."""
    if not path.exists():
        raise ValidationError(
            f"Seed file {path.name} is missing.",
            details={"path": str(path)},
        )
    parsed: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return parsed


def _coordinates(raw: Any, *, context: str) -> LonLat:
    """Validate a ``[lon, lat]`` pair from a seed file.

    Seed files are hand-maintained, so a transposed pair is a live risk. India
    spans roughly 68-98E and 6-38N, which overlaps in neither direction, so a
    transposition lands outside the box and is caught here rather than becoming
    a station in the Indian Ocean.
    """
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValidationError(f"{context} needs a [longitude, latitude] pair.")
    lon, lat = float(raw[0]), float(raw[1])
    return validate_within_india((lon, lat))


def load_sources(session: Session, path: Path = SOURCES_FILE) -> int:
    """Load the pollution-source registry. Returns the number stored."""
    document = _read(path)
    loaded = 0

    for entry in document.get("sources", []):
        name = str(entry["name"])
        station_repository.upsert_pollution_source(
            session,
            name=name,
            source_type=SourceType(entry["source_type"]),
            coordinates=_coordinates(entry.get("coordinates"), context=f"Source {name!r}"),
            emission_prior=float(entry["emission_prior"]),
            extra={"note": entry.get("note")},
        )
        loaded += 1

    logger.info("seed.sources_loaded", count=loaded, path=str(path))
    return loaded


def load_authorities(session: Session, path: Path = AUTHORITIES_FILE) -> int:
    """Load the authority registry. Returns the number stored."""
    document = _read(path)
    loaded = 0
    names: list[str] = []

    for entry in document.get("authorities", []):
        name = str(entry["name"])
        ring_raw = entry.get("jurisdiction", [])
        if len(ring_raw) < _MIN_RING_VERTICES:
            raise ValidationError(
                f"Authority {name!r} needs at least {_MIN_RING_VERTICES} jurisdiction vertices.",
            )
        ring = [
            _coordinates(vertex, context=f"Authority {name!r} jurisdiction") for vertex in ring_raw
        ]

        alert_repository.upsert_authority(
            session,
            name=name,
            jurisdiction=ring,
            contact_email=entry.get("contact_email"),
            escalation_tier=int(entry.get("escalation_tier", 1)),
        )
        names.append(name)
        loaded += 1

    # Authorities no longer in the registry stop receiving alerts, but keep the
    # alerts they were already sent: that trail is the point of the system.
    retired = alert_repository.retire_authorities_except(session, names)
    logger.info("seed.authorities_loaded", count=loaded, retired=retired, path=str(path))
    return loaded


def load_all(session: Session) -> SeedReport:
    """Load both registries."""
    return SeedReport(
        sources=load_sources(session),
        authorities=load_authorities(session),
    )
