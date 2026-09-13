"""Sentinel-5P ingestion and the regional picture it gives each city.

The satellite tier answers a question the monitors cannot: what is happening in
the air *between and beyond* them. A city with one working monitor, like
Coimbatore, still gets a daily NO2 and aerosol picture over its whole area.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.constants import (
    CITY_VIEW_RADIUS_M,
    PILOT_CITY_CENTRES,
    S5P_PRODUCT_UNITS,
    SATELLITE_H3_RESOLUTION,
    SATELLITE_LOOKBACK_DAYS,
)
from app.core.enums import PilotCity, SatelliteProduct
from app.core.geo import LonLat, haversine_distance_m
from app.core.h3_grid import cell_boundary_lonlat, cell_centroid, cells_within_radius
from app.core.logging import get_logger
from app.external.s5p_client import CellMean, Sentinel5PClient
from app.repositories import satellite_repository
from app.repositories.satellite_repository import DailyMean, SatelliteRow

logger = get_logger(__name__)


#: What the service needs from a client, so tests can supply one without Earth Engine.
type MeansFetcher = Callable[[SatelliteProduct, dict[str, list[LonLat]], date], list[CellMean]]


@dataclass(frozen=True, slots=True)
class IngestSummary:
    """What one ingestion run stored."""

    city: PilotCity
    days: int
    stored: int
    days_observed: dict[SatelliteProduct, int]


@dataclass(frozen=True, slots=True)
class CellValue:
    """A cell's latest value, with its outline for drawing."""

    h3_cell: str
    boundary: list[LonLat]
    observed_on: date
    value: float
    pixel_count: int


@dataclass(frozen=True, slots=True)
class CityPicture:
    """A product's recent series and latest map over one city."""

    city: PilotCity
    product: SatelliteProduct
    unit: str
    series: list[DailyMean]
    cells: list[CellValue]


def city_cells(city: PilotCity) -> dict[str, list[LonLat]]:
    """The coarse satellite cells whose centres fall in a city's view, with their outlines.

    The ring search over-covers the disc, so cells are filtered by centroid:
    otherwise each Earth Engine request would average cells well outside the
    city it is meant to describe.
    """
    centre = PILOT_CITY_CENTRES[city.value]
    cells = cells_within_radius(centre, CITY_VIEW_RADIUS_M, resolution=SATELLITE_H3_RESOLUTION)
    return {
        cell: cell_boundary_lonlat(cell)
        for cell in sorted(cells)
        if haversine_distance_m(cell_centroid(cell), centre) <= CITY_VIEW_RADIUS_M
    }


def ingest_city(
    session: Session,
    city: PilotCity,
    fetch: MeansFetcher,
    *,
    days: int = SATELLITE_LOOKBACK_DAYS,
    today: date | None = None,
    products: tuple[SatelliteProduct, ...] = tuple(SatelliteProduct),
) -> IngestSummary:
    """Fetch and store each product's daily cell means for the last ``days`` days.

    Today is excluded: its overpass may not have been processed yet, and a
    partial day stored now would sit beside complete days as if comparable.
    """
    reference = today or datetime.now(UTC).date()
    cells = city_cells(city)
    stored = 0
    observed: dict[SatelliteProduct, int] = {}

    for product in products:
        observed[product] = 0
        for offset in range(days, 0, -1):
            day = reference - timedelta(days=offset)
            means = fetch(product, cells, day)
            if means:
                observed[product] += 1
            stored += satellite_repository.upsert_observations(
                session,
                [
                    SatelliteRow(
                        h3_cell=mean.cell,
                        observed_on=day,
                        product=product,
                        value=mean.value,
                        unit=S5P_PRODUCT_UNITS[product.value],
                        pixel_count=mean.pixel_count,
                    )
                    for mean in means
                ],
            )

    logger.info(
        "satellite.city_ingested",
        city=city.value,
        stored=stored,
        days_observed={product.value: count for product, count in observed.items()},
    )
    return IngestSummary(city=city, days=days, stored=stored, days_observed=observed)


def ingest_with_earth_engine(
    settings: Settings, session: Session, city: PilotCity
) -> IngestSummary:
    """Ingest a city using the configured Earth Engine account.

    Raises:
        MissingCredentialError: Earth Engine is not configured.
        UpstreamUnavailableError: Earth Engine refused or failed.
    """
    client = Sentinel5PClient(settings)
    return ingest_city(session, city, client.daily_cell_means)


def city_picture(
    session: Session,
    city: PilotCity,
    product: SatelliteProduct,
    *,
    days: int,
    today: date | None = None,
) -> CityPicture:
    """A product's daily series over a city, and each cell's latest value."""
    reference = today or datetime.now(UTC).date()
    since = reference - timedelta(days=days)
    cells = city_cells(city)
    ids = list(cells)

    latest = satellite_repository.latest_per_cell(session, ids, product, since)
    return CityPicture(
        city=city,
        product=product,
        unit=S5P_PRODUCT_UNITS[product.value],
        series=satellite_repository.daily_means(session, ids, product, since),
        cells=[
            CellValue(
                h3_cell=row.h3_cell,
                boundary=cells[row.h3_cell],
                observed_on=row.observed_on,
                value=row.value,
                pixel_count=row.pixel_count,
            )
            for row in latest
        ],
    )
