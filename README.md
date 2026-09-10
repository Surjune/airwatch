# AirWatch

**Federated hyperlocal air quality intelligence for Indian cities.**

Detects hidden pollution hotspots, attributes them to probable sources, forecasts spikes across
economic corridors 24–72h ahead, and lets cities share predictive models without sharing raw data.

---

## The problem

Indian cities monitor macro-level air quality but consistently miss hyper-local pollution events.
The reason is an economics problem wearing a technology costume:

**1. The accurate instrument cannot be dense; the dense instrument cannot be accurate.**
A CPCB reference-grade CAAQMS costs roughly ₹1–1.5 crore to install. India has ~400–550 of them,
and only ~12% of census cities and towns have any monitoring at all — 28 NCAP cities still have
zero real-time stations. One station is treated as representing tens of km². But PM2.5 varies 3–5×
within a single kilometre: a brick kiln, a landfill fire, a construction site, an arterial road at
6pm. The official number is a spatial average that structurally cannot see the event harming you.
A ₹15,000 low-cost sensor can be deployed 100× denser, but reads 20–40 µg/m³ off under humidity —
so it is inadmissible for policy.

**2. AQI is retrospective by construction.** It is a 24-hour rolling average. A three-hour toxic
plume is diluted into a daily number, published after people already breathed it.

**3. The data is fragmented along administrative lines, and pollution is not.** CPCB, ~35 state
boards, municipal corporations, ISRO, IMD and private networks each hold a fragment. Punjab's
stubble smoke becomes Delhi's health emergency in ~48 hours. No state will hand another its raw
data — that is a governance wall, not a bandwidth problem, which is why every attempt at a single
national data lake stalls.

**4. No attribution means no enforcement, so punishment becomes collective.** Even when a spike is
detected, nobody knows which source caused it. The policy response is therefore a sledgehammer —
GRAP shuts down all construction — instead of "this kiln, this stretch, this dump."

### Who pays

Roughly **1.7 million deaths in India in 2022** from PM2.5 exposure, and an economic loss of about
**9.5% of GDP (~$339B)**. The burden is concentrated on outdoor workers who cannot leave the
exposure (traffic police, construction labour, delivery riders, street vendors), children in
schools on arterial roads where lung-development loss is permanent, settlements beside industrial
corridors and landfills, and respiratory and cardiac patients.

Two groups are routinely mis-blamed: **farmers**, who have a 2–3 week window between paddy harvest
and wheat sowing and no affordable alternative, and **industrial units**, shut down collectively
because attribution is missing.

---

## The approach

Do not try to replace the reference network. Use it as ground truth to calibrate a cheap dense
network, and use satellites and meteorology to fill the space between.

| Tier | Source | Property | Role |
| --- | --- | --- | --- |
| 1 — Truth, sparse | CPCB CAAQMS, OpenAQ | accurate, ~400 points | ground truth, calibration target, validation |
| 2 — Dense, biased | low-cost sensors, citizen photos | everywhere, systematically wrong | spatial density once calibrated |
| 3 — Uniform, coarse | Sentinel-5P, NASA FIRMS, Open-Meteo/ERA5 | complete coverage, low resolution | covariates, fire events, transport physics |

Four things follow that current systems do not do:

- **A hotspot is an anomaly against a locally expected baseline**, not a national threshold.
  40 µg/m³ in a clean southern city is an event; the same reading in Delhi in November is noise.
  This is what "hidden" actually means.
- **Attribution by wind back-trajectory.** Trace upwind from the hotspot through the wind field and
  intersect with a source registry and FIRMS fire pixels. Output changes from "AQI is bad" to
  "this plume traces to a fire detected 40 minutes ago at these coordinates."
- **Forecast before exposure**, 24–72h along economic corridors, so the alert arrives in time to
  matter.
- **Federated by necessity.** Cities exchange model weights, not raw data. A model trained in Delhi
  and Kanpur gives Coimbatore — which has almost no stations — a working forecast on day one.
  This is the only architecture that survives Indian data-governance reality.

Software cannot stop the burning. What it can do is collapse detection-to-response from days to
minutes, make enforcement surgical instead of collective, cut an individual's actual inhaled dose
through timing and routing, and build the evidence trail that makes accountability possible.

---

## Validated results

### Reconstructing unmonitored ground

Numbers below come from `npm run ml:validate-loso` against 14,324 hourly PM2.5
readings from 61 real CPCB/DPCC stations in Delhi, backfilled over 14 days.

**Leave-one-station-out**: hide one real station completely — from the features
*and* from training — estimate its location from the rest of the network, and
compare against what it actually recorded.

| Method | MAE | RMSE | R² |
| --- | --- | --- | --- |
| Inverse-distance weighting | **11.48** | **17.30** | **0.232** |
| LightGBM (absolute target) | 12.84 | 18.48 | 0.124 |
| LightGBM (residual to IDW) | 12.95 | 18.55 | 0.117 |

Two findings, both reported as they came out:

**1. The learned model loses to plain interpolation, so IDW is what ships.**
Gradient boosting was ~12% worse on MAE despite receiving the IDW estimate as an
input feature. With 36 scorable stations it learns each site's idiosyncrasies
instead of a spatial relationship that transfers to ground the network does not
cover. Shipping it anyway would mean publishing worse numbers with more
confidence. Predicting the residual to IDW instead of the concentration did not
rescue it.

**2. R² of 0.232 is the headline, and it is a result about the problem, not
about the method.** Even with 61 monitors inside 25 km — one of the densest
networks in India — neighbouring stations explain under a quarter of the
variance at an unmonitored point. This is the resolution mismatch in the
problem statement above, measured rather than asserted. The hardest station to
reconstruct is Anand Vihar (MAE 40 µg/m³), a bus terminal beside an industrial
belt: exactly the kind of hyper-local source that a city-average AQI cannot see.

**Error is predictable, which is what makes uncertainty honest.** Disagreement
between nearby monitors tracks error closely:

| Spread among 3 nearest stations | Mean absolute error |
| --- | --- |
| 0–5 µg/m³ | 9.89 |
| 5–15 µg/m³ | 11.39 |
| 15–30 µg/m³ | 13.66 |
| 30+ µg/m³ | 24.47 |

The fused surface therefore publishes a per-cell uncertainty fitted to this
relationship, and returns *nothing* rather than a number for cells too poorly
supported to estimate. A cell nothing supports is drawn as unknown, never as
clean.

**What would actually improve this** is not a better model but better-resolved
inputs — the low-cost sensor tier and satellite AOD — which is the argument for
the three-tier design rather than a bigger network of reference monitors.

### Forecasting, 24-72 hours

Validated on a temporal holdout -- trained on the earliest days, tested on the
latest -- because a random split would place hours from the same afternoon on
both sides and let autocorrelation stand in for skill.

| Method | 24h MAE | 48h MAE | 72h MAE |
| --- | --- | --- | --- |
| Persistence | 22.05 | 23.51 | 21.63 |
| **Climatology** | **15.59** | **16.47** | **15.77** |
| LightGBM (absolute) | 17.50 | 18.87 | 18.51 |
| LightGBM (residual to climatology) | 17.39 | 18.59 | 18.33 |

**Climatology wins at every horizon, so climatology is what ships.** Knowing
what a station is *usually* like at 3pm beats knowing what it is doing right now
by a wide margin, which is a real statement about the pollutant: Delhi PM2.5 is
dominated by its daily cycle.

This is the second phase where a learned model lost to a simple baseline, and
both point at the same cause rather than at the model. Around 2,800 training
rows drawn from fourteen days cannot support a twenty-feature gradient-boosted
model against a strong prior. The next real improvement is months of history and
denser inputs, not a different architecture.

**What the climatological forecast cannot do**, stated plainly because the
output looks more confident than it is: it has no day-to-day skill. It predicts
the same value for 15:30 on Friday, Saturday and Sunday, because that is what a
diurnal climatology is. It captures the daily cycle and the spatial gradient; it
cannot say that Saturday will be worse than Friday. Supplying that was the job
of the weather-driven model, and with this much data it could not.

A corridor run across Delhi, from Dwarka east to Anand Vihar, does show the
gradient clearly -- 18 µg/m³ at the western end rising to 51 at the eastern,
roughly a threefold change across one city. The western 6 km return no forecast
at all, because no station lies within range; that stretch renders as unknown
rather than as clean.

Uncertainty is published with every point and is frequently larger than the
signal (18 ± 28 µg/m³ at the clean end). The forecast is currently more useful
for *where along a route* the air turns than for the absolute level.

## Status

Under active development. See `docs/` for architecture notes.

## Known limitations

Deferred deliberately, and tracked here rather than as TODOs in the code.

- **Sensor calibration is not yet trained.** Calibration needs paired
  (low-cost sensor, reference) observations and every station ingested so far is
  reference-grade, so there is nothing to calibrate against yet. The conversion
  and storage path keeps the raw value and the calibrating model version
  separately, so calibration can be applied later without re-ingesting.
- **The forecast is climatological and has no day-to-day skill.** It resolves
  the daily cycle and the spatial gradient but predicts the same value for a
  given hour on consecutive days. Learned models were measured against it and
  lost; see the validation table above.
- **The fusion model is inverse-distance weighting, not machine learning.** That
  is an empirical decision recorded above, not an unfinished one.
- **No authentication in v1.** The API is anonymous, protected only by per-IP rate limiting and a
  locked CORS allowlist.
- **Upstream CO units are not trustworthy at face value.** Several live Delhi stations declare CO
  in `ppb` while reporting values around 1.2 -- implausible as ppb (ambient CO runs in the hundreds)
  and exactly right as ppm. The conversion is implemented correctly for the declared unit; a
  per-pollutant plausibility guard that flags rather than ingests out-of-range values is still to be
  added. Until then a CO sub-index from OpenAQ should be treated as unreliable.
- **Stations carry duplicate sensors across generations.** A live station commonly exposes both a
  current sensor and a decommissioned one for the same pollutant, and the API returns the final
  value of each. Readings are filtered by observation recency per reading, not per station.
- **data.gov.in is intermittently unavailable.** The CPCB direct client is a redundancy path; the
  portal's API gateway returned 502 across all endpoints during development. OpenAQ carries the
  same CPCB station data and is the primary reference-tier source.
- **Sentinel-5P is ~7 km resolution with a daily revisit,** so it constrains fusion covariates
  rather than detecting hotspots directly.
- **Back-trajectory uses a single-layer wind field,** not full HYSPLIT dispersion.
- **Citizen photo PM2.5 is a proxy** with wide error bars, and is never used as the sole evidence
  for a cell.
- **FIRMS misses fires between satellite overpasses,** and most stubble burning has shifted to
  16:00-18:00 specifically to fall outside them.

## Licence

MIT
