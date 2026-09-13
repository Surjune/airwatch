"""Which pilot city a position belongs to, for scoping a view.

Lives in ``core`` because both the analysis and the alerting services scope by
city, and services may not import one another.
"""

from __future__ import annotations

from app.core.constants import CITY_VIEW_RADIUS_M, PILOT_CITY_CENTRES
from app.core.enums import PilotCity
from app.core.geo import LonLat, haversine_distance_m


def in_city(coordinates: LonLat, city: PilotCity | None) -> bool:
    """Whether a position falls in a city's view. Everything does when no city is given."""
    if city is None:
        return True
    return haversine_distance_m(coordinates, PILOT_CITY_CENTRES[city.value]) <= CITY_VIEW_RADIUS_M
