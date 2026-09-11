"""Assembling the exchange payloads a partner node consumes.

Everything here is a projection of data the node already holds into a shape
another agency can ingest without negotiating a schema first. Nothing is
computed specially for export, which is deliberate: an exchange format that
reports different numbers from the operational API is a format that will
eventually be used to settle an argument and lose.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core import aqi
from app.core.config import Settings
from app.core.constants import (
    H3_RESOLUTION,
    PUBLISHED_FEDERATED_SPARSE_NODE_CHANGE,
    PUBLISHED_FORECAST_LEARNED_MAE_UGM3,
    PUBLISHED_FORECAST_MAE_UGM3,
    PUBLISHED_FORECAST_PERSISTENCE_MAE_UGM3,
    PUBLISHED_FUSION_LEARNED_MAE_UGM3,
    PUBLISHED_FUSION_MAE_UGM3,
    PUBLISHED_FUSION_R2,
)
from app.core.enums import Pollutant
from app.core.logging import get_logger
from app.ml.forecast_features import federated_feature_names
from app.ml.fusion_features import FEATURE_NAMES as FUSION_FEATURE_NAMES
from app.ml.hotspot_detection import detect_over_window
from app.repositories import observation_repository
from app.schemas.interop import (
    OBSERVED_PROPERTY_BASE_URI,
    Capability,
    ExchangeMetadata,
    HotspotCollection,
    HotspotFeature,
    HotspotProperties,
    ModelCard,
    ModelCatalogue,
    ModelPerformance,
    NodeCapabilities,
    ObservationCollection,
    ObservationFeature,
    ObservationProperties,
    ObservedProperty,
    PointGeometry,
    UnitOfMeasurement,
)
from app.services.health_service import APP_VERSION

logger = get_logger(__name__)

#: Terms the exchanged data is offered under. Named explicitly because a
#: receiving agency cannot lawfully republish data whose licence is unstated,
#: and "we assumed it was fine" is not a position a state body can take.
EXCHANGE_LICENCE = "CC-BY-4.0"

#: Attached to every payload. Estimated values crossing an administrative
#: boundary are the ones most likely to be mistaken for measurements, because
#: the receiving side cannot see how they were produced.
EXCHANGE_DISCLAIMER = (
    "Values are as measured or estimated by the issuing node and carry the "
    "uncertainty stated with them. Estimates are not regulatory measurements "
    "and must not be used as a compliance record for another jurisdiction."
)

#: How a hotspot was established, stated so a partner can judge whether their
#: own detections are comparable with these.
DETECTION_METHOD = (
    "Residual against an inverse-distance prediction from the surrounding "
    "network, standardised by the error model fitted in leave-one-station-out "
    "validation, then required to persist across multiple intervals."
)

#: Default and maximum spans a caller may request, in hours.
DEFAULT_OBSERVATION_WINDOW_HOURS = 24
MAX_OBSERVATION_WINDOW_HOURS = 720

#: Most features one response may carry. A fortnight of a dense network is tens
#: of thousands of readings, and an exchange endpoint that streams all of them
#: in a single document fails on the receiving side rather than here. The
#: response says when it has been clipped, so a partner never mistakes a
#: truncated window for a quiet one.
MAX_FEATURES_PER_RESPONSE = 5000

#: Unit metadata for the mass concentrations everything is normalised to.
_MASS_CONCENTRATION = UnitOfMeasurement(
    name="microgram per cubic metre",
    symbol="ug/m3",
    definition="http://qudt.org/vocab/unit/MicroGM-PER-M3",
)


def capabilities(settings: Settings) -> NodeCapabilities:
    """Describe what this node offers, so a partner can integrate at runtime."""
    return NodeCapabilities(
        node_id=settings.node_id,
        node_name=settings.node_name,
        operator=settings.node_operator,
        api_version=APP_VERSION,
        spatial_index="H3",
        h3_resolution=H3_RESOLUTION,
        pollutants=list(Pollutant),
        licence=EXCHANGE_LICENCE,
        endpoints=[
            Capability(
                path="/v1/interop/capabilities",
                method="GET",
                description="This document.",
            ),
            Capability(
                path="/v1/interop/observations",
                method="GET",
                description=(
                    "Station observations as a GeoJSON FeatureCollection with "
                    "OGC SensorThings property names."
                ),
            ),
            Capability(
                path="/v1/interop/hotspots",
                method="GET",
                description=(
                    "Detected episodes as GeoJSON, each carrying observed, "
                    "expected and excess so a partner can tell a local source "
                    "from a regional episode."
                ),
            ),
            Capability(
                path="/v1/interop/models",
                method="GET",
                description=(
                    "Model cards with the measured performance of every "
                    "estimator this node runs, including the ones that lost."
                ),
            ),
        ],
    )


def _metadata(settings: Settings, *, returned: int, truncated: bool = False) -> ExchangeMetadata:
    return ExchangeMetadata(
        returned=returned,
        truncated=truncated,
        node_id=settings.node_id,
        node_name=settings.node_name,
        operator=settings.node_operator,
        generated_at=datetime.now(UTC),
        h3_resolution=H3_RESOLUTION,
        licence=EXCHANGE_LICENCE,
        disclaimer=EXCHANGE_DISCLAIMER,
    )


def observations(
    session: Session,
    settings: Settings,
    pollutant: Pollutant,
    *,
    window_hours: int = DEFAULT_OBSERVATION_WINDOW_HOURS,
    now: datetime | None = None,
) -> ObservationCollection:
    """Recent station observations as a GeoJSON FeatureCollection."""
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)

    matched = observation_repository.observed_readings_in_window(session, pollutant, since)
    truncated = len(matched) > MAX_FEATURES_PER_RESPONSE

    features = [
        ObservationFeature(
            geometry=PointGeometry(coordinates=reading.coordinates),
            properties=ObservationProperties(
                **{
                    "@iot.id": f"{settings.node_id}:observation:"
                    f"{reading.station_id}:{reading.observed_at.isoformat()}",
                    "resultTime": reading.observed_at.isoformat(),
                    "unitOfMeasurement": _MASS_CONCENTRATION,
                    "observedProperty": ObservedProperty(
                        name=pollutant.value,
                        definition=f"{OBSERVED_PROPERTY_BASE_URI}/{pollutant.value}",
                    ),
                    # Every station ingested so far is a regulatory monitor. When
                    # a low-cost tier exists this becomes per-station, and a
                    # partner can weight the two differently -- which is the
                    # entire reason the field is carried rather than assumed.
                    "resultQuality": "reference",
                },
                node_id=settings.node_id,
                station_name=reading.station_name,
                h3_cell=reading.h3_cell,
                result=reading.value,
                aqi=aqi.sub_index(pollutant, reading.value),
                aqi_category=aqi.category(aqi.sub_index(pollutant, reading.value)),
            ),
        )
        for reading in matched[:MAX_FEATURES_PER_RESPONSE]
    ]

    logger.info(
        "interop.observations_served",
        pollutant=pollutant.value,
        window_hours=window_hours,
        features=len(features),
        truncated=truncated,
    )
    return ObservationCollection(
        features=features,
        metadata=_metadata(settings, returned=len(features), truncated=truncated),
    )


def hotspots(
    session: Session,
    settings: Settings,
    pollutant: Pollutant,
    *,
    window_hours: int = DEFAULT_OBSERVATION_WINDOW_HOURS,
    now: datetime | None = None,
) -> HotspotCollection:
    """Detected episodes as a GeoJSON FeatureCollection."""
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=window_hours)

    readings = observation_repository.observed_readings_in_window(session, pollutant, since)
    names = {reading.station_id: reading.station_name for reading in readings}

    features = [
        HotspotFeature(
            geometry=PointGeometry(coordinates=hotspot.coordinates),
            properties=HotspotProperties(
                **{
                    "@iot.id": f"{settings.node_id}:hotspot:"
                    f"{hotspot.h3_cell}:{hotspot.first_seen_at.isoformat()}"
                },
                node_id=settings.node_id,
                station_name=names.get(hotspot.station_id),
                h3_cell=hotspot.h3_cell,
                pollutant=pollutant,
                first_seen_at=hotspot.first_seen_at,
                last_seen_at=hotspot.last_seen_at,
                duration_hours=hotspot.duration_hours,
                peak_observed=hotspot.peak_observed,
                peak_expected=hotspot.peak_observed - hotspot.peak_residual,
                peak_excess=hotspot.peak_residual,
                peak_z=hotspot.peak_z,
                detection_method=DETECTION_METHOD,
            ),
        )
        for hotspot in detect_over_window(readings)
    ]

    logger.info(
        "interop.hotspots_served",
        pollutant=pollutant.value,
        window_hours=window_hours,
        features=len(features),
    )
    return HotspotCollection(
        features=features,
        metadata=_metadata(settings, returned=len(features)),
    )


def models(settings: Settings) -> ModelCatalogue:
    """Model cards for every estimator this node runs.

    Both cards withhold a weight vector, and both say why. The learned models
    were trained, validated and lost to their baselines, so publishing their
    weights would invite a partner to adopt something this node measured to be
    worse. Stating that is more useful to a data-poor city than a download link.
    """
    return ModelCatalogue(
        node_id=settings.node_id,
        generated_at=datetime.now(UTC),
        model_count=2,
        models=[
            ModelCard(
                model_id=f"{settings.node_id}:surface:idw",
                node_id=settings.node_id,
                task="Estimate concentration at a location with no monitor.",
                estimator="Inverse-distance weighting, power 2, with a fitted uncertainty model.",
                version=APP_VERSION,
                feature_schema=list(FUSION_FEATURE_NAMES),
                performance=[
                    ModelPerformance(
                        metric="MAE (ug/m3)",
                        value=PUBLISHED_FUSION_MAE_UGM3,
                        baseline="LightGBM, given the interpolated estimate as a feature",
                        baseline_value=PUBLISHED_FUSION_LEARNED_MAE_UGM3,
                        validation="Leave-one-station-out over 61 Delhi stations.",
                    ),
                    ModelPerformance(
                        metric="R2",
                        value=PUBLISHED_FUSION_R2,
                        validation="Leave-one-station-out over 61 Delhi stations.",
                    ),
                ],
                weights_withheld_because=(
                    "The shipped estimator is interpolation and has no learned weights. "
                    "The gradient-boosted alternative was trained and lost, so its "
                    "weights are not offered."
                ),
                limitations=[
                    "R2 of 0.232 means neighbouring stations explain under a quarter of "
                    "the variance at an unmonitored point, even in a dense network.",
                    "Uncertainty widens sharply where nearby monitors disagree; a cell "
                    "too poorly supported to estimate returns nothing rather than a number.",
                    "Every input station is reference-grade. No low-cost tier has been "
                    "calibrated, so the dense-sensor argument is untested here.",
                ],
                licence=EXCHANGE_LICENCE,
            ),
            ModelCard(
                model_id=f"{settings.node_id}:forecast:climatology",
                node_id=settings.node_id,
                task="Forecast concentration 24 to 72 hours ahead along a corridor.",
                estimator="Per-station diurnal climatology, distance-weighted across stations.",
                version=APP_VERSION,
                feature_schema=list(federated_feature_names()),
                performance=[
                    ModelPerformance(
                        metric="MAE at 24h (ug/m3)",
                        value=PUBLISHED_FORECAST_MAE_UGM3,
                        baseline="LightGBM on the same temporal holdout",
                        baseline_value=PUBLISHED_FORECAST_LEARNED_MAE_UGM3,
                        validation="Temporal holdout: trained on earliest days, tested on latest.",
                    ),
                    ModelPerformance(
                        metric="MAE at 24h (ug/m3)",
                        value=PUBLISHED_FORECAST_MAE_UGM3,
                        baseline="Persistence",
                        baseline_value=PUBLISHED_FORECAST_PERSISTENCE_MAE_UGM3,
                        validation="Temporal holdout: trained on earliest days, tested on latest.",
                    ),
                ],
                weights_withheld_because=(
                    "Climatology has no weight vector. The learned model that would have "
                    "had one lost to it at every horizon, and federated averaging of that "
                    "model measurably harmed the sparse node "
                    f"({PUBLISHED_FEDERATED_SPARSE_NODE_CHANGE:+.1%} on its own holdout), "
                    "so adopting it is not recommended on this evidence."
                ),
                limitations=[
                    "No day-to-day skill: the same value is predicted for a given hour on "
                    "consecutive days. It captures the daily cycle and the spatial "
                    "gradient, not tomorrow being worse than today.",
                    "Fitted on fourteen days of history. The binding constraint is data "
                    "volume, not architecture.",
                    "The schema is the 17 features every node can compute. Meteorological "
                    "features are excluded because they are ingested for one node only.",
                ],
                licence=EXCHANGE_LICENCE,
            ),
        ],
    )
