"""How far a regional model sits from the monitors inside its grid cell.

A model concentration is an average over tens of kilometres; a monitor measures
one street. They are expected to differ, and the size of the difference is what
decides how a modelled number may be read. So before a model hour is shown
beside a city, it is paired with every monitor reading the model covers and the
pairs are summarised the way household sensors are: a median ratio and a median
difference, established only past a minimum sample.

A monitor reading is compared with the model interpolated to its timestamp:
monitors report hour-ending averages at half-past in UTC, the model reports on
the hour, and taking the nearer hour would bias the pairing by half an hour of
the daily cycle.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta

from app.core.constants import CAMS_COMPARISON_MIN_PAIRS, CAMS_PAIR_MAX_GAP_MINUTES
from app.ml.sensor_colocation import ColocatedPair, ColocationSummary, summarise


def model_at(
    model: Mapping[datetime, float],
    moment: datetime,
    *,
    max_gap: timedelta = timedelta(minutes=CAMS_PAIR_MAX_GAP_MINUTES),
) -> float | None:
    """The model's value at a moment, interpolated between the hours either side.

    Returns None when either neighbouring hour is missing or too far away,
    rather than extrapolating from one side.
    """
    floor = moment.replace(minute=0, second=0, microsecond=0)
    if floor == moment and floor in model:
        return model[floor]
    ceiling = floor + timedelta(hours=1)
    before, after = model.get(floor), model.get(ceiling)
    if before is None or after is None:
        return None
    if moment - floor > max_gap or ceiling - moment > max_gap:
        return None
    weight = (moment - floor) / (ceiling - floor)
    return before + (after - before) * weight


def compare(
    model: Mapping[datetime, float],
    readings: Sequence[tuple[datetime, float]],
    *,
    min_pairs: int = CAMS_COMPARISON_MIN_PAIRS,
) -> ColocationSummary:
    """Summarise the model against monitor readings as model / monitor.

    A ratio above 1 means the model reads high; below 1, low.
    """
    pairs = [
        ColocatedPair(sensor_value=modelled, reference_value=value)
        for moment, value in readings
        if (modelled := model_at(model, moment)) is not None
    ]
    return summarise(pairs, min_pairs=min_pairs)
