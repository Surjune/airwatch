"""Persistence for the CAMS regional model's hourly concentrations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.enums import Pollutant
from app.core.geo import LonLat
from app.repositories.models import ModelConcentration


@dataclass(frozen=True, slots=True)
class ModelRow:
    """One modelled hour, ready to store or as read back."""

    city: str
    pollutant: Pollutant
    observed_at: datetime
    value: float
    is_forecast: bool
    grid_point: LonLat


def upsert_hours(session: Session, rows: Sequence[ModelRow]) -> int:
    """Store model hours, replacing an hour already held.

    Replaced rather than skipped: each run of the model revises its recent past
    and its forecast, and the latest run is the better estimate of both.
    """
    if not rows:
        return 0
    statement = insert(ModelConcentration).values(
        [
            {
                "city": row.city,
                "pollutant": row.pollutant,
                "observed_at": row.observed_at,
                "value": row.value,
                "is_forecast": row.is_forecast,
                "grid_longitude": row.grid_point[0],
                "grid_latitude": row.grid_point[1],
            }
            for row in rows
        ]
    )
    statement = statement.on_conflict_do_update(
        constraint="uq_model_city_pollutant_hour",
        set_={
            "value": statement.excluded.value,
            "is_forecast": statement.excluded.is_forecast,
            "grid_longitude": statement.excluded.grid_longitude,
            "grid_latitude": statement.excluded.grid_latitude,
            "fetched_at": statement.excluded.fetched_at,
        },
    )
    session.execute(statement)
    return len(rows)


def hours_between(
    session: Session, city: str, pollutant: Pollutant, since: datetime, until: datetime
) -> list[ModelRow]:
    """A city's model hours for a pollutant in a window, oldest first."""
    statement = (
        select(ModelConcentration)
        .where(
            ModelConcentration.city == city,
            ModelConcentration.pollutant == pollutant,
            ModelConcentration.observed_at >= since,
            ModelConcentration.observed_at <= until,
        )
        .order_by(ModelConcentration.observed_at)
    )
    return [
        ModelRow(
            city=row.city,
            pollutant=row.pollutant,
            observed_at=row.observed_at,
            value=row.value,
            is_forecast=row.is_forecast,
            grid_point=(row.grid_longitude, row.grid_latitude),
        )
        for row in session.execute(statement).scalars()
    ]
