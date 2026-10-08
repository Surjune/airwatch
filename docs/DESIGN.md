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

## Complaint reports, and what they refuse to claim

A resident who photographs smoke behind a bus stand wants to *do* something with
it. So a submission can carry a concern (open burning, industrial smoke,
construction dust...) and a description in their own words, and it produces a
reference (`AW-P-000123` for a photograph, `AW-S-000045` for a sensor reading)
and a PDF they can attach to a grievance.

- **Only the submitting browser can reach it.** A description can reveal where
  someone lives. The list and the PDF are keyed on the anonymous device
  identifier, sent as an `X-Device-ID` header so it never appears in a URL, and a
  reference belonging to another device returns the same 404 as one that does
  not exist.
- **It names who is responsible, from boundaries, and says that is an assumption.**
  The district administration and state body come from the same OpenStreetMap
  jurisdictions that route alerts; which office inside each handles complaints is
  left for that body to confirm.
- **It does not pretend an office was told.** AirWatch does not forward individual
  complaints. The report says so, tells the resident where to lodge it, and says
  that a persistent excess detected by the monitors is routed on its own.
- **It never upgrades the measurement.** A photograph's report states the haze
  index and gives a PM2.5 estimate only if the calibration exists, labelled with
  the date it was computed; the photo itself is not stored. A sensor reading's
  report prints the value as reported and its uncalibrated index.
- **It prints the resident's language, and English beneath it.** The PDF embeds
  Noto Sans with Tamil and Devanagari fallbacks and shapes text with HarfBuzz, so
  a description written in Tamil prints as Tamil rather than as boxes. The
  official it is taken to may not read Tamil, so Gemini's English translation is
  printed under it, labelled as a machine translation (see below).

The layout lives in `app/documents/complaint_pdf.py`, a leaf that receives
already-worded sections; every sentence is decided in `complaint_service`, where
the rules about what can be claimed are.

## The spoken guide, and why it is scripted

A resident who photographs smoke is exactly the person the dashboard's English prose fails. The
guide explains each screen aloud in English, Hindi or Tamil, and four decisions shape it:

- **Written, not generated.** A language model asked to explain a screen would sometimes describe a
  button that does not exist, or promise that a complaint is forwarded. The scripts are fixed text in
  `app/guides/scripts/<language>.toml`, reviewed like code, and a loader refuses a language that is
  missing a screen, so no screen goes silent in Tamil.
- **Said the way people say it.** Interface labels stay in English inside a Hindi or Tamil sentence
  ("Open the map दबाएँ"), because that is the word on the button the listener has to find. Terms a
  voice would misread are rewritten only in what is spoken: "PM2.5" becomes "पीएम टू पॉइंट फाइव".
- **One clip per paragraph, stored once.** Each paragraph is synthesised by Sarvam AI's Bulbul v3,
  keyed by a hash of the words, voice, model and settings, and kept in `voice_guide_clips`. A
  corrected sentence gets a new clip and a new URL, so browsers may cache a clip for a year.
  `deploy.sh` generates every clip in advance, and a stored clip plays even if the key is removed or
  Sarvam is down. There are 87 clips across the three languages, generated once, so the
  cost does not grow with visitors.
- **The words are always on screen.** The transcript highlights the paragraph being spoken and each
  paragraph plays on a tap. The guide works for someone who is hard of hearing, in a quiet office,
  and on a deployment with no key, which shows the transcript and says the voice is not set up.

## Coimbatore, and the regional model

Every source was checked for Coimbatore in September 2026:

| Source | What it holds for Coimbatore |
| --- | --- |
| OpenAQ | Four government monitors on record: SIDCO Kurichi (silent except CO and weather since 14 September), PSG College (silent since July), Tirupur and Ooty (silent since April) |
| CPCB live feed (data.gov.in) | SIDCO Kurichi only |
| AirGradient public network | 183 sensors in India, none within 60 km |
| Sensor.Community | None |
| **CAMS model via Open-Meteo** | Every hour, six pollutants, 92 days back and 5 days ahead, no key |

The model is the only source that fills the hours, so it is stored and shown -- on its own terms:
- **Its own table.** `model_concentrations` is never read by detection, fusion, the corridor
  forecast or validation, all of which read measurements. A modelled value cannot become a hotspot.
- **Its bias travels with it.** Each view pairs the model, interpolated to the half-past timestamp
  each monitor reports at, with the city's reference readings over the fortnight, and states the
  median ratio -- established only after 24 paired hours, so one day's cycle is represented.
- **Past and future are drawn differently.** The chart draws the reconstruction solid and the
  forecast dashed.
- **The bias is real and not one-directional.** On 15 September 2026 the model read 0.63× SIDCO
  Kurichi's PM10 (218 pairs), 1.24× Kanpur's PM2.5 monitors (671 pairs) and 1.81× Delhi's (12,969
  pairs across 56 monitors). A single correction factor would be wrong in two cities out of three,
  so none is applied; the ratio is shown instead.
- **Where no route forecast is possible**, as on every Coimbatore corridor, the Forecast screen
  offers the model's city-wide outlook instead of an empty page, and says plainly it cannot see
  where along a road the air changes.

## When an upstream goes quiet

Every monitor reading reaches AirWatch through OpenAQ, and OpenAQ relays CPCB. Two kinds of
silence have happened, and they are handled differently:

- **A station stops.** SIDCO Kurichi, Coimbatore's one working monitor, stopped sending PM10,
  NO₂, SO₂ and O₃ on 14 September 2026; CPCB's own feed went quiet for it the same night. Nothing
  downstream can bring it back. What the page can do is say so: a station that has not reported
  for six hours is described as silent, with the time of its last report, rather than as one whose
  latest hour lacked a pollutant; tier counts include only stations that reported in those six
  hours; and while no monitor in the city reports, Overview shows the CAMS model's current hour,
  labelled as modelled and followed by its measured bias.
- **The relay stops.** On 16 September 2026 OpenAQ stopped relaying every CPCB station in India
  at 16:30 UTC, while its other providers (the US Embassy monitor, AirGradient) carried on. The
  hourly cycle stores only each sensor's latest value, so the hours of a stall would have stayed
  missing after it ended, thinning every 24-hour average and detection window across them. Now,
  when a station's newest PM2.5 or PM10 reading is more than three hours after the last one
  stored, the worker fetches the sensor's hourly history for the gap (up to 14 days), stores only
  the hours strictly between, and logs how many it found. The gap is filled once; a failed fill is
  logged and left for the backfill command without costing other stations their cycle.

CPCB's data.gov.in feed cannot stand in for the missing hours: it publishes sub-indices, and
turning an index back into a concentration would be a guess.

### The backup feed: the World Air Quality Index Project

On 29 September 2026 OpenAQ stopped relaying all 448 CPCB stations in India within the same hour,
and data.gov.in's API refused connections, while the monitors kept publishing. The World Air
Quality Index Project (WAQI, aqicn.org) still receives Delhi's: it reads DPCC's own portal and an
IMD station directly. Its CPCB-fed stations, Kanpur's among them, have not updated since 23 June
2026, so it cannot help Kanpur or Coimbatore. With a `WAQI_API_TOKEN`, the worker's
`backup:<city>` step (`services/backup_feed_service.py`) fills the gap under these rules:

- **Only where OpenAQ is silent.** A reference monitor is filled only when its newest PM2.5 or
  PM10 is more than two hours old. With every monitor reporting, no request is made.
- **Only the same instrument.** WAQI stations come from a map search of the city's view, never
  from a "nearest station" lookup; for Coimbatore that lookup returns a Delhi site 2,000 km
  away. A WAQI station pairs with a monitor within 1 km, or within 5 km when the site names
  agree (WAQI places DPCC's Mundka 4.5 km from OpenAQ's position for it). Pairing is
  one-to-one, closest first.
- **Only the monitor's own agency.** The monitor's name ends with its agency ("- DPCC", "- IMD",
  "- CPCB"), and WAQI's attribution must name the same body. That keeps out Clarity's community
  sensors, which WAQI also lists in Delhi, and any second agency's instrument under the same site
  name.
- **Fresh, converted and marked.** A WAQI figure more than three hours old is skipped. PM2.5 and
  PM10 are turned back from the US AQI into µg/m³; gases are not, because the US AQI quotes them
  in parts per billion at its own reference conditions. Whole-number indices mean about
  ±0.25 µg/m³ of rounding in the 51–100 band, under 1 µg/m³ at the top. The reading is stored
  with origin `waqi`, and the monitor list and map tag it "via aqicn.org", with the attribution
  WAQI's terms require.
- **Never over OpenAQ, and retired when OpenAQ returns.** A WAQI figure is written only where
  nothing is stored. An OpenAQ reading for the same hour replaces it, and OpenAQ's catch-up
  removes the WAQI figures inside a gap it has refilled. Gaps are measured from OpenAQ's own
  readings, so a stand-in cannot hide one.
- **Not passed on.** WAQI's terms forbid redistributing its data as cached or archived data, so
  the partner exchange API (`/v1/interop/observations`) serves OpenAQ readings only. Public
  non-commercial use also requires notifying WAQI by email first.

**Which US AQI table.** The US EPA lowered its PM2.5 breakpoints in May 2024, and the two tables
disagree by up to a quarter outside 35.5–55.4 µg/m³. On 2 October 2026 WAQI's PM2.5 index was
compared with OpenAQ's raw concentration for the same station and hour at 91 stations outside
India (Korea, Japan, Taiwan, the Netherlands and the US). At the 42 where the tables give
different answers, the **2012 table matched WAQI within one point at 36, the 2024 table at 2**.
`WAQI_PM25_BREAKPOINTS` is the 2012 table.

The first dry run against live data, on 2 October 2026, paired 22 of Delhi's 56 monitors (21 DPCC
sites and IMD's Pusa), every one passing the agency check, with PM2.5 between 25 and 73 µg/m³.

### Official figures without data.gov.in: TNPCB and the daily bulletin

data.gov.in's API refused every connection from 25 September 2026, from a home connection in
India and from the server alike. On 8 October every other route to CPCB's figures was tried:

| Source | Kanpur | Coimbatore | Used |
| --- | --- | --- | --- |
| CPCB's live dashboard (`airquality.cpcb.gov.in/ccr`) | live | live | No: it needs a CAPTCHA and its API answers in encrypted form, which is a refusal of automated use |
| TNPCB's AQI page (`tnpcb.gov.in/aqi.php`) | -- | updated hourly | **Yes**, for Tamil Nadu |
| UPPCB's website | archives only | -- | No |
| CPCB's daily AQI bulletin (PDF) | daily | daily | **Yes**, for every city |
| WAQI | stale since 23 June | stale since 23 June | Delhi only (above) |
| IQAir | current, but four stations with one identical value | -- | No: looks estimated, and the free API is city-level US AQI only |

**TNPCB.** The page carries, per Tamil Nadu station, exactly what data.gov.in carries: each
pollutant's minimum, maximum and average CPCB sub-index over 24 hours, stamped in IST, and says the
data is obtained from CPCB. `external/tnpcb_client.py` reads the station entries out of the page's
script; a page with none, or an entry of a new shape, is a typed error. TNPCB gives no
coordinates, so a station is placed where CPCB's own feed last put it, or where OpenAQ puts the
monitor of the same name, and left out if neither knows it. Each stored sub-index records its
relay (`data.gov.in` or `tnpcb`), and the card names it. TNPCB's site states no reuse terms beyond
"All rights reserved"; the figures are CPCB's, which CPCB publishes openly on data.gov.in, and
AirWatch credits both.

**The daily bulletin.** CPCB publishes one PDF a day (`AQI_Bulletin_YYYYMMDD.pdf`) giving each
city's AQI as the average of its reporting stations over the 24 hours to 4 pm IST, the prominent
pollutants, and how many of the city's stations took part. It appeared every day of the outage.
`external/cpcb_bulletin_client.py` reads the rows from the PDF's text; a bulletin whose heading
names another day, or with no rows, is an error. On 8 October all 263 rows of the day's bulletin
parsed but one, a wrapped "Aurangabad" line that is not a pilot city. The worker fetches today's
bulletin until it has it and yesterday's while today's is not out, so a day costs a few requests.

The overview leads with CPCB's hourly figure when current; failing that, AirWatch's live index;
failing that, the bulletin while it is under 30 hours past its 4 pm; failing all three, CPCB's last
report marked as old. The bulletin's line stays under whichever leads.

## WHO's guideline, and what it is compared with

CPCB's index answers "how does this compare with India's standards". Residents
also meet WHO's 2021 guideline in the news, and it is much stricter: 15 µg/m³ of
PM2.5 over 24 hours against India's 60. A PM2.5 day CPCB calls *Satisfactory* can
be four times WHO's level. So each monitor's reading carries a second comparison,
*24 h avg 3.2× WHO*, beside its CPCB band.

- **A daily level is compared with a daily average, never with an hour.** WHO's
  PM levels are 24-hour averages. Setting an hourly reading against one would
  overstate every evening peak. The stations endpoint therefore averages each
  monitor's last 24 hours, first within each hour and then across hours, so a
  station reporting every 15 minutes counts each hour once.
- **A patchy day is not a day.** The average is stated only when at least 18 of
  the 24 hours have readings: 75% data capture, the rule the EU air quality
  directive sets for a daily mean. With less, the badge is omitted rather than
  guessed.
- **Guidance, not law.** WHO defines its 24-hour levels as the 99th percentile of
  a year's days, so three or four days above them are allowed. One day above is a
  comparison, not a breach, and the screen calls WHO's figure a guideline, never a
  limit. Ozone (8-hour level only) and ammonia (none) are not compared.

The levels live in `core/constants.py` and the arithmetic in `core/who.py`; the
frontend only puts the API's multiple into words.

## Google Gemini, and what it is allowed to say

Gemini does three jobs. None produces a number AirWatch publishes.

**Reading a photograph.** The haze index says how polluted a photo looks; it cannot say what is
polluting. Gemini is asked for the single most visible source, its own confidence, and one sentence
on what in the frame supports it.
- **Never a gate.** The reading happens after the submission is stored. It changes no haze index,
  trust score or calibration pair, and a Gemini outage returns the submission with a note instead.
- **It may say "nothing".** The answer includes *haze without a visible source*, *no visible
  pollution* and *not outdoor*, so the model is never forced to name a culprit.
- **Privacy first.** Gemini receives a re-encoded copy at most 1024 px wide. Re-encoding drops the
  EXIF block, which can carry the resident's exact position; the original is not stored.
- **Labelled as what it is.** The confidence is the model's own and uncalibrated, and the screen and
  PDF call the reading an AI suggestion that establishes no source.

**Writing an alert brief.** Officials skim. The brief turns an alert into two sentences and a
suggested inspection, and is the place a language model is most tempted to invent.
- **Only the alert's facts go in:** the reading, the prediction, the excess, the times in IST, and
  the ranked source with its plausibility, each number rounded once.
- **Every figure that comes out is checked** (`core/grounding.py`). A number in the brief that does
  not appear verbatim in those facts discards the whole brief with a typed error. "74.0" does not
  pass for "74": a strict check that occasionally drops a good brief costs nothing.
- **Written once, on request.** Briefs are generated when someone presses the button, then stored,
  so every reader sees the same words and a console of forty alerts does not trigger forty requests.

**Translating a complaint.** A description written in Tamil or Hindi is evidence an official in
another office may not be able to read. The PDF prints it as written and, beneath it, in English.
- **The resident's words stay the record.** The translation is labelled as a machine translation
  by Gemini, naming the language it came from, and says the words above it are the record.
- **Figures are checked here too.** A translation that states a number the original does not is
  discarded. Tamil and Devanagari numerals count as the same figures as their ASCII digits, so
  ५० translated as 50 passes.
- **The description is data, not instructions.** It is sent between tags with an instruction to
  translate anything that reads like a command rather than follow it, and the answer must fit a
  schema of language, whether it is already English, and the English text.
- **Once per text.** Translations are stored by a SHA-256 of the description, so every download of
  every report quoting the same words prints the same English. A description Gemini finds to be
  English is stored too, and not sent again.
- **Never a gate.** Without a key, or when Gemini fails, the report is produced anyway. Beside a
  description in a non-Latin script it says why no translation is shown; text in Latin letters
  is left alone, since it is most likely English already.

**Busy models.** A Gemini model can answer "high demand" for minutes. The client tries the next
model instead of retrying the same one, and records which model wrote each answer.

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
