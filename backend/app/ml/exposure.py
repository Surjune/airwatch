"""Choosing when to travel, from the shape of the day.

The forecast this rests on is a diurnal climatology, and its limits are already
recorded: it has no day-to-day skill and cannot say whether Friday will be worse
than Thursday. What it does resolve is the shape of an average day, and that
turns out to be exactly what a timing decision needs. "Is three in the afternoon
better than eight in the morning on this route" is answerable from a
climatology; "will tomorrow be bad" is not.

So the advisory is built on the one thing the estimator is genuinely good at,
rather than on the thing it was originally hoped to do.

**Exposure, not inhaled mass.** The quantity here is concentration multiplied by
time, in ug/m3 x minutes. Converting that into micrograms actually inhaled needs
a ventilation rate, which depends on the person, their age and how hard they are
working -- and inventing one would add a fabricated factor to a number that is
useful without it. The comparison between departure times is unaffected either
way, and the comparison is the part anyone acts on.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from app.core.constants import EXPOSURE_MEANINGFUL_REDUCTION, EXPOSURE_TRAVEL_SPEED_KMH

#: Minutes in an hour, for turning a travel time into exposure minutes.
_MINUTES_PER_HOUR = 60.0


@dataclass(frozen=True, slots=True)
class RouteSample:
    """One point along a route, with the concentration expected there."""

    distance_along_km: float
    value: float


@dataclass(frozen=True, slots=True)
class DepartureOption:
    """What travelling this route at one hour would cost in exposure."""

    hour: int

    #: Concentration times time, in ug/m3 x minutes.
    exposure: float

    #: Time-weighted mean concentration along the route, in ug/m3.
    mean_concentration: float

    #: Minutes spent travelling.
    travel_minutes: float


@dataclass(frozen=True, slots=True)
class Advisory:
    """A recommendation, or an explicit refusal to make one."""

    options: list[DepartureOption]
    best: DepartureOption | None
    worst: DepartureOption | None

    #: Fraction of exposure avoided by taking the best option over the worst.
    reduction: float

    #: True when the spread across the day is large enough to act on. Reported
    #: rather than hidden: recommending an hour on a 3% difference would dress
    #: noise as advice, and the forecast's own error is far larger than that.
    is_meaningful: bool

    explanation: str


def route_exposure(
    samples: Sequence[RouteSample],
    *,
    speed_kmh: float = EXPOSURE_TRAVEL_SPEED_KMH,
) -> tuple[float, float, float]:
    """Exposure, mean concentration and travel time for one traversal.

    Each pair of samples defines a segment, and the segment is weighted by how
    long is spent in it rather than by how many samples fall there. Weighting by
    sample count instead would let a densely sampled clean stretch outvote a
    short filthy one, which inverts the thing being measured.

    Returns:
        ``(exposure, mean concentration, travel minutes)``. All zero when the
        route has fewer than two samples, which is the honest answer for a route
        nothing supports.
    """
    if len(samples) < 2 or speed_kmh <= 0:
        return 0.0, 0.0, 0.0

    ordered = sorted(samples, key=lambda sample: sample.distance_along_km)

    exposure = 0.0
    minutes = 0.0

    for current, following in pairwise(ordered):
        segment_km = following.distance_along_km - current.distance_along_km
        if segment_km <= 0:
            continue
        segment_minutes = (segment_km / speed_kmh) * _MINUTES_PER_HOUR
        # The segment is represented by the mean of its endpoints -- the
        # trapezoid rule -- which is nearer the truth than taking either end.
        segment_value = (current.value + following.value) / 2.0

        exposure += segment_value * segment_minutes
        minutes += segment_minutes

    mean = exposure / minutes if minutes > 0 else 0.0
    return exposure, mean, minutes


def advise(
    options: Sequence[DepartureOption],
    *,
    meaningful_reduction: float = EXPOSURE_MEANINGFUL_REDUCTION,
) -> Advisory:
    """Rank departure times and say whether the difference is worth acting on.

    Args:
        options: One entry per candidate departure hour.
        meaningful_reduction: Relative saving below which the spread across the
            day is treated as noise rather than as a finding.

    Returns:
        The ranking, with the recommendation explicitly withheld when the day is
        flat. A system that always names a best hour would be giving advice on
        days when it has none to give.
    """
    usable = [option for option in options if option.exposure > 0]
    if not usable:
        return Advisory(
            options=list(options),
            best=None,
            worst=None,
            reduction=0.0,
            is_meaningful=False,
            explanation=(
                "No forecast was available along this route, so no timing advice can "
                "be given. That is unknown ground rather than clean air."
            ),
        )

    best = min(usable, key=lambda option: option.exposure)
    worst = max(usable, key=lambda option: option.exposure)
    reduction = (worst.exposure - best.exposure) / worst.exposure if worst.exposure > 0 else 0.0
    meaningful = reduction >= meaningful_reduction

    if meaningful:
        explanation = (
            f"Travelling at {best.hour:02d}:00 rather than {worst.hour:02d}:00 avoids about "
            f"{reduction:.0%} of the exposure on this route. That is the shape of an "
            "average day, not a forecast for any particular one: the estimator resolves "
            "the daily cycle and has no day-to-day skill."
        )
    else:
        explanation = (
            f"Departure time makes little difference on this route -- about {reduction:.0%} "
            "between best and worst, which is smaller than the forecast's own error. "
            "Recommending an hour on that would be dressing noise as advice."
        )

    return Advisory(
        options=sorted(options, key=lambda option: option.hour),
        best=best,
        worst=worst,
        reduction=reduction,
        is_meaningful=meaningful,
        explanation=explanation,
    )
