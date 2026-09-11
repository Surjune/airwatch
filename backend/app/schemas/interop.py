"""Exchange formats for sharing observations and models between cities.

The governance problem this answers is specific. CPCB, roughly thirty-five state
boards, municipal corporations, ISRO and IMD each hold a fragment of the same
picture, and Punjab's smoke is Delhi's emergency within two days. No state will
hand another its raw database, so every attempt at a single national data lake
stalls -- not on bandwidth, on ownership.

What a state *will* exchange is a bounded, self-describing envelope it can audit
before sending. So the shapes here are deliberately conservative:

* **GeoJSON, because everything reads GeoJSON.** A partner needs no client
  library and no schema negotiation to put these on a map.
* **OGC SensorThings property names** (``result``, ``resultTime``,
  ``unitOfMeasurement``, ``observedProperty``) so the payload lines up with the
  vocabulary Indian environmental data programmes already reference, rather than
  inventing a private one.
* **Provenance on every feature.** A receiving node must be able to say which
  node produced a number, at what quality, under what licence. Anonymous data
  cannot be audited, and data that cannot be audited does not get used in a
  decision anyone has to defend.
* **Uncertainty travels with the value.** An estimate that crosses a boundary
  without its error bar invites the receiving city to treat it as a measurement.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.core.enums import Pollutant

#: The only coordinate reference system this API speaks, stated explicitly
#: because a silently assumed CRS is the classic way spatial exchange goes wrong.
CRS_URI = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"

#: Vocabulary the observed properties are drawn from.
OBSERVED_PROPERTY_BASE_URI = "http://vocab.nerc.ac.uk/standard_name"


class UnitOfMeasurement(BaseModel):
    """An OGC SensorThings unit block."""

    name: str
    symbol: str
    definition: str


class ObservedProperty(BaseModel):
    """What was measured, named in a way a partner can resolve."""

    name: str
    definition: str


class ObservationProperties(BaseModel):
    """Properties of one exchanged observation."""

    iot_id: str = Field(
        alias="@iot.id",
        description="Globally unique within the federation: node id plus local identity.",
    )
    node_id: str = Field(description="Which node produced this observation.")
    station_name: str
    h3_cell: str = Field(
        description=(
            "Resolution-8 H3 index. The shared spatial key that makes two "
            "cities' data comparable without either resampling the other's grid."
        )
    )
    result: float
    result_time: str = Field(alias="resultTime", description="UTC, ISO 8601.")
    unit_of_measurement: UnitOfMeasurement = Field(alias="unitOfMeasurement")
    observed_property: ObservedProperty = Field(alias="observedProperty")
    result_quality: str = Field(
        alias="resultQuality",
        description=(
            "Measurement tier. 'reference' is a calibrated regulatory monitor; "
            "anything else carries wider error and must not be treated as ground truth."
        ),
    )
    aqi: float
    aqi_category: str

    model_config = {"populate_by_name": True}


class HotspotProperties(BaseModel):
    """Properties of one exchanged hotspot episode.

    Deliberately carries expected alongside observed. A neighbouring state
    receiving only the concentration cannot tell a local source from a regional
    episode it is already living through, which is the distinction that decides
    whether the finding is theirs to act on.
    """

    iot_id: str = Field(alias="@iot.id")
    node_id: str
    station_name: str | None = None
    h3_cell: str
    pollutant: Pollutant
    first_seen_at: datetime
    last_seen_at: datetime
    duration_hours: float
    peak_observed: float
    peak_expected: float
    peak_excess: float
    peak_z: float
    detection_method: str = Field(
        description="How the excess was established, so a partner can judge comparability."
    )

    model_config = {"populate_by_name": True}


class PointGeometry(BaseModel):
    """A GeoJSON point, always (longitude, latitude)."""

    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]


class ObservationFeature(BaseModel):
    """One observation as a GeoJSON feature."""

    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: ObservationProperties


class HotspotFeature(BaseModel):
    """One hotspot as a GeoJSON feature."""

    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: HotspotProperties


class ExchangeMetadata(BaseModel):
    """Who sent this, when, and on what terms."""

    node_id: str
    node_name: str
    operator: str
    generated_at: datetime
    crs: str = CRS_URI
    h3_resolution: int
    licence: str
    disclaimer: str

    returned: int = Field(description="Features in this response.")
    truncated: bool = Field(
        default=False,
        description=(
            "True when more features matched than the response carries. A "
            "partner that cannot tell a complete answer from a clipped one "
            "would silently treat a truncated window as a quiet period."
        ),
    )


class ObservationCollection(BaseModel):
    """A GeoJSON FeatureCollection of observations."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ObservationFeature]
    metadata: ExchangeMetadata


class HotspotCollection(BaseModel):
    """A GeoJSON FeatureCollection of hotspot episodes."""

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[HotspotFeature]
    metadata: ExchangeMetadata


class ModelPerformance(BaseModel):
    """A measured score, with what it was measured against.

    The baseline is optional because not every metric has one. A metric with no
    comparison says so rather than naming itself as its own baseline, which
    would read as a model that matched a rival exactly.
    """

    metric: str
    value: float
    baseline: str | None = Field(
        default=None, description="What this was compared with, if anything."
    )
    baseline_value: float | None = None
    validation: str = Field(description="How the holdout was constructed.")


class ModelCard(BaseModel):
    """What a partner city needs in order to decide whether to adopt a model.

    The performance figures are reported whether or not they flatter the system.
    A federation in which nodes publish only favourable numbers is worse than no
    federation: a data-poor city would adopt a model that harms it and have no
    way to find out.
    """

    model_id: str
    node_id: str
    task: str
    estimator: str
    version: str
    trained_at: datetime | None = None

    feature_schema: list[str] = Field(
        description=(
            "The shared feature set. Smaller than any single node's, because a "
            "feature one node can compute and another cannot does not average."
        )
    )
    training_rows: int | None = None
    performance: list[ModelPerformance]

    weights: list[float] | None = Field(
        default=None,
        description=(
            "Published only when a learned model beat its baseline on this "
            "node's own holdout. Null means no weight vector is offered, and the "
            "reason is in `weights_withheld_because`."
        ),
    )
    weights_withheld_because: str | None = None

    limitations: list[str]
    licence: str

    model_config = {"protected_namespaces": ()}


class ModelCatalogue(BaseModel):
    """Every model this node is willing to share."""

    node_id: str
    generated_at: datetime
    model_count: int
    models: list[ModelCard]

    model_config = {"protected_namespaces": ()}


class Capability(BaseModel):
    """One exchange endpoint this node offers."""

    path: str
    method: str
    description: str


class NodeCapabilities(BaseModel):
    """A node's self-description, so a partner can integrate without asking.

    Discovery matters more here than in an ordinary API. Nodes are operated by
    different agencies on different timelines, so a partner has to be able to
    find out what a node supports at runtime rather than from a document that
    was accurate when someone last edited it.
    """

    node_id: str
    node_name: str
    operator: str
    api_version: str
    crs: str = CRS_URI
    spatial_index: str
    h3_resolution: int
    pollutants: list[Pollutant]
    endpoints: list[Capability]
    licence: str
    contact: str | None = None
