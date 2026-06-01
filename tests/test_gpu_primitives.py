"""Parity tests for backend primitive operations (exp, log10, matmul, einsum).

Each test generates synthetic inputs, runs the backend primitive, and asserts
numerical identity with the NumPy reference within float64 tolerance.
"""
from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend


pytestmark = pytest.mark.unit


def _available_backends() -> list[str]:
    """Return ['cpu'] plus any GPU backends that can be imported."""
    backends = ["cpu"]
    for name in ("mlx", "cupy", "halide"):
        try:
            select_backend(name)
            backends.append(name)
        except (BackendUnavailableError, Exception):
            pass
    return backends


def _get_backend(name: str):
    if name == "cpu":
        return NumpyBackend()
    return select_backend(name)


TOLERANCE = 1e-10


@pytest.mark.parametrize("backend_name", _available_backends())
def test_backend_exp_matches_numpy(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    data = rng.uniform(-10.0, 10.0, (32, 32, 3))
    backend_data = backend.asarray(data.astype(np.float64 if backend_name == "cpu" else np.float32))

    result = backend.exp(backend_data)
    result_np = backend.to_numpy(result)
    expected = np.exp(np.asarray(data, dtype=result_np.dtype))

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=TOLERANCE), (
        f"backend={backend_name!r} exp mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


@pytest.mark.parametrize("backend_name", _available_backends())
def test_backend_log10_matches_numpy(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    data = rng.uniform(1e-6, 100.0, (32, 32, 3))
    backend_data = backend.asarray(data.astype(np.float64 if backend_name == "cpu" else np.float32))

    result = backend.log10(backend_data)
    result_np = backend.to_numpy(result)
    expected = np.log10(np.asarray(data, dtype=result_np.dtype))

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=TOLERANCE), (
        f"backend={backend_name!r} log10 mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


@pytest.mark.parametrize("backend_name", _available_backends())
def test_backend_matmul_matches_numpy(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    a = rng.standard_normal((16, 16, 3))
    b = rng.standard_normal((3, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32
    a_backend = backend.asarray(a.astype(dtype))
    b_backend = backend.asarray(b.astype(dtype))

    result = backend.matmul(a_backend, b_backend)
    result_np = backend.to_numpy(result)
    expected = np.matmul(np.asarray(a, dtype=dtype), np.asarray(b, dtype=dtype))

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=TOLERANCE), (
        f"backend={backend_name!r} matmul mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


@pytest.mark.parametrize("backend_name", _available_backends())
def test_backend_einsum_matches_numpy(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    a = rng.standard_normal((8, 8, 81))
    b = rng.standard_normal((81, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32
    a_backend = backend.asarray(a.astype(dtype))
    b_backend = backend.asarray(b.astype(dtype))

    result = backend.einsum("ijk,kl->ijl", a_backend, b_backend)
    result_np = backend.to_numpy(result)
    expected = np.einsum("ijk,kl->ijl", np.asarray(a, dtype=dtype), np.asarray(b, dtype=dtype))

    # float32 backends accumulate rounding from 81-term dot products
    tol = TOLERANCE if backend_name == "cpu" else 1e-5
    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=tol), (
        f"backend={backend_name!r} einsum mismatch: max_abs_diff={max_abs_diff:.2e}"
    )
