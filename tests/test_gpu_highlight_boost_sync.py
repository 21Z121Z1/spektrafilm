from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.kernels.color import boost_highlights_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend


pytestmark = pytest.mark.unit


class _NoScalarMaxGpuBackend(NumpyBackend):
    name = "fake_gpu"
    supports_gpu = True

    def __init__(self) -> None:
        super().__init__()
        self.name = "fake_gpu"
        self.supports_gpu = True
        self.default_dtype = np.float32
        self.max_array_calls = 0

    def asarray(self, value, dtype=None):  # noqa: ANN001
        return np.asarray(value, dtype=dtype or self.default_dtype)

    def max(self, x):  # noqa: ANN001
        raise AssertionError("GPU highlight boost must not call scalar backend.max()")

    def max_array(self, x):  # noqa: ANN001
        self.max_array_calls += 1
        return np.max(x)


def _highlight_ramp() -> np.ndarray:
    return np.array(
        [
            [[0.00, 0.02, 0.05], [0.10, 0.20, 0.30]],
            [[0.40, 0.55, 0.70], [0.85, 1.00, 1.20]],
        ],
        dtype=np.float32,
    )


def test_boost_highlights_gpu_path_uses_backend_resident_max_array() -> None:
    backend = _NoScalarMaxGpuBackend()
    image = _highlight_ramp()

    result = boost_highlights_backend(
        image,
        boost_ev=1.5,
        boost_range=0.35,
        protect_ev=0.0,
        backend=backend,
    )

    assert backend.max_array_calls == 1
    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


@pytest.mark.parametrize(
    "image",
    [
        _highlight_ramp(),
        np.zeros((2, 3, 3), dtype=np.float32),
        np.full((2, 3, 3), 0.05, dtype=np.float32),
    ],
)
def test_boost_highlights_gpu_max_array_path_matches_cpu_scalar_reference(image: np.ndarray) -> None:
    fake_gpu = _NoScalarMaxGpuBackend()
    cpu = NumpyBackend()

    actual = boost_highlights_backend(
        image,
        boost_ev=1.5,
        boost_range=0.35,
        protect_ev=0.0,
        backend=fake_gpu,
    )
    expected = boost_highlights_backend(
        image,
        boost_ev=1.5,
        boost_range=0.35,
        protect_ev=0.0,
        backend=cpu,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_boost_highlights_explicit_x_max_preserves_scalar_path_for_tiled_callers() -> None:
    backend = NumpyBackend()
    image = _highlight_ramp()
    x_max = backend.max(image)

    actual = boost_highlights_backend(
        image[:1],
        boost_ev=1.5,
        boost_range=0.35,
        protect_ev=0.0,
        backend=backend,
        x_max=x_max,
    )
    expected = boost_highlights_backend(
        image[:1],
        boost_ev=1.5,
        boost_range=0.35,
        protect_ev=0.0,
        backend=backend,
        x_max=x_max,
    )

    np.testing.assert_array_equal(actual, expected)
