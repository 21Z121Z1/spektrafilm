from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, backend_summary, select_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend


pytestmark = pytest.mark.unit


def test_numpy_backend_exposes_required_array_ops() -> None:
    backend = NumpyBackend()
    values = np.array([-4.0, -1.0, 0.0, 2.0, 9.0], dtype=np.float64)

    np.testing.assert_allclose(backend.abs(values), np.abs(values))
    assert backend.max(values) == np.max(values)
    np.testing.assert_allclose(backend.pow(np.abs(values), 0.5), np.sqrt(np.abs(values)))
    np.testing.assert_allclose(backend.power(10.0, values), np.power(10.0, values))
    np.testing.assert_allclose(
        backend.where(values < 0, -values, values),
        np.where(values < 0, -values, values),
    )
    np.testing.assert_allclose(backend.clip(values, 0.0, 1.0), np.clip(values, 0.0, 1.0))
    np.testing.assert_allclose(backend.nan_to_num(np.array([np.nan, 1.0])), np.array([0.0, 1.0]))


def test_select_backend_cpu_is_strict_numpy_backend() -> None:
    backend = select_backend("cpu")

    assert backend.name == "cpu"
    assert not backend.supports_gpu
    assert backend_summary(backend) == "cpu"


def test_select_backend_rejects_unknown_backend_name() -> None:
    with pytest.raises(ValueError, match="compute_backend"):
        select_backend("vulkan")


def test_select_backend_auto_returns_usable_backend() -> None:
    backend = select_backend("auto")

    assert backend.name in {"cpu", "mlx"}
    assert isinstance(backend.supports_gpu, bool)


def test_select_backend_mlx_is_strict_when_requested() -> None:
    try:
        backend = select_backend("mlx")
    except BackendUnavailableError:
        return

    assert backend.name == "mlx"
    assert backend.supports_gpu
