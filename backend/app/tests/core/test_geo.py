"""Tests for geodesic and wind-vector helpers.

The wind convention tests are the important ones: a sign error here would invert
every back-trajectory and attribute every plume to a source on the wrong side of
the city.
"""

from __future__ import annotations

import math

import pytest

from app.core import geo
from app.core.exceptions import InvalidGeometryError

#: (lon, lat) — note the order, which is GeoJSON/PostGIS, not Leaflet.
DELHI: geo.LonLat = (77.2090, 28.6139)
KANPUR: geo.LonLat = (80.3319, 26.4499)
COIMBATORE: geo.LonLat = (76.9558, 11.0168)


class TestValidateLonLat:
    def test_accepts_indian_coordinates(self) -> None:
        assert geo.validate_lon_lat(*DELHI) == DELHI

    def test_a_range_check_cannot_catch_a_swapped_indian_coordinate(self) -> None:
        # Transposed Delhi is (28.61, 77.21), and 77.21 is a legal latitude, so
        # this passes. Documented as a test because it is the precise reason
        # validate_within_india exists; anyone tempted to rely on the range check
        # alone at an ingestion boundary should see this fail their assumption.
        assert geo.validate_lon_lat(28.6139, 77.2090) == (28.6139, 77.2090)

    def test_catches_a_swap_only_when_the_longitude_exceeds_90(self) -> None:
        # Eastern India (Guwahati, 91.75E) is the one region where transposition
        # does produce an out-of-range latitude.
        with pytest.raises(InvalidGeometryError, match="Latitude"):
            geo.validate_lon_lat(26.1445, 91.7362)

    def test_rejects_out_of_range_longitude(self) -> None:
        with pytest.raises(InvalidGeometryError, match="Longitude"):
            geo.validate_lon_lat(181.0, 0.0)

    def test_rejects_nan(self) -> None:
        with pytest.raises(InvalidGeometryError, match="numbers"):
            geo.validate_lon_lat(math.nan, 0.0)


class TestIndiaBounds:
    """The ingestion-boundary check that actually catches transposed pairs."""

    @pytest.mark.parametrize("point", [DELHI, KANPUR, COIMBATORE])
    def test_accepts_indian_cities(self, point: geo.LonLat) -> None:
        assert geo.validate_within_india(point) == point

    def test_rejects_a_transposed_indian_coordinate(self) -> None:
        # This is the case a plain range check waves through: latitude 77.21 is
        # legal, but it is in Kazakhstan, not Delhi.
        with pytest.raises(InvalidGeometryError, match="outside India"):
            geo.validate_within_india((28.6139, 77.2090))

    def test_rejects_a_coordinate_in_another_country(self) -> None:
        london: geo.LonLat = (-0.1276, 51.5072)
        with pytest.raises(InvalidGeometryError, match="outside India"):
            geo.validate_within_india(london)

    def test_predicate_returns_false_rather_than_raising(self) -> None:
        assert geo.is_within_india(DELHI) is True
        assert geo.is_within_india((-0.1276, 51.5072)) is False

    def test_error_carries_the_offending_coordinate(self) -> None:
        with pytest.raises(InvalidGeometryError) as excinfo:
            geo.validate_within_india((28.6139, 77.2090))
        assert excinfo.value.details["longitude"] == pytest.approx(28.6139)
        assert excinfo.value.details["latitude"] == pytest.approx(77.2090)


class TestHaversineDistance:
    def test_zero_for_identical_points(self) -> None:
        assert geo.haversine_distance_m(DELHI, DELHI) == pytest.approx(0.0, abs=1e-6)

    def test_one_degree_of_latitude_is_about_111_km(self) -> None:
        distance = geo.haversine_distance_m((0.0, 0.0), (0.0, 1.0))
        assert distance == pytest.approx(111_195.0, rel=1e-3)

    def test_delhi_to_kanpur(self) -> None:
        # Great-circle distance is roughly 395 km.
        distance = geo.haversine_distance_m(DELHI, KANPUR)
        assert 380_000 < distance < 410_000

    def test_is_symmetric(self) -> None:
        assert geo.haversine_distance_m(DELHI, COIMBATORE) == pytest.approx(
            geo.haversine_distance_m(COIMBATORE, DELHI)
        )


class TestBearing:
    def test_due_north(self) -> None:
        assert geo.initial_bearing_deg((0.0, 0.0), (0.0, 1.0)) == pytest.approx(0.0)

    def test_due_east(self) -> None:
        assert geo.initial_bearing_deg((0.0, 0.0), (1.0, 0.0)) == pytest.approx(90.0)

    def test_due_south(self) -> None:
        assert geo.initial_bearing_deg((0.0, 0.0), (0.0, -1.0)) == pytest.approx(180.0)

    def test_due_west(self) -> None:
        assert geo.initial_bearing_deg((0.0, 0.0), (-1.0, 0.0)) == pytest.approx(270.0)


class TestDestinationPoint:
    def test_round_trips_with_distance_and_bearing(self) -> None:
        bearing = geo.initial_bearing_deg(DELHI, KANPUR)
        distance = geo.haversine_distance_m(DELHI, KANPUR)
        lon, lat = geo.destination_point(DELHI, bearing, distance)
        assert lon == pytest.approx(KANPUR[0], abs=1e-4)
        assert lat == pytest.approx(KANPUR[1], abs=1e-4)

    def test_zero_distance_returns_the_origin(self) -> None:
        lon, lat = geo.destination_point(DELHI, 45.0, 0.0)
        assert (lon, lat) == pytest.approx(DELHI)

    def test_rejects_negative_distance(self) -> None:
        with pytest.raises(InvalidGeometryError, match="negative"):
            geo.destination_point(DELHI, 0.0, -100.0)


class TestWindConventions:
    """Meteorological convention: a direction names where wind comes *from*.

    The u/v components point where the air is *going*, so the two are opposite.
    """

    @pytest.mark.parametrize(
        ("wind_u", "wind_v", "expected_from"),
        [
            (0.0, -1.0, 0.0),  # air moving south -> a northerly
            (-1.0, 0.0, 90.0),  # air moving west  -> an easterly
            (0.0, 1.0, 180.0),  # air moving north -> a southerly
            (1.0, 0.0, 270.0),  # air moving east  -> a westerly
        ],
    )
    def test_from_direction_at_the_cardinals(
        self, wind_u: float, wind_v: float, expected_from: float
    ) -> None:
        assert geo.wind_from_direction_deg(wind_u, wind_v) == pytest.approx(expected_from)

    @pytest.mark.parametrize(
        ("wind_u", "wind_v", "expected_to"),
        [
            (0.0, -1.0, 180.0),
            (-1.0, 0.0, 270.0),
            (0.0, 1.0, 0.0),
            (1.0, 0.0, 90.0),
        ],
    )
    def test_to_direction_is_the_reciprocal(
        self, wind_u: float, wind_v: float, expected_to: float
    ) -> None:
        assert geo.wind_to_direction_deg(wind_u, wind_v) == pytest.approx(expected_to)

    def test_speed_from_components(self) -> None:
        assert geo.wind_speed_ms(3.0, 4.0) == pytest.approx(5.0)

    def test_calm_air_has_no_direction(self) -> None:
        # Returning an arbitrary bearing here would silently point a
        # back-trajectory somewhere; the caller must handle calm explicitly.
        with pytest.raises(InvalidGeometryError, match="undefined"):
            geo.wind_from_direction_deg(0.0, 0.0)

    def test_backtracking_walks_toward_the_source(self) -> None:
        # A westerly (air moving east) carries a plume eastward, so tracing back
        # from the hotspot must move west, decreasing longitude.
        from_direction = geo.wind_from_direction_deg(wind_u=5.0, wind_v=0.0)
        upwind_lon, _ = geo.destination_point(DELHI, from_direction, 10_000.0)
        assert upwind_lon < DELHI[0]


class TestAngularDifference:
    @pytest.mark.parametrize(
        ("a", "b", "expected"),
        [
            (0.0, 0.0, 0.0),
            (10.0, 350.0, 20.0),  # must wrap across north
            (0.0, 180.0, 180.0),
            (90.0, 270.0, 180.0),
            (45.0, 90.0, 45.0),
        ],
    )
    def test_wraps_correctly(self, a: float, b: float, expected: float) -> None:
        assert geo.angular_difference_deg(a, b) == pytest.approx(expected)
