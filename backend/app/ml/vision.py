"""Estimating atmospheric haze from a photograph.

**What this does and does not claim.** A photograph cannot measure PM2.5. What
it can measure is how much contrast the atmosphere has removed between the
camera and the scene, and that is a real physical quantity: the dark-channel
prior (He, Sun and Tang, CVPR 2009) recovers a transmission map, and the
transmission is ``exp(-beta * d)`` for extinction coefficient ``beta`` over
scene depth ``d``.

The problem is ``d``. Recovering an absolute extinction coefficient needs the
distance to what was photographed, and a single image does not contain it. So
this module stops where the physics stops: it returns a dimensionless haze
index in [0, 1], and nothing here converts that to a concentration.

That conversion is deliberately somewhere else, fitted against co-located
reference monitors, because an uncalibrated concentration derived from a
photograph is a fabricated reading -- and in a public-health context a wrong
number is worse than no number. The honest sequence is: photograph gives haze
index, haze index near a reference station gives a calibration pair, enough
pairs give a relation with a measured error, and only then does a photograph
taken away from any station produce a concentration.

Three failure modes are checked before any of that, because each one makes a
clear day look hazy and would be invisible in the output:

* **Darkness.** The prior assumes a lit outdoor scene. At night the dark channel
  is low everywhere and clear air is indistinguishable from thick haze.
* **Blur.** Defocus removes the same high-frequency contrast haze removes, so a
  blurred photograph of clear air reads as a sharp photograph of dirty air.
* **Blown-out exposure.** The prior needs something dark in the frame. If
  nothing is, there is no signal to measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from app.core.constants import (
    HAZE_ANALYSIS_MAX_EDGE_PIXELS,
    HAZE_ATMOSPHERIC_LIGHT_FRACTION,
    HAZE_DCP_OMEGA,
    HAZE_DCP_PATCH_PIXELS,
    HAZE_MAX_MEAN_LUMINANCE,
    HAZE_MIN_EDGE_PIXELS,
    HAZE_MIN_LAPLACIAN_VARIANCE,
    HAZE_MIN_MEAN_LUMINANCE,
)

#: Largest value a channel can hold in an 8-bit image.
_MAX_CHANNEL_VALUE = 255.0

#: Luminance weights for Rec. 601 greyscale conversion, which approximates
#: perceived brightness better than a plain channel mean.
_LUMINANCE_WEIGHTS = (0.299, 0.587, 0.114)

#: Smallest atmospheric light accepted per channel, so dividing by it cannot
#: explode on a frame with a fully black channel.
_MIN_ATMOSPHERIC_LIGHT = 1.0

#: Expected number of array dimensions for an RGB image.
_RGB_DIMENSIONS = 3

#: Expected number of colour channels.
_RGB_CHANNELS = 3


class RejectionReason(StrEnum):
    """Why an image could not be analysed.

    Reported rather than collapsed into a single failure, because each reason
    tells the submitter something different about how to take a usable photo.
    """

    TOO_SMALL = "too_small"
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"
    OUT_OF_FOCUS = "out_of_focus"


@dataclass(frozen=True, slots=True)
class HazeAnalysis:
    """What a photograph yields about the atmosphere in front of it."""

    #: Mean atmospheric opacity over the frame, in [0, 1]. Zero is perfectly
    #: clear air; one is a scene entirely obscured.
    haze_index: float

    #: Mean recovered transmission, in [0, 1]. The complement of the index,
    #: carried separately because it is the quantity with the physical meaning.
    transmission: float

    #: Spread of transmission across the frame. A scene at mixed depths varies
    #: legitimately, so a very low spread suggests a flat subject -- a wall, a
    #: close-up -- where the estimate describes the subject, not the air.
    transmission_spread: float

    #: Mean luminance, 0-255, carried so a reviewer can see the lighting the
    #: estimate was made under.
    mean_luminance: float

    #: Sharpness, as the variance of the Laplacian.
    sharpness: float


@dataclass(frozen=True, slots=True)
class Rejection:
    """An image that cannot support an estimate."""

    reason: RejectionReason
    detail: str


def _as_float_rgb(image: np.ndarray) -> np.ndarray:
    """Validate an RGB array and return it as floats in 0-255.

    Raises:
        ValueError: The array is not a three-channel image. A caller passing a
            greyscale or RGBA array would otherwise get a silently wrong dark
            channel.
    """
    if image.ndim != _RGB_DIMENSIONS or image.shape[2] != _RGB_CHANNELS:
        raise ValueError(
            f"Expected an (H, W, 3) RGB image, got shape {image.shape!r}.",
        )
    return image.astype(np.float64)


def downscale(image: np.ndarray, max_edge: int = HAZE_ANALYSIS_MAX_EDGE_PIXELS) -> np.ndarray:
    """Reduce an image so the longest edge is at most ``max_edge``.

    Uses plain decimation rather than an averaging resize. Averaging is a
    low-pass filter, and it would raise the dark channel by smoothing away the
    dark pixels the prior depends on -- making every downscaled photo look
    hazier than it is.
    """
    rgb = _as_float_rgb(image)
    height, width = rgb.shape[:2]
    longest = max(height, width)
    if longest <= max_edge:
        return rgb

    step = int(np.ceil(longest / max_edge))
    return rgb[::step, ::step, :]


def dark_channel(rgb: np.ndarray, patch: int = HAZE_DCP_PATCH_PIXELS) -> np.ndarray:
    """The dark channel: per-pixel minimum over colour, then over a local patch.

    In a haze-free outdoor scene most local patches contain something close to
    black -- a shadow, a dark surface, a gap. Haze adds airlight everywhere, so
    it lifts that floor, and how far it has been lifted is the signal.
    """
    per_pixel_min = rgb.min(axis=2)
    return _minimum_filter(per_pixel_min, patch)


def _minimum_filter(plane: np.ndarray, patch: int) -> np.ndarray:
    """Local minimum over a square window, with edges handled by reflection.

    Implemented as two separable one-dimensional passes over strided views: a
    square window minimum is the row minimum of the column minimum, and doing
    it in one pass per axis keeps this linear in pixels rather than quadratic in
    the patch size.
    """
    radius = max(1, patch // 2)
    padded = np.pad(plane, radius, mode="reflect")

    width = 2 * radius + 1
    rows = np.lib.stride_tricks.sliding_window_view(padded, width, axis=0).min(axis=-1)
    both = np.lib.stride_tricks.sliding_window_view(rows, width, axis=1).min(axis=-1)
    result: np.ndarray = both
    return result


def atmospheric_light(
    rgb: np.ndarray,
    dark: np.ndarray,
    fraction: float = HAZE_ATMOSPHERIC_LIGHT_FRACTION,
) -> np.ndarray:
    """Estimate the airlight colour from the haziest pixels.

    The brightest pixels *of the dark channel* are used rather than the
    brightest pixels of the image. A white car is bright but not hazy; a patch
    whose darkest colour is also bright is almost certainly sky or dense haze,
    which is what airlight is.
    """
    flat_dark = dark.reshape(-1)
    count = max(1, int(flat_dark.size * fraction))
    haziest = np.argpartition(flat_dark, -count)[-count:]

    pixels = rgb.reshape(-1, _RGB_CHANNELS)[haziest]
    light: np.ndarray = np.maximum(pixels.mean(axis=0), _MIN_ATMOSPHERIC_LIGHT)
    return light


def transmission_map(
    rgb: np.ndarray,
    light: np.ndarray,
    *,
    patch: int = HAZE_DCP_PATCH_PIXELS,
    omega: float = HAZE_DCP_OMEGA,
) -> np.ndarray:
    """Recover per-pixel transmission from the scattering model.

    Inverting ``I = J t + A (1 - t)`` under the dark-channel assumption gives
    ``t = 1 - omega * darkchannel(I / A)``. Transmission near one means the air
    between camera and scene removed little light; near zero means it removed
    almost all of it.
    """
    normalised = rgb / light
    return np.clip(1.0 - omega * _minimum_filter(normalised.min(axis=2), patch), 0.0, 1.0)


def luminance(rgb: np.ndarray) -> np.ndarray:
    """Rec. 601 luminance of an RGB image."""
    weights = np.array(_LUMINANCE_WEIGHTS)
    result: np.ndarray = rgb @ weights
    return result


def laplacian_variance(plane: np.ndarray) -> float:
    """Sharpness, as the variance of a discrete Laplacian.

    A standard focus measure. Used here as a rejection test rather than a
    quality score: blur and haze remove the same high-frequency contrast, so an
    out-of-focus photograph of clear air is indistinguishable from a sharp
    photograph of dirty air, and accepting one would silently invent pollution.
    """
    if min(plane.shape) < _RGB_DIMENSIONS:
        return 0.0
    interior = plane[1:-1, 1:-1]
    response = (
        plane[:-2, 1:-1] + plane[2:, 1:-1] + plane[1:-1, :-2] + plane[1:-1, 2:] - 4.0 * interior
    )
    return float(response.var())


def analyse(image: np.ndarray) -> HazeAnalysis | Rejection:
    """Measure atmospheric haze in a photograph.

    Args:
        image: An ``(H, W, 3)`` RGB array. Values may be integer or float in
            0-255.

    Returns:
        A :class:`HazeAnalysis`, or a :class:`Rejection` naming the reason the
        image cannot support one. Rejection is a normal outcome, not an error:
        most of the ways a photograph fails here make clear air look dirty, so
        refusing is the safe direction to fail in.
    """
    rgb = downscale(image)

    if min(rgb.shape[:2]) < HAZE_MIN_EDGE_PIXELS:
        return Rejection(
            reason=RejectionReason.TOO_SMALL,
            detail=(
                f"The image is {rgb.shape[1]}x{rgb.shape[0]}; the shorter edge must be at "
                f"least {HAZE_MIN_EDGE_PIXELS} pixels."
            ),
        )

    grey = luminance(rgb)
    mean_luminance = float(grey.mean())

    if mean_luminance < HAZE_MIN_MEAN_LUMINANCE:
        return Rejection(
            reason=RejectionReason.TOO_DARK,
            detail=(
                "The scene is too dark to read haze from. In darkness a clear sky and a "
                "thick haze look the same to this method."
            ),
        )

    if mean_luminance > HAZE_MAX_MEAN_LUMINANCE:
        return Rejection(
            reason=RejectionReason.TOO_BRIGHT,
            detail=(
                "The frame is over-exposed. The measurement needs something dark in the "
                "scene, and there is nothing dark here."
            ),
        )

    sharpness = laplacian_variance(grey)
    if sharpness < HAZE_MIN_LAPLACIAN_VARIANCE:
        return Rejection(
            reason=RejectionReason.OUT_OF_FOCUS,
            detail=(
                "The image is too blurred. Blur removes the same contrast haze removes, so "
                "a blurred photo of clean air would be reported as polluted air."
            ),
        )

    dark = dark_channel(rgb)
    light = atmospheric_light(rgb, dark)
    transmission = transmission_map(rgb, light)

    mean_transmission = float(transmission.mean())
    return HazeAnalysis(
        haze_index=1.0 - mean_transmission,
        transmission=mean_transmission,
        transmission_spread=float(transmission.std()),
        mean_luminance=mean_luminance,
        sharpness=sharpness,
    )
