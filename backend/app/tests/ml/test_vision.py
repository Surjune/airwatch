"""Tests for haze estimation from a photograph.

The assertions that matter most are the rejections. Every way a photograph can
fail here -- darkness, blur, over-exposure -- makes clean air look dirty, so a
bug in this module does not produce an obviously broken number. It produces a
plausible-looking pollution reading from a clear day, which is the single worst
output this project can emit.

Synthetic images are used rather than fixtures because the physical claim is
directional and can be stated exactly: adding airlight to a scene must raise the
haze index, and nothing else here should.
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.constants import HAZE_MIN_EDGE_PIXELS
from app.ml.vision import (
    HazeAnalysis,
    Rejection,
    RejectionReason,
    analyse,
    dark_channel,
    downscale,
    laplacian_variance,
    luminance,
    transmission_map,
)

RNG = np.random.default_rng(20260912)

#: Comfortably above the minimum edge, so size is never the reason a test fails.
SIZE = 160


def textured_scene(brightness: float = 110.0, contrast: float = 70.0) -> np.ndarray:
    """A sharp, well-lit scene with genuinely dark pixels in most patches.

    Built from noise rather than a smooth gradient: the dark-channel prior needs
    local dark pixels, and a smooth image has none in the interior of a patch.
    """
    base = RNG.uniform(0.0, 1.0, size=(SIZE, SIZE, 3))
    return np.clip(brightness + contrast * (base - 0.5) * 2.0, 0.0, 255.0)


def add_haze(scene: np.ndarray, strength: float, airlight: float = 235.0) -> np.ndarray:
    """Composite airlight over a scene, following the scattering model.

    ``I = J t + A (1 - t)`` with a uniform transmission ``t = 1 - strength``.
    This is the forward model the analyser inverts, so it is the correct way to
    generate a test image whose true haze is known.
    """
    transmission = 1.0 - strength
    return np.clip(scene * transmission + airlight * strength, 0.0, 255.0)


class TestDarkChannel:
    def test_a_scene_with_dark_pixels_has_a_low_dark_channel(self) -> None:
        scene = textured_scene(brightness=90.0, contrast=90.0)
        assert float(dark_channel(scene).mean()) < 90.0

    def test_haze_raises_the_dark_channel(self) -> None:
        # The entire premise: airlight lifts the floor that a haze-free scene has.
        scene = textured_scene()
        clear = float(dark_channel(scene).mean())
        hazy = float(dark_channel(add_haze(scene, 0.6)).mean())

        assert hazy > clear

    def test_preserves_the_image_shape(self) -> None:
        assert dark_channel(textured_scene()).shape == (SIZE, SIZE)

    def test_rejects_a_non_rgb_array(self) -> None:
        # A greyscale or RGBA array would produce a silently wrong dark channel
        # rather than an error, so the shape is checked rather than assumed.
        with pytest.raises(ValueError, match="RGB"):
            downscale(np.zeros((SIZE, SIZE)))


class TestTransmission:
    def test_clear_air_transmits_more_than_hazy_air(self) -> None:
        scene = textured_scene()
        light = np.array([235.0, 235.0, 235.0])

        clear = float(transmission_map(scene, light).mean())
        hazy = float(transmission_map(add_haze(scene, 0.7), light).mean())

        assert clear > hazy

    def test_transmission_stays_within_bounds(self) -> None:
        scene = add_haze(textured_scene(), 0.4)
        light = np.array([200.0, 210.0, 220.0])

        transmission = transmission_map(scene, light)

        assert float(transmission.min()) >= 0.0
        assert float(transmission.max()) <= 1.0


class TestAnalyse:
    def test_reports_haze_rising_with_added_airlight(self) -> None:
        # Monotonicity is the property a calibration depends on. If the index did
        # not rise with haze, fitting it against reference readings would produce
        # a relation with no physical content.
        scene = textured_scene()
        indices: list[float] = []
        for strength in (0.0, 0.2, 0.4, 0.6):
            result = analyse(add_haze(scene, strength))
            assert isinstance(result, HazeAnalysis)
            indices.append(result.haze_index)

        assert indices == sorted(indices)

    def test_the_index_and_the_transmission_are_complements(self) -> None:
        result = analyse(add_haze(textured_scene(), 0.3))
        assert isinstance(result, HazeAnalysis)

        assert result.haze_index == pytest.approx(1.0 - result.transmission)

    def test_the_index_is_bounded(self) -> None:
        for strength in (0.0, 0.5, 0.95):
            result = analyse(add_haze(textured_scene(), strength))
            assert isinstance(result, HazeAnalysis)
            assert 0.0 <= result.haze_index <= 1.0

    def test_reports_the_conditions_the_estimate_was_made_under(self) -> None:
        # Carried so a reviewer can see whether the photo was marginal, rather
        # than having to trust a bare number.
        result = analyse(textured_scene())
        assert isinstance(result, HazeAnalysis)

        assert result.mean_luminance > 0
        assert result.sharpness > 0
        assert result.transmission_spread >= 0


class TestRejections:
    def test_a_night_photograph_is_refused(self) -> None:
        # In darkness the dark channel is low everywhere, so clear air and thick
        # haze are indistinguishable. Guessing would be guessing in the
        # direction of "clean".
        result = analyse(textured_scene(brightness=15.0, contrast=10.0))

        assert isinstance(result, Rejection)
        assert result.reason is RejectionReason.TOO_DARK

    def test_an_over_exposed_photograph_is_refused(self) -> None:
        result = analyse(np.full((SIZE, SIZE, 3), 250.0))

        assert isinstance(result, Rejection)
        assert result.reason is RejectionReason.TOO_BRIGHT

    def test_a_blurred_photograph_is_refused(self) -> None:
        # The most dangerous case: blur removes exactly the contrast haze
        # removes, so a blurred photo of clean air reads as polluted air.
        flat = np.full((SIZE, SIZE, 3), 120.0)

        result = analyse(flat)

        assert isinstance(result, Rejection)
        assert result.reason is RejectionReason.OUT_OF_FOCUS

    def test_a_tiny_photograph_is_refused(self) -> None:
        small = HAZE_MIN_EDGE_PIXELS - 1
        result = analyse(RNG.uniform(60.0, 200.0, size=(small, small, 3)))

        assert isinstance(result, Rejection)
        assert result.reason is RejectionReason.TOO_SMALL

    def test_every_rejection_explains_itself(self) -> None:
        # The submitter has to be able to act on the refusal, so each reason
        # carries prose rather than only a code.
        for image in (
            textured_scene(brightness=10.0, contrast=5.0),
            np.full((SIZE, SIZE, 3), 252.0),
            np.full((SIZE, SIZE, 3), 120.0),
        ):
            result = analyse(image)
            assert isinstance(result, Rejection)
            assert len(result.detail) > 20


class TestDownscale:
    def test_reduces_a_large_image(self) -> None:
        large = RNG.uniform(0.0, 255.0, size=(2000, 1500, 3))
        assert max(downscale(large).shape[:2]) <= 512

    def test_leaves_a_small_image_alone(self) -> None:
        scene = textured_scene()
        assert downscale(scene).shape == scene.shape

    def test_does_not_smooth_away_the_dark_pixels(self) -> None:
        # Decimation rather than averaging, deliberately. An averaging resize is
        # a low-pass filter and would raise the dark channel, making every
        # downscaled photograph look hazier than it is.
        large = np.tile(textured_scene(), (8, 8, 1))

        before = float(dark_channel(large).mean())
        after = float(dark_channel(downscale(large)).mean())

        assert after == pytest.approx(before, abs=12.0)


class TestHelpers:
    def test_luminance_weights_green_most(self) -> None:
        red = np.zeros((4, 4, 3))
        red[:, :, 0] = 255.0
        green = np.zeros((4, 4, 3))
        green[:, :, 1] = 255.0

        assert float(luminance(green).mean()) > float(luminance(red).mean())

    def test_sharpness_separates_texture_from_flatness(self) -> None:
        assert laplacian_variance(luminance(textured_scene())) > laplacian_variance(
            luminance(np.full((SIZE, SIZE, 3), 120.0))
        )

    def test_sharpness_of_a_degenerate_plane_is_zero(self) -> None:
        assert laplacian_variance(np.zeros((2, 2))) == 0.0
