"""Source attribution by wind back-trajectory.

Detection says a place is dirtier than it should be. Attribution asks what put
it there, which is the difference between "AQI is bad in east Delhi" and "the
excess at Anand Vihar traces upwind to a fire detected forty minutes ago at
these coordinates". Only the second is something an official can act on, and
only the second makes enforcement surgical instead of collective.

The method is a Lagrangian back-trajectory. Take the air now sitting over the
hotspot and walk it backwards through the wind field: at each step, move against
the flow by wind speed times the step. That traces where the air came from.
Candidate sources are then whatever sits near that path.

Certainty degrades with every step, and the geometry says so explicitly. The
search widens into a cone that opens with backtrack time, because both
horizontal dispersion and error in the wind field compound the further back the
trajectory runs. A source six hours upwind is inside a much broader cone than
one twenty minutes upwind, and is scored accordingly.

**What this is not.** It is not a dispersion model. It uses a single-layer wind
field sampled at one point in the city, no vertical motion, no turbulence
closure, no chemistry. It ranks plausible candidates; it does not prove
causation. Every result carries a confidence and the ranking is never presented
as a finding of fact -- naming the wrong operator in an enforcement context is
worse than naming nobody.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.constants import (
    ATTRIBUTION_CONE_HALF_ANGLE_DEG,
    ATTRIBUTION_CONE_WIDENING_DEG_PER_HOUR,
    ATTRIBUTION_DISTANCE_HALF_LIFE_M,
    ATTRIBUTION_FIRE_BASE_PRIOR,
    ATTRIBUTION_FIRE_LOOKBACK_HOURS,
    ATTRIBUTION_FIRE_REFERENCE_FRP_MW,
    ATTRIBUTION_LOCAL_SOURCE_RADIUS_M,
    ATTRIBUTION_MAX_BACKTRACK_HOURS,
    ATTRIBUTION_MAX_CANDIDATES,
    ATTRIBUTION_MIN_CONFIDENCE,
    ATTRIBUTION_STEP_MINUTES,
)
from app.core.enums import SourceType
from app.core.geo import (
    LonLat,
    angular_difference_deg,
    destination_point,
    haversine_distance_m,
    initial_bearing_deg,
    wind_from_direction_deg,
    wind_speed_ms,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

#: Seconds in an hour and minutes in an hour, for stepping the trajectory.
_SECONDS_PER_HOUR = 3600.0
_MINUTES_PER_HOUR = 60.0

#: Wind speed, in m/s, below which the air is treated as calm. Under calm
#: conditions a trajectory has no meaningful direction: pollution accumulates
#: locally rather than being carried from somewhere else, so tracing upwind
#: would invent a source that had nothing to do with it.
_CALM_THRESHOLD_MS = 0.5


@dataclass(frozen=True, slots=True)
class WindHour:
    """The wind field for one hour."""

    wind_u: float
    wind_v: float

    @property
    def speed_ms(self) -> float:
        return wind_speed_ms(self.wind_u, self.wind_v)

    @property
    def is_calm(self) -> bool:
        return self.speed_ms < _CALM_THRESHOLD_MS


@dataclass(frozen=True, slots=True)
class CandidateSource:
    """Something that might have produced the excess."""

    identifier: str
    name: str
    source_type: SourceType
    coordinates: LonLat
    emission_prior: float
    #: When the source was observed emitting, for fires. None for a registered
    #: facility, which may or may not have been active.
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    """One step of the air parcel's path backwards in time."""

    position: LonLat
    at_time: datetime
    hours_back: float
    #: Half-angle of the search cone at this point, in degrees. Grows with
    #: backtrack time as wind-field error and dispersion compound.
    cone_half_angle_deg: float


@dataclass(frozen=True, slots=True)
class Attribution:
    """A ranked candidate explanation for a hotspot."""

    source: CandidateSource
    confidence: float
    distance_m: float
    hours_upwind: float
    angular_offset_deg: float
    explanation: str


def back_trajectory(
    origin: LonLat,
    start_time: datetime,
    wind_by_hour: Mapping[datetime, WindHour],
    *,
    max_hours: int = ATTRIBUTION_MAX_BACKTRACK_HOURS,
    step_minutes: int = ATTRIBUTION_STEP_MINUTES,
) -> list[TrajectoryPoint]:
    """Trace where the air over a point came from.

    Args:
        origin: ``(lon, lat)`` of the hotspot.
        start_time: The hour the hotspot was observed, in UTC.
        wind_by_hour: Wind field keyed by hour. Hours are matched to the nearest
            available record, since station hours and weather hours do not align.
        max_hours: How far back to trace. Beyond roughly six hours a
            single-layer wind field accumulates too much error to name a source
            responsibly.
        step_minutes: Integration step.

    Returns:
        Points from the origin backwards in time, oldest last. Tracing stops
        early at a calm hour: without wind the air did not come from anywhere
        else, and continuing would invent a direction the data does not support.
    """
    step = timedelta(minutes=step_minutes)
    step_seconds = step_minutes * 60.0
    steps = int(max_hours * _MINUTES_PER_HOUR / step_minutes)

    position = origin
    at_time = start_time
    points = [
        TrajectoryPoint(
            position=origin,
            at_time=start_time,
            hours_back=0.0,
            cone_half_angle_deg=ATTRIBUTION_CONE_HALF_ANGLE_DEG,
        )
    ]

    for index in range(1, steps + 1):
        wind = _wind_for(at_time, wind_by_hour)
        if wind is None or wind.is_calm:
            break

        # The direction the wind blows *from* is the direction the air came
        # from, so stepping that way walks the parcel backwards in time.
        upwind_bearing = wind_from_direction_deg(wind.wind_u, wind.wind_v)
        position = destination_point(position, upwind_bearing, wind.speed_ms * step_seconds)
        at_time = at_time - step
        hours_back = index * step_minutes / _MINUTES_PER_HOUR

        points.append(
            TrajectoryPoint(
                position=position,
                at_time=at_time,
                hours_back=hours_back,
                cone_half_angle_deg=(
                    ATTRIBUTION_CONE_HALF_ANGLE_DEG
                    + ATTRIBUTION_CONE_WIDENING_DEG_PER_HOUR * hours_back
                ),
            )
        )

    return points


def _wind_for(at_time: datetime, wind_by_hour: Mapping[datetime, WindHour]) -> WindHour | None:
    """Find the wind record closest to a time, within half an hour."""
    exact = wind_by_hour.get(at_time)
    if exact is not None:
        return exact

    best: WindHour | None = None
    best_gap = timedelta(minutes=30)
    for candidate_time, wind in wind_by_hour.items():
        gap = abs(candidate_time - at_time)
        if gap <= best_gap:
            best_gap = gap
            best = wind
    return best


def attribute(
    origin: LonLat,
    observed_at: datetime,
    trajectory: Sequence[TrajectoryPoint],
    sources: Sequence[CandidateSource],
    *,
    min_confidence: float = ATTRIBUTION_MIN_CONFIDENCE,
    max_candidates: int = ATTRIBUTION_MAX_CANDIDATES,
) -> list[Attribution]:
    """Rank candidate sources against a back-trajectory.

    Args:
        origin: ``(lon, lat)`` of the hotspot.
        observed_at: When the hotspot was observed, in UTC.
        trajectory: The path from :func:`back_trajectory`.
        sources: Registered facilities and observed fires to consider.
        min_confidence: Candidates below this are not surfaced. Deliberately
            high: an enforcement action against the wrong operator is worse than
            no name at all.
        max_candidates: Most candidates to return.

    Returns:
        Candidates ranked by confidence, strongest first. An empty list is a
        legitimate answer meaning nothing in the registry explains the excess --
        which is itself informative, since it points at an unregistered source.
    """
    if len(trajectory) < 2:
        # No usable wind, so no directional evidence. Returning nothing is
        # correct; guessing from proximity alone would name whichever facility
        # happened to be nearest regardless of whether the air came from it.
        return []

    scored: list[Attribution] = []
    for source in sources:
        assessment = _score_source(origin, observed_at, trajectory, source)
        if assessment is not None and assessment.confidence >= min_confidence:
            scored.append(assessment)

    scored.sort(key=lambda item: item.confidence, reverse=True)
    return scored[:max_candidates]


def _score_source(
    origin: LonLat,
    observed_at: datetime,
    trajectory: Sequence[TrajectoryPoint],
    source: CandidateSource,
) -> Attribution | None:
    """Score one candidate against the trajectory, or None if it is not in the cone."""
    if not _is_temporally_plausible(observed_at, source):
        return None

    distance_m = haversine_distance_m(origin, source.coordinates)

    # A source close enough to need no transport is judged on proximity alone.
    # Insisting it lie upwind would hide precisely the local sources -- a bus
    # terminal, a landfill across the road -- that hyper-local detection exists
    # to find, especially at the low wind speeds these hotspots occur under.
    if distance_m <= ATTRIBUTION_LOCAL_SOURCE_RADIUS_M:
        distance_score = 0.5 ** (distance_m / ATTRIBUTION_DISTANCE_HALF_LIFE_M)
        return Attribution(
            source=source,
            confidence=min(1.0, distance_score * _normalised_prior(source)),
            distance_m=distance_m,
            hours_upwind=0.0,
            angular_offset_deg=0.0,
            explanation=(
                f"{source.name} sits {distance_m / 1000:.1f} km from the hotspot, "
                "close enough that no transport is required to explain the excess"
            ),
        )

    best: tuple[float, TrajectoryPoint, float] | None = None

    for point in trajectory[1:]:
        # The cone opens along the trajectory. A source counts if the bearing
        # from the hotspot to it lies within the cone's half-angle of the
        # bearing from the hotspot to this trajectory point.
        bearing_to_source = initial_bearing_deg(origin, source.coordinates)
        bearing_to_point = initial_bearing_deg(origin, point.position)
        offset = angular_difference_deg(bearing_to_source, bearing_to_point)

        if offset > point.cone_half_angle_deg:
            continue

        # Also require the source to be roughly as far upwind as this point, so
        # a facility just past the hotspot is not matched to a distant step.
        distance_to_point = haversine_distance_m(origin, point.position)
        if distance_m > distance_to_point * 2:
            continue

        angular_score = 1.0 - (offset / point.cone_half_angle_deg)
        if best is None or angular_score > best[0]:
            best = (angular_score, point, offset)

    if best is None:
        return None

    angular_score, point, offset = best
    distance_score = 0.5 ** (distance_m / ATTRIBUTION_DISTANCE_HALF_LIFE_M)
    prior = _normalised_prior(source)

    confidence = min(1.0, angular_score * distance_score * prior)

    return Attribution(
        source=source,
        confidence=confidence,
        distance_m=distance_m,
        hours_upwind=point.hours_back,
        angular_offset_deg=offset,
        explanation=(
            f"{source.name} lies {distance_m / 1000:.1f} km upwind, "
            f"{offset:.0f} degrees off the trajectory traced back "
            f"{point.hours_back:.1f} h"
        ),
    )


def _is_temporally_plausible(observed_at: datetime, source: CandidateSource) -> bool:
    """Whether a source could have been emitting in time to cause the excess."""
    if source.observed_at is None:
        # A registered facility has no single moment of emission.
        return True
    age = observed_at - source.observed_at
    if age < timedelta(0):
        # Detected after the hotspot: it cannot be the cause.
        return False
    return age <= timedelta(hours=ATTRIBUTION_FIRE_LOOKBACK_HOURS)


def _normalised_prior(source: CandidateSource) -> float:
    """Scale a source's emission prior into a multiplier near one."""
    return max(0.0, min(1.0, source.emission_prior))


def fire_to_candidate(
    identifier: str,
    coordinates: LonLat,
    observed_at: datetime,
    frp_mw: float,
    confidence: float,
) -> CandidateSource:
    """Convert a satellite fire detection into an attribution candidate.

    A fire is weighted by its radiative power, which is a proxy for how much
    smoke it is producing, and by the detection confidence. Both are scaled so a
    large blaze outranks a small field fire without letting radiative power
    overwhelm the geometry -- a huge fire in the wrong direction still did not
    cause this hotspot.
    """
    power_factor = min(2.0, frp_mw / ATTRIBUTION_FIRE_REFERENCE_FRP_MW + 0.5)
    prior = ATTRIBUTION_FIRE_BASE_PRIOR * power_factor * confidence
    return CandidateSource(
        identifier=identifier,
        name=f"Active fire ({frp_mw:.1f} MW)",
        source_type=SourceType.CROP_RESIDUE_FIRE,
        coordinates=coordinates,
        emission_prior=min(1.0, prior),
        observed_at=observed_at,
    )
