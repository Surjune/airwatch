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
- **Federated by necessity.** Cities exchange model weights, not raw data, because that is the
  only arrangement that survives Indian data-governance reality. The hope is that a model trained
  in Delhi and Kanpur gives a city like Coimbatore — which has almost no stations — a working
  forecast from the start. That is a claim, not a result: the measurements below have not yet
  established that sharing helps any node.

Software cannot stop the burning. What it can do is collapse detection-to-response from days to
minutes, make enforcement surgical instead of collective, cut an individual's actual inhaled dose
through timing and routing, and build the evidence trail that makes accountability possible.

---

## Validated results

### How these results are judged

Every comparison below was re-run with two safeguards added after a published
federation claim turned out to rest on noise (see *Federation*).

- **Pinned data.** Validations read only observations before 12 September 2026
  00:00 UTC. Without that cutoff every figure drifted as the hourly worker added
  data — LightGBM's error here had already moved from the originally published
  12.84 to 12.44 — so the tables below supersede the first published figures.
- **Intervals, and a rule for reading them.** Each method is compared with the
  baseline by a bootstrap that resamples **whole stations**, since a station that
  is hard to predict is hard every hour and its rows are not independent. A
  method is called better or worse only when the 95% interval excludes zero *and*
  the difference exceeds 2%.

### Reconstructing unmonitored ground

Numbers below come from `npm run ml:validate-loso`: 7,957 scored station-hours
across 36 held-out CPCB/DPCC stations in Delhi.

**Leave-one-station-out**: hide one real station completely — from the features
*and* from training — estimate its location from the rest of the network, and
compare against what it actually recorded.

| Method | MAE | RMSE | R² |
| --- | --- | --- | --- |
| Inverse-distance weighting | **11.48** | **17.29** | **0.233** |
| LightGBM (absolute target) | 12.44 | 18.15 | 0.155 |
| LightGBM (residual to IDW) | 12.61 | 18.34 | 0.137 |

| Against IDW (36 stations) | Difference (µg/m³) | 95% interval | Verdict |
| --- | --- | --- | --- |
| LightGBM (absolute) | −0.96 | [−2.08, +0.06] | inconclusive |
| LightGBM (residual) | −1.14 | [−2.29, −0.10] | worse |

Two findings:

**1. No learned model is established as better than interpolation, so IDW is
what ships.** The residual framing is established as worse. The absolute
framing's deficit is not established — its interval just crosses zero — though an
earlier version of this section stated it flatly as "~12% worse" from a point
estimate. Either way
nothing shows a gain, and without evidence of one the simpler estimator is the
one to trust. With 36 scorable stations the trees tend to learn each site's
idiosyncrasies rather than a spatial relationship that transfers to ground the
network does not cover.

**2. R² of 0.233 is the headline, and it is a result about the problem, not
about the method.** Even with more than 60 monitors inside 25 km — one of the densest
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
| 5–15 µg/m³ | 11.38 |
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
| Persistence | 21.39 | 22.87 | 20.27 |
| **Climatology** | **15.24** | **16.12** | **14.62** |
| LightGBM (absolute) | 17.12 | 18.32 | 17.50 |
| LightGBM (residual to climatology) | 16.79 | 18.14 | 16.58 |

| Against climatology (62 stations) | 24h | 48h | 72h |
| --- | --- | --- | --- |
| Persistence | −6.15 [−7.34, −4.88] | −6.76 [−8.31, −5.34] | −5.65 [−6.86, −4.55] |
| LightGBM (absolute) | −1.88 [−2.56, −1.05] | −2.20 [−3.00, −1.37] | −2.88 [−3.87, −1.90] |
| LightGBM (residual) | −1.55 [−2.27, −0.67] | −2.02 [−2.81, −1.15] | −1.96 [−2.72, −1.27] |

*Difference in MAE (µg/m³) with 95% station-level interval; negative means worse
than climatology.*

**Climatology wins at every horizon, and this one survives the stricter test,
so climatology is what ships.** Every interval above excludes zero and every
difference clears the practical threshold. Knowing what a station is
*usually* like at 3pm beats knowing what it is doing right now by a wide margin,
which is a real statement about the pollutant: Delhi PM2.5 is dominated by its
daily cycle.

This is the second phase where a learned model failed to beat a simple
baseline, and both point at the same cause rather than at the model. Around 3,000 training
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

### Federation: does sharing weights help the data-poor city?

The premise of the federated design is that a city with three monitors benefits
from a model shaped partly by a city with sixty, without either handing over raw
data. That is a claim, and `npm run fl:validate` measures it: each node compares
the federated global model against its own local one, on its own held-out data.

First, the monitoring gap that motivates the whole arrangement, as it actually
stands in the pilot cities:

| City | Active stations | Hourly PM2.5 readings |
| --- | --- | --- |
| Delhi | 61 | 14,385 |
| Kanpur | 3 | 660 |
| Coimbatore | 0 usable | 0 |

Coimbatore has a population near 2.5 million and **one** monitoring station in
range. That station reports as active, because OpenAQ's station-level timestamp
is the maximum across all its sensors — but its PM2.5 sensor last produced a
value five weeks earlier. The site is alive because its thermometer is. A city
of millions has no current particulate monitoring at all, while every count of
"active stations" includes it.

**The result: nothing is established either way — and an earlier version of
this README said otherwise.**

Every federated model was compared with each city's own model on that city's
held-out rows, with a paired bootstrap interval on the difference. A verdict of
*helped* or *harmed* requires the interval to exclude zero **and** the effect to
be large enough to act on (2%); anything else is reported as what it is.

| Node | Test rows | Own model | Plain averaging | Fine-tuned | Local head |
| --- | --- | --- | --- | --- | --- |
| Delhi | 493 | 16.82 | 16.84 | 16.84 | 16.79 |
| Kanpur | 23 | 9.21 | 9.85 | 9.63 | 8.91 |

| Node | Candidate | Gain vs own model (µg/m³) | 95% interval | Verdict |
| --- | --- | --- | --- | --- |
| Delhi | plain averaging | −0.013 | [−0.036, +0.010] | inconclusive |
| Delhi | fine-tuned | −0.013 | [−0.021, −0.004] | no practical difference |
| Delhi | local head | +0.030 | [+0.007, +0.053] | no practical difference |
| Kanpur | plain averaging | −0.631 | [−3.441, +2.203] | inconclusive |
| Kanpur | fine-tuned | −0.417 | [−1.875, +1.112] | inconclusive |
| Kanpur | local head | +0.303 | [−1.606, +2.115] | inconclusive |

**A correction.** This section previously read *"federation harmed the sparse
node"*, and the dashboard called that *"the measurement, not a provisional
result."* It was a point estimate — Kanpur's error rising from 9.21 to 9.85 —
on 23 held-out rows, and its interval, [−3.44, +2.20] µg/m³, shows those rows
cannot tell it apart from no effect at all. The claim was stated with a certainty
the evidence never had. It is corrected here, on the dashboard, and in the
interop model card, and the rule that caught it (`app/core/evidence.py`) now
decides every published verdict, so the experiment and the API cannot disagree.

**Personalisation was then tried**, because it is the standard answer to the
non-IID harm the point estimates suggested: fine-tuning the global model locally,
and keeping the shared slopes while refitting each city's intercept (a local
head). The local head gives Kanpur its best point estimate, 8.91 — better than
its own model — and that holds across every combination of rounds and proximal
strength tried. It is **also inconclusive**: its interval spans zero too. A
number that looks better on 23 rows is no more a finding than one that looks
worse.

On Delhi's 493 rows the intervals are narrow enough to exclude zero, but the
differences are a few hundredths of a microgram — real, and far too small to
matter. That is why significance alone is not enough to call an effect.

**What the evidence supports**, then, is modest: federating did not demonstrably
help or hurt either city, so each keeps its own model. The plausible mechanism —
Kanpur's cleaner, less variable air is an easier task, and a global model that
is roughly 97% Delhi pulls it toward a harder regime — matches the direction of
every point estimate and is not established by any of them. **What would settle
it is more Kanpur history, not a different model:** a holdout several times
larger would narrow those intervals enough to tell the options apart.

There are also two participating nodes, not the intended three, and fourteen
days of history, and the task is forecasting, where climatology already beat
every learned model.

**A federation constraint worth recording**: the shared feature schema is 17
features, not the forecast model's full set. Meteorology is ingested only for
Delhi, and a feature one node can compute and another cannot does not average.
Agreeing the smaller common schema is the correct trade, and is a good example
of federation being a governance problem before it is a modelling one.

## What the API exposes

Four analysis endpoints, four exchange endpoints, and the alert console. Every
estimated quantity carries its uncertainty or confidence in the payload, and
every error returns the same envelope with a correlation ID.

| Endpoint | What it answers |
| --- | --- |
| `GET /v1/stations` | Latest reading at every station, worst first |
| `GET /v1/hotspots` | Locations dirtier than their neighbourhood predicts, with ranked candidate sources |
| `GET /v1/forecast/corridor` | Concentration outlook along a route |
| `GET /v1/exposure/advisory` | When to travel a route, by the exposure each departure costs |
| `GET /v1/alerts` | The alert inbox, ordered by standardised excess |
| `POST /v1/alerts/dispatch` | Detect over a window and route alerts to the responsible authorities |
| `POST /v1/alerts/{id}/acknowledge` | Record that an authority has seen an alert |
| `POST /v1/alerts/{id}/resolve` | Close an alert with a note describing the outcome |
| `POST /v1/alerts/deliver` | Send recorded alerts to the configured endpoint |
| `GET /v1/alerts/sla-breaches` | Alerts past their response deadline |
| `GET /v1/federation/status` | Live node coverage, and whether federating helped |
| `GET /v1/interop/capabilities` | What this node offers a partner, discoverable at runtime |
| `GET /v1/interop/observations` | Observations as GeoJSON with OGC SensorThings property names |
| `GET /v1/interop/hotspots` | Detected episodes as GeoJSON, carrying observed, expected and excess |
| `GET /v1/interop/models` | Model cards: what each estimator scored, and what it lost to |
| `POST /v1/citizen/reports` | Submit a geotagged photograph; returns the haze it measured |
| `GET /v1/citizen/reports` | Recent submissions, and which of them also calibrate |
| `GET /v1/citizen/calibration` | Whether a photograph can yield a concentration yet |

### Alerting, and why it is shaped this way

Routing is spatial, not configured per station, because a hotspot can appear on
ground no monitor covers -- which is the reason for estimating a surface at all.
Three rules follow, and all three exist to protect the one thing the chain
depends on, that alerts keep being read:

- **One alert per episode.** A source that burns for eight hours is one event.
- **Lowest jurisdiction tier first,** so a municipal body is reached before a
  state board rather than both being told and each assuming the other is acting.
- **An unrouted hotspot is reported, not dropped.** A hotspot inside no
  registered jurisdiction is a gap in the authority registry; hiding it would
  make an incomplete registry look like a quiet day.
- **Recording an alert and delivering it are separate facts.** Delivery runs as
  its own step, because a slow endpoint would otherwise stall detection and a
  failed one would lose the alert. A failed delivery keeps the alert queued with
  the reason attached, so an authority that was never told stays distinguishable
  from one that was told and stayed silent.

Resolution requires a note. A resolution with no explanation records that
someone clicked a button, which is not the same as recording that something was
done, and the difference is the whole value of the trail.

Measured against the live database: **21 episodes detected, 21 routed, 0
unrouted**, and a second run suppressed all 21. Anand Vihar routes to East Delhi,
Nehru Nagar to South Delhi.

### Turning a weak forecast into a decision it can actually support

Climatology beat every learned model, which meant the forecast has no day-to-day
skill: it cannot say whether Friday will be worse than Thursday. That is a real
limitation and it is recorded above.

What it *does* resolve is the shape of an average day — and that is exactly what
a timing decision needs. "Is the evening usually better than the afternoon on
this route" is a question about the daily cycle; "will tomorrow be bad" is not.
So the exposure advisory is built on the one thing the estimator is genuinely
good at rather than on the thing it was hoped to do.

Each candidate departure hour is forecast along the whole route and integrated
with **time spent in each segment as the weight** — weighting by sample count
instead would let a long clean stretch outvote the short filthy one that
determines the dose. On the Dwarka–Anand Vihar corridor the answer is concrete:
travelling at 20:00 rather than 16:00 avoids about **25%** of the exposure.

Two refusals are built in. When the spread across the day is smaller than the
forecast's own error, **no hour is named** — advice gets acted on, and naming one
there would be dressing noise as advice. And the quantity is exposure
(µg/m³ × minutes), never micrograms inhaled: that needs a ventilation rate which
depends on the person, and inventing one would add a fabricated factor to a
number that is useful without it.

### The citizen tier, and what a photograph can establish

A reference monitor costs ~₹1 crore and there are a few hundred in the country.
There are a billion cameras. The risk is that density arrives without accuracy
and gets treated as if it had both, so this tier is arranged to fail towards
silence.

A photograph cannot measure PM2.5. It can measure how much contrast the
atmosphere removed, which the dark-channel prior (He, Sun and Tang, CVPR 2009)
recovers as a transmission map; transmission is `exp(-βd)` for extinction over
scene depth. The depth is not in the image, so the measurement stops at a
dimensionless **haze index** in [0, 1].

Converting that to micrograms needs an empirical relation, and the only
defensible source is this network's own data: submissions taken within 3 km of a
reference monitor pair a haze index with a measured concentration. **Below
thirty pairs, no concentration is published** — not a rough number, not a wide
interval. The response carries the haze index, a null estimate, and a sentence
saying what is missing. An uncalibrated concentration derived from a photograph
is a fabricated reading.

The error is measured by leave-one-out rather than in-sample, because at this
sample size the fit has seen every point it would otherwise be scored on.

Three image conditions are refused outright — **darkness, blur, over-exposure**
— because each one makes clean air look dirty. A bug here would not produce an
obviously broken number; it would produce a plausible pollution reading from a
clear day, which is the worst output this system can emit. A refusal returns the
reason, so the photograph can be retaken.

Trust moves only when a comparison was possible. A device is never penalised for
photographing somewhere the reference network cannot check it, since that is
exactly where the tier is most needed.

### Interoperability, and why weights are withheld

No state hands another its raw database, so a national data lake stalls on
ownership rather than bandwidth. What a state will exchange is a bounded,
self-describing envelope it can audit before sending -- hence GeoJSON, OGC
SensorThings property names, and an explicit CRS, licence and measurement tier
on every payload.

`GET /v1/interop/models` publishes the measured performance of every estimator,
including the two that lost, and offers **no weight vector**. That is deliberate
rather than unfinished: the learned models were trained, validated and beaten by
their baselines, and neither federated averaging nor its personalised variants
is established as improving on a node's own model. Publishing weights without
evidence of benefit would invite a data-poor city to adopt something nobody can
show is better. The reason is stated in the card.

## Running it

```bash
npm run db:up         # Postgres + PostGIS + TimescaleDB, and Redis
npm run db:migrate    # apply migrations
npm run seed          # load the source and authority registries
npm run ingest:once   # pull live data from OpenAQ, Open-Meteo and FIRMS
npm run backfill      # pull hourly history so forecasting has a series
npm run dev           # API on :8000, web on :5173
```

### Keeping it current

Without a schedule the data goes stale within a day, and a hotspot that develops
overnight goes unseen until someone runs ingestion by hand. The worker runs one
cycle per hour -- ingest every pilot city, detect and route, deliver:

```bash
npm run worker        # long-running, one cycle per hour
npm run worker:once   # a single cycle, for cron or Windows Task Scheduler
```

Each step is isolated, so an outage for one city or one upstream does not stop
the others, and detection still runs over the data already held. `worker:once`
exits non-zero if any step failed, so a scheduler watching the exit code sees it.

On Windows, schedule it hourly with:

```powershell
schtasks /Create /SC HOURLY /TN "AirWatch worker" /TR "cmd /c cd /d C:\path\to\airwatch && npm run worker:once >> worker.log 2>&1"
```

A cycle stores each station's latest reading, so hotspot detection needs a few
hours of cycles before a persistent episode can appear. After a long gap, run
`npm run backfill` once to restore the hourly history.

### Reproducing the headline result

Every figure here came from live upstreams over a fourteen-day window, which
nobody else can reproduce without three API keys and the same fortnight of
weather. So the episode is committed:

```bash
npm run demo:replay
```

That loads `infra/fixtures/delhi-anand-vihar-august.json` — 1,232 real CPCB and
DPCC readings from 63 stations over three days — and runs the actual detection
over them. It prints what it found and exits non-zero if the episode is not
there:

```
Anand Vihar, New Delhi - DPCC: 381 ug/m3 where the network predicted 40
                               (excess 341, z=20.4, 7 intervals)
    candidate: Anand Vihar ISBT and rail terminal (60% plausible)
PASS: the expected episode at Anand Vihar was found.
```

The fixture carries its own acceptance criterion, so the file states what it is
supposed to demonstrate. The same replay runs in the test suite against an empty
database, which makes it a regression test rather than a demo: if a change to
fusion, the uncertainty model or the persistence filter quietly stops the system
seeing a bus terminal running nine times its neighbourhood, the suite fails.

Verification:

```bash
npm run check              # lint, formatting, types, and every test
npm run ml:validate-loso   # leave-one-station-out on the fused surface
npm run ml:validate-forecast
npm run fl:validate        # does federation help the sparse node?
npm run alerts:dispatch    # detect and route from the command line
npm run alerts:deliver     # send recorded alerts to the configured endpoint
```

### Running the federation across processes

`npm run fl:validate` measures federation in one process. The same protocol also
runs with each city as its own process, over Flower's gRPC transport, so no
party ever holds another's data:

```bash
npm run fl:server -- --nodes 2
npm run fl:node -- --city delhi --pinned
npm run fl:node -- --city kanpur --pinned
```

The server opens no database. The first round exchanges per-feature sums and
counts, from which it builds the shared scaler; every round after that exchanges
model weights only, and each node reports the global model's error on its own
held-out rows. Membership is fixed at the first round, and a node that drops out
stops the run rather than being averaged around.

Training is deterministic, so the transport can be held to an exact standard:
with `--pinned` it reproduces the in-process result — Delhi 16.84 and Kanpur 9.85
µg/m³ after ten rounds — and a test drives Flower's own round loop and checks the
weights match to floating-point precision.

Tests marked `integration` need a reachable PostgreSQL and skip with a reported
reason when there is none, so `npm run check` is green on a clean clone.

## Known limitations

Deferred deliberately, and tracked here rather than as TODOs in the code.

- **No low-cost sensor tier exists.** Every station ingested is reference-grade, so the
  sensor-calibration model the three-tier design depends on has nothing to calibrate against. The
  storage path keeps the raw value and the calibrating model version separately, so calibration can
  be applied later without re-ingesting.
- **The citizen tier has no calibration yet, by construction.** It needs thirty photographs taken
  near a reference monitor across a range of conditions. Until then it reports a haze index and no
  concentration, which is the intended behaviour rather than an unfinished one.
- **Coimbatore has one working reference monitor, and its PM2.5 sensor is down.** The dashboard
  opens on Coimbatore and on PM10, because SIDCO Kurichi (TNPCB) reports PM10 while its PM2.5 sensor
  returned nothing across the ingested fortnight, and PSG College of Arts and Science has not
  reported since July. With one station, hotspot detection (which needs at least three neighbours)
  and corridor forecasts cannot run, and both screens say so rather than showing an empty result.
  Citizen photographs taken there are measured and shown, but cannot count toward calibration, which
  is fitted against PM2.5; a photo pairs only with a reading within 90 minutes and 3 km of it.
- **EXIF corroborates but cannot authenticate.** Metadata is read and a photograph whose own header
  places it in another city, or hours from the claimed time, is refused. But EXIF is editable and
  routinely stripped, so absence cannot be treated as fraud: an unverifiable submission is accepted,
  marked, and held below the trust a pair needs to shape the calibration. A determined spoofer can
  still write matching metadata; this raises the cost, it does not close the hole.
- **No federated model is established as helping or harming either node.**
  Plain averaging and two personalised variants are implemented, tested and
  published with bootstrap intervals; Kanpur's 23-row holdout leaves every one of
  them inconclusive. The limiting factor is the size of that holdout, which only
  more history can fix.
- **Federation nodes share one database and one machine.** Each city runs as its
  own process and reads only its own city's rows, but the pilot points every node
  at the same PostgreSQL. Transport is loopback and unencrypted; a deployment
  across state boundaries needs TLS and node authentication, which v1 does not set
  up.
- **The Flower entry points are deprecated.** Nodes use `start_server` and
  `start_client`, which Flower 1.x supports but has superseded with its
  SuperLink/SuperNode deployment. The dependency is capped below 2.0; moving to
  SuperLink is packaging work, and the strategy and client carry over unchanged.
- **Station-level activity is not pollutant-level activity.** A site whose
  PM2.5 sensor is dead still reports as active if any other sensor is live.
  Confirming a pollutant is reporting requires querying its sensor history.
- **The forecast is climatological and has no day-to-day skill.** It resolves
  the daily cycle and the spatial gradient but predicts the same value for a
  given hour on consecutive days. Learned models were measured against it and
  lost; see the validation table above.
- **The fusion model is inverse-distance weighting, not machine learning.** That
  is an empirical decision recorded above, not an unfinished one.
- **Jurisdiction polygons are illustrative bounding boxes.** `infra/seed/delhi_authorities.json`
  stands in for authoritative administrative boundaries, which were unavailable. Routing works and
  is spatially correct at city-zone granularity, but a deployment must load the real geometry: an
  alert delivered to the wrong body is worse than one never sent, because it creates a record of
  notification that nobody could act on.
- **No model weights are published for exchange.** `GET /v1/interop/models` serves model cards with
  measured performance and withholds weights, because both learned models lost to their baselines.
  The envelope supports weights; there is nothing this node would honestly recommend adopting.
- **Delivery is a webhook only.** An authority's endpoint receives a machine-readable event; there
  is no email or SMS gateway. That is a deliberate choice -- a control room needs an event its own
  software can file and close, and anything needing email can subscribe to the same webhook through
  a gateway the authority controls -- but it does mean a deployment with no such endpoint records
  alerts without delivering them, and says so rather than claiming success.
- **No authentication in v1.** The API is anonymous, protected only by per-client rate limiting
  (`RATE_LIMIT_PER_MINUTE`, default 120, with `Retry-After` on refusal) and a locked CORS allowlist.
  The limit is held in memory per process, so each uvicorn worker enforces it separately and a
  restart forgets it; a multi-worker deployment would move it to Redis. It keys on the connecting
  address and deliberately ignores `X-Forwarded-For`, which any caller can forge, so behind a
  reverse proxy the proxy must supply the real address (uvicorn `--proxy-headers`).
- **Upstream CO units are not trustworthy at face value.** Several live Delhi stations declare CO
  in `ppb` while reporting values around 1.2 -- implausible as ppb (ambient CO runs in the hundreds)
  and exactly right as ppm. Every one of the 114 CO readings in the pilot database had this error.
  A plausibility guard now flags any reading outside physical bounds (`PLAUSIBLE_CONCENTRATION_RANGE`)
  at ingestion, and `npm run data:reflag` re-applies the bounds to rows already stored; flagged rows
  are kept but excluded from every estimate. The values are deliberately not "corrected" to ppm:
  guessing what an instrument meant would be inventing a number. So there is currently no usable CO
  data, rather than wrong CO data. Negative values, which some networks emit as "no data" sentinels,
  are dropped at ingestion.
- **Stations carry duplicate sensors across generations.** A live station commonly exposes both a
  current sensor and a decommissioned one for the same pollutant, and the API returns the final
  value of each. Readings are filtered by observation recency per reading, not per station.
- **There is no direct CPCB client.** `CPCB_API_KEY` is accepted by the configuration but nothing
  reads it. A direct data.gov.in path was planned as redundancy and abandoned when the portal's API
  gateway returned 502 across every endpoint during development. OpenAQ carries the same CPCB and
  DPCC station data and is the only reference-tier source actually in use, so the network currently
  has a single point of failure upstream.
- **Sentinel-5P is not ingested, and the blocker is a permission rather than code.** The service
  account authenticates, but Earth Engine refuses the project: the caller needs
  `roles/serviceusage.serviceUsageConsumer` on the Google Cloud project, and the project itself must
  be registered for Earth Engine with the API enabled. No client was written against an API that has
  never answered — every other upstream here was verified against the live service before being
  documented as working, and a client shipped on the strength of mocked tests alone would not meet
  that bar.
  When it is unblocked, the honest use is narrow: Sentinel-5P measures NO2 column density at ~7 km
  with a daily revisit, so it would be published as NO2 in its own units and never converted into a
  PM2.5 figure. It constrains covariates and covers ground no station reaches; it does not detect
  hyperlocal hotspots.
- **Back-trajectory uses a single-layer wind field,** not full HYSPLIT dispersion.
- **Citizen photo PM2.5 is a proxy** with wide error bars, and is never used as the sole evidence
  for a cell.
- **FIRMS misses fires between satellite overpasses,** and most stubble burning has shifted to
  16:00-18:00 specifically to fall outside them.

## Licence

MIT
