"""Tests for classifying an OpenAQ location as a reference monitor or a low-cost sensor.

The regression these guard: every location was once stored as a reference
monitor, which put five AirGradient units into detection and validation as if
they were regulatory analysers.
"""

from __future__ import annotations

from app.core.enums import StationTier
from app.external.openaq_client import OpenAQLocation
from app.services.ingestion_service import station_tier


def location(*, is_monitor: bool, parameters: list[tuple[str, str]]) -> OpenAQLocation:
    return OpenAQLocation.model_validate(
        {
            "id": 1,
            "name": "Test site",
            "coordinates": {"latitude": 28.6, "longitude": 77.2},
            "isMonitor": is_monitor,
            "sensors": [
                {"id": index, "name": name, "parameter": {"id": index, "name": name, "units": unit}}
                for index, (name, unit) in enumerate(parameters)
            ],
        }
    )


AIRGRADIENT = [("pm1", "µg/m³"), ("pm25", "µg/m³"), ("relativehumidity", "%"), ("um003", "p/cm³")]
ANALYSER_SITE = [("pm25", "µg/m³"), ("pm10", "µg/m³"), ("no2", "µg/m³"), ("so2", "µg/m³")]


def test_a_flagged_monitor_is_reference() -> None:
    assert (
        station_tier(location(is_monitor=True, parameters=ANALYSER_SITE)) is StationTier.REFERENCE
    )


def test_an_optical_particle_sensor_is_low_cost() -> None:
    assert station_tier(location(is_monitor=False, parameters=AIRGRADIENT)) is StationTier.LOW_COST


def test_an_unflagged_site_that_measures_gases_is_still_reference() -> None:
    # Several DPCC and UPPCB analyser sites were added to OpenAQ with the monitor
    # flag unset. An optical sensor cannot measure NO2 or SO2, so they are not
    # low-cost, whatever the flag says.
    assert (
        station_tier(location(is_monitor=False, parameters=ANALYSER_SITE)) is StationTier.REFERENCE
    )


def test_an_unflagged_site_reporting_only_particulates_is_low_cost() -> None:
    particulates = [("pm25", "µg/m³"), ("pm10", "µg/m³")]
    assert station_tier(location(is_monitor=False, parameters=particulates)) is StationTier.LOW_COST
