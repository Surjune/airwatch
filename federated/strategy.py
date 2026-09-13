"""Federated aggregation: FedAvg, FedProx, and the check that keeps it honest.

The federated design exists for a governance reason, not a technical one. No
state pollution control board will hand another its raw monitoring data, and
every attempt at a single national data lake has stalled on that rather than on
bandwidth. Model weights are not raw data, so they can cross a boundary that
observations cannot.

**Why a linear model.** FedAvg averages parameters. A gradient-boosted ensemble
has no averageable parameter vector -- two forests cannot be meaningfully
averaged into a third -- so the method itself forces a model with weights. That
is not a compromise here: leave-one-station-out and forecast validation both
found simple estimators beating gradient boosting at this data volume, so a
regularised linear model is what the data supports anyway.

**Why features are standardised from shared statistics.** Averaging coefficients
is only meaningful if every node's features are on the same scale. Nodes
therefore exchange per-feature count, sum and sum of squares first, and the
server builds one scaler from those. Aggregate statistics are not observations:
no reading, station or location leaves a node, which is the property the whole
arrangement depends on.

**Why a negative-transfer check.** Federation is asserted to help data-poor
cities. That is a claim, and this module is built to be able to refute it: each
node compares the global model against its own local one on its own held-out
data, and the result is reported per node rather than averaged into a headline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

#: Smallest standard deviation treated as real. A feature that is constant
#: across a node -- a single-station city where every row shares a value --
#: would otherwise divide by zero and produce infinite standardised features.
_MIN_STD = 1e-8


@dataclass(frozen=True, slots=True)
class FeatureStats:
    """Per-feature summary a node shares so a common scaler can be built.

    Counts and sums only. These describe the shape of a node's data without
    revealing any row of it, which is what lets them cross a boundary that the
    observations themselves cannot.
    """

    count: int
    total: np.ndarray
    total_squares: np.ndarray


@dataclass(frozen=True, slots=True)
class GlobalScaler:
    """Feature means and standard deviations agreed across the federation."""

    mean: np.ndarray
    std: np.ndarray

    def transform(self, features: np.ndarray) -> np.ndarray:
        """Standardise a feature matrix."""
        scaled: np.ndarray = (features - self.mean) / np.maximum(self.std, _MIN_STD)
        return scaled


@dataclass(frozen=True, slots=True)
class LocalUpdate:
    """What one node returns from a round of local training."""

    node: str
    weights: np.ndarray
    #: Rows the node trained on. FedAvg weights by this, so a city with sixty
    #: stations counts for more than one with three -- which is correct, and is
    #: also exactly why the small node has to be checked for harm separately.
    sample_count: int


def aggregate_statistics(stats: Sequence[FeatureStats]) -> GlobalScaler:
    """Build one scaler from every node's summary statistics.

    Raises:
        ValueError: No statistics were supplied, or they describe no rows.
    """
    if not stats:
        raise ValueError("Cannot build a scaler with no node statistics.")

    total_count = sum(item.count for item in stats)
    if total_count == 0:
        raise ValueError("Node statistics describe zero samples.")

    total = np.sum([item.total for item in stats], axis=0)
    total_squares = np.sum([item.total_squares for item in stats], axis=0)

    mean = total / total_count
    # Variance from the aggregate: E[x^2] - E[x]^2, clipped because floating
    # point can push a near-zero variance slightly negative.
    variance = np.maximum(total_squares / total_count - mean**2, 0.0)
    return GlobalScaler(mean=mean, std=np.sqrt(variance))


def compute_statistics(features: np.ndarray) -> FeatureStats:
    """Summarise a node's features for sharing."""
    return FeatureStats(
        count=len(features),
        total=features.sum(axis=0),
        total_squares=(features**2).sum(axis=0),
    )


def federated_average(updates: Sequence[LocalUpdate]) -> np.ndarray:
    """Combine node weights into one global model, weighted by sample count.

    Raises:
        ValueError: No updates were supplied, or they describe no samples.
    """
    if not updates:
        raise ValueError("Cannot aggregate an empty set of updates.")

    total_samples = sum(update.sample_count for update in updates)
    if total_samples == 0:
        raise ValueError("Updates describe zero samples.")

    stacked = np.stack([update.weights for update in updates])
    weights = np.array([update.sample_count for update in updates], dtype=float)
    return np.average(stacked, axis=0, weights=weights)


def train_local(
    features: np.ndarray,
    targets: np.ndarray,
    *,
    initial_weights: np.ndarray,
    global_weights: np.ndarray | None = None,
    epochs: int = 50,
    learning_rate: float = 0.05,
    l2: float = 0.01,
    proximal_mu: float = 0.0,
) -> np.ndarray:
    """Run one node's local training for a round.

    Plain gradient descent on a ridge objective, plus the FedProx proximal term
    when ``proximal_mu`` is non-zero.

    Args:
        features: Standardised feature matrix, with a bias column already added.
        targets: Observed values.
        initial_weights: Where this round starts, normally the global model.
        global_weights: The global model the proximal term pulls toward.
        epochs: Local gradient steps.
        learning_rate: Step size.
        l2: Ridge penalty.
        proximal_mu: FedProx strength. Constrains a node from drifting far from
            the global model during local training, which is what stops a
            heavily non-IID node -- Delhi in November against Coimbatore in June
            -- from dragging aggregation somewhere that suits neither.

    Returns:
        The node's updated weights.
    """
    weights = initial_weights.copy()
    anchor = global_weights if global_weights is not None else initial_weights
    sample_count = max(len(features), 1)

    for _ in range(epochs):
        residual = features @ weights - targets
        gradient = features.T @ residual / sample_count + l2 * weights
        if proximal_mu:
            gradient = gradient + proximal_mu * (weights - anchor)
        weights = weights - learning_rate * gradient

    return weights


def fine_tune(
    global_weights: np.ndarray,
    features: np.ndarray,
    targets: np.ndarray,
    *,
    epochs: int,
    learning_rate: float = 0.05,
    l2: float = 0.01,
    proximal_mu: float = 0.0,
) -> np.ndarray:
    """Personalise the global model to one node by continuing training locally.

    The node starts from what the federation learned and takes a few steps on its
    own data. This is the standard answer to non-IID harm: the shared model
    supplies a starting point a sparse node could not reach alone, and the local
    steps move it back toward the regime the node actually lives in. With a
    non-zero ``proximal_mu`` the steps are anchored to the global model, so a
    node with very little data cannot simply overfit its way back to local-only.

    Args:
        global_weights: The federated model, the starting point.
        features: This node's standardised training features, with a bias column.
        targets: This node's training targets. Never its held-out data.
        epochs: Local steps.
        learning_rate: Step size.
        l2: Ridge penalty.
        proximal_mu: Pull back toward the global model.

    Returns:
        The node's personalised weights. The global model is not modified.
    """
    return train_local(
        features,
        targets,
        initial_weights=global_weights,
        global_weights=global_weights,
        epochs=epochs,
        learning_rate=learning_rate,
        l2=l2,
        proximal_mu=proximal_mu,
    )


def refit_intercept(
    global_weights: np.ndarray, features: np.ndarray, targets: np.ndarray
) -> np.ndarray:
    """Keep the shared slopes, and give the node its own baseline level.

    A shared representation with a local head, in its simplest linear form. The
    federation's feature weights -- how lags, time of day and climatology relate
    to the next day's value -- are kept, because that relationship is what many
    cities' data can estimate better than one city's. Only the intercept is refit,
    in closed form, to the node's own mean residual, because the level of
    pollution is exactly what differs most between a clean city and a dirty one.

    Kanpur's point estimates under plain averaging suggest it is pulled toward
    Delhi's harder, dirtier regime -- not established, on 23 held-out rows -- and
    that is largely a difference of level; this is the cheapest change that
    could undo it.

    Args:
        global_weights: The federated model, whose last weight is the intercept.
        features: This node's standardised training features, with a bias column.
        targets: This node's training targets.

    Returns:
        A copy of the global weights with the intercept replaced.
    """
    weights = global_weights.copy()
    residual = targets - features @ global_weights
    # The bias column is constant 1, so shifting its weight by the mean residual
    # is the least-squares intercept for fixed slopes.
    weights[-1] = global_weights[-1] + float(np.mean(residual))
    return weights


def run_in_process(
    training_sets: Sequence[tuple[str, np.ndarray, np.ndarray]],
    *,
    rounds: int,
    local_epochs: int,
    learning_rate: float,
    l2: float,
    proximal_mu: float,
) -> tuple[np.ndarray, GlobalScaler]:
    """Run the whole federation in one process, with no transport.

    The reference the Flower transport is held to: every step here is
    deterministic, so a run across processes must reproduce these weights
    exactly, and a transport that does not has a bug rather than a variance.

    Args:
        training_sets: ``(node, features, targets)`` per node, unscaled.
        rounds: Training rounds after the statistics exchange.
        local_epochs: Local steps per round.
        learning_rate: Step size.
        l2: Ridge penalty.
        proximal_mu: FedProx strength.

    Returns:
        The global weights and the scaler they assume.
    """
    scaler = aggregate_statistics(
        [compute_statistics(features) for _, features, _ in training_sets]
    )
    global_weights = np.zeros(len(scaler.mean) + 1)

    for _ in range(rounds):
        updates = [
            LocalUpdate(
                node=node,
                weights=train_local(
                    add_bias_column(scaler.transform(features)),
                    targets,
                    initial_weights=global_weights,
                    global_weights=global_weights,
                    epochs=local_epochs,
                    learning_rate=learning_rate,
                    l2=l2,
                    proximal_mu=proximal_mu,
                ),
                sample_count=len(targets),
            )
            for node, features, targets in training_sets
        ]
        global_weights = federated_average(updates)

    return global_weights, scaler


def add_bias_column(features: np.ndarray) -> np.ndarray:
    """Append a constant column so the model can fit an intercept."""
    return np.hstack([features, np.ones((len(features), 1))])


def mean_absolute_error(features: np.ndarray, targets: np.ndarray, weights: np.ndarray) -> float:
    """Mean absolute error of a linear model."""
    return float(np.mean(np.abs(features @ weights - targets)))
