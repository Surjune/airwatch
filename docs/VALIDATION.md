# Validation: what was measured, and how it was judged

The headline figures in the [README](../README.md) come from here. Every claim below was measured on the pinned data described first, and every comparison carries an interval.

## How these results are judged

Every comparison below was re-run with two safeguards added after a published
federation claim turned out to rest on noise (see *Federation*).

- **Pinned data.** Validations read only observations before 12 September 2026
  00:00 UTC. Without that cutoff every figure drifted as the hourly worker added
  data — LightGBM's error here had already moved from the originally published
  12.84 to 12.44 — so the tables below supersede the first published figures.
- **Reference monitors only.** Five AirGradient low-cost sensors were once
  ingested as if they were reference monitors, because ingestion ignored
  OpenAQ's own classification. Their uncalibrated readings sat inside every
  validation below. They are now stored as the low-cost tier and excluded from
  all analysis, and every figure here was re-run without them. No conclusion
  changed; most numbers did.
- **Intervals, and a rule for reading them.** Each method is compared with the
  baseline by a bootstrap that resamples **whole stations**, since a station that
  is hard to predict is hard every hour and its rows are not independent. A
  method is called better or worse only when the 95% interval excludes zero *and*
  the difference exceeds 2%.

## Reconstructing unmonitored ground

Numbers below come from `npm run ml:validate-loso`: 7,001 scored station-hours
across 33 held-out reference stations in Delhi-NCR.

**Leave-one-station-out**: hide one real station completely — from the features
*and* from training — estimate its location from the rest of the network, and
compare against what it actually recorded.

| Method | MAE | RMSE | R² |
| --- | --- | --- | --- |
| Inverse-distance weighting | **11.75** | **17.85** | **0.246** |
| LightGBM (absolute target) | 12.76 | 19.00 | 0.146 |
| LightGBM (residual to IDW) | 13.00 | 19.25 | 0.123 |

| Against IDW (33 stations) | Difference (µg/m³) | 95% interval | Verdict |
| --- | --- | --- | --- |
| LightGBM (absolute) | −1.01 | [−2.17, +0.07] | inconclusive |
| LightGBM (residual) | −1.25 | [−2.56, −0.07] | worse |

Two findings:

**1. No learned model is established as better than interpolation, so IDW is
what ships.** The residual framing is established as worse. The absolute
framing's deficit is not established — its interval just crosses zero — though an
earlier version of this section stated it flatly as "~12% worse" from a point
estimate. Either way
nothing shows a gain, and without evidence of one the simpler estimator is the
one to trust. With 33 scorable stations the trees tend to learn each site's
idiosyncrasies rather than a spatial relationship that transfers to ground the
network does not cover.

**2. R² of 0.246 is the headline, and it is a result about the problem, not
about the method.** Even with more than 60 monitors inside 25 km — one of the densest
networks in India — neighbouring stations explain under a quarter of the
variance at an unmonitored point. This is the resolution mismatch in the
problem statement above, measured rather than asserted. The hardest station to
reconstruct is Anand Vihar (MAE 42 µg/m³), a bus terminal beside an industrial
belt: exactly the kind of hyper-local source that a city-average AQI cannot see.

**Error is predictable, which is what makes uncertainty honest.** Disagreement
between nearby monitors tracks error closely:

| Spread among 3 nearest stations | Mean absolute error |
| --- | --- |
| 0–5 µg/m³ | 10.45 |
| 5–15 µg/m³ | 11.52 |
| 15–30 µg/m³ | 13.57 |
| 30+ µg/m³ | 24.76 |

The fused surface therefore publishes a per-cell uncertainty fitted to this
relationship, and returns *nothing* rather than a number for cells too poorly
supported to estimate. A cell nothing supports is drawn as unknown, never as
clean.

**What would actually improve this** is not a better model but better-resolved
inputs — the low-cost sensor tier and satellite AOD — which is the argument for
the three-tier design rather than a bigger network of reference monitors.

## Forecasting, 24-72 hours

Validated on a temporal holdout -- trained on the earliest days, tested on the
latest -- because a random split would place hours from the same afternoon on
both sides and let autocorrelation stand in for skill.

| Method | 24h MAE | 48h MAE | 72h MAE |
| --- | --- | --- | --- |
| Persistence | 21.68 | 23.02 | 22.21 |
| **Climatology** | **15.79** | **16.35** | **16.24** |
| LightGBM (absolute) | 17.77 | 19.95 | 19.71 |
| LightGBM (residual to climatology) | 17.41 | 19.55 | 19.02 |

| Against climatology (58 stations) | 24h | 48h | 72h |
| --- | --- | --- | --- |
| Persistence | −5.89 [−7.27, −4.52] | −6.67 [−8.40, −5.10] | −5.97 [−7.19, −4.85] |
| LightGBM (absolute) | −1.98 [−2.78, −0.99] | −3.60 [−4.64, −2.49] | −3.47 [−4.22, −2.69] |
| LightGBM (residual) | −1.62 [−2.44, −0.62] | −3.20 [−4.18, −2.08] | −2.79 [−3.44, −2.12] |

*Difference in MAE (µg/m³) with 95% station-level interval; negative means worse
than climatology.*

**Climatology wins at every horizon, and this one survives the stricter test,
so climatology is what ships.** Every interval above excludes zero and every
difference clears the practical threshold. Knowing what a station is
*usually* like at 3pm beats knowing what it is doing right now by a wide margin,
which is a real statement about the pollutant: Delhi PM2.5 is dominated by its
daily cycle.

This is the second phase where a learned model failed to beat a simple
baseline, and both point at the same cause rather than at the model. Around 2,600 training
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

## Federation: does sharing weights help the data-poor city?

The premise of the federated design is that a city with three monitors benefits
from a model shaped partly by a city with sixty, without either handing over raw
data. That is a claim, and `npm run fl:validate` measures it: each node compares
the federated global model against its own local one, on its own held-out data.

First, the monitoring gap that motivates the whole arrangement, as it actually
stands in the pilot cities:

| City | Active stations | Hourly PM2.5 readings |
| --- | --- | --- |
| Delhi-NCR | 56 | 13,100 |
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
| Delhi | 405 | 18.11 | 18.14 | 18.13 | 18.07 |
| Kanpur | 23 | 9.20 | 10.18 | 9.75 | 9.20 |

| Node | Candidate | Gain vs own model (µg/m³) | 95% interval | Verdict |
| --- | --- | --- | --- | --- |
| Delhi | plain averaging | −0.027 | [−0.059, +0.005] | inconclusive |
| Delhi | fine-tuned | −0.017 | [−0.027, −0.006] | no practical difference |
| Delhi | local head | +0.038 | [+0.015, +0.062] | no practical difference |
| Kanpur | plain averaging | −0.979 | [−3.895, +1.926] | inconclusive |
| Kanpur | fine-tuned | −0.548 | [−1.931, +0.873] | inconclusive |
| Kanpur | local head | −0.006 | [−2.014, +1.870] | inconclusive |

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
head). On the data first used, the local head gave Kanpur a point estimate
better than its own model. With the low-cost sensors removed from Delhi's data it
no longer does — its gain is −0.006 — and it was **inconclusive either way**: its
interval spanned zero both times. A number that looks better on 23 rows is no
more a finding than one that looks worse, and this is what that looks like in
practice.

On Delhi's 405 rows the intervals are narrow enough to exclude zero, but the
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
