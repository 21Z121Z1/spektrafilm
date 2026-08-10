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


def test_mallett_mlx_backend_matches_existing_cpu_semantics() -> None:
    """Keep the existing direct Mallett CPU/MLX paths mutually consistent.

    Current upstream experimental changed Mallett's normalization semantics;
    that migration is intentionally not folded into this conformance audit.
    """
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
