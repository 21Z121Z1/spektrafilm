from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, backend_summary, select_backend
from spektrafilm.gpu.mlx_backend import MlxBackend
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

    assert backend.name in {"cpu", "mlx", "cupy"}
    assert isinstance(backend.supports_gpu, bool)


def test_select_backend_mlx_is_strict_when_requested() -> None:
    try:
        backend = select_backend("mlx")
    except BackendUnavailableError:
        return

    assert backend.name == "mlx"
    assert backend.supports_gpu


def test_mlx_backend_rejects_false_positive_metal_availability(monkeypatch) -> None:
    fake_mlx = types.ModuleType("mlx")
    fake_core = types.ModuleType("mlx.core")
    fake_core.float32 = object()
    fake_core.float16 = object()
    fake_core.metal = types.SimpleNamespace(is_available=lambda: True)

    def fail_array(*_args, **_kwargs):
        raise RuntimeError("No Metal device available")

    fake_core.array = fail_array
    fake_core.eval = lambda *_values: None
    fake_mlx.core = fake_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)

    with pytest.raises(BackendUnavailableError, match="usable Apple Metal device"):
        MlxBackend()


@pytest.mark.parametrize("backend_name", ["cupy", "cuda"])
def test_select_backend_cupy_aliases_are_strict_when_requested(backend_name: str) -> None:
    try:
        backend = select_backend(backend_name)
    except BackendUnavailableError:
        return

    assert backend.name == "cupy"
    assert backend.supports_gpu
