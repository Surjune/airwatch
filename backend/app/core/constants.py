"""Every threshold, weight, hyperparameter and physical constant used by AirWatch.

A bare numeric literal anywhere in `services/`, `ml/` or `repositories/` is a review
failure. Each constant below carries the source or the reasoning behind its value.
"""

from __future__ import annotations

from typing import Final

# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

#: Seed for every stochastic component (model training, FL client sampling,
#: train/test splits). Fixed so a re-run reproduces a published number exactly.
RANDOM_SEED: Final[int] = 20260907


# ---------------------------------------------------------------------------
# Spatial grid
# ---------------------------------------------------------------------------

#: Mean Earth radius in metres (IUGG mean radius R1). Used for haversine distance
#: and for stepping a parcel along a back-trajectory. Sufficient for the few-km
#: distances AirWatch works over; a full ellipsoidal model would change results
#: by far less than the wind-field uncertainty already present.
EARTH_MEAN_RADIUS_M: Final[float] = 6_371_008.8

#: H3 resolution for the canonical analysis grid. Resolution 8 averages
#: ~0.46 km^2 per cell (~0.46 km edge), which is the scale at which a kiln,
#: a landfill fire or an arterial road is a distinguishable source. Every
#: layer -- fusion, hotspots, forecasts, federated features, interop exchange --
#: is keyed on this resolution; cross-city model sharing is only coherent if
#: every node uses the same grid.
H3_RESOLUTION: Final[int] = 8

#: Coarser resolution used only for map rendering when the viewport is zoomed
#: out far enough that r8 hexes would be sub-pixel.
H3_RESOLUTION_OVERVIEW: Final[int] = 6

#: WGS84. All geometry is stored in this CRS, always in (longitude, latitude).
SRID_WGS84: Final[int] = 4326

#: Bounding box of India including its island territories, as
#: (min_lon, min_lat, max_lon, max_lat). Used to catch transposed coordinates at
#: ingestion. A plain WGS84 range check cannot do this: swapping Delhi's
#: (77.21, 28.61) yields latitude 77.21, which is a legal latitude, so the pair
#: passes a range check and silently lands the station in Kazakhstan. Only a
#: regional bound catches it.
INDIA_BBOX: Final[tuple[float, float, float, float]] = (68.0, 6.0, 97.5, 37.5)


# ---------------------------------------------------------------------------
# CPCB National Air Quality Index
# ---------------------------------------------------------------------------
# Breakpoints from the CPCB National AQI methodology (CPCB, 2014). Each entry is
# (concentration_low, concentration_high, index_low, index_high) and the
# sub-index is linearly interpolated within the band. The reported AQI is the
# maximum sub-index across pollutants.
#
# Averaging periods differ per pollutant and are enforced in core/aqi.py:
#   PM2.5, PM10, NO2, SO2, NH3, Pb -> 24 hours
#   O3, CO                         -> 8 hours (rolling maximum)

AQIBreakpoint = tuple[float, float, float, float]

#: PM2.5 in ug/m^3, 24-hour average.
AQI_BREAKPOINTS_PM25: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 30.0, 0.0, 50.0),
    (30.0, 60.0, 51.0, 100.0),
    (60.0, 90.0, 101.0, 200.0),
    (90.0, 120.0, 201.0, 300.0),
    (120.0, 250.0, 301.0, 400.0),
    (250.0, 500.0, 401.0, 500.0),
)

#: PM10 in ug/m^3, 24-hour average.
AQI_BREAKPOINTS_PM10: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 50.0, 0.0, 50.0),
    (50.0, 100.0, 51.0, 100.0),
    (100.0, 250.0, 101.0, 200.0),
    (250.0, 350.0, 201.0, 300.0),
    (350.0, 430.0, 301.0, 400.0),
    (430.0, 600.0, 401.0, 500.0),
)

#: NO2 in ug/m^3, 24-hour average.
AQI_BREAKPOINTS_NO2: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 40.0, 0.0, 50.0),
    (40.0, 80.0, 51.0, 100.0),
    (80.0, 180.0, 101.0, 200.0),
    (180.0, 280.0, 201.0, 300.0),
    (280.0, 400.0, 301.0, 400.0),
    (400.0, 1000.0, 401.0, 500.0),
)

#: SO2 in ug/m^3, 24-hour average.
AQI_BREAKPOINTS_SO2: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 40.0, 0.0, 50.0),
    (40.0, 80.0, 51.0, 100.0),
    (80.0, 380.0, 101.0, 200.0),
    (380.0, 800.0, 201.0, 300.0),
    (800.0, 1600.0, 301.0, 400.0),
    (1600.0, 2400.0, 401.0, 500.0),
)

#: O3 in ug/m^3, 8-hour rolling maximum.
AQI_BREAKPOINTS_O3: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 50.0, 0.0, 50.0),
    (50.0, 100.0, 51.0, 100.0),
    (100.0, 168.0, 101.0, 200.0),
    (168.0, 208.0, 201.0, 300.0),
    (208.0, 748.0, 301.0, 400.0),
    (748.0, 1000.0, 401.0, 500.0),
)

#: CO in mg/m^3 (note: milligrams, unlike every other pollutant), 8-hour rolling
#: maximum. The unit difference is a common source of error and is converted
#: explicitly at the ingestion boundary.
AQI_BREAKPOINTS_CO: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 1.0, 0.0, 50.0),
    (1.0, 2.0, 51.0, 100.0),
    (2.0, 10.0, 101.0, 200.0),
    (10.0, 17.0, 201.0, 300.0),
    (17.0, 34.0, 301.0, 400.0),
    (34.0, 50.0, 401.0, 500.0),
)

#: NH3 in ug/m^3, 24-hour average.
AQI_BREAKPOINTS_NH3: Final[tuple[AQIBreakpoint, ...]] = (
    (0.0, 200.0, 0.0, 50.0),
    (200.0, 400.0, 51.0, 100.0),
    (400.0, 800.0, 101.0, 200.0),
    (800.0, 1200.0, 201.0, 300.0),
    (1200.0, 1800.0, 301.0, 400.0),
    (1800.0, 2400.0, 401.0, 500.0),
)

#: AQI category lower bounds, CPCB naming. Used for colour scales and advisories.
AQI_CATEGORY_BOUNDS: Final[tuple[tuple[float, str], ...]] = (
    (0.0, "Good"),
    (51.0, "Satisfactory"),
    (101.0, "Moderate"),
    (201.0, "Poor"),
    (301.0, "Very Poor"),
    (401.0, "Severe"),
)

#: The index is not defined above this value; concentrations beyond the top
#: breakpoint are clamped here and flagged.
AQI_MAX: Final[float] = 500.0

#: Micrograms in a milligram. Needed because OpenAQ reports CO in ug/m^3 while
#: the CPCB AQI breakpoint table for CO is in mg/m^3. Applying the table to an
#: unconverted value understates the CO sub-index by a factor of 1000, which
#: would silently erase a genuine CO episode.
MICROGRAMS_PER_MILLIGRAM: Final[float] = 1000.0

#: Molar volume of an ideal gas in litres per mole at the CPCB reference
#: condition (25 degrees C, 1013.25 hPa). Gaseous pollutants reported as a
#: mixing ratio must be converted to a mass concentration before the CPCB
#: breakpoint tables apply.
MOLAR_VOLUME_L_PER_MOL: Final[float] = 24.45

#: Molar masses in grams per mole, for the mixing-ratio conversion
#: ug/m3 = ppb * molar_mass / molar_volume. Particulates are absent by design:
#: PM2.5 and PM10 are mixtures of solids with no single molar mass, so a ppb
#: figure for them is meaningless rather than merely inconvenient.
MOLAR_MASS_G_PER_MOL: Final[dict[str, float]] = {
    "no2": 46.0055,
    "so2": 64.066,
    "o3": 47.998,
    "co": 28.010,
    "nh3": 17.031,
}

#: Parts per billion in one part per million.
PPB_PER_PPM: Final[float] = 1000.0

#: WHO 2021 global air quality guideline, PM2.5 24-hour mean, in ug/m^3. Shown
#: alongside the CPCB category because the Indian standard (60) is 4x higher and
#: the gap matters for honest public communication.
WHO_PM25_24H_GUIDELINE: Final[float] = 15.0

#: CPCB National Ambient Air Quality Standard, PM2.5 24-hour mean, in ug/m^3.
CPCB_PM25_24H_STANDARD: Final[float] = 60.0


# ---------------------------------------------------------------------------
# Sensor tiers and calibration
# ---------------------------------------------------------------------------

#: Minimum number of paired (sensor, reference) hourly observations before a
#: per-sensor calibration model is trained. Below this the global fallback model
#: is used instead. Indian colocation studies typically train on multi-week
#: windows; 336 hours is two full weeks, enough to span a diurnal and a weekly
#: cycle without waiting for a seasonal one.
CALIBRATION_MIN_PAIRED_HOURS: Final[int] = 336

#: A low-cost sensor is treated as colocated with a reference station when it is
#: within this distance, in metres. Beyond it the pairing is no longer a
#: like-for-like comparison of the same air mass.
CALIBRATION_COLOCATION_RADIUS_M: Final[float] = 500.0

#: Fraction of the paired record held out, chronologically, to report honest
#: before/after calibration error. Chronological rather than random because a
#: random split leaks future information through autocorrelation.
CALIBRATION_HOLDOUT_FRACTION: Final[float] = 0.25

#: Relative humidity above which uncorrected optical particle counters
#: systematically over-read, because water uptake swells the particles they
#: size. This is the dominant low-cost sensor bias in the Indian monsoon and is
#: why RH is a mandatory calibration feature rather than an optional one.
HYGROSCOPIC_GROWTH_RH_THRESHOLD_PCT: Final[float] = 70.0


# ---------------------------------------------------------------------------
# Fusion
# ---------------------------------------------------------------------------

#: Inverse-distance weighting exponent for aggregating calibrated sensor values
#: into a cell. 2.0 is the standard choice and matches the inverse-square
#: dilution of a point source in the absence of a modelled wind field.
IDW_POWER: Final[float] = 2.0

#: Sensors beyond this distance from a cell centroid, in metres, contribute
#: nothing to it. Roughly 5 km: past this an urban PM2.5 field decorrelates
#: enough that a reading is no longer evidence about the cell.
FUSION_MAX_SENSOR_DISTANCE_M: Final[float] = 5000.0

#: A cell with no sensor inside FUSION_MAX_SENSOR_DISTANCE_M falls back to
#: satellite and meteorology only. Its uncertainty is multiplied by this factor
#: so the UI can never present an unsupported estimate as a confident one.
FUSION_NO_SENSOR_UNCERTAINTY_MULTIPLIER: Final[float] = 2.5


# ---------------------------------------------------------------------------
# Hotspot detection
# ---------------------------------------------------------------------------
# A hotspot is an anomaly against the locally expected baseline, not a breach of
# a national threshold. 40 ug/m^3 in a clean southern city is an event; the same
# reading in Delhi in November is unremarkable. This is what "hidden" means.

#: Standardised residual above which a cell is a hotspot candidate. 3.0 is the
#: conventional three-sigma outlier bound, giving ~0.13% false positives on a
#: normal residual distribution before the persistence and contiguity filters.
HOTSPOT_ZSCORE_THRESHOLD: Final[float] = 3.0

#: Consecutive hourly intervals a candidate must persist before it is confirmed.
#: Two hours filters single-frame sensor glitches while still catching a short
#: waste-burning event.
HOTSPOT_MIN_PERSISTENCE_INTERVALS: Final[int] = 2

#: Contiguous candidate cells required. A real plume covers more than one r8 hex
#: (~0.46 km^2); a lone flagged cell is far more likely to be a faulty sensor.
HOTSPOT_MIN_CONTIGUOUS_CELLS: Final[int] = 2

#: Days of history used to build the per-cell, per-hour-of-week baseline.
#: 28 days spans four occurrences of each hour-of-week slot.
HOTSPOT_BASELINE_WINDOW_DAYS: Final[int] = 28

#: Minimum baseline observations for a cell before anomaly detection may run
#: there. Below this the baseline variance is too poorly estimated to trust.
HOTSPOT_BASELINE_MIN_OBSERVATIONS: Final[int] = 8


# ---------------------------------------------------------------------------
# Source attribution
# ---------------------------------------------------------------------------

#: How far back the Lagrangian trajectory is stepped, in hours. Beyond ~6 hours
#: a single-layer wind field accumulates too much error to name a source
#: responsibly.
ATTRIBUTION_MAX_BACKTRACK_HOURS: Final[int] = 6

#: Integration step for the back-trajectory, in minutes. Smaller steps track
#: curvature in the wind field; 15 minutes is well below the hourly resolution
#: of the wind input, so it is not the limiting error term.
ATTRIBUTION_STEP_MINUTES: Final[int] = 15

#: Half-angle of the probability cone at the hotspot, in degrees, widening with
#: backtrack distance. Represents horizontal dispersion plus wind-direction
#: uncertainty; 15 degrees is a standard Gaussian-plume opening for neutral
#: stability.
ATTRIBUTION_CONE_HALF_ANGLE_DEG: Final[float] = 15.0

#: Additional cone widening per hour of backtracking, in degrees, to reflect
#: compounding wind-field error the further back the trajectory runs.
ATTRIBUTION_CONE_WIDENING_DEG_PER_HOUR: Final[float] = 5.0

#: A FIRMS fire detection is considered for attribution only if it occurred
#: within this many hours before the hotspot. Smoke from an older fire has
#: usually dispersed or moved beyond the traceable window.
ATTRIBUTION_FIRE_LOOKBACK_HOURS: Final[int] = 12

#: Candidates scoring below this confidence are not surfaced at all. An
#: enforcement action against the wrong operator is worse than no name, so the
#: floor is deliberately high.
ATTRIBUTION_MIN_CONFIDENCE: Final[float] = 0.35

#: Maximum ranked candidates returned for a hotspot. The UI shows all of them
#: with confidences; it never presents the top one as established fact.
ATTRIBUTION_MAX_CANDIDATES: Final[int] = 5


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

#: Forecast horizons in hours. One model per horizon, as direct multi-horizon
#: regression avoids the error compounding of recursive one-step forecasting.
FORECAST_HORIZONS_HOURS: Final[tuple[int, ...]] = (24, 48, 72)

#: Longest horizon, used for validation bounds and API parameter limits.
FORECAST_MAX_HORIZON_HOURS: Final[int] = 72

#: Lagged observations fed to the forecast model, in hours. Covers the previous
#: hour, the previous day at the same hour, and the previous week at the same
#: hour, so the model sees the diurnal and weekly cycles directly.
FORECAST_LAG_HOURS: Final[tuple[int, ...]] = (1, 2, 3, 6, 12, 24, 48, 168)

#: Spacing of sample points along a corridor polyline, in metres, when
#: aggregating cells for the corridor view.
CORRIDOR_SAMPLE_SPACING_M: Final[float] = 2000.0


# ---------------------------------------------------------------------------
# Federated learning
# ---------------------------------------------------------------------------

#: Federated rounds per training cycle.
FL_NUM_ROUNDS: Final[int] = 10

#: Minimum participating city nodes before aggregation proceeds. Two nodes is
#: the smallest number for which averaging means anything.
FL_MIN_AVAILABLE_CLIENTS: Final[int] = 2

#: FedProx proximal term. Constrains local updates from drifting far from the
#: global model, which is what keeps a heavily non-IID node -- Delhi in
#: November against Coimbatore in June -- from destabilising aggregation.
#: 0.0 reduces the strategy to plain FedAvg.
FL_PROXIMAL_MU: Final[float] = 0.01

#: Gaussian noise multiplier for optional differential privacy on shared
#: weights. Off by default: it costs accuracy, and the weights-not-data design
#: already removes the raw-data disclosure that blocks inter-state sharing.
FL_DP_NOISE_MULTIPLIER: Final[float] = 0.0

#: A round is rejected if the aggregated model is worse than the previous global
#: model on a node's held-out set by more than this fraction. Guards against
#: negative transfer, so the federation claim stays honest.
FL_NEGATIVE_TRANSFER_TOLERANCE: Final[float] = 0.02


# ---------------------------------------------------------------------------
# External clients
# ---------------------------------------------------------------------------

#: OpenAQ v3 API root. Serves CPCB and state-board stations for India, which is
#: why it is the primary reference-tier source rather than a supplement.
OPENAQ_BASE_URL: Final[str] = "https://api.openaq.org/v3"

#: Open-Meteo API root. Needs no credential, which is why it is the
#: meteorological backbone rather than an optional extra.
OPENMETEO_BASE_URL: Final[str] = "https://api.open-meteo.com/v1"

#: Hourly variables requested from Open-Meteo. boundary_layer_height is the one
#: that matters most and is easy to overlook: a shallow nocturnal boundary layer
#: traps emissions in a fraction of the volume, so the same emission rate
#: produces a far higher concentration. Without it, winter-night spikes look
#: like new sources rather than the same sources in a smaller box.
OPENMETEO_HOURLY_VARIABLES: Final[tuple[str, ...]] = (
    "temperature_2m",
    "relative_humidity_2m",
    "wind_speed_10m",
    "wind_direction_10m",
    "boundary_layer_height",
    "precipitation",
)

#: Open-Meteo defaults wind speed to km/h. AirWatch stores m/s, and the request
#: asks for m/s explicitly rather than converting after the fact -- a silent 3.6x
#: error in the wind field would misplace every back-trajectory.
OPENMETEO_WIND_SPEED_UNIT: Final[str] = "ms"

#: Largest forecast horizon Open-Meteo serves, in days.
OPENMETEO_MAX_FORECAST_DAYS: Final[int] = 16

#: NASA FIRMS API root. The active-fire product is served as CSV, not JSON.
FIRMS_BASE_URL: Final[str] = "https://firms.modaps.eosdis.nasa.gov/api"

#: FIRMS active-fire source. VIIRS on Suomi-NPP resolves fires at 375 m, against
#: MODIS at 1 km, which matters because a single stubble field is well under a
#: MODIS pixel.
FIRMS_DEFAULT_SOURCE: Final[str] = "VIIRS_SNPP_NRT"

#: Largest day range the FIRMS area endpoint accepts in one request. Verified
#: against the live API, which rejects 6 or more with "Invalid day range.
#: Expects [1..5]" -- some documentation still says 10.
FIRMS_MAX_DAY_RANGE: Final[int] = 5

#: VIIRS confidence classes mapped to a numeric score. VIIRS reports letters
#: (low/nominal/high) while MODIS reports 0-100, so both are normalised to a
#: fraction for attribution scoring.
FIRMS_CONFIDENCE_SCORES: Final[dict[str, float]] = {
    "l": 0.25,
    "n": 0.65,
    "h": 0.95,
}

#: Fire radiative power, in megawatts, below which a detection is treated as too
#: weak to be a plausible plume source. Small agricultural fires do sit near this
#: floor, so it is deliberately low: missing a stubble fire is worse than
#: carrying a few weak detections into the attribution cone.
FIRMS_MIN_FRP_MW: Final[float] = 1.0

#: Largest radius OpenAQ accepts on a coordinates query, in metres.
OPENAQ_MAX_RADIUS_M: Final[int] = 25_000

#: Largest page size OpenAQ accepts.
OPENAQ_MAX_PAGE_LIMIT: Final[int] = 1000

#: A station whose most recent reading is older than this is treated as dormant
#: and excluded from ingestion. Delhi has stations last seen in 2018 sitting
#: alongside live ones; including them would silently dilute the fused surface
#: with decade-old air.
STATION_STALE_AFTER_DAYS: Final[int] = 7


#: Per-request timeout for upstream APIs, in seconds.
HTTP_TIMEOUT_SECONDS: Final[float] = 30.0

#: Retry attempts for a failed upstream call, including the first attempt.
HTTP_MAX_ATTEMPTS: Final[int] = 3

#: Exponential backoff base, in seconds: waits 1s, 2s, 4s between attempts.
HTTP_BACKOFF_BASE_SECONDS: Final[float] = 1.0

#: Cache lifetime for upstream responses, in seconds. One hour matches the
#: native reporting cadence of CPCB and OpenAQ, so a shorter TTL would only add
#: load without adding information.
UPSTREAM_CACHE_TTL_SECONDS: Final[int] = 3600

#: Cache lifetime for meteorological forecasts, in seconds. Open-Meteo refreshes
#: its forecast roughly every three hours.
FORECAST_CACHE_TTL_SECONDS: Final[int] = 10800


# ---------------------------------------------------------------------------
# Citizen reports
# ---------------------------------------------------------------------------

#: Maximum accepted photo upload size, in bytes.
CITIZEN_PHOTO_MAX_BYTES: Final[int] = 10 * 1024 * 1024

#: Reports accepted per device per hour, limiting flooding of the trust system.
CITIZEN_REPORTS_PER_DEVICE_PER_HOUR: Final[int] = 10

#: Starting trust score for a new device.
CITIZEN_INITIAL_TRUST_SCORE: Final[float] = 0.5

#: Trust below which a report is stored but excluded from fusion.
CITIZEN_MIN_TRUST_FOR_FUSION: Final[float] = 0.3

#: A photo-derived PM2.5 estimate is a proxy with wide error bars, so it enters
#: fusion at this weight relative to a calibrated low-cost sensor reading.
CITIZEN_PHOTO_FUSION_WEIGHT: Final[float] = 0.2


# ---------------------------------------------------------------------------
# Alerting
# ---------------------------------------------------------------------------

#: Hours an authority has to acknowledge an alert before it escalates.
ALERT_ACK_SLA_HOURS: Final[int] = 2

#: Hours to resolve an acknowledged alert before it escalates.
ALERT_RESOLUTION_SLA_HOURS: Final[int] = 24

#: Suppression window, in hours, preventing repeat alerts for the same cell and
#: source while an alert is already open. Without it a multi-hour fire produces
#: an alert every detection interval and the console becomes unusable.
ALERT_SUPPRESSION_HOURS: Final[int] = 6


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

#: Requests permitted per IP per minute. v1 is anonymous, so this is the only
#: thing standing between the API and a scraper.
RATE_LIMIT_REQUESTS_PER_MINUTE: Final[int] = 120

#: Maximum cells returned by a single grid query, bounding response size.
MAX_GRID_CELLS_PER_REQUEST: Final[int] = 5000

#: Header carrying the correlation ID bound to every log line for a request.
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
