"""Hidden hotspot detection.

A hotspot here is **not** a place where the air is bad. It is a place where the
air is worse than the surrounding network predicts it should be. Those are
different claims, and only the second one locates a source.

The distinction matters because a threshold on concentration finds whatever the
whole city is already experiencing. On a bad Delhi day every station breaches
200 ug/m3 and a threshold detector flags all sixty of them, which tells an
official nothing they did not already know and points at nothing they can act
on. Meanwhile a settlement burning waste beside a landfill in an otherwise clean
southern city never breaches anything, and is never seen at all.

The signal used instead is the residual against neighbours: observed minus what
inverse-distance weighting predicts from every *other* station. That quantity is
exactly what leave-one-station-out validation measured, so its typical size is
known rather than assumed, and the uncertainty model fitted there becomes the
denominator of a z-score. A citywide episode moves observation and prediction
together and produces no residual; a local source moves only the observation.

Two filters then separate a source from a sensor fault:

* **Persistence.** A real source burns, idles or emits for hours. A single
  anomalous reading is far more likely to be a glitch.
* **Contiguity.** A plume covers more than one 0.46 km hexagon. A lone flagged
  cell surrounded by unremarkable ones is more likely a miscalibrated monitor,
  which is a finding about the monitor rather than about the air.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.constants import (
    HOTSPOT_MIN_CONTIGUOUS_CELLS,
    HOTSPOT_MIN_PERSISTENCE_INTERVALS,
    HOTSPOT_ZSCORE_THRESHOLD,
)
from app.core.geo import LonLat
from app.core.h3_grid import H3Cell
from app.core.h3_grid import neighbours as h3_neighbours
from app.core.logging import get_logger
from app.core.observations import ObservedReading
from app.ml.fusion_features import StationReading, estimate_cell

logger = get_logger(__name__)

#: Longest gap, in hours, that two flagged readings can straddle and still count
#: as the same continuing episode. Station reporting is irregular enough that
#: requiring strictly consecutive hours would split one event into several.
_MAX_EPISODE_GAP_HOURS = 3


@dataclass(frozen=True, slots=True)
class CellAnomaly:
    """One location-hour scored against what its neighbourhood predicted."""

    station_id: int
    h3_cell: H3Cell
    coordinates: LonLat
    observed_at: datetime
    observed: float
    expected: float
    uncertainty: float

    @property
    def residual(self) -> float:
        """How much dirtier than predicted. Negative means cleaner."""
        return self.observed - self.expected

    @property
    def z_score(self) -> float:
        """Residual in units of the expected error at this location.

        Dividing by the fitted uncertainty rather than a fixed number is what
        keeps the threshold fair. A cell whose neighbours disagree wildly has a
        genuinely uncertain prediction, and should need a larger excess before
        anyone is sent to investigate.
        """
        if self.uncertainty <= 0:  # pragma: no cover - uncertainty has a floor.
            return 0.0
        return self.residual / self.uncertainty


@dataclass(frozen=True, slots=True)
class Hotspot:
    """A location that stayed dirtier than its neighbourhood for several hours."""

    station_id: int
    h3_cell: H3Cell
    coordinates: LonLat
    first_seen_at: datetime
    last_seen_at: datetime
    intervals: int
    peak_z: float
    peak_residual: float
    mean_residual: float
    peak_observed: float

    @property
    def duration_hours(self) -> float:
        return (self.last_seen_at - self.first_seen_at).total_seconds() / 3600.0


def score_hour(
    readings: Sequence[StationReading],
    cells: dict[int, H3Cell],
    observed_at: datetime,
) -> list[CellAnomaly]:
    """Score every station for one hour against the rest of the network.

    Args:
        readings: Every station's reading for this hour.
        cells: Station id to H3 cell, so an anomaly knows where it sits on the
            analysis grid.
        observed_at: The hour, in UTC.

    Returns:
        One anomaly per station that had enough neighbours to be predicted.
        Stations the network cannot predict are omitted rather than assumed
        normal: an unsupported location is unknown, not clean.
    """
    anomalies: list[CellAnomaly] = []

    for target in readings:
        # The station being scored is excluded from its own prediction. Leaving
        # it in would make every location predict itself perfectly and no
        # hotspot would ever be found.
        others = [r for r in readings if r.station_id != target.station_id]
        estimate = estimate_cell(target.coordinates, others)
        if estimate is None:
            continue

        cell = cells.get(target.station_id)
        if cell is None:
            continue

        anomalies.append(
            CellAnomaly(
                station_id=target.station_id,
                h3_cell=cell,
                coordinates=target.coordinates,
                observed_at=observed_at,
                observed=target.value,
                expected=estimate.value,
                uncertainty=estimate.uncertainty,
            )
        )

    return anomalies


def detect_hotspots(
    anomalies: Iterable[CellAnomaly],
    *,
    z_threshold: float = HOTSPOT_ZSCORE_THRESHOLD,
    min_intervals: int = HOTSPOT_MIN_PERSISTENCE_INTERVALS,
) -> list[Hotspot]:
    """Group flagged hours into persistent episodes per location.

    Args:
        anomalies: Scored location-hours, in any order.
        z_threshold: Standardised excess above which an hour is flagged.
        min_intervals: Flagged hours an episode needs before it is reported.

    Returns:
        Confirmed hotspots, worst first by peak z-score.
    """
    by_station: dict[int, list[CellAnomaly]] = defaultdict(list)
    for anomaly in anomalies:
        if anomaly.z_score >= z_threshold:
            by_station[anomaly.station_id].append(anomaly)

    hotspots: list[Hotspot] = []
    for flagged in by_station.values():
        flagged.sort(key=lambda item: item.observed_at)
        for episode in _split_into_episodes(flagged):
            if len(episode) < min_intervals:
                # One flagged hour is far more likely to be a glitch than a
                # source, and dispatching an inspector on it wastes the trust
                # the whole alerting chain depends on.
                continue
            hotspots.append(_summarise(episode))

    hotspots.sort(key=lambda hotspot: hotspot.peak_z, reverse=True)
    return hotspots


def detect_over_window(
    readings: Iterable[ObservedReading],
    *,
    z_threshold: float = HOTSPOT_ZSCORE_THRESHOLD,
    min_intervals: int = HOTSPOT_MIN_PERSISTENCE_INTERVALS,
) -> list[Hotspot]:
    """Score a whole window of readings and return the episodes it contains.

    Scoring is per hour, because a station is only comparable with the
    neighbours that reported at the same time. Grouping first and scoring
    within each group is what keeps a reading from being compared against a
    neighbour's value from six hours earlier.

    Args:
        readings: Every stored reading in the window, in any order.
        z_threshold: Standardised excess above which an hour is flagged.
        min_intervals: Flagged hours an episode needs before it is reported.

    Returns:
        Confirmed hotspots, worst first.
    """
    by_hour: dict[datetime, list[StationReading]] = defaultdict(list)
    cells: dict[int, H3Cell] = {}

    for reading in readings:
        cells[reading.station_id] = reading.h3_cell
        by_hour[reading.observed_at].append(
            StationReading(
                station_id=reading.station_id,
                coordinates=reading.coordinates,
                value=reading.value,
            )
        )

    anomalies: list[CellAnomaly] = []
    for observed_at, hour_readings in by_hour.items():
        anomalies.extend(score_hour(hour_readings, cells, observed_at))

    return detect_hotspots(anomalies, z_threshold=z_threshold, min_intervals=min_intervals)


def _split_into_episodes(flagged: list[CellAnomaly]) -> list[list[CellAnomaly]]:
    """Split one station's flagged hours into separate continuing episodes."""
    episodes: list[list[CellAnomaly]] = []
    current: list[CellAnomaly] = []

    for anomaly in flagged:
        if current:
            gap = anomaly.observed_at - current[-1].observed_at
            if gap > timedelta(hours=_MAX_EPISODE_GAP_HOURS):
                episodes.append(current)
                current = []
        current.append(anomaly)

    if current:
        episodes.append(current)
    return episodes


def _summarise(episode: list[CellAnomaly]) -> Hotspot:
    """Reduce a run of flagged hours to a single hotspot record."""
    peak = max(episode, key=lambda item: item.z_score)
    return Hotspot(
        station_id=peak.station_id,
        h3_cell=peak.h3_cell,
        coordinates=peak.coordinates,
        first_seen_at=episode[0].observed_at,
        last_seen_at=episode[-1].observed_at,
        intervals=len(episode),
        peak_z=peak.z_score,
        peak_residual=peak.residual,
        mean_residual=sum(item.residual for item in episode) / len(episode),
        peak_observed=peak.observed,
    )


def filter_by_contiguity(
    flagged_cells: Sequence[H3Cell],
    *,
    min_contiguous: int = HOTSPOT_MIN_CONTIGUOUS_CELLS,
) -> set[H3Cell]:
    """Keep only flagged cells that touch at least one other flagged cell.

    A plume covers more than one 0.46 km hexagon, so an isolated flagged cell is
    more likely a faulty monitor than a source.

    This applies to the fused grid, where every cell is estimated and neighbours
    exist. It is deliberately *not* applied to station-level detection: reference
    stations sit kilometres apart and almost never occupy adjacent resolution-8
    cells, so requiring contiguity there would reject every genuine hotspot for
    a reason that has nothing to do with the air.

    Args:
        flagged_cells: Cells flagged this interval.
        min_contiguous: Size a connected group must reach to be kept.

    Returns:
        The subset belonging to a group of at least ``min_contiguous`` cells.
    """
    flagged = set(flagged_cells)
    if min_contiguous <= 1:
        return flagged

    kept: set[H3Cell] = set()
    for cell in flagged:
        touching = {c for c in h3_neighbours(cell, k=1) if c in flagged}
        # grid_disk includes the cell itself, so a group of the required size
        # means that many flagged cells counting this one.
        if len(touching) >= min_contiguous:
            kept.add(cell)
    return kept
