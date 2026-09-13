"""What one city node trains on, built from that city's own observations.

Shared by the validation script and the Flower client so the experiment that
produced the published transfer results and the transport that runs it across
processes cannot quietly train on different data.

In this deployment every node reads the same database and filters to its own
city. That is a convenience of running the pilot on one machine, not part of the
design: nothing here needs another city's rows, so pointing a node at its own
database changes nothing below.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from sqlalchemy import select

from app.core.constants import (
    FL_HORIZON_HOURS,
    FL_ISSUE_STRIDE,
    FL_MIN_NODE_ROWS,
    FL_NODE_RADIUS_M,
    FL_TARGET_MATCH_SECONDS,
    FORECAST_TEST_FRACTION,
    PILOT_CITY_CENTRES,
)
from app.core.enums import Pollutant, StationTier
from app.core.geo import haversine_distance_m
from app.ml.forecast_features import (
    FEDERATED_EXCLUDED_PREFIXES,
    ForecastInputs,
    build_climatology,
    build_features,
)
from app.repositories.models import Measurement, Station
from app.repositories.session import session_scope

#: Per-station hourly series: station id -> observation time -> value.
type StationSeries = dict[int, dict[datetime, float]]


@dataclass(slots=True)
class NodeData:
    """One city's training and test matrices."""

    name: str
    x_train: np.ndarray
    y_train: np.ndarray
    x_test: np.ndarray
    y_test: np.ndarray
    stations: int


def federated_columns(columns: tuple[str, ...]) -> tuple[str, ...]:
    """Restrict the feature set to what every node can compute.

    The exclusion list is defined alongside the model in
    ``app.ml.forecast_features`` so the schema nodes train on and the schema a
    node publishes in its model card cannot drift apart.
    """
    return tuple(name for name in columns if not name.startswith(FEDERATED_EXCLUDED_PREFIXES))


def assign_city(position: tuple[float, float]) -> str | None:
    """Assign a ``(lon, lat)`` station position to the nearest pilot city in range."""
    best: tuple[str, float] | None = None
    for city, centre in PILOT_CITY_CENTRES.items():
        distance = haversine_distance_m(position, centre)
        if distance <= FL_NODE_RADIUS_M and (best is None or distance < best[1]):
            best = (city, distance)
    return best[0] if best else None


def load_city_series(
    pollutant: Pollutant,
    *,
    until: datetime | None = None,
    only: str | None = None,
) -> tuple[dict[str, StationSeries], dict[str, int]]:
    """Load per-station hourly series, grouped by city.

    Args:
        pollutant: The pollutant to load.
        until: Exclude observations at or after this instant. Validation pins it
            so a re-run cannot drift as ingestion adds data.
        only: Keep a single city. A node passes its own name and never holds
            another city's observations in memory.

    Returns:
        Series by city, and the number of stations contributing to each.
    """
    by_city: dict[str, StationSeries] = defaultdict(lambda: defaultdict(dict))

    with session_scope() as session:
        positions = {
            station_id: (float(lon), float(lat))
            for station_id, lon, lat in session.execute(
                select(Station.id, Station.geom.ST_X(), Station.geom.ST_Y())
            ).all()
        }
        query = (
            select(Measurement.station_id, Measurement.observed_at, Measurement.value_raw)
            .join(Station, Station.id == Measurement.station_id)
            .where(Station.tier == StationTier.REFERENCE)
        ).where(
            Measurement.pollutant == pollutant,
            Measurement.is_plausible.is_(True),
        )
        if until is not None:
            query = query.where(Measurement.observed_at < until)
        rows = session.execute(query).all()

    for station_id, observed_at, value in rows:
        position = positions.get(station_id)
        if position is None:
            continue
        city = assign_city(position)
        if city is None or (only is not None and city != only):
            continue
        by_city[city][station_id][observed_at] = float(value)

    station_counts = {city: len(series) for city, series in by_city.items()}
    return by_city, station_counts


def build_node(
    name: str,
    series: StationSeries,
    columns: tuple[str, ...],
    stations: int,
) -> NodeData | None:
    """Build one city's forecast matrices, split temporally.

    Returns:
        The node's data, or None when there are too few usable rows for a
        holdout that could report anything.
    """
    rows: list[tuple[datetime, list[float], float]] = []

    for history in series.values():
        if len(history) < 2:
            continue
        ordered = sorted(history)

        for index in range(0, len(ordered), FL_ISSUE_STRIDE):
            issued_at = ordered[index]
            known = {when: value for when, value in history.items() if when <= issued_at}
            if not known:
                continue

            target = actual_near(history, issued_at, FL_HORIZON_HOURS)
            if target is None:
                continue

            inputs = ForecastInputs(
                history=known,
                climatology=build_climatology(known),
                issue_weather=None,
                target_weather=None,
            )
            features = build_features(inputs, issued_at, FL_HORIZON_HOURS)
            if features is None:
                continue

            vector = [features[column] for column in columns]
            if any(np.isnan(vector)):
                # A node cannot train on rows with missing lags, and imputing
                # them would put invented history into a federated model that
                # other cities then inherit.
                continue
            rows.append((issued_at, vector, target))

    if len(rows) < FL_MIN_NODE_ROWS:
        return None

    rows.sort(key=lambda row: row[0])
    issue_times = sorted({row[0] for row in rows})
    cutoff = issue_times[int(len(issue_times) * (1 - FORECAST_TEST_FRACTION))]

    train = [row for row in rows if row[0] < cutoff]
    test = [row for row in rows if row[0] >= cutoff]
    if not train or not test:
        return None

    return NodeData(
        name=name,
        x_train=np.array([row[1] for row in train]),
        y_train=np.array([row[2] for row in train]),
        x_test=np.array([row[1] for row in test]),
        y_test=np.array([row[2] for row in test]),
        stations=stations,
    )


def actual_near(
    history: dict[datetime, float], issued_at: datetime, horizon_hours: int
) -> float | None:
    """The observation nearest the target hour, within the match tolerance."""
    target_time = issued_at + timedelta(hours=horizon_hours)
    exact = history.get(target_time)
    if exact is not None:
        return exact
    for observed_at, value in history.items():
        if abs((observed_at - target_time).total_seconds()) <= FL_TARGET_MATCH_SECONDS:
            return value
    return None
