"""Persistence for daily Sentinel-5P cell means."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import SatelliteProduct
from app.repositories.models import SatelliteObservation


@dataclass(frozen=True, slots=True)
class SatelliteRow:
    """One cell's daily mean, ready to store."""

    h3_cell: str
    observed_on: date
    product: SatelliteProduct
    value: float
    unit: str
    pixel_count: int


@dataclass(frozen=True, slots=True)
class DailyMean:
    """A product's mean across a set of cells on one day."""

    observed_on: date
    value: float
    cells: int


def upsert_observations(session: Session, rows: Sequence[SatelliteRow]) -> int:
    """Store daily means, replacing a day already stored for the same cell and product.

    A re-run replaces rather than skips, because near-real-time products are
    occasionally reprocessed within days and the later value is the better one.
    """
    if not rows:
        return 0
    statement = insert(SatelliteObservation).values(
        [
            {
                "h3_cell": row.h3_cell,
                "observed_on": row.observed_on,
                "product": row.product,
                "value": row.value,
                "unit": row.unit,
                "pixel_count": row.pixel_count,
            }
            for row in rows
        ]
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_satellite_cell_day_product",
        set_={
            "value": statement.excluded.value,
            "unit": statement.excluded.unit,
            "pixel_count": statement.excluded.pixel_count,
        },
    )
    session.execute(statement)
    return len(rows)


def daily_means(
    session: Session, cells: Sequence[str], product: SatelliteProduct, since: date
) -> list[DailyMean]:
    """Each day's mean over the given cells, oldest first."""
    statement = (
        select(
            SatelliteObservation.observed_on,
            func.avg(SatelliteObservation.value),
            func.count(SatelliteObservation.id),
        )
        .where(
            SatelliteObservation.product == product,
            SatelliteObservation.h3_cell.in_(cells),
            SatelliteObservation.observed_on >= since,
        )
        .group_by(SatelliteObservation.observed_on)
        .order_by(SatelliteObservation.observed_on)
    )
    return [
        DailyMean(observed_on=day, value=float(value), cells=int(count))
        for day, value, count in session.execute(statement).all()
    ]


def latest_per_cell(
    session: Session, cells: Sequence[str], product: SatelliteProduct, since: date
) -> list[SatelliteObservation]:
    """Each cell's most recent observation since a day, for drawing the map layer."""
    statement = (
        select(SatelliteObservation)
        .where(
            SatelliteObservation.product == product,
            SatelliteObservation.h3_cell.in_(cells),
            SatelliteObservation.observed_on >= since,
        )
        .distinct(SatelliteObservation.h3_cell)
        .order_by(SatelliteObservation.h3_cell, SatelliteObservation.observed_on.desc())
    )
    return list(session.execute(statement).scalars())
