"""How far household sensors sit from the reference monitors beside them.

A low-cost optical sensor is not wrong at random. It over-reads in humid air,
when hygroscopic particles swell into the size range it counts, and by an amount
that differs between models. That is what makes the tier fixable: a systematic
bias can be measured against a monitor and removed. It is also what makes it
dangerous to show unexamined, because a consistent over-read looks exactly like
a real neighbourhood hotspot.

This module only measures. It summarises co-located pairs -- a citizen reading
and the reference reading nearest it in space and time -- into a median ratio
and a median difference. Medians rather than means, because one sensor in a
kitchen beside a stove is an outlier that a mean would spread across every
correction. Nothing is applied to any reading here: below the minimum sample the
ratio is reported as unestablished, and a reader is told why.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import median

from app.core.constants import CITIZEN_SENSOR_BIAS_MIN_PAIRS


@dataclass(frozen=True, slots=True)
class ColocatedPair:
    """A citizen sensor reading and the reference reading it was checked against."""

    sensor_value: float
    reference_value: float


@dataclass(frozen=True, slots=True)
class ColocationSummary:
    """What the pairs so far say about the tier's bias."""

    pairs: int
    pairs_needed: int
    #: Median of sensor / reference. Above 1 means sensors read high.
    median_ratio: float | None
    #: Median of sensor - reference, in ug/m3.
    median_difference: float | None
    #: True once there are enough pairs for the ratio to be read as a bias.
    is_established: bool


def relative_difference(sensor_value: float, reference_value: float) -> float | None:
    """Signed difference as a fraction of the reference, or None against a zero reference.

    A zero reference is not an error -- clean air after rain reads near zero --
    but a ratio against it is undefined, and returning a large number would read
    as a sensor wildly over-reading.
    """
    if reference_value <= 0:
        return None
    return (sensor_value - reference_value) / reference_value


def summarise(
    pairs: Sequence[ColocatedPair], *, min_pairs: int = CITIZEN_SENSOR_BIAS_MIN_PAIRS
) -> ColocationSummary:
    """Summarise co-located pairs into a bias estimate.

    Pairs against a zero reference count towards the difference but not the
    ratio, for the reason given in :func:`relative_difference`.

    Returns:
        The summary. With no pairs both statistics are None; with some, they are
        computed and reported, and ``is_established`` says whether there are
        enough of them to act on.
    """
    if not pairs:
        return ColocationSummary(
            pairs=0,
            pairs_needed=min_pairs,
            median_ratio=None,
            median_difference=None,
            is_established=False,
        )

    ratios = [
        pair.sensor_value / pair.reference_value for pair in pairs if pair.reference_value > 0
    ]
    return ColocationSummary(
        pairs=len(pairs),
        pairs_needed=min_pairs,
        median_ratio=median(ratios) if ratios else None,
        median_difference=median(pair.sensor_value - pair.reference_value for pair in pairs),
        is_established=len(pairs) >= min_pairs,
    )
