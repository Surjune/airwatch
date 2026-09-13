"""Sentinel-5P TROPOMI columns from Google Earth Engine.

TROPOMI measures what the whole atmospheric column holds -- NO2 from traffic and
combustion, SO2 from coal and smelting, CO from burning, and an absorbing
aerosol index that lights up smoke and dust. It sees every city every day at
roughly 5 km, which is exactly what the ground network lacks, and cannot say
what anyone breathed, which is exactly what the ground network provides.

Unlike the other clients this does not speak HTTP itself: Earth Engine's Python
library owns authentication and request batching. The client therefore wraps
that library at its two touch points -- counting a day's images and reducing an
image over cells -- and maps its exceptions to the typed upstream errors every
other client raises.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import ee

from app.core.config import Settings
from app.core.constants import S5P_PRODUCTS, S5P_SAMPLE_SCALE_M, SATELLITE_MIN_PIXELS
from app.core.enums import SatelliteProduct
from app.core.exceptions import (
    MissingCredentialError,
    UpstreamResponseError,
    UpstreamUnavailableError,
)
from app.core.geo import LonLat
from app.core.logging import get_logger

logger = get_logger(__name__)

PROVIDER = "Google Earth Engine"

#: Property names Earth Engine gives a combined mean+count reducer's outputs.
_MEAN_KEY = "mean"
_COUNT_KEY = "count"
_CELL_KEY = "cell"


@dataclass(frozen=True, slots=True)
class CellMean:
    """One product's mean over one cell on one day."""

    cell: str
    value: float
    pixel_count: int


class Sentinel5PClient:
    """Daily TROPOMI means over a set of cells."""

    def __init__(self, settings: Settings) -> None:
        """Authenticate with the configured service account.

        Raises:
            MissingCredentialError: Any of the three Earth Engine settings is empty.
            UpstreamUnavailableError: Earth Engine refused the credentials or the
                project -- most often a missing IAM role or an unregistered project.
        """
        for attribute, env_var in (
            ("gee_service_account_email", "GEE_SERVICE_ACCOUNT_EMAIL"),
            ("gee_private_key_path", "GEE_PRIVATE_KEY_PATH"),
            ("gee_project_id", "GEE_PROJECT_ID"),
        ):
            if not settings.has(attribute):
                raise MissingCredentialError(PROVIDER, env_var)

        try:
            credentials = ee.ServiceAccountCredentials(
                settings.gee_service_account_email, settings.gee_private_key_path
            )
            ee.Initialize(credentials, project=settings.gee_project_id)
        except (ee.EEException, OSError, ValueError) as error:
            # The message names the missing role or unregistered project, which is
            # what an operator needs; it never contains the key itself.
            raise UpstreamUnavailableError(
                PROVIDER, f"Earth Engine refused to initialise: {error}"
            ) from error

    def daily_cell_means(
        self,
        product: SatelliteProduct,
        cells: Mapping[str, Sequence[LonLat]],
        day: date,
    ) -> list[CellMean]:
        """Mean of one product over each cell for one UTC day.

        Args:
            product: The TROPOMI product.
            cells: Cell id to its boundary ring, as ``(lon, lat)`` vertices.
            day: The UTC day.

        Returns:
            One entry per cell with at least :data:`SATELLITE_MIN_PIXELS` valid
            pixels. A day with no overpass or full cloud cover returns nothing,
            which is an absence of observation rather than a zero.

        Raises:
            UpstreamUnavailableError: Earth Engine failed the request.
            UpstreamResponseError: The response was not in the expected shape.
        """
        collection_id, band = S5P_PRODUCTS[product.value]
        start = datetime.combine(day, time.min, tzinfo=UTC)
        end = start + timedelta(days=1)

        try:
            images = self._images(collection_id, band, start, end)
            if self._count(images) == 0:
                return []
            features = self._reduce(images.mean(), cells)
        except ee.EEException as error:
            raise UpstreamUnavailableError(
                PROVIDER, f"Earth Engine request failed for {product.value} on {day}: {error}"
            ) from error

        return self._parse(features, product, day)

    def _images(self, collection_id: str, band: str, start: datetime, end: datetime) -> Any:
        """One product's images for a time window. Isolated so tests can stub it."""
        return (
            ee.ImageCollection(collection_id)
            .filterDate(start.isoformat(), end.isoformat())
            .select(band)
        )

    def _count(self, images: Any) -> int:
        """How many images a filtered collection holds. Isolated so tests can stub it."""
        return int(images.size().getInfo())

    def _reduce(self, image: Any, cells: Mapping[str, Sequence[LonLat]]) -> list[Any]:
        """Reduce an image over each cell. Isolated so tests can stub it."""
        regions = ee.FeatureCollection(
            [
                ee.Feature(
                    ee.Geometry.Polygon([[list(vertex) for vertex in ring]]), {_CELL_KEY: cell}
                )
                for cell, ring in cells.items()
            ]
        )
        reducer = ee.Reducer.mean().combine(ee.Reducer.count(), sharedInputs=True)
        result = image.reduceRegions(collection=regions, reducer=reducer, scale=S5P_SAMPLE_SCALE_M)
        info = result.getInfo()
        if not isinstance(info, dict) or not isinstance(info.get("features"), list):
            raise UpstreamResponseError(PROVIDER, "reduceRegions returned no feature list.")
        return list(info["features"])

    @staticmethod
    def _parse(features: list[Any], product: SatelliteProduct, day: date) -> list[CellMean]:
        """Turn reduced features into cell means, dropping thinly observed cells."""
        means: list[CellMean] = []
        for feature in features:
            properties = feature.get("properties") if isinstance(feature, dict) else None
            if not isinstance(properties, dict):
                raise UpstreamResponseError(PROVIDER, "A reduced feature had no properties.")
            cell = properties.get(_CELL_KEY)
            value = properties.get(_MEAN_KEY)
            count = properties.get(_COUNT_KEY)
            if not isinstance(cell, str):
                raise UpstreamResponseError(PROVIDER, "A reduced feature had no cell id.")
            # A cell every pixel of which was masked comes back with a null mean:
            # nothing was observed there, which is not a measurement of zero.
            if not isinstance(value, int | float) or not isinstance(count, int | float):
                continue
            if count < SATELLITE_MIN_PIXELS:
                continue
            means.append(CellMean(cell=cell, value=float(value), pixel_count=int(count)))

        logger.info(
            "s5p.day_reduced",
            product=product.value,
            day=day.isoformat(),
            cells_requested=len(features),
            cells_observed=len(means),
        )
        return means
