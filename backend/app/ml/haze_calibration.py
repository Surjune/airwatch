"""Fitting a haze index to a concentration, from co-located observations.

This is the step that decides whether the citizen tier produces a number at all.

A photograph gives a dimensionless haze index. Turning that into micrograms per
cubic metre requires an empirical relation, and the only defensible source for
one is this network's own data: submissions taken near a reference monitor pair
a haze index with a measured concentration, and enough of those pairs fit a
relation whose error can be stated.

Two properties are deliberate:

* **Below the minimum sample, nothing is published.** Not a rough number, not a
  wide interval -- nothing. A concentration fitted from eight points would carry
  an error larger than the range it was predicting, and publishing it would mean
  a citizen reading a figure that the system itself cannot stand behind.
* **The error is measured by leave-one-out, not on the training points.** With a
  sample this small, in-sample error is close to meaningless: the fit has seen
  every point it is being scored on. Leave-one-out asks the question that
  matters -- how wrong is this on a photograph it has not seen.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from app.core.constants import CITIZEN_CALIBRATION_MIN_PAIRS

#: Smallest spread of haze indices that can support a slope. If every pair was
#: taken in identical conditions the fit has no leverage, and extrapolating from
#: it would produce confident nonsense away from that one point.
_MIN_HAZE_SPREAD = 0.02

#: Pairs needed before leave-one-out can be computed at all.
_MIN_PAIRS_FOR_HOLDOUT = 3


@dataclass(frozen=True, slots=True)
class CalibrationPair:
    """One photograph taken close enough to a monitor to be compared with it."""

    haze_index: float
    reference_value: float


@dataclass(frozen=True, slots=True)
class HazeEstimate:
    """A concentration derived from a haze index, with its measured error."""

    value: float
    uncertainty: float

    @property
    def upper_bound(self) -> float:
        """Value plus uncertainty, which is what a precautionary decision uses."""
        return self.value + self.uncertainty


@dataclass(frozen=True, slots=True)
class HazeCalibration:
    """A fitted relation between haze index and concentration."""

    slope: float
    intercept: float

    #: Leave-one-out mean absolute error, in the concentration's units.
    mae: float

    #: Pairs the fit was built from, published so a consumer can weigh it.
    pairs: int

    #: Range of haze indices the fit was trained across. An index outside this
    #: is an extrapolation and is reported as such rather than silently
    #: evaluated.
    haze_min: float
    haze_max: float

    def estimate(self, haze_index: float) -> HazeEstimate:
        """Apply the relation to a haze index.

        Concentrations are clamped at zero: the fit is linear and a clear
        photograph can otherwise produce a negative concentration, which is not
        a value any consumer should have to reason about.
        """
        value = max(0.0, self.slope * haze_index + self.intercept)
        return HazeEstimate(value=value, uncertainty=self.mae)

    def is_extrapolating(self, haze_index: float) -> bool:
        """Whether this index sits outside the range the fit was built on."""
        return haze_index < self.haze_min or haze_index > self.haze_max


def _fit_line(haze: np.ndarray, reference: np.ndarray) -> tuple[float, float]:
    """Least-squares slope and intercept."""
    design = np.column_stack([haze, np.ones_like(haze)])
    solution, *_ = np.linalg.lstsq(design, reference, rcond=None)
    return float(solution[0]), float(solution[1])


def _leave_one_out_mae(haze: np.ndarray, reference: np.ndarray) -> float:
    """Mean absolute error when each point is predicted by a fit excluding it.

    The honest error for a sample this size. Scoring on the training points
    would report how well the line remembers, not how well it generalises.
    """
    errors: list[float] = []
    for index in range(haze.size):
        mask = np.ones(haze.size, dtype=bool)
        mask[index] = False
        if np.ptp(haze[mask]) < _MIN_HAZE_SPREAD:
            continue
        slope, intercept = _fit_line(haze[mask], reference[mask])
        predicted = max(0.0, slope * float(haze[index]) + intercept)
        errors.append(abs(predicted - float(reference[index])))

    if not errors:
        return float("inf")
    return float(np.mean(errors))


def fit(pairs: Sequence[CalibrationPair]) -> HazeCalibration | None:
    """Fit the haze-to-concentration relation.

    Args:
        pairs: Co-located observations, in any order.

    Returns:
        The fitted relation, or None when the sample cannot support one --
        because there are too few pairs, or because they span too narrow a range
        of haze to establish a slope. None means the citizen tier reports a haze
        index and no concentration, which is the correct answer rather than a
        degraded one.
    """
    if len(pairs) < CITIZEN_CALIBRATION_MIN_PAIRS:
        return None

    haze = np.array([pair.haze_index for pair in pairs], dtype=np.float64)
    reference = np.array([pair.reference_value for pair in pairs], dtype=np.float64)

    if float(np.ptp(haze)) < _MIN_HAZE_SPREAD:
        return None

    slope, intercept = _fit_line(haze, reference)

    mae = (
        _leave_one_out_mae(haze, reference)
        if haze.size >= _MIN_PAIRS_FOR_HOLDOUT
        else float("inf")
    )
    if not np.isfinite(mae):
        return None

    return HazeCalibration(
        slope=slope,
        intercept=intercept,
        mae=mae,
        pairs=len(pairs),
        haze_min=float(haze.min()),
        haze_max=float(haze.max()),
    )
