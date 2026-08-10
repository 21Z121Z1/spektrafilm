from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.color import rgb_to_raw_mallett2019_backend
from spektrafilm.utils.spectral_upsampling import rgb_to_raw_mallett2019


pytestmark = pytest.mark.unit


def _sensitivity() -> np.ndarray:
    w = np.linspace(0.0, 1.0, 81, dtype=np.float64)
    return np.stack(
        (
            0.35 + 0.9 * w,
            0.72 + 0.18 * np.cos(2.0 * np.pi * w),
            1.18 - 0.52 * w,
        ),
        axis=-1,
    )


@pytest.mark.parametrize("reference_illuminant", ["D55", "D65", "A"])
def test_mallett_neutral_is_per_channel_balanced(reference_illuminant: str) -> None:
    sensitivity = _sensitivity()
    neutral = np.full((1, 1, 3), 0.184, dtype=np.float64)

    raw = rgb_to_raw_mallett2019(
        neutral,
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=False,
        reference_illuminant=reference_illuminant,
    )

    np.testing.assert_allclose(raw[0, 0], np.ones(3), rtol=2e-6, atol=2e-6)


def test_mallett_mlx_backend_matches_cpu_reference() -> None:
    try:
        backend = select_backend("mlx", precision="float32")
    except (BackendUnavailableError, ValueError) as exc:
        pytest.skip(str(exc))

    sensitivity = _sensitivity()
    rgb = np.array(
        [
            [[0.184, 0.184, 0.184], [0.72, 0.42, 0.31], [0.18, 0.48, 0.13]],
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        ],
        dtype=np.float32,
    )

    expected = rgb_to_raw_mallett2019(
        rgb,
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=False,
        reference_illuminant="D55",
    )
    actual_backend = rgb_to_raw_mallett2019_backend(
        backend.asarray(rgb),
        sensitivity,
        color_space="sRGB",
        apply_cctf_decoding=False,
        reference_illuminant="D55",
        backend=backend,
    )
    actual = backend.to_numpy(actual_backend)

    np.testing.assert_allclose(actual, expected, rtol=3e-5, atol=3e-5)
