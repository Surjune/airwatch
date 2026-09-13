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


class SatelliteProduct(StrEnum):
    """A Sentinel-5P TROPOMI column product ingested from Earth Engine."""

    NO2 = "no2"
    SO2 = "so2"
    CO = "co"
    AEROSOL_INDEX = "aerosol_index"


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


class ComplaintCategory(StrEnum):
    """What a resident says they saw, attached to a photograph or sensor reading.

    Kept to the source types an inspector would be sent to check, so a complaint
    can be read by the body responsible without translation. ``other`` exists
    because a forced wrong category is worse than an honest unknown.
    """

    OPEN_BURNING = "open_burning"
    INDUSTRIAL_SMOKE = "industrial_smoke"
    CONSTRUCTION_DUST = "construction_dust"
    VEHICLE_EXHAUST = "vehicle_exhaust"
    CROP_RESIDUE_BURNING = "crop_residue_burning"
    ROAD_DUST = "road_dust"
    OTHER = "other"


class SubmissionKind(StrEnum):
    """Which citizen tier a submission came through."""

    PHOTO = "photo"
    SENSOR = "sensor"


class AlertKind(StrEnum):
    """Why an authority received an alert.

    ``local``: the hotspot is on its ground. ``coordination``: the hotspot is on
    someone else's ground, but the likeliest upwind source is on this one, so the
    body able to inspect the source is asked to act for a neighbour. Pollution
    does not stop at a district line, and neither can the response.
    """

    LOCAL = "local"
    COORDINATION = "coordination"


class GuideScreen(StrEnum):
    """A screen of the web interface that has a spoken guide.

    Mirrors the frontend's screen keys, so a guide is addressed by the same word
    the address bar shows.
    """

    OVERVIEW = "overview"
    MAP = "map"
    CORRIDOR = "corridor"
    ALERTS = "alerts"
    FEDERATION = "federation"
    CITIZEN = "citizen"


class GuideLanguage(StrEnum):
    """A language the voice guide is written and spoken in.

    Hindi and Tamil because the pilot cities are Delhi-NCR and Kanpur, and
    Coimbatore; English for everyone else. Values are ISO 639-1 codes.
    """

    ENGLISH = "en"
    HINDI = "hi"
    TAMIL = "ta"
