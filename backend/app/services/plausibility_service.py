"""Re-applying the plausibility bounds to readings already stored.

Ingestion flags readings as they arrive. This exists for everything that arrived
before a bound was defined or changed -- notably the CO readings stored in ppm
units mislabelled as ppb, all of which were published before the guard existed.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.core.logging import get_logger
from app.core.plausibility import plausible_range
from app.repositories import observation_repository

logger = get_logger(__name__)


def reassess(session: Session) -> dict[Pollutant, int]:
    """Re-flag every stored reading against the current bounds.

    Returns:
        How many readings of each pollutant are flagged afterwards.
    """
    flagged: dict[Pollutant, int] = {}
    for pollutant in Pollutant:
        low, high = plausible_range(pollutant)
        flagged[pollutant] = observation_repository.reflag_measurements(
            session, pollutant, low, high
        )
    logger.info(
        "plausibility.reassessed",
        flagged={pollutant.value: count for pollutant, count in flagged.items()},
    )
    return flagged
