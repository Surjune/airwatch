"""SQLAlchemy ORM models.

The repository layer is the only layer permitted to touch the database, so the
table definitions live here rather than in a top-level package. Nothing above
`repositories/` may import these.

Two decisions run through the whole schema:

* **Every observation is keyed to an H3 cell as well as a point.** The point is
  the truth; the cell is what fusion, hotspot detection, forecasting and the
  federated feature space all join on. Storing both means a spatial query can
  use the PostGIS index while an analysis query can group by cell without a
  join.
* **A calibrated value never overwrites its raw value.** Calibration is a model
  output that changes when the model is retrained, so the raw reading and the
  version of the model that corrected it are both kept. Overwriting would make a
  published number impossible to reproduce.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from geoalchemy2 import Geometry
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SqlEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.constants import (
    COMPLAINT_DESCRIPTION_MAX_LENGTH,
    GEMINI_ACTION_MAX_CHARS,
    GEMINI_BRIEF_MAX_CHARS,
    SRID_WGS84,
)
from app.core.enums import (
    AlertKind,
    AlertStatus,
    ComplaintCategory,
    HotspotStatus,
    Pollutant,
    SatelliteProduct,
    SourceType,
    StationTier,
)

#: Length of an H3 cell index in its canonical string form.
H3_INDEX_LENGTH = 15


def _enum_values(enum_class: type[StrEnum]) -> list[str]:
    """Persist an enum by its value rather than its member name.

    SQLAlchemy's native enum defaults to the member name, which would store
    "PM25" where the project's canonical identifier -- shared by the database,
    the API and the interoperability envelope -- is "pm25". A partner city
    reading our exchange format would then see a different spelling from the one
    the schema documents.
    """
    return [member.value for member in enum_class]


class Base(DeclarativeBase):
    """Declarative base for every AirWatch table."""


def _complaint_category_column() -> Mapped[ComplaintCategory | None]:
    """The optional complaint category shared by both citizen tables.

    One native type serves both, so a category means the same thing whichever
    tier it arrived through. ``create_type=False`` because the migration creates
    it once, before either column.
    """
    return mapped_column(
        SqlEnum(
            ComplaintCategory,
            name="complaint_category",
            create_type=False,
            values_callable=_enum_values,
        ),
        nullable=True,
    )


def _point_column(nullable: bool = False) -> Mapped[str]:
    """A WGS84 point column, always in (longitude, latitude) order.

    ``spatial_index=False`` is deliberate. GeoAlchemy2 otherwise creates the GiST
    index itself via a DDL listener, while Alembic autogenerate independently
    emits a CREATE INDEX for the same index -- and the migration fails on the
    duplicate. Each table declares its own GiST index in ``__table_args__``
    instead, so Alembic is the single owner of index creation.
    """
    return mapped_column(
        Geometry(geometry_type="POINT", srid=SRID_WGS84, spatial_index=False),
        nullable=nullable,
    )


class Station(Base):
    """A monitoring station of any tier.

    Reference stations, low-cost sensors and satellite pseudo-stations all live
    in one table because fusion treats them as one population with different
    trust weights, not as separate kinds of thing.
    """

    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    #: Upstream provider name, for example "OpenAQ" or "FIRMS".
    source: Mapped[str] = mapped_column(String(64), nullable=False)

    #: Identifier this station carries in the upstream system. Paired with
    #: `source` it is unique, which is what makes ingestion idempotent.
    source_station_id: Mapped[str] = mapped_column(String(128), nullable=False)

    name: Mapped[str] = mapped_column(String(256), nullable=False)

    tier: Mapped[StationTier] = mapped_column(
        SqlEnum(
            StationTier,
            name="station_tier",
            native_enum=True,
            values_callable=_enum_values,
        ),
        nullable=False,
    )

    geom: Mapped[str] = _point_column()

    #: H3 cell containing the station, at the canonical analysis resolution.
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)

    #: Operator, where the upstream reports one — CPCB, a state board, a private
    #: network. Retained because provenance drives the trust weight.
    operator: Mapped[str | None] = mapped_column(String(128), nullable=True)

    #: Most recent observation seen for this station, used to skip dormant ones.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Anything provider-specific worth keeping without a dedicated column.
    extra: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    measurements: Mapped[list[Measurement]] = relationship(
        back_populates="station", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "source_station_id", name="uq_station_source_identity"),
        Index("ix_stations_geom", "geom", postgresql_using="gist"),
    )


class Measurement(Base):
    """One pollutant reading from one station at one time.

    A TimescaleDB hypertable partitioned on ``observed_at``. Timescale requires
    the partitioning column to appear in the primary key, which is why the key is
    composite rather than a surrogate id.
    """

    __tablename__ = "measurements"

    station_id: Mapped[int] = mapped_column(
        ForeignKey("stations.id", ondelete="CASCADE"), primary_key=True
    )
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pollutant: Mapped[Pollutant] = mapped_column(
        SqlEnum(Pollutant, name="pollutant", native_enum=True, values_callable=_enum_values),
        primary_key=True,
    )

    #: The reading exactly as the upstream delivered it, already normalised into
    #: the unit the CPCB AQI table expects for this pollutant.
    value_raw: Mapped[float] = mapped_column(Float, nullable=False)

    #: The calibrated value, once a calibration model has been applied. Null
    #: until then. Never written over `value_raw`: recalibration must be
    #: reproducible, and a published number has to stay explainable.
    value_calibrated: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: Which calibration model produced `value_calibrated`.
    calibration_model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    #: Unit the values are stored in, kept explicitly because CO is milligrams
    #: while every other pollutant is micrograms.
    unit: Mapped[str] = mapped_column(String(16), nullable=False)

    #: False when the reading failed a plausibility check. Kept rather than
    #: deleted, so a bad sensor is visible as a pattern instead of vanishing.
    is_plausible: Mapped[bool] = mapped_column(nullable=False, default=True)

    station: Mapped[Station] = relationship(back_populates="measurements")

    __table_args__ = (
        CheckConstraint("value_raw >= 0", name="ck_measurement_non_negative"),
        Index("ix_measurements_observed_at", "observed_at"),
        Index("ix_measurements_pollutant_time", "pollutant", "observed_at"),
    )


class WeatherObservation(Base):
    """Hourly meteorology for one H3 cell.

    Keyed by cell rather than by point: the wind field is interpolated onto the
    analysis grid so that a trajectory step and a fusion feature read the same
    value for the same place.
    """

    __tablename__ = "weather_observations"

    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    #: Eastward and northward components of the flow, in m/s. Stored as
    #: components rather than speed and bearing so they can be averaged and
    #: interpolated without the wraparound that ruins an average of angles.
    wind_u: Mapped[float] = mapped_column(Float, nullable=False)
    wind_v: Mapped[float] = mapped_column(Float, nullable=False)

    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    relative_humidity_pct: Mapped[float] = mapped_column(Float, nullable=False)

    #: Boundary layer depth in metres. Null when the provider had no value; the
    #: absence widens downstream uncertainty rather than being filled with a
    #: guess.
    pbl_height_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    #: True for a forecast hour, false for one that has already happened. Both
    #: live here because a back-trajectory needs the past and a corridor forecast
    #: needs the future.
    is_forecast: Mapped[bool] = mapped_column(nullable=False, default=False)

    __table_args__ = (
        CheckConstraint(
            "relative_humidity_pct >= 0 AND relative_humidity_pct <= 100",
            name="ck_weather_humidity_range",
        ),
        CheckConstraint("pbl_height_m IS NULL OR pbl_height_m >= 0", name="ck_weather_pbl_range"),
        Index("ix_weather_observed_at", "observed_at"),
    )


class FireDetection(Base):
    """One satellite active-fire pixel.

    The evidence that turns an attributed plume into a named source with a
    timestamp.
    """

    __tablename__ = "fire_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geom: Mapped[str] = _point_column()
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Detection confidence as a fraction, normalised across VIIRS letter classes
    #: and MODIS percentages.
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

    #: Fire radiative power in megawatts — the weight used when ranking this
    #: fire against other candidate sources for a hotspot.
    frp_mw: Mapped[float] = mapped_column(Float, nullable=False)

    brightness_k: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_daytime: Mapped[bool] = mapped_column(nullable=False, default=True)
    satellite: Mapped[str] = mapped_column(String(32), nullable=False, default="")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_fire_confidence_range"),
        CheckConstraint("frp_mw >= 0", name="ck_fire_frp_non_negative"),
        # The same pixel is re-reported across overlapping requests, so
        # ingestion has to be idempotent on the physical detection itself.
        UniqueConstraint(
            "observed_at", "h3_cell", "frp_mw", "satellite", name="uq_fire_detection_identity"
        ),
        Index("ix_fire_observed_at", "observed_at"),
        Index("ix_fire_detections_geom", "geom", postgresql_using="gist"),
    )


class OfficialSubIndex(Base):
    """A station's official CPCB sub-index for one pollutant, as CPCB published it.

    Kept apart from ``measurements`` on purpose. These are indices averaged over
    CPCB's own periods (24 hours for particulates), not hourly concentrations, and
    mixing the two would let a daily average stand in for an hour in detection.
    They exist to show what the official feed says right now, including for the
    stations OpenAQ lags on by days.
    """

    __tablename__ = "official_sub_indices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    station_name: Mapped[str] = mapped_column(String(256), nullable=False)
    city: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(128), nullable=False)
    geom: Mapped[str] = _point_column()
    pollutant: Mapped[Pollutant] = mapped_column(
        SqlEnum(Pollutant, name="pollutant", create_type=False, values_callable=_enum_values),
        nullable=False,
    )
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sub_index: Mapped[float] = mapped_column(Float, nullable=False)
    sub_index_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    sub_index_max: Mapped[float | None] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "station_name", "pollutant", "reported_at", name="uq_official_station_pollutant_time"
        ),
        CheckConstraint("sub_index >= 0", name="ck_official_sub_index_non_negative"),
        Index("ix_official_city_reported", "city", "reported_at"),
    )


class SatelliteObservation(Base):
    """A daily mean of one Sentinel-5P product over one coarse H3 cell.

    Satellite columns are a covariate and a regional picture, not a ground
    measurement: a tropospheric NO2 column says how much gas sat above a
    ~36 km^2 cell during one overpass, not what anyone breathed. They are kept on
    their own coarse grid for exactly that reason.
    """

    __tablename__ = "satellite_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False)
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    product: Mapped[SatelliteProduct] = mapped_column(
        SqlEnum(SatelliteProduct, name="satellite_product", values_callable=_enum_values),
        nullable=False,
    )
    #: Mean over the cell's valid pixels, in the unit of ``unit``.
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Valid level-3 pixels behind the mean, so a thinly observed day can be told
    #: apart from a well observed one.
    pixel_count: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("h3_cell", "observed_on", "product", name="uq_satellite_cell_day_product"),
        CheckConstraint("pixel_count > 0", name="ck_satellite_pixels_positive"),
        Index("ix_satellite_product_day", "product", "observed_on"),
    )


class PollutionSource(Base):
    """A registered emitter, used as an attribution candidate.

    Distinct from a fire detection: a fire is an observed event, whereas an entry
    here is a known facility that may or may not be emitting at any given moment.
    """

    __tablename__ = "pollution_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        SqlEnum(SourceType, name="source_type", native_enum=True, values_callable=_enum_values),
        nullable=False,
    )

    geom: Mapped[str] = _point_column()
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)

    #: Relative prior on how much this source emits when active, used to rank
    #: candidates inside an attribution cone. A landfill fire and a single
    #: construction site are not equally likely explanations for the same plume.
    emission_prior: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    extra: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("emission_prior >= 0", name="ck_source_prior_non_negative"),
        Index("ix_pollution_sources_geom", "geom", postgresql_using="gist"),
    )


class Authority(Base):
    """A body responsible for acting on pollution inside a jurisdiction.

    Routing is geographic rather than configured per station, because a hotspot
    can appear anywhere on the grid -- including places with no monitor at all,
    which is the whole point of estimating a surface.
    """

    __tablename__ = "authorities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)

    #: Polygon this authority is responsible for, in WGS84.
    jurisdiction: Mapped[str] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=SRID_WGS84, spatial_index=False),
        nullable=False,
    )

    contact_email: Mapped[str | None] = mapped_column(String(320), nullable=True)

    #: Ordering used when jurisdictions overlap: the lowest tier that contains
    #: the hotspot is notified first, so a municipal body is reached before a
    #: state board rather than both being alerted for the same event.
    escalation_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    #: Whether new alerts may be routed here. An authority dropped from the
    #: registry is retired rather than deleted, because alerts already routed to
    #: it are part of the accountability trail and must keep pointing at the body
    #: that actually received them.
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True, server_default="true")

    __table_args__ = (
        Index("ix_authorities_jurisdiction", "jurisdiction", postgresql_using="gist"),
    )


class Hotspot(Base):
    """A confirmed episode of a location being dirtier than its neighbourhood."""

    __tablename__ = "hotspots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geom: Mapped[str] = _point_column()
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)

    #: The station that observed it, when detection ran on a monitored cell.
    #: Null once detection runs on the fused surface, where a hotspot can appear
    #: on ground no station covers.
    station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True
    )

    pollutant: Mapped[Pollutant] = mapped_column(
        SqlEnum(Pollutant, name="pollutant", native_enum=True, values_callable=_enum_values),
        nullable=False,
    )

    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    #: Consecutive intervals the excess persisted.
    intervals: Mapped[int] = mapped_column(Integer, nullable=False)

    #: Excess over the neighbourhood prediction, in units of expected error.
    peak_z: Mapped[float] = mapped_column(Float, nullable=False)

    #: Excess in concentration units, which is what a human reads.
    peak_residual: Mapped[float] = mapped_column(Float, nullable=False)
    peak_observed: Mapped[float] = mapped_column(Float, nullable=False)

    status: Mapped[HotspotStatus] = mapped_column(
        SqlEnum(
            HotspotStatus, name="hotspot_status", native_enum=True, values_callable=_enum_values
        ),
        nullable=False,
        default=HotspotStatus.CONFIRMED,
    )

    attributions: Mapped[list[HotspotAttribution]] = relationship(
        back_populates="hotspot", cascade="all, delete-orphan"
    )
    alerts: Mapped[list[Alert]] = relationship(
        back_populates="hotspot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # One episode per location per start time, so re-running detection over
        # an overlapping window converges rather than duplicating.
        UniqueConstraint("h3_cell", "first_seen_at", "pollutant", name="uq_hotspot_episode"),
        Index("ix_hotspots_last_seen", "last_seen_at"),
        Index("ix_hotspots_geom", "geom", postgresql_using="gist"),
    )


class HotspotAttribution(Base):
    """A ranked candidate explanation for a hotspot.

    Every row carries its confidence, and the UI must show it. A ranked
    candidate is never a finding of fact.
    """

    __tablename__ = "hotspot_attributions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotspot_id: Mapped[int] = mapped_column(
        ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False, index=True
    )

    #: Registry source, when the candidate is a known facility. Null for a
    #: satellite fire detection, which is an observed event rather than a
    #: registered site.
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("pollution_sources.id", ondelete="SET NULL"), nullable=True
    )

    candidate_name: Mapped[str] = mapped_column(String(256), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        SqlEnum(SourceType, name="source_type", native_enum=True, values_callable=_enum_values),
        nullable=False,
    )

    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    distance_m: Mapped[float] = mapped_column(Float, nullable=False)
    hours_upwind: Mapped[float] = mapped_column(Float, nullable=False)
    explanation: Mapped[str] = mapped_column(String(512), nullable=False)

    hotspot: Mapped[Hotspot] = relationship(back_populates="attributions")

    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_attribution_confidence"),
        UniqueConstraint("hotspot_id", "candidate_name", name="uq_attribution_candidate"),
    )


class Alert(Base):
    """An alert routed to an authority, and what happened to it.

    The acknowledgement and resolution timestamps are the accountability trail.
    An alert that was sent and never acknowledged is as much a finding as the
    hotspot that produced it.
    """

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    hotspot_id: Mapped[int] = mapped_column(
        ForeignKey("hotspots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    authority_id: Mapped[int] = mapped_column(
        ForeignKey("authorities.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    status: Mapped[AlertStatus] = mapped_column(
        SqlEnum(AlertStatus, name="alert_status", native_enum=True, values_callable=_enum_values),
        nullable=False,
        default=AlertStatus.SENT,
    )

    #: When the alert was *recorded*. Distinct from delivery: an alert exists
    #: in the trail the moment it is raised, whether or not anyone was reachable.
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: When the authority's endpoint accepted it, if it ever did. Null here with
    #: a non-null sent_at is the honest state for an alert nobody was told about,
    #: and collapsing the two would let an undelivered alert read as delivered.
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    #: Why delivery failed, when it did. Kept so a silent authority can be
    #: distinguished from an unreachable one -- which are different findings.
    delivery_error: Mapped[str | None] = mapped_column(String(512), nullable=True)

    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    #: Whether the hotspot is on this authority's ground, or its likeliest source
    #: is. Existing alerts are all local, which the server default records.
    kind: Mapped[AlertKind] = mapped_column(
        SqlEnum(AlertKind, name="alert_kind", native_enum=True, values_callable=_enum_values),
        nullable=False,
        default=AlertKind.LOCAL,
        server_default=AlertKind.LOCAL.value,
    )
    #: For a coordination request: the source this authority is asked to check,
    #: and how plausible attribution judged it. Null on a local alert.
    source_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    hotspot: Mapped[Hotspot] = relationship(back_populates="alerts")

    __table_args__ = (
        # One open alert per hotspot per authority: a multi-hour event must not
        # produce an alert every detection interval, or the console becomes
        # unusable and the alerts stop being read at all.
        UniqueConstraint("hotspot_id", "authority_id", name="uq_alert_hotspot_authority"),
        Index("ix_alerts_status", "status"),
    )


class CitizenReport(Base):
    """A photograph submitted by a member of the public, and what it yielded.

    The haze index is stored; a derived concentration is not. The conversion is a
    model output fitted from co-located pairs and it changes whenever the fit is
    rebuilt, so storing a concentration would freeze one version of the relation
    into the record and make a published figure impossible to reproduce. The same
    reasoning as calibrated station readings, applied to a weaker measurement.

    ``reference_value`` is the concentration a nearby monitor reported at the
    time, when one was in range. That pairing is what the calibration is fitted
    from, which makes early submissions near stations the thing that eventually
    lets a submission far from any station mean something.
    """

    __tablename__ = "citizen_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geom: Mapped[str] = _point_column()
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)

    #: When the photograph was taken, not when it was uploaded.
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: Opaque per-device identifier, used for rate limiting and trust. Not a
    #: user account: this tier is anonymous, and a device that submits nonsense
    #: needs to stop counting without anyone being identified.
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    haze_index: Mapped[float] = mapped_column(Float, nullable=False)
    transmission: Mapped[float] = mapped_column(Float, nullable=False)
    mean_luminance: Mapped[float] = mapped_column(Float, nullable=False)
    sharpness: Mapped[float] = mapped_column(Float, nullable=False)

    #: Nearest reference station at submission time, when one was within range.
    reference_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True
    )
    reference_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: Confidence this device's submissions carry, decayed when a submission
    #: disagrees with the surrounding network.
    trust_score: Mapped[float] = mapped_column(Float, nullable=False)

    #: What the resident says they saw, when they said. Optional: a photograph
    #: taken only to measure haze is still a contribution.
    category: Mapped[ComplaintCategory | None] = _complaint_category_column()
    description: Mapped[str | None] = mapped_column(
        String(COMPLAINT_DESCRIPTION_MAX_LENGTH), nullable=True
    )

    extra: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        CheckConstraint("haze_index >= 0 AND haze_index <= 1", name="ck_citizen_haze_range"),
        CheckConstraint("trust_score >= 0 AND trust_score <= 1", name="ck_citizen_trust_range"),
        Index("ix_citizen_reports_captured", "captured_at"),
        Index("ix_citizen_reports_geom", "geom", postgresql_using="gist"),
    )


class CitizenSensorReading(Base):
    """A reading a member of the public took from their own low-cost sensor.

    Stored as reported and never corrected. A household optical sensor over-reads
    in humid air by an amount that varies by model and by day, so any correction
    applied at storage would be a guess frozen into the record. The comparison
    with the nearest reference monitor is stored instead, which is the evidence
    a correction would eventually be fitted from.

    Kept apart from ``measurements``: those are stations with a fixed identity and
    a history, and every analysis query filters them to the reference tier. A
    reading here is a single anonymous observation that must never reach
    detection, fusion or forecasting by accident.
    """

    __tablename__ = "citizen_sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    geom: Mapped[str] = _point_column()
    h3_cell: Mapped[str] = mapped_column(String(H3_INDEX_LENGTH), nullable=False, index=True)

    #: When the sensor measured, not when the reading was submitted.
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    #: Opaque per-device identifier, for rate limiting. Not an account.
    device_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    #: What the submitter says the instrument is, free text ("AirGradient ONE").
    sensor_model: Mapped[str] = mapped_column(String(80), nullable=False)

    pollutant: Mapped[Pollutant] = mapped_column(
        SqlEnum(Pollutant, name="pollutant", create_type=False, values_callable=_enum_values),
        nullable=False,
    )
    #: As reported, in ug/m3.
    value: Mapped[float] = mapped_column(Float, nullable=False)

    #: Nearest reference monitor reading in space and time, when one was in range.
    reference_station_id: Mapped[int | None] = mapped_column(
        ForeignKey("stations.id", ondelete="SET NULL"), nullable=True
    )
    reference_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reference_distance_m: Mapped[float | None] = mapped_column(Float, nullable=True)

    #: What the resident says they saw, when they said.
    category: Mapped[ComplaintCategory | None] = _complaint_category_column()
    description: Mapped[str | None] = mapped_column(
        String(COMPLAINT_DESCRIPTION_MAX_LENGTH), nullable=True
    )

    __table_args__ = (
        CheckConstraint("value >= 0", name="ck_citizen_sensor_value_non_negative"),
        Index("ix_citizen_sensor_readings_observed", "observed_at"),
        Index("ix_citizen_sensor_readings_geom", "geom", postgresql_using="gist"),
    )


class VoiceGuideClip(Base):
    """Synthesised speech for one paragraph of the voice guide.

    Stored so each paragraph is paid for once, not once per listener: the guide
    is fixed text, so the same words in the same voice always produce the same
    clip. The key is a hash of everything that shapes the audio -- the words, the
    language, the voice, the model and its settings -- so an edited paragraph
    gets a new clip and the old one simply stops being asked for.
    """

    __tablename__ = "voice_guide_clips"

    #: SHA-256 of the synthesis inputs, in hex.
    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: ISO 639-1 guide language, kept so stale clips can be found and pruned.
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    model: Mapped[str] = mapped_column(String(32), nullable=False)
    speaker: Mapped[str] = mapped_column(String(32), nullable=False)
    audio: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertBrief(Base):
    """A plain-language brief for one alert, written by Google Gemini.

    Stored once written, so an alert is summarised once rather than on every
    view, and every reader sees the same words. Only a brief whose figures all
    appear in the alert's own facts is ever stored.
    """

    __tablename__ = "alert_briefs"

    alert_id: Mapped[int] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), primary_key=True
    )
    summary: Mapped[str] = mapped_column(String(GEMINI_BRIEF_MAX_CHARS), nullable=False)
    suggested_action: Mapped[str] = mapped_column(String(GEMINI_ACTION_MAX_CHARS), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
