from __future__ import annotations

import math

import numpy as np
import pytest

from spektrafilm.utils.autoexposure import measure_autoexposure_ev


pytestmark = pytest.mark.unit


MIDDLE_GRAY = 0.184


def _constant_rgb(value: float, size: int = 16) -> np.ndarray:
    return np.full((size, size, 3), float(value), dtype=np.float32)


def test_scene_linear_meter_maps_uniform_luminance_to_middle_gray_ev() -> None:
    image = _constant_rgb(0.8)

    ev = measure_autoexposure_ev(
        image,
        color_space="ACEScg",
        apply_cctf_decoding=False,
        method="scene_linear",
    )

    assert ev == pytest.approx(math.log2(MIDDLE_GRAY / 0.8), abs=1e-6)


def test_scene_linear_meter_preserves_middle_gray_with_hdr_specular_region() -> None:
    image = _constant_rgb(MIDDLE_GRAY, size=32)
    image[10:22, 24:32, :] = 16.0

    ev = measure_autoexposure_ev(
        image,
        color_space="ACEScg",
        apply_cctf_decoding=False,
        method="scene_linear",
    )

    assert ev == pytest.approx(0.0, abs=0.20)


def test_scene_linear_aces_meter_ignores_stale_cctf_decoding_flag() -> None:
    image = _constant_rgb(0.8)

    linear_ev = measure_autoexposure_ev(
        image,
        color_space="ACEScg",
        apply_cctf_decoding=False,
        method="scene_linear",
    )
    stale_flag_ev = measure_autoexposure_ev(
        image,
        color_space="ACEScg",
        apply_cctf_decoding=True,
        method="scene_linear",
    )

    assert stale_flag_ev == pytest.approx(linear_ev, abs=1e-12)
    assert stale_flag_ev == pytest.approx(math.log2(MIDDLE_GRAY / 0.8), abs=1e-6)


def test_autoexposure_ignores_invalid_samples_and_clamps_negative_luminance() -> None:
    image = _constant_rgb(MIDDLE_GRAY)
    image[0, 0, :] = (np.nan, np.inf, -np.inf)
    image[0, 1, :] = (-1.0, -1.0, -1.0)

    ev = measure_autoexposure_ev(
        image,
        color_space="sRGB",
        apply_cctf_decoding=False,
        method="center_weighted",
    )

    assert math.isfinite(ev)
    assert ev == pytest.approx(0.0, abs=0.05)


def test_autoexposure_rejects_unknown_method() -> None:
    with pytest.raises(ValueError, match="Unsupported auto exposure method"):
        measure_autoexposure_ev(
            _constant_rgb(MIDDLE_GRAY),
            color_space="sRGB",
            apply_cctf_decoding=False,
            method="unknown",
        )


@pytest.mark.parametrize(
    "method",
    [
        "average",
        "median",
        "center_weighted",
        "partial",
        "matrix",
        "multi_zone",
        "highlight_weighted",
    ],
)
def test_legacy_autoexposure_methods_remain_finite_on_small_images(method: str) -> None:
    ev = measure_autoexposure_ev(
        _constant_rgb(MIDDLE_GRAY, size=3),
        color_space="sRGB",
        apply_cctf_decoding=False,
        method=method,
    )

    assert math.isfinite(ev)
    assert ev == pytest.approx(0.0, abs=0.05)
