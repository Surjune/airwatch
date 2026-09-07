"""Geodesic and wind-vector helpers — the single source of truth.

Two conventions are enforced here and must not be re-derived elsewhere:

**Coordinate order.** Every function takes and returns ``(longitude, latitude)``,
matching GeoJSON and PostGIS. Leaflet uses ``(lat, lon)``; that flip happens once,
in ``frontend/src/lib/``, never in this layer.

**Wind direction.** Meteorological convention: a "direction" is the direction the
wind blows *from*. A northerly wind (0 degrees) moves air southward. The ``u``/``v``
components are the eastward and northward components of the flow, so they point
where the air is going, which is the opposite. Getting this backwards inverts every
back-trajectory and would attribute every plume to a source on the wrong side of
the city, so the conversions live here and are tested at the four cardinals.
"""

from __future__ import annotations

import math

from app.core.constants import EARTH_MEAN_RADIUS_M, INDIA_BBOX
from app.core.exceptions import InvalidGeometryError

#: A (longitude, latitude) pair in WGS84, in that order.
LonLat = tuple[float, float]

_MIN_LONGITUDE = -180.0
_MAX_LONGITUDE = 180.0
_MIN_LATITUDE = -90.0
_MAX_LATITUDE = 90.0
_FULL_CIRCLE_DEG = 360.0
_HALF_CIRCLE_DEG = 180.0

#: Bearing of due north in the meteorological convention, used to convert between
#: mathematical (counterclockwise from east) and compass (clockwise from north)
#: angles: compass = 270 - math_angle.
_COMPASS_FROM_MATH_OFFSET_DEG = 270.0


def validate_lon_lat(lon: float, lat: float) -> LonLat:
    """Validate a coordinate pair and return it unchanged.

    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.

    Returns:
        The validated ``(lon, lat)`` pair.

    Raises:
        InvalidGeometryError: A value is out of range or not a number.

    Note:
        This is a WGS84 range check and nothing more. It cannot detect most
        transposed coordinates, because a swapped Indian longitude usually lands
        inside the legal latitude range -- Delhi transposed is (28.61, 77.21),
        and 77.21 is a perfectly valid latitude. Use
        :func:`validate_within_india` at ingestion boundaries where the data is
        known to be Indian.
    """
    if lon != lon or lat != lat:  # NaN check.
        raise InvalidGeometryError("Coordinates must be numbers.")
    if not _MIN_LONGITUDE <= lon <= _MAX_LONGITUDE:
        raise InvalidGeometryError(
            f"Longitude {lon} is outside [{_MIN_LONGITUDE}, {_MAX_LONGITUDE}]. "
            "Coordinates are (longitude, latitude), in that order.",
        )
    if not _MIN_LATITUDE <= lat <= _MAX_LATITUDE:
        raise InvalidGeometryError(
            f"Latitude {lat} is outside [{_MIN_LATITUDE}, {_MAX_LATITUDE}]. "
            "Coordinates are (longitude, latitude), in that order.",
        )
    return lon, lat


def is_within_india(point: LonLat) -> bool:
    """Whether a coordinate falls inside India's bounding box.

    Args:
        point: ``(lon, lat)`` in WGS84.

    Returns:
        True when the point is inside :data:`INDIA_BBOX`. Returns False rather
        than raising for a coordinate that is merely outside the region.

    Raises:
        InvalidGeometryError: The coordinate is not a valid WGS84 pair at all.
    """
    lon, lat = validate_lon_lat(*point)
    min_lon, min_lat, max_lon, max_lat = INDIA_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def validate_within_india(point: LonLat) -> LonLat:
    """Validate that a coordinate is inside India, and return it unchanged.

    The practical purpose is catching transposed coordinates at the ingestion
    boundary, which :func:`validate_lon_lat` cannot do on its own. Every Indian
    longitude (68-97.5) is a legal latitude, so a swap survives a range check but
    fails this one -- transposed Delhi becomes (28.61, 77.21), whose latitude of
    77.21 is far north of India.

    Args:
        point: ``(lon, lat)`` in WGS84.

    Returns:
        The validated ``(lon, lat)`` pair.

    Raises:
        InvalidGeometryError: The coordinate is malformed or outside India.
    """
    lon, lat = validate_lon_lat(*point)
    if not is_within_india((lon, lat)):
        raise InvalidGeometryError(
            f"Coordinate ({lon}, {lat}) is outside India. "
            "Coordinates are (longitude, latitude) in that order; "
            "a transposed pair is the usual cause.",
            details={"longitude": lon, "latitude": lat},
        )
    return lon, lat


def haversine_distance_m(origin: LonLat, destination: LonLat) -> float:
    """Great-circle distance between two points, in metres.

    Args:
        origin: ``(lon, lat)`` of the first point.
        destination: ``(lon, lat)`` of the second point.

    Returns:
        Distance in metres.
    """
    lon1, lat1 = validate_lon_lat(*origin)
    lon2, lat2 = validate_lon_lat(*destination)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_MEAN_RADIUS_M * math.asin(math.sqrt(a))


def initial_bearing_deg(origin: LonLat, destination: LonLat) -> float:
    """Initial compass bearing from origin to destination, in degrees.

    Args:
        origin: ``(lon, lat)`` of the start point.
        destination: ``(lon, lat)`` of the end point.

    Returns:
        Bearing in degrees clockwise from true north, in [0, 360).
    """
    lon1, lat1 = validate_lon_lat(*origin)
    lon2, lat2 = validate_lon_lat(*destination)

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    y = math.sin(delta_lambda) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda)
    return math.degrees(math.atan2(y, x)) % _FULL_CIRCLE_DEG


def destination_point(origin: LonLat, bearing_deg: float, distance_m: float) -> LonLat:
    """Point reached by travelling a distance along a bearing from an origin.

    This is the stepping function for the Lagrangian back-trajectory: each step
    moves the parcel one interval further upwind.

    Args:
        origin: ``(lon, lat)`` start point.
        bearing_deg: Compass bearing to travel, degrees clockwise from north.
        distance_m: Distance to travel, in metres. Must not be negative; to
            reverse direction, add 180 to the bearing.

    Returns:
        The ``(lon, lat)`` destination.

    Raises:
        InvalidGeometryError: The distance is negative.
    """
    if distance_m < 0:
        raise InvalidGeometryError(
            f"Distance must not be negative ({distance_m}); reverse the bearing instead.",
        )

    lon, lat = validate_lon_lat(*origin)
    angular_distance = distance_m / EARTH_MEAN_RADIUS_M
    theta = math.radians(bearing_deg)
    phi1 = math.radians(lat)
    lambda1 = math.radians(lon)

    sin_phi2 = math.sin(phi1) * math.cos(angular_distance) + math.cos(phi1) * math.sin(
        angular_distance
    ) * math.cos(theta)
    phi2 = math.asin(sin_phi2)
    lambda2 = lambda1 + math.atan2(
        math.sin(theta) * math.sin(angular_distance) * math.cos(phi1),
        math.cos(angular_distance) - math.sin(phi1) * sin_phi2,
    )

    # Normalise longitude back into [-180, 180].
    lon2 = (math.degrees(lambda2) + _HALF_CIRCLE_DEG) % _FULL_CIRCLE_DEG - _HALF_CIRCLE_DEG
    return lon2, math.degrees(phi2)


def wind_speed_ms(wind_u: float, wind_v: float) -> float:
    """Wind speed from its components.

    Args:
        wind_u: Eastward component of the flow, in m/s.
        wind_v: Northward component of the flow, in m/s.

    Returns:
        Speed in m/s.
    """
    return math.hypot(wind_u, wind_v)


def wind_from_direction_deg(wind_u: float, wind_v: float) -> float:
    """Direction the wind blows *from*, in degrees clockwise from north.

    This is the meteorological convention and the direction a back-trajectory
    travels: to find what produced the air now overhead, walk toward where it
    came from.

    Args:
        wind_u: Eastward component of the flow, in m/s.
        wind_v: Northward component of the flow, in m/s.

    Returns:
        Bearing in [0, 360). A wind with ``v`` negative (air moving south) is a
        northerly, and returns 0.

    Raises:
        InvalidGeometryError: Both components are zero, so no direction exists.
            Calm air cannot carry a plume, and the caller must handle that case
            rather than receive an arbitrary bearing.
    """
    if wind_u == 0 and wind_v == 0:
        raise InvalidGeometryError(
            "Wind direction is undefined when both components are zero.",
        )
    math_angle = math.degrees(math.atan2(wind_v, wind_u))
    return (_COMPASS_FROM_MATH_OFFSET_DEG - math_angle) % _FULL_CIRCLE_DEG


def wind_to_direction_deg(wind_u: float, wind_v: float) -> float:
    """Direction the wind blows *toward*, in degrees clockwise from north.

    The downwind bearing, used to project where a plume from a known source will
    travel next.

    Args:
        wind_u: Eastward component of the flow, in m/s.
        wind_v: Northward component of the flow, in m/s.

    Returns:
        Bearing in [0, 360).

    Raises:
        InvalidGeometryError: Both components are zero.
    """
    return (wind_from_direction_deg(wind_u, wind_v) + _HALF_CIRCLE_DEG) % _FULL_CIRCLE_DEG


def angular_difference_deg(bearing_a: float, bearing_b: float) -> float:
    """Smallest absolute angle between two bearings, in degrees.

    Used to test whether a candidate source falls inside the attribution cone.

    Args:
        bearing_a: First bearing in degrees.
        bearing_b: Second bearing in degrees.

    Returns:
        A value in [0, 180].
    """
    difference = abs(bearing_a - bearing_b) % _FULL_CIRCLE_DEG
    return min(difference, _FULL_CIRCLE_DEG - difference)
