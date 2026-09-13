"""What crosses the wire between the federation server and a city node.

A federation run has two phases, and the phase travels in each round's config:

1. **statistics** -- the node returns per-feature sums and sums of squares, and
   the server builds one scaler from them. Counts and sums, never rows.
2. **train** -- the server sends the global weights with the agreed scaler; the
   node returns weights trained on its own data.

Kept free of Flower imports so both ends, and their tests, agree on the format
without a running transport.
"""

from __future__ import annotations

import numpy as np

from federated.strategy import GlobalScaler

#: Config key naming the phase of a round.
PHASE_KEY = "phase"

#: Phase in which nodes share feature statistics.
STATISTICS_PHASE = "statistics"

#: Phase in which nodes train on the global model.
TRAIN_PHASE = "train"

#: Config key carrying the FedProx proximal strength for a training round.
PROXIMAL_MU_KEY = "proximal_mu"

#: Metric key a node uses to name itself in evaluation results. Evaluation
#: reports only the node's name and its error, never a row of its data.
NODE_KEY = "node"

#: A model on the wire is exactly three arrays: weights, scaler mean, scaler std.
_MODEL_ARRAYS = 3


class ProtocolError(ValueError):
    """A message did not match the federation protocol."""


def pack_model(weights: np.ndarray, scaler: GlobalScaler) -> list[np.ndarray]:
    """Encode the global model and the scaler its weights assume."""
    return [weights, scaler.mean, scaler.std]


def unpack_model(arrays: list[np.ndarray]) -> tuple[np.ndarray, GlobalScaler]:
    """Decode a model sent by :func:`pack_model`.

    Raises:
        ProtocolError: The arrays are not a model, or the weights do not fit the
            scaler -- one weight per feature plus the intercept.
    """
    if len(arrays) != _MODEL_ARRAYS:
        raise ProtocolError(f"Expected {_MODEL_ARRAYS} arrays for a model, got {len(arrays)}.")
    weights, mean, std = arrays
    if mean.shape != std.shape or weights.shape != (mean.shape[0] + 1,):
        raise ProtocolError(
            f"Weights of shape {weights.shape} do not fit a scaler over {mean.shape[0]} features."
        )
    return weights, GlobalScaler(mean=mean, std=std)
