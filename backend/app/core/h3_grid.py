"""H3 hexagonal grid helpers — the single source of truth for cell indexing.

Every layer of AirWatch is keyed on the same grid: fused concentrations, hotspot
anomalies, forecasts, federated feature vectors and the interoperability envelope.
Cross-city model sharing is only coherent because a feature vector for a cell in
Coimbatore describes the same size and shape of ground as one in Delhi.

**Coordinate order.** The ``h3`` library takes and returns ``(lat, lng)``. AirWatch
uses ``(lon, lat)`` everywhere else. This module is the only place that flip is
allowed to happen, and every conversion below is explicit about which order it is
handing to the library.
"""

from __future__ import annotations

import math

import h3

from app.core.constants import H3_RESOLUTION, SRID_WGS84
from app.core.exceptions import InvalidH3IndexError
from app.core.geo import LonLat, validate_lon_lat

#: An H3 cell index in its canonical string form.
H3Cell = str

__all__ = [
    "SRID_WGS84",
    "H3Cell",
    "cell_boundary_lonlat",
    "cell_centroid",
    "cell_to_geojson_polygon",
    "cells_within_radius",
    "coarsen",
    "grid_ring",
    "neighbours",
    "point_to_cell",
    "validate_cell",
]


def point_to_cell(point: LonLat, resolution: int = H3_RESOLUTION) -> H3Cell:
    """Index a point to its containing H3 cell.

    Args:
        point: ``(lon, lat)`` in WGS84.
        resolution: H3 resolution, defaulting to the canonical analysis grid.

    Returns:
        The H3 cell index.
    """
    lon, lat = validate_lon_lat(*point)
    # h3 takes (lat, lng); AirWatch carries (lon, lat). Flip here, explicitly.
    cell: H3Cell = h3.latlng_to_cell(lat, lon, resolution)
    return cell


def validate_cell(cell: H3Cell, *, expected_resolution: int | None = H3_RESOLUTION) -> H3Cell:
    """Validate an H3 index arriving from an untrusted source.

    Args:
        cell: The index to check.
        expected_resolution: Resolution the cell must be at, or ``None`` to accept
            any resolution.

    Returns:
        The validated cell index.

    Raises:
        InvalidH3IndexError: The index is malformed or at the wrong resolution.
    """
    if not isinstance(cell, str) or not h3.is_valid_cell(cell):
        raise InvalidH3IndexError(f"{cell!r} is not a valid H3 cell index.")

    if expected_resolution is not None:
        actual = int(h3.get_resolution(cell))
        if actual != expected_resolution:
            raise InvalidH3IndexError(
                f"H3 cell {cell} is resolution {actual}, expected {expected_resolution}.",
            )
    return cell


def cell_centroid(cell: H3Cell) -> LonLat:
    """Return the centroid of a cell as ``(lon, lat)``.

    Args:
        cell: A valid H3 cell index.

    Raises:
        InvalidH3IndexError: The index is malformed.
    """
    validate_cell(cell, expected_resolution=None)
    # h3 returns (lat, lng); flip to AirWatch's (lon, lat).
    lat, lon = h3.cell_to_latlng(cell)
    return lon, lat


def cell_boundary_lonlat(cell: H3Cell) -> list[LonLat]:
    """Return the cell's vertices as ``(lon, lat)`` pairs.

    Args:
        cell: A valid H3 cell index.

    Returns:
        The boundary vertices in order, without repeating the first point.

    Raises:
        InvalidH3IndexError: The index is malformed.
    """
    validate_cell(cell, expected_resolution=None)
    # h3 returns a sequence of (lat, lng); flip each to (lon, lat).
    return [(lon, lat) for lat, lon in h3.cell_to_boundary(cell)]


def cell_to_geojson_polygon(cell: H3Cell) -> dict[str, object]:
    """Render a cell as a GeoJSON Polygon geometry.

    GeoJSON requires ``(lon, lat)`` order and a closed ring, so the first vertex
    is repeated at the end.

    Args:
        cell: A valid H3 cell index.

    Returns:
        A GeoJSON geometry dict ready to embed in a Feature.
    """
    ring = cell_boundary_lonlat(cell)
    closed_ring = [*ring, ring[0]]
    return {"type": "Polygon", "coordinates": [closed_ring]}


def neighbours(cell: H3Cell, k: int = 1) -> list[H3Cell]:
    """Return the cell and every cell within ``k`` steps of it.

    Used for the contiguity test in hotspot detection and for neighbourhood
    features in fusion.

    Args:
        cell: A valid H3 cell index.
        k: Ring distance. ``k=1`` yields the cell plus its six neighbours.

    Raises:
        InvalidH3IndexError: The index is malformed.
        ValueError: ``k`` is negative.
    """
    validate_cell(cell, expected_resolution=None)
    if k < 0:
        raise ValueError(f"Ring distance must not be negative ({k}).")
    return list(h3.grid_disk(cell, k))


def grid_ring(cell: H3Cell, k: int) -> list[H3Cell]:
    """Return only the cells exactly ``k`` steps away, excluding the interior.

    Args:
        cell: A valid H3 cell index.
        k: Ring distance.

    Raises:
        InvalidH3IndexError: The index is malformed.
        ValueError: ``k`` is negative.
    """
    validate_cell(cell, expected_resolution=None)
    if k < 0:
        raise ValueError(f"Ring distance must not be negative ({k}).")
    return list(h3.grid_ring(cell, k))


def cells_within_radius(
    centre: LonLat,
    radius_m: float,
    resolution: int = H3_RESOLUTION,
) -> list[H3Cell]:
    """Return every cell whose centroid lies within a radius of a point.

    Args:
        centre: ``(lon, lat)`` of the circle centre.
        radius_m: Radius in metres.
        resolution: H3 resolution to index at.

    Returns:
        Cell indices covering the disc, including the centre cell.

    Raises:
        ValueError: The radius is negative.
    """
    if radius_m < 0:
        raise ValueError(f"Radius must not be negative ({radius_m}).")

    centre_cell = point_to_cell(centre, resolution)
    if radius_m == 0:
        return [centre_cell]

    # Convert a metric radius into a ring count via the resolution's average edge
    # length, then round up so the disc is fully covered rather than clipped.
    edge_length_m = float(h3.average_hexagon_edge_length(resolution, unit="m"))
    rings = max(1, math.ceil(radius_m / edge_length_m))
    return list(h3.grid_disk(centre_cell, rings))


def coarsen(cell: H3Cell, resolution: int) -> H3Cell:
    """Return the ancestor of a cell at a coarser resolution.

    Used to aggregate the analysis grid for zoomed-out map rendering.

    Args:
        cell: A valid H3 cell index.
        resolution: Target resolution, which must be coarser than the cell's own.

    Raises:
        InvalidH3IndexError: The index is malformed, or the target resolution is
            finer than the cell's, which would require inventing detail.
    """
    validate_cell(cell, expected_resolution=None)
    current = int(h3.get_resolution(cell))
    if resolution > current:
        raise InvalidH3IndexError(
            f"Cannot coarsen resolution {current} cell to finer resolution {resolution}.",
        )
    parent: H3Cell = h3.cell_to_parent(cell, resolution)
    return parent
