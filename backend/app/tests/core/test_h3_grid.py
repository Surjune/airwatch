"""Tests for H3 grid helpers, including the (lat, lng) to (lon, lat) boundary."""

from __future__ import annotations

import pytest

from app.core import h3_grid
from app.core.constants import H3_RESOLUTION, H3_RESOLUTION_OVERVIEW
from app.core.exceptions import InvalidGeometryError, InvalidH3IndexError
from app.core.geo import LonLat, haversine_distance_m

DELHI: LonLat = (77.2090, 28.6139)
COIMBATORE: LonLat = (76.9558, 11.0168)

#: Average edge length at resolution 8 is roughly 460 m, so a centroid can never
#: be further than about that from a point inside the same cell.
R8_MAX_CENTROID_OFFSET_M = 600.0


class TestPointToCell:
    def test_indexes_at_the_canonical_resolution(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        assert h3_grid.validate_cell(cell) == cell

    def test_distinct_cities_get_distinct_cells(self) -> None:
        assert h3_grid.point_to_cell(DELHI) != h3_grid.point_to_cell(COIMBATORE)

    def test_rejects_an_out_of_range_coordinate(self) -> None:
        with pytest.raises(InvalidGeometryError):
            h3_grid.point_to_cell((200.0, 28.6139))


class TestValidateCell:
    def test_rejects_a_malformed_index(self) -> None:
        with pytest.raises(InvalidH3IndexError, match="not a valid"):
            h3_grid.validate_cell("not-an-h3-index")

    def test_rejects_the_wrong_resolution(self) -> None:
        coarse = h3_grid.point_to_cell(DELHI, resolution=H3_RESOLUTION_OVERVIEW)
        with pytest.raises(InvalidH3IndexError, match="expected"):
            h3_grid.validate_cell(coarse, expected_resolution=H3_RESOLUTION)

    def test_accepts_any_resolution_when_unconstrained(self) -> None:
        coarse = h3_grid.point_to_cell(DELHI, resolution=H3_RESOLUTION_OVERVIEW)
        assert h3_grid.validate_cell(coarse, expected_resolution=None) == coarse


class TestCentroidAndBoundary:
    def test_centroid_is_near_the_indexed_point(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        centroid = h3_grid.cell_centroid(cell)
        assert haversine_distance_m(DELHI, centroid) < R8_MAX_CENTROID_OFFSET_M

    def test_centroid_preserves_lon_lat_order(self) -> None:
        # If the (lat, lng) flip were missed, longitude and latitude would swap
        # and Delhi's centroid would land in the Indian Ocean.
        lon, lat = h3_grid.cell_centroid(h3_grid.point_to_cell(DELHI))
        assert 76.0 < lon < 78.0
        assert 28.0 < lat < 29.0

    def test_boundary_is_a_hexagon(self) -> None:
        boundary = h3_grid.cell_boundary_lonlat(h3_grid.point_to_cell(DELHI))
        assert len(boundary) == 6

    def test_boundary_vertices_are_lon_lat(self) -> None:
        for lon, lat in h3_grid.cell_boundary_lonlat(h3_grid.point_to_cell(DELHI)):
            assert 76.0 < lon < 78.0
            assert 28.0 < lat < 29.0


class TestGeoJSON:
    def test_polygon_ring_is_closed(self) -> None:
        geometry = h3_grid.cell_to_geojson_polygon(h3_grid.point_to_cell(DELHI))
        assert geometry["type"] == "Polygon"
        coordinates = geometry["coordinates"]
        assert isinstance(coordinates, list)
        ring = coordinates[0]
        # GeoJSON requires the first and last positions to be identical.
        assert ring[0] == ring[-1]
        assert len(ring) == 7


class TestNeighbours:
    def test_k1_returns_the_cell_and_its_six_neighbours(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        assert len(h3_grid.neighbours(cell, k=1)) == 7

    def test_k0_returns_only_the_cell(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        assert h3_grid.neighbours(cell, k=0) == [cell]

    def test_ring_excludes_the_interior(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        ring = h3_grid.grid_ring(cell, k=1)
        assert len(ring) == 6
        assert cell not in ring

    def test_rejects_negative_k(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        with pytest.raises(ValueError, match="negative"):
            h3_grid.neighbours(cell, k=-1)


class TestCellsWithinRadius:
    def test_zero_radius_returns_only_the_containing_cell(self) -> None:
        assert h3_grid.cells_within_radius(DELHI, 0.0) == [h3_grid.point_to_cell(DELHI)]

    def test_always_includes_the_centre_cell(self) -> None:
        cells = h3_grid.cells_within_radius(DELHI, 2000.0)
        assert h3_grid.point_to_cell(DELHI) in cells

    def test_a_larger_radius_covers_more_cells(self) -> None:
        assert len(h3_grid.cells_within_radius(DELHI, 5000.0)) > len(
            h3_grid.cells_within_radius(DELHI, 1000.0)
        )

    def test_rejects_negative_radius(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            h3_grid.cells_within_radius(DELHI, -1.0)


class TestCoarsen:
    def test_returns_the_ancestor_at_the_overview_resolution(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        parent = h3_grid.coarsen(cell, H3_RESOLUTION_OVERVIEW)
        assert h3_grid.validate_cell(parent, expected_resolution=H3_RESOLUTION_OVERVIEW)

    def test_neighbouring_fine_cells_share_a_coarse_ancestor(self) -> None:
        cell = h3_grid.point_to_cell(DELHI)
        parents = {h3_grid.coarsen(c, H3_RESOLUTION_OVERVIEW) for c in h3_grid.neighbours(cell, 1)}
        # Seven adjacent r8 cells cannot span more than a couple of r6 parents.
        assert len(parents) <= 3

    def test_refuses_to_invent_detail(self) -> None:
        coarse = h3_grid.point_to_cell(DELHI, resolution=H3_RESOLUTION_OVERVIEW)
        with pytest.raises(InvalidH3IndexError, match="finer"):
            h3_grid.coarsen(coarse, H3_RESOLUTION)
