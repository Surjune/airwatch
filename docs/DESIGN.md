# Design notes: why each part is shaped the way it is

The [README](../README.md) says what AirWatch does. This file records the decisions behind the parts where the obvious design would have been wrong.

## Alerting, and why it is shaped this way

Routing is spatial, not configured per station, because a hotspot can appear on
ground no monitor covers -- which is the reason for estimating a surface at all.
Five rules follow, and all of them exist to protect the one thing the chain
depends on, that alerts keep being read and reach someone able to act:

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
- **The body that can act on the source is asked too.** See the next section.

Resolution requires a note. A resolution with no explanation records that
someone clicked a button, which is not the same as recording that something was
done, and the difference is the whole value of the trail.

Measured on the deployed server on 13 September 2026, over the backfilled
fortnight: **22 episodes detected, 23 alerts raised, 0 unrouted** -- 22 local
alerts and 1 coordination request. A second run within the suppression window
raises nothing new.

## Coordination across a boundary

The authority a hotspot sits in often cannot act on its cause. Punjab's stubble
smoke is Delhi's emergency; a landfill fire on one side of a district line is the
neighbouring district's bad air. Routing only by where the hotspot is sends the
alert to the one body that can do nothing about the source.

So dispatch traces every hotspot upwind. When its likeliest candidate lies inside
a different jurisdiction, that jurisdiction receives a **coordination request**
alongside the local alert. The rules, in `core/alerting.coordination_targets`:

- The candidate must reach `COORDINATION_MIN_CONFIDENCE` (0.5), higher than the
  0.35 that merely decides what is shown, because a request spends another
  body's inspection capacity.
- One request per authority, for its most plausible source; the local authority
  is never asked twice; a source on unregistered ground has nobody to ask.
- A hotspot inside no jurisdiction can still reach the authority holding its
  source -- that body is still the one able to act.
- The request says what it is: a ranked candidate with its confidence, never an
  established cause. The webhook event is `airwatch.coordination_request` and
  carries `requested_action.inspect_source`.

The first real one, from the deployed data: the monitor at **Prashant Garden,
Khora (UPPCB)** read 74 µg/m³ where its neighbours predicted 20. The local alert
went to the Gautam Buddha Nagar district administration in Uttar Pradesh. The
back-trajectory ranked the **Ghazipur landfill** first at 69% plausible, and the
landfill is in East Delhi -- so the East Delhi district administration received a
request to act for its neighbour across a state line. That is the interstate
coordination the problem statement asks for, arising from the data rather than
configured by hand.

A wind field keyed by hour alone would have made this unreliable: weather is
stored for every pilot city with identical timestamps, and until this was fixed a
Delhi trajectory could be stepped through Coimbatore's wind. Each trajectory now
uses the nearest weather cell within 40 km (`ATTRIBUTION_WIND_MAX_DISTANCE_M`),
and reports itself unavailable when there is none.

## Turning a weak forecast into a decision it can actually support

Climatology beat every learned model, which meant the forecast has no day-to-day
skill: it cannot say whether Friday will be worse than Thursday. That is a real
limitation and it is recorded in [VALIDATION.md](VALIDATION.md).

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

## The citizen tier, and what a photograph can establish

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

## Household sensor readings, and why none is corrected

A resident with an AirGradient, PurpleAir or Atmotube can post what it reads
(`POST /v1/citizen/sensor-readings`). These optical counters are the density the
three-tier design needs -- and they over-read in humid air, when particles swell,
by an amount that differs by model and by day.

- **Checked at the boundary.** PM2.5 and PM10 only, because consumer gas cells
  drift too far to compare. A value outside physical bounds is refused with a
  reason, since at this tier it is a typing error rather than an instrument fault
  worth keeping. Readings older than three hours describe different air.
- **Stored as reported, never corrected.** Any factor applied at storage would be
  a guess frozen into the record.
- **Paired, not trusted.** Each reading is matched to the nearest reference
  reading within 3 km and 90 minutes, by the same query that pairs a photograph.
  The tier publishes the median sensor-to-monitor ratio -- a median, so one sensor
  beside a kitchen stove cannot move it -- and marks it established only after 30
  pairs, the same bar as the photo calibration.
- **Kept out of every estimate.** Detection, fusion and forecasting read the
  reference tier only. On the map these readings are squares, so they cannot be
  mistaken for a monitor (filled circle) or a community network sensor (dashed
  ring), and every one is labelled "as reported".

The instrument model is recorded on purpose: a correction can only ever be fitted
per model if the model was written down.

## Interoperability, and why weights are withheld

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
