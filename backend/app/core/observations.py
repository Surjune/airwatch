"""The shape of a stored observation, shared across layers.

This type exists so that loading readings and analysing them do not have to
agree on a tuple layout. The repository produces it, the detector consumes it,
and neither imports the other -- which is what lets two different services run
detection without one importing the other or copying the loading loop.

It lives in ``core`` because ``core`` is the only layer everything may import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.geo import LonLat
from app.core.h3_grid import H3Cell


@dataclass(frozen=True, slots=True)
class ObservedReading:
    """One station's reading at one hour, with everything needed to place it."""

    station_id: int
    station_name: str
    coordinates: LonLat
    h3_cell: H3Cell
    observed_at: datetime
    value: float
