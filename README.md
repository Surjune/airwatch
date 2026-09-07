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

## Status

Under active development. See `docs/` for architecture notes.

## Licence

MIT
