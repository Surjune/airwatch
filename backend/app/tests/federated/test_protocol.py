"""Tests for the federation wire format."""

from __future__ import annotations

import numpy as np
import pytest
from federated.protocol import ProtocolError, pack_model, unpack_model
from federated.strategy import GlobalScaler

SCALER = GlobalScaler(mean=np.array([10.0, 20.0]), std=np.array([1.0, 2.0]))


def test_a_model_survives_the_round_trip() -> None:
    weights = np.array([0.5, -0.25, 3.0])

    decoded_weights, decoded_scaler = unpack_model(pack_model(weights, SCALER))

    np.testing.assert_array_equal(decoded_weights, weights)
    np.testing.assert_array_equal(decoded_scaler.mean, SCALER.mean)
    np.testing.assert_array_equal(decoded_scaler.std, SCALER.std)


def test_rejects_anything_that_is_not_three_arrays() -> None:
    with pytest.raises(ProtocolError, match="Expected 3 arrays"):
        unpack_model([np.zeros(3)])


def test_rejects_weights_without_an_intercept() -> None:
    # Weights must cover every feature plus the bias; one short means a node
    # would silently apply slopes to the wrong columns.
    with pytest.raises(ProtocolError, match="do not fit"):
        unpack_model([np.zeros(2), SCALER.mean, SCALER.std])


def test_rejects_a_scaler_whose_parts_disagree() -> None:
    with pytest.raises(ProtocolError, match="do not fit"):
        unpack_model([np.zeros(3), SCALER.mean, np.ones(3)])
