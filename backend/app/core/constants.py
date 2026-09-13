"""Every threshold, weight, hyperparameter and physical constant used by AirWatch.

A bare numeric literal anywhere in `services/`, `ml/` or `repositories/` is a review
failure. Each constant below carries the source or the reasoning behind its value.
"""

from __future__ import annotations

from datetime import UTC, datetime
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

#: Range, per pollutant, outside which a stored concentration is flagged rather
#: than published. Values are in the unit each AQI table expects (mg/m^3 for CO,
#: ug/m^3 for everything else), inclusive at both ends. The bounds are ceilings
#: on what ambient air can hold, not on what is unhealthy: a reading of 700 PM2.5
#: in a Delhi November is terrible and real, and must never be filtered.
#:
#: * PM2.5, 1000: the default range of the beta-attenuation monitors common in the
#:   CAAQMS network; a larger value is saturation or a unit error.
#: * PM10, 2000: dust storms over the Indo-Gangetic plain carry hourly PM10 above
#:   1000, so the ceiling sits well clear of them.
#: * Gases: the top of each CPCB breakpoint table, far beyond any recorded ambient
#:   hourly value.
#: * CO floor, 0.05 mg/m^3 (about 44 ppb): below the cleanest remote-background CO
#:   on Earth, so an urban reading under it is a unit error. It exists for the
#:   failure actually observed: Delhi stations reporting ppm while declaring ppb,
#:   which lands every value a factor of 1000 too low and entirely below this.
#:
#: Zero is allowed for the others: a clean hour can read at the detection limit.
PLAUSIBLE_CONCENTRATION_RANGE: Final[dict[str, tuple[float, float]]] = {
    "pm25": (0.0, 1000.0),
    "pm10": (0.0, 2000.0),
    "no2": (0.0, 1000.0),
    "so2": (0.0, 2400.0),
    "o3": (0.0, 1000.0),
    "nh3": (0.0, 2400.0),
    "co": (0.05, 50.0),
}


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

#: Neighbours used for the local mean and spread features. Three is enough to
#: describe the immediate neighbourhood without reaching across a city whose
#: districts have genuinely different air.
FUSION_NEAREST_K: Final[int] = 3

#: Fewest neighbouring stations required before a cell can be estimated at all.
#: Below this the estimate is an extrapolation from one or two points, and
#: reporting it with the same confidence as a well-supported cell would be the
#: exact overclaiming this project exists to remove.
FUSION_MIN_NEIGHBOURS: Final[int] = 3

#: Radii, in metres, at which neighbouring stations are counted. Station density
#: is itself a feature: a cell surrounded by monitors is far better constrained
#: than one on the edge of the network, and the model should be able to tell.
#:
#: Both radii must sit strictly inside FUSION_MAX_SENSOR_DISTANCE_M. An earlier
#: pairing of 5 km and 10 km against a 5 km cutoff made the two counts
#: identical by construction -- a feature that looked informative and carried no
#: information at all.
FUSION_DENSITY_RADII_M: Final[tuple[float, ...]] = (2000.0, 5000.0)

#: Hours in a day and days in a week, for the cyclical time encoding. Encoded as
#: sine and cosine pairs so that hour 23 and hour 0 are adjacent, which a raw
#: integer would place maximally far apart.
HOURS_PER_DAY: Final[int] = 24

#: Distances are stored in metres and presented in kilometres.
METRES_PER_KILOMETRE: Final[float] = 1000.0
DAYS_PER_WEEK: Final[int] = 7

#: Uncertainty of a fused estimate, in ug/m3, before any local penalty. Fitted
#: to the leave-one-station-out run: cells whose three nearest stations agree
#: closely still carry a mean absolute error near 10 ug/m3, because Delhi PM2.5
#: is genuinely hyperlocal and neighbours explain under a quarter of the
#: variance at an unmonitored point.
FUSION_BASE_UNCERTAINTY_UGM3: Final[float] = 9.5

#: Additional uncertainty per ug/m3 of disagreement among the nearest stations.
#: Measured, not assumed: observed error rose from 9.9 to 24.5 ug/m3 as
#: neighbour spread went from under 5 to over 30. Disagreement between monitors
#: is the single best available warning that an estimate is unreliable.
FUSION_SPREAD_UNCERTAINTY_COEFFICIENT: Final[float] = 0.4

#: Additional uncertainty per kilometre to the nearest station. Small because
#: Delhi's network is dense enough that distance varied little across the
#: validation set; it matters far more in a sparsely monitored city.
FUSION_DISTANCE_UNCERTAINTY_PER_KM: Final[float] = 0.35


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

#: Radius, in metres, within which a source needs no transport to explain a
#: hotspot. Delhi hotspots are frequently detected at wind speeds under 2 m/s,
#: where a plume moves only a few kilometres an hour and the excess is simply
#: the source the monitor is standing next to. Requiring every candidate to lie
#: upwind makes exactly these -- a bus terminal, a landfill across the road --
#: permanently invisible, which is the opposite of the intended behaviour.
ATTRIBUTION_LOCAL_SOURCE_RADIUS_M: Final[float] = 2000.0

#: Distance, in metres, over which a candidate's plausibility halves. A source
#: sitting in the trajectory's path but 20 km upwind is a far weaker explanation
#: than one 2 km upwind, because dispersion has had far longer to dilute it.
ATTRIBUTION_DISTANCE_HALF_LIFE_M: Final[float] = 5000.0

#: Emission prior for a satellite fire detection of average radiative power,
#: used to put fires on the same scale as registry sources. A fire is an
#: observed, actively-emitting event rather than a facility that may or may not
#: be running, so it starts higher.
ATTRIBUTION_FIRE_BASE_PRIOR: Final[float] = 1.5

#: Fire radiative power, in megawatts, at which a detection reaches twice the
#: base prior. Keeps a large landfill blaze ranked above a small field fire
#: without letting radiative power dominate the geometry.
ATTRIBUTION_FIRE_REFERENCE_FRP_MW: Final[float] = 20.0

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

#: Lags used when the record is too short to carry a weekly term. The 168-hour
#: lag is the most informative single feature for urban PM2.5 -- traffic repeats
#: weekly -- but requiring it discards the first seven days of a fourteen-day
#: record, halving the training set to buy one feature. Below roughly a month of
#: history this set is the better trade.
FORECAST_LAG_HOURS_SHORT: Final[tuple[int, ...]] = (1, 2, 3, 6, 12, 24, 48)

#: Fraction of the record held out for testing, taken from the end rather than
#: sampled at random. A random split would put hours from the same afternoon on
#: both sides, and autocorrelation would let the model read the answer off its
#: neighbours -- producing an excellent score that says nothing about
#: forecasting anything.
FORECAST_TEST_FRACTION: Final[float] = 0.25

#: Fewest observations a station needs before its diurnal climatology is used.
#: Below this the hourly means are dominated by which few days happened to be
#: observed rather than by the daily cycle they are meant to describe.
FORECAST_MIN_CLIMATOLOGY_OBSERVATIONS: Final[int] = 48

#: Expected absolute error of a climatological forecast, in ug/m3, at the
#: shortest horizon. Measured on a temporal holdout rather than assumed: 15.6 at
#: 24 hours, 16.5 at 48, 15.8 at 72. Published alongside every forecast, because
#: a 24-hour outlook stated without it invites planning against a number that is
#: routinely a whole AQI band out.
FORECAST_BASE_UNCERTAINTY_UGM3: Final[float] = 15.6

#: Additional expected error per 24 hours of horizon. Small, because the
#: measured error barely grows with lead time -- the diurnal cycle a
#: climatological forecast relies on is just as predictable three days out as
#: one, which is precisely why it beat the learned models.
FORECAST_UNCERTAINTY_PER_DAY_UGM3: Final[float] = 0.5

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

#: Observations after this instant are excluded from every validation run.
#:
#: Without a cutoff the experiments read the whole database, and the scheduled
#: worker adds to it every hour, so every published figure would drift silently
#: between one run and the next -- LightGBM's LOSO error had already moved from
#: 12.84 to 12.44 before this was pinned. A result that changes when re-run with
#: no change to the method is not reproducible, so the recorded window is fixed.
#: It is the instant before the worker began collecting.
VALIDATION_DATA_UNTIL: Final[datetime] = datetime(2026, 9, 12, tzinfo=UTC)

#: Resamples for a bootstrap interval on a model comparison. Ten thousand keeps
#: the interval endpoints stable to about two decimal places, finer than any
#: difference worth reporting.
BOOTSTRAP_RESAMPLES: Final[int] = 10_000

#: Two-sided coverage of a reported bootstrap interval.
BOOTSTRAP_CONFIDENCE: Final[float] = 0.95

#: Relative difference below which two models are treated as equivalent even
#: when the interval excludes zero. On thousands of rows a 0.5% difference can be
#: statistically certain and still change nothing anyone should do.
MODEL_COMPARISON_TOLERANCE: Final[float] = 0.02

#: Local steps a node takes when personalising the global model. Equal to one
#: round of local training: enough to move toward the node's own regime, few
#: enough that a node with a few dozen rows is not simply retraining from the
#: federated start point into a local-only model.
FL_FINE_TUNE_EPOCHS: Final[int] = 30

#: Local gradient steps per round. Enough for a node's update to carry its data,
#: few enough that ten rounds still leave the average in charge rather than each
#: node converging alone between aggregations.
FL_LOCAL_EPOCHS: Final[int] = 30

#: Gradient-descent step size on standardised features. Stable for a ridge
#: objective whose features have unit variance by construction.
FL_LEARNING_RATE: Final[float] = 0.05

#: Ridge penalty on node models. Small: it keeps weights finite on a node whose
#: lag features are nearly collinear, without shrinking the climatology signal.
FL_L2: Final[float] = 0.01

#: Distance, in metres, within which a station belongs to a federated node.
#: Wider than PILOT_CITY_RADIUS_M, which scopes live coverage counts, because the
#: federated task needs every usable series around a city; the published transfer
#: results were measured with this radius, so it is not unified with that one.
FL_NODE_RADIUS_M: Final[float] = 40_000.0

#: The single horizon the federated forecast is trained and compared at. One
#: horizon keeps the comparison between local and global models clean.
FL_HORIZON_HOURS: Final[int] = 24

#: Hours between issue times sampled from a station's history, matching the
#: forecast validation so federated and centralised results are comparable.
FL_ISSUE_STRIDE: Final[int] = 3

#: Smallest number of usable rows for a node to participate. Below it a temporal
#: split leaves a holdout too small to report anything about.
FL_MIN_NODE_ROWS: Final[int] = 20

#: How far from the target hour an observation may be and still count as the
#: outcome. Inside the 1-hour reporting cadence, so it never borrows the next hour.
FL_TARGET_MATCH_SECONDS: Final[int] = 2700

#: Where the federation server listens. Loopback by default: exposing it beyond
#: one machine is a deployment decision that needs TLS, which v1 does not set up.
FL_SERVER_ADDRESS: Final[str] = "127.0.0.1:8080"

#: How long, in seconds, the server waits for every expected node to connect
#: before giving up. Long enough to start the nodes by hand in separate terminals.
FL_NODE_WAIT_SECONDS: Final[int] = 300


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

#: Minimum share of an hour that must actually be observed before its aggregate
#: is trusted. OpenAQ builds an hourly value from whatever 15-minute samples
#: exist, so an hour can be reported from a single reading. Training on those
#: teaches the model that sparsely-sampled hours behave differently, when the
#: only real difference is how much was measured.
MIN_HOURLY_COVERAGE_PCT: Final[float] = 50.0

#: Days of history pulled per sensor when backfilling. Two weeks spans two of
#: every weekday, which is the shortest window that lets a model separate the
#: weekly traffic cycle from the daily one.
BACKFILL_DAYS: Final[int] = 14

#: Minimum gap between OpenAQ requests, in seconds. The free tier allows roughly
#: 60 requests per minute, and a Delhi run makes one call per active station --
#: 60 of them -- so an unpaced run trips the quota partway through and loses the
#: remaining stations. Pacing is cheaper than retrying against a 429.
OPENAQ_MIN_REQUEST_INTERVAL_SECONDS: Final[float] = 1.1

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


# ---------------------------------------------------------------------------
# Citizen reports
# ---------------------------------------------------------------------------

#: Maximum accepted photo upload size, in bytes.
CITIZEN_PHOTO_MAX_BYTES: Final[int] = 10 * 1024 * 1024


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

#: Tracked clients above which the limiter forgets fully refilled buckets. A
#: refilled bucket is identical to an unseen client, so the sweep changes no
#: decision; the threshold only sets how often the sweep's cost is paid.
RATE_LIMIT_SWEEP_THRESHOLD_CLIENTS: Final[int] = 10_000

#: Paths exempt from the limit. A liveness probe polled by an orchestrator must
#: never be refused, or a busy node would be restarted for being busy.
RATE_LIMIT_EXEMPT_PATHS: Final[frozenset[str]] = frozenset({"/v1/health"})

#: Longest rejected value echoed back in a validation error envelope. Repeating
#: the input helps a client see what was refused, but a request body can be
#: arbitrarily large and a response is not the place to mirror it back in full.
VALIDATION_INPUT_ECHO_MAX_CHARS: Final[int] = 200

#: Header carrying the correlation ID bound to every log line for a request.
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"


# ---------------------------------------------------------------------------
# Published model performance
# ---------------------------------------------------------------------------
# Measured figures, published to partner nodes exactly as they came out.
# A federation where nodes advertise only flattering numbers is worse than no
# federation, because a data-poor city would adopt a model that harms it and
# have no way to discover that. Sources are the validation runs in /ml.

#: Mean absolute error, ug/m3, of the shipped inverse-distance surface under
#: leave-one-station-out validation: 7,957 scored station-hours across 36 held-out
#: stations, data before VALIDATION_DATA_UNTIL. Source: `npm run ml:validate-loso`.
PUBLISHED_FUSION_MAE_UGM3: Final[float] = 11.48

#: Coefficient of determination for the same run. Low by design of the problem,
#: not of the method: even inside one of India's densest networks, neighbouring
#: stations explain under a quarter of the variance at an unmonitored point.
PUBLISHED_FUSION_R2: Final[float] = 0.233

#: What gradient boosting scored on the identical split, having also received
#: the interpolated estimate as an input feature. Its deficit against IDW,
#: -0.96 ug/m3 over a station-level interval of [-2.08, +0.06], is not established
#: as worse -- but nothing establishes it as better either, so IDW ships.
PUBLISHED_FUSION_LEARNED_MAE_UGM3: Final[float] = 12.44

#: Mean absolute error, ug/m3, of the shipped diurnal climatology at 24 hours,
#: on a temporal holdout, data before VALIDATION_DATA_UNTIL.
#: Source: `npm run ml:validate-forecast`.
PUBLISHED_FORECAST_MAE_UGM3: Final[float] = 15.24

#: The better of the two gradient-boosted framings (residual to climatology) at
#: the same horizon on the same holdout. Established as worse than climatology:
#: -1.55 ug/m3, station-level interval [-2.27, -0.67].
PUBLISHED_FORECAST_LEARNED_MAE_UGM3: Final[float] = 16.79

#: What persistence -- assuming the current value holds -- scored.
PUBLISHED_FORECAST_PERSISTENCE_MAE_UGM3: Final[float] = 21.39


# ---------------------------------------------------------------------------
# Citizen photo haze estimation
# ---------------------------------------------------------------------------
# A photograph cannot measure PM2.5. What it can measure is how much contrast
# the atmosphere has removed, and that quantity -- dimensionless, in [0, 1] --
# is what this tier produces. Turning it into a concentration needs an empirical
# relation fitted against co-located reference monitors, so the conversion only
# happens once enough pairs exist to fit one. Until then the tier reports the
# haze index and says it is uncalibrated, because an uncalibrated concentration
# derived from a photograph is a fabricated reading.

#: Local patch width, in pixels, for the dark-channel prior. He, Sun and Tang
#: (CVPR 2009) use 15x15: large enough that most patches contain a genuinely
#: dark pixel in a haze-free scene, small enough not to blur across depth edges.
HAZE_DCP_PATCH_PIXELS: Final[int] = 15

#: Fraction of haze retained when inverting the scattering model. He et al. use
#: 0.95 rather than 1.0 because a perfectly dehazed distant object looks
#: unnatural, and because some aerial perspective is a real depth cue.
HAZE_DCP_OMEGA: Final[float] = 0.95

#: Top fraction of dark-channel pixels averaged to estimate atmospheric light.
#: He et al. use the brightest 0.1%, which lands on sky or haze rather than on a
#: white object.
HAZE_ATMOSPHERIC_LIGHT_FRACTION: Final[float] = 0.001

#: Longest edge, in pixels, an image is downscaled to before analysis. The dark
#: channel is a local-minimum filter, so cost grows with pixel count while the
#: statistic itself is scale-stable; 512 keeps a phone photo under a second.
HAZE_ANALYSIS_MAX_EDGE_PIXELS: Final[int] = 512

#: Shortest edge, in pixels, an image must have to be analysed at all. Below
#: this the patch filter has too few independent patches to be meaningful.
HAZE_MIN_EDGE_PIXELS: Final[int] = 64

#: Mean luminance, 0-255, below which a photo is treated as taken in darkness.
#: The dark-channel prior assumes a lit outdoor scene; at night the dark channel
#: is low everywhere and a clear night is indistinguishable from thick haze.
HAZE_MIN_MEAN_LUMINANCE: Final[float] = 40.0

#: Mean luminance above which the frame is treated as blown out, where the prior
#: also fails because nothing in it is dark.
HAZE_MAX_MEAN_LUMINANCE: Final[float] = 240.0

#: Variance of the Laplacian below which an image is treated as out of focus.
#: Blur removes exactly the high-frequency contrast haze removes, so a blurred
#: clear photo reads as a sharp hazy one.
HAZE_MIN_LAPLACIAN_VARIANCE: Final[float] = 15.0

#: Radius, in metres, within which a citizen photo is treated as co-located with
#: a reference station for the purpose of building the calibration. Wider than
#: the fusion sensor cutoff because the pairing only has to be representative of
#: the same air mass, not of the same 0.46 km cell.
CITIZEN_COLOCATION_RADIUS_M: Final[int] = 3000

#: Co-located pairs needed before a haze index is converted to a concentration.
#: Thirty is the smallest sample from which a single-predictor fit reports an
#: error worth publishing; below it the fit's own uncertainty exceeds the signal.
CITIZEN_CALIBRATION_MIN_PAIRS: Final[int] = 30

#: How stale a photo's capture time may be and still describe current air, in
#: hours. A pollution episode lasts hours, so a photo from yesterday is a
#: photograph of different air.
CITIZEN_MAX_CAPTURE_AGE_HOURS: Final[int] = 3

#: Reports one device may submit per hour. A dense tier is only useful if it is
#: not trivially floodable by a single participant.
CITIZEN_MAX_REPORTS_PER_DEVICE_PER_HOUR: Final[int] = 6

#: Trust a new device starts with, and the floor and step of its adjustment.
#: Trust rises when a submission agrees with the surrounding network and falls
#: when it does not, so a device that consistently disagrees stops influencing
#: anything without being blocked outright.
CITIZEN_INITIAL_TRUST: Final[float] = 0.5
CITIZEN_MIN_TRUST: Final[float] = 0.05
CITIZEN_TRUST_STEP: Final[float] = 0.1

#: Relative disagreement with the co-located reference above which a submission
#: counts as contradicted for trust purposes.
CITIZEN_DISAGREEMENT_TOLERANCE: Final[float] = 0.5


# ---------------------------------------------------------------------------
# Photo provenance
# ---------------------------------------------------------------------------
# EXIF cannot be trusted as proof: it is trivially editable and most messaging
# apps strip it entirely. It is useful in exactly one direction -- when metadata
# is present and contradicts the submitted claim, that is evidence against the
# claim. Absence is not evidence either way, so an unverifiable submission is
# accepted and marked, never rejected.

#: How far the EXIF geotag may sit from the submitted position before the two
#: are treated as describing different places. Generous, because consumer GPS
#: under tree cover or beside tall buildings drifts by a few hundred metres and
#: a stricter bound would reject honest submissions.
EXIF_POSITION_TOLERANCE_M: Final[int] = 1000

#: How far the EXIF capture time may sit from the submitted capture time.
#: Cameras with an unset clock are common, so this catches a contradiction
#: rather than enforcing accuracy.
EXIF_TIME_TOLERANCE_MINUTES: Final[int] = 30

#: Trust a submission carries when its metadata could not be checked at all.
#: Below CITIZEN_INITIAL_TRUST, so an unverifiable photo still appears on the
#: map but does not shape the calibration.
CITIZEN_UNVERIFIED_TRUST: Final[float] = 0.3


# ---------------------------------------------------------------------------
# Federation
# ---------------------------------------------------------------------------

#: Pilot city centres, in (longitude, latitude). Chosen to span distinct
#: pollution regimes: Delhi for stubble, traffic and industry together; Kanpur
#: for the Indo-Gangetic industrial belt; Coimbatore as the southern node with
#: almost no monitoring, which is the one federation is supposed to help and
#: therefore the one that tests the claim.
PILOT_CITY_CENTRES: Final[dict[str, tuple[float, float]]] = {
    "delhi": (77.2090, 28.6139),
    "kanpur": (80.3319, 26.4499),
    "coimbatore": (76.9558, 11.0168),
}

#: Fire search boxes per pilot city, as (west, south, east, north). Wider than the
#: station radius on purpose: the fire being looked for is the one upwind of the
#: city, not the one inside it.
PILOT_CITY_FIRE_BOXES: Final[dict[str, tuple[float, float, float, float]]] = {
    "delhi": (76.0, 27.8, 78.2, 29.3),
    "kanpur": (79.8, 26.0, 80.9, 27.0),
    "coimbatore": (76.4, 10.6, 77.5, 11.5),
}

#: Radius, in metres, within which a station counts as belonging to a city.
PILOT_CITY_RADIUS_M: Final[int] = 25_000

#: How recently a station must have reported a pollutant to count as reporting
#: it. Deliberately separate from a station being "active": a site whose PM2.5
#: sensor died months ago still reports as active if its thermometer works, and
#: that distinction is the whole Coimbatore finding.
PILOT_REPORTING_WINDOW_HOURS: Final[int] = 48

#: Measured error, in ug/m3, of each node's own forecast model on its held-out
#: data. The baseline every federated candidate is compared against.
#: Source: `npm run fl:validate`, seeded, reproducible exactly.
FEDERATED_LOCAL_MAE_UGM3: Final[dict[str, float]] = {"delhi": 16.82, "kanpur": 9.21}

#: Each federated candidate against the node's own model, on the same held-out
#: rows: (candidate MAE, gain, interval low, interval high), all in ug/m3, gain
#: positive when the candidate is better. Intervals are 95% paired bootstraps, kept
#: to three decimals: rounding to two turned Delhi's fine-tuned upper bound of
#: -0.004 into -0.00, which reads as zero and flipped its verdict.
#:
#: Published with the intervals because the point estimates alone were once
#: stated as findings. Kanpur's plain-averaging row was reported as "federation
#: measurably harmed Kanpur"; its interval, [-3.441, +2.203], shows 23 held-out rows
#: cannot distinguish that from no effect. Every Kanpur candidate is inconclusive,
#: and no candidate is established as helping or harming either node.
#: Source: `npm run fl:validate`.
FEDERATED_CANDIDATE_RESULTS: Final[dict[str, dict[str, tuple[float, float, float, float]]]] = {
    "delhi": {
        "global": (16.84, -0.013, -0.036, 0.010),
        "fine-tuned": (16.84, -0.013, -0.021, -0.004),
        "local head": (16.79, 0.030, 0.007, 0.053),
    },
    "kanpur": {
        "global": (9.85, -0.631, -3.441, 2.203),
        "fine-tuned": (9.63, -0.417, -1.875, 1.112),
        "local head": (8.91, 0.303, -1.606, 2.115),
    },
}

#: Training and test rows each node contributed to that run, published so a
#: reader can see how thin the evidence is.
FEDERATED_TRAIN_ROWS: Final[dict[str, int]] = {"delhi": 1719, "kanpur": 55}
FEDERATED_TEST_ROWS: Final[dict[str, int]] = {"delhi": 493, "kanpur": 23}


# ---------------------------------------------------------------------------
# Personal exposure
# ---------------------------------------------------------------------------
# The forecast is a diurnal climatology with no day-to-day skill, so it cannot
# say whether tomorrow will be worse than today. What it does resolve is the
# daily cycle, and that is exactly what a timing decision needs: "is 3pm better
# than 8am on this route" is answerable from a climatology in a way that "will
# Friday be bad" is not. The advisory is built on the one thing the estimator is
# actually good at.

#: Assumed travel speed along a corridor, in km/h. Urban arterial traffic in an
#: Indian metro, well below the free-flow limit. Time spent in a segment is what
#: turns a concentration into an exposure, so this is the factor that matters.
EXPOSURE_TRAVEL_SPEED_KMH: Final[float] = 20.0

#: Departure hours evaluated, in local time. A working day at two-hour
#: resolution; finer would imply a precision the climatology does not have.
EXPOSURE_CANDIDATE_HOURS: Final[tuple[int, ...]] = (6, 8, 10, 12, 14, 16, 18, 20, 22)

#: Relative reduction below which two departure times are treated as equivalent.
#: The forecast error is frequently larger than the signal, so a difference of a
#: few percent is not a recommendation -- it is noise wearing one.
EXPOSURE_MEANINGFUL_REDUCTION: Final[float] = 0.10


# ---------------------------------------------------------------------------
# Scheduled worker
# ---------------------------------------------------------------------------

#: Minutes between worker cycles. OpenAQ publishes CPCB readings hourly, so a
#: faster cycle re-reads the same values and spends the rate limit for nothing,
#: while a slower one lets a developing episode go unseen for longer than the
#: data actually requires.
WORKER_INTERVAL_MINUTES: Final[int] = 60

#: Hours of history each cycle's detection looks back over. Long enough to
#: contain a persistent episode, short enough that a run reports what is
#: happening rather than re-reporting last week.
WORKER_DETECTION_WINDOW_HOURS: Final[int] = 24
