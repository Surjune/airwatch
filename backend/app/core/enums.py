"""Shared enumerations.

Leaf-level: every layer may import these, and they import nothing themselves.
"""

from __future__ import annotations

from enum import StrEnum


class PilotCity(StrEnum):
    """A city this deployment ingests, analyses and can scope a view to."""

    DELHI = "delhi"
    KANPUR = "kanpur"
    COIMBATORE = "coimbatore"


class Pollutant(StrEnum):
    """Pollutants in the CPCB National AQI.

    Values are the canonical identifiers used in the database, the API and the
    interoperability envelope, so they must stay stable across versions.
    """

    PM25 = "pm25"
    PM10 = "pm10"
    NO2 = "no2"
    SO2 = "so2"
    O3 = "o3"
    CO = "co"
    NH3 = "nh3"


class StationTier(StrEnum):
    """Provenance tier of an observation, which sets how much it is trusted.

    The three-tier split is the core of the design: reference instruments are
    accurate but sparse, low-cost sensors are dense but biased, and citizen
    reports are ubiquitous but very noisy. Fusion weights each accordingly.
    """

    #: CPCB CAAQMS or equivalent regulatory-grade analyser. Ground truth, and the
    #: calibration target for everything else.
    REFERENCE = "reference"

    #: Low-cost optical particle counter. Usable only after calibration.
    LOW_COST = "low_cost"

    #: Photo-derived estimate from a citizen submission. Lowest weight, never
    #: used as the sole evidence for a cell.
    CITIZEN = "citizen"

    #: Satellite retrieval. Uniform coverage, coarse resolution; a covariate for
    #: fusion rather than a direct measurement of surface concentration.
    SATELLITE = "satellite"


class SourceType(StrEnum):
    """Categories in the pollution source registry, used for attribution."""

    INDUSTRY = "industry"
    LANDFILL = "landfill"
    BRICK_KILN = "brick_kiln"
    CONSTRUCTION = "construction"
    ROAD_SEGMENT = "road_segment"
    CROP_RESIDUE_FIRE = "crop_residue_fire"
    WASTE_BURNING = "waste_burning"
    THERMAL_POWER = "thermal_power"


class HotspotStatus(StrEnum):
    """Lifecycle of a detected hotspot."""

    #: Threshold exceeded but persistence or contiguity not yet satisfied.
    CANDIDATE = "candidate"

    #: All detection criteria met.
    CONFIRMED = "confirmed"

    #: Concentrations returned to the expected baseline.
    RESOLVED = "resolved"

    #: Reviewed by an authority and judged not a real event.
    DISMISSED = "dismissed"


class AlertStatus(StrEnum):
    """Lifecycle of an alert routed to an authority.

    The transitions are what turn a detection into an accountability trail; an
    alert with no acknowledgement is as much a finding as the hotspot itself.
    """

    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
