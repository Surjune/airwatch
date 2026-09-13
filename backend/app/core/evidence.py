"""Deciding whether a measured difference between two models is real.

A point estimate on a small holdout is not a finding. The federated experiment
reported Kanpur's error rising from 9.21 to 9.85 under averaging, and that was
published as "federation measurably harmed Kanpur" -- on 23 held-out rows. A
paired bootstrap over those rows puts the harm's 95% interval at roughly -2 to
+3 ug/m3: the data cannot distinguish harm from no effect at all. The claim was
stated with a certainty the evidence never had.

This module is the single definition of the rule that replaces it, used both by
the validation experiment that produces the numbers and by the API that
publishes them, so the two cannot disagree about what counts as evidence.

**Two conditions, not one.** An effect is called helped or harmed only when its
interval excludes zero *and* its size clears a practical tolerance. The first
guards against noise on a small holdout; the second against the opposite
mistake on a large one, where 493 rows can make a 0.2% difference
statistically certain and still practically meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.core.constants import BOOTSTRAP_CONFIDENCE, BOOTSTRAP_RESAMPLES

#: Percentage points in a whole, for turning coverage into percentile bounds.
_PERCENT = 100.0


class Effect(StrEnum):
    """What the evidence supports about a candidate model against a baseline."""

    HELPED = "helped"
    HARMED = "harmed"

    #: The interval excludes zero but the effect is too small to act on.
    NO_PRACTICAL_DIFFERENCE = "no_practical_difference"

    #: The interval includes zero: the data cannot tell this apart from no effect.
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class EffectEstimate:
    """A measured difference with its uncertainty.

    ``gain`` is in the error's units and positive when the candidate is better,
    so "higher is better" holds for every field.
    """

    gain: float
    low: float
    high: float
    samples: int


def paired_bootstrap(
    baseline_errors: np.ndarray,
    candidate_errors: np.ndarray,
    *,
    resamples: int = BOOTSTRAP_RESAMPLES,
    confidence: float = BOOTSTRAP_CONFIDENCE,
    seed: int,
) -> EffectEstimate:
    """Interval on how much better a candidate is than a baseline.

    Paired rather than independent: both models are scored on the same rows, so
    resampling rows keeps each row's two errors together. Treating them as
    independent samples would ignore that some rows are hard for every model and
    inflate the interval.

    Args:
        baseline_errors: Absolute error of the baseline on each held-out row.
        candidate_errors: Absolute error of the candidate on the same rows.
        resamples: Bootstrap draws.
        confidence: Two-sided coverage of the interval.
        seed: Required rather than defaulted, so every published interval can be
            reproduced exactly.

    Raises:
        ValueError: The arrays differ in length or are empty.
    """
    if baseline_errors.shape != candidate_errors.shape:
        raise ValueError("Paired errors must be scored on the same rows.")
    if baseline_errors.size == 0:
        raise ValueError("Cannot bootstrap an empty holdout.")

    differences = baseline_errors - candidate_errors
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, differences.size, size=(resamples, differences.size))
    means = differences[draws].mean(axis=1)

    tail = (1.0 - confidence) / 2.0 * _PERCENT
    low, high = np.percentile(means, [tail, _PERCENT - tail])
    return EffectEstimate(
        gain=float(differences.mean()),
        low=float(low),
        high=float(high),
        samples=int(differences.size),
    )


def classify(estimate: EffectEstimate, *, baseline_error: float, tolerance: float) -> Effect:
    """What an estimate supports, requiring both significance and size.

    Args:
        estimate: The measured gain and its interval.
        baseline_error: The baseline's mean error, to express the gain relatively.
        tolerance: Relative gain below which a real difference is still too
            small to change what anyone should do.
    """
    if estimate.low <= 0.0 <= estimate.high:
        return Effect.INCONCLUSIVE

    relative = estimate.gain / baseline_error if baseline_error > 0 else 0.0
    if abs(relative) < tolerance:
        return Effect.NO_PRACTICAL_DIFFERENCE
    return Effect.HELPED if estimate.gain > 0 else Effect.HARMED
