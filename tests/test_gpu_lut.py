from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.lut import (
    apply_lut_bilinear_2d_numpy,
    apply_lut_cubic_2d_mlx,
    apply_lut_cubic_2d_numpy,
    apply_lut_trilinear_3d_mlx,
    apply_lut_trilinear_3d_numpy,
)
from spektrafilm.utils.lut import compute_with_lut
from spektrafilm.utils.fast_interp_lut import apply_lut_cubic_2d


pytestmark = pytest.mark.unit


def _affine_3d(data: np.ndarray) -> np.ndarray:
    out = np.empty(data.shape[:-1] + (3,), dtype=np.float64)
    out[..., 0] = 0.7 * data[..., 0] + 0.2 * data[..., 1] + 0.1
    out[..., 1] = -0.1 * data[..., 0] + 0.5 * data[..., 1] + 0.3 * data[..., 2]
    out[..., 2] = 0.25 * data[..., 0] - 0.2 * data[..., 1] + 0.9 * data[..., 2] + 0.05
    return out


def _affine_2d(data: np.ndarray) -> np.ndarray:
    out = np.empty(data.shape[:-1] + (3,), dtype=np.float64)
    out[..., 0] = 0.4 * data[..., 0] + 0.2 * data[..., 1]
    out[..., 1] = -0.3 * data[..., 0] + 0.8 * data[..., 1] + 0.1
    out[..., 2] = 0.6 * data[..., 0] - 0.1 * data[..., 1] + 0.2
    return out


def _make_3d_lut(size: int) -> np.ndarray:
    axis = np.linspace(0.0, 1.0, size, dtype=np.float64)
    r, g, b = np.meshgrid(axis, axis, axis, indexing="ij")
    return _affine_3d(np.stack((r, g, b), axis=-1))


def _make_2d_lut(size: int) -> np.ndarray:
    axis = np.linspace(0.0, 1.0, size, dtype=np.float64)
    x, y = np.meshgrid(axis, axis, indexing="ij")
    return _affine_2d(np.stack((x, y), axis=-1))


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_trilinear_3d_lut_numpy_reference_is_exact_for_affine_lut() -> None:
    lut = _make_3d_lut(7)
    image = np.array(
        [
            [[0.0, 0.1, 0.2], [0.3, 0.4, 0.5]],
            [[0.6, 0.7, 0.8], [1.0, 0.25, 0.75]],
        ],
        dtype=np.float64,
    )

    actual = apply_lut_trilinear_3d_numpy(lut, image)
    expected = _affine_3d(image)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_bilinear_2d_lut_numpy_reference_is_exact_for_affine_lut() -> None:
    lut = _make_2d_lut(9)
    image = np.array(
        [
            [[0.0, 0.1], [0.3, 0.4]],
            [[0.6, 0.7], [1.0, 0.25]],
        ],
        dtype=np.float64,
    )

    actual = apply_lut_bilinear_2d_numpy(lut, image)
    expected = _affine_2d(image)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_cubic_2d_lut_numpy_reference_matches_cpu_lut() -> None:
    lut = _make_2d_lut(9)
    image = np.array(
        [
            [[0.02, 0.10], [0.31, 0.42]],
            [[0.63, 0.74], [0.98, 0.25]],
        ],
        dtype=np.float64,
    )

    actual = apply_lut_cubic_2d_numpy(lut, image)
    expected = apply_lut_cubic_2d(lut, image)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_compute_with_lut_gpu_trilinear_without_gpu_falls_back_to_cpu_lut() -> None:
    data = np.array(
        [
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [[0.7, 0.8, 0.9], [0.2, 0.8, 0.4]],
        ],
        dtype=np.float64,
    )

    actual, lut = compute_with_lut(
        data,
        _affine_3d,
        steps=9,
        method="gpu_trilinear",
        gpu_backend=None,
    )

    assert lut.shape == (9, 9, 9, 3)
    np.testing.assert_allclose(actual, _affine_3d(data), rtol=1e-8, atol=1e-8)


def test_trilinear_3d_lut_mlx_matches_numpy_reference_when_available() -> None:
    backend = _mlx_backend_or_skip()
    lut = _make_3d_lut(7)
    image = np.array(
        [
            [[0.0, 0.1, 0.2], [0.3, 0.4, 0.5]],
            [[0.6, 0.7, 0.8], [1.0, 0.25, 0.75]],
        ],
        dtype=np.float32,
    )

    actual = apply_lut_trilinear_3d_mlx(lut.astype(np.float32), image, mx=backend.mx)
    expected = apply_lut_trilinear_3d_numpy(lut, image)

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)


def test_cubic_2d_lut_mlx_matches_numpy_reference_when_available() -> None:
    backend = _mlx_backend_or_skip()
    lut = _make_2d_lut(9).astype(np.float32)
    image = np.array(
        [
            [[0.02, 0.10], [0.31, 0.42]],
            [[0.63, 0.74], [0.98, 0.25]],
        ],
        dtype=np.float32,
    )

    actual = apply_lut_cubic_2d_mlx(lut, image, mx=backend.mx)
    expected = apply_lut_cubic_2d_numpy(lut, image)

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-5, atol=2e-5)
