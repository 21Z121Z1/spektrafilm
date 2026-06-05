from __future__ import annotations

import sys
import types

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, backend_summary, select_backend, tiled_processing
from spektrafilm.gpu.cupy_backend import CupyBackend
from spektrafilm.gpu.mlx_backend import MlxBackend
from spektrafilm.gpu.numpy_backend import NumpyBackend


pytestmark = pytest.mark.unit


def test_numpy_backend_exposes_required_array_ops() -> None:
    backend = NumpyBackend()
    values = np.array([-4.0, -1.0, 0.0, 2.0, 9.0], dtype=np.float64)

    np.testing.assert_allclose(backend.abs(values), np.abs(values))
    assert backend.max(values) == np.max(values)
    np.testing.assert_allclose(backend.max_array(values), np.max(values))
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
    with pytest.raises(ValueError, match="halide"):
        select_backend("vulkan")


def test_select_backend_auto_returns_usable_backend() -> None:
    backend = select_backend("auto")

    assert backend.name in {"cpu", "mlx", "cupy"}
    assert isinstance(backend.supports_gpu, bool)


def test_select_backend_auto_float64_falls_back_to_cpu() -> None:
    backend = select_backend("auto", precision="float64")

    assert backend.name == "cpu"
    assert "float64" in (backend.fallback_reason or "")


def test_select_backend_mlx_float64_is_strict_error() -> None:
    with pytest.raises((BackendUnavailableError, ValueError), match="float64"):
        select_backend("mlx", precision="float64")


def test_select_backend_halide_is_strict_when_requested() -> None:
    try:
        backend = select_backend("halide")
    except BackendUnavailableError:
        return

    assert backend.name == "halide"
    assert backend.supports_gpu
    assert backend_summary(backend, runtime_gpu_enabled=True) == "halide"


def test_halide_backend_exposes_required_array_ops() -> None:
    try:
        backend = select_backend("halide")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))

    values = np.array([-4.0, -1.0, 0.0, 2.0, 9.0], dtype=np.float32)

    np.testing.assert_allclose(backend.abs(values), np.abs(values))
    assert backend.max(values) == float(np.max(values))
    np.testing.assert_allclose(backend.max_array(values), np.max(values))
    np.testing.assert_allclose(backend.pow(np.abs(values), 0.5), np.sqrt(np.abs(values)), atol=1e-6)
    np.testing.assert_allclose(backend.power(10.0, values), np.power(10.0, values), atol=1e-6)
    np.testing.assert_allclose(
        backend.where(values < 0, -values, values),
        np.where(values < 0, -values, values),
    )
    np.testing.assert_allclose(backend.clip(values, 0.0, 1.0), np.clip(values, 0.0, 1.0))
    np.testing.assert_allclose(backend.nan_to_num(np.array([np.nan, 1.0])), np.array([0.0, 1.0]))


def test_select_backend_mlx_is_strict_when_requested() -> None:
    try:
        backend = select_backend("mlx")
    except BackendUnavailableError:
        return

    assert backend.name == "mlx"
    assert backend.supports_gpu


def test_mlx_max_array_does_not_eval_when_available(monkeypatch) -> None:
    try:
        backend = select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))

    def fail_eval(*_args, **_kwargs):
        raise AssertionError("max_array must not force MLX evaluation")

    monkeypatch.setattr(backend, "eval", fail_eval)
    values = backend.asarray(np.array([1.0, 2.0, 3.0], dtype=np.float32))

    result = backend.max_array(values)

    assert backend._is_mlx_array(result)


def test_mlx_compiled_elementwise_cache_reuses_stable_shape_dtype(monkeypatch) -> None:
    try:
        backend = select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))

    compile_calls = []

    def fake_compile(function):
        compile_calls.append(function)

        def wrapped(*args):
            return function(*args)

        return wrapped

    monkeypatch.setattr(backend.mx, "compile", fake_compile, raising=False)
    image = backend.asarray(np.ones((2, 3), dtype=np.float32))
    same_shape = backend.asarray(np.full((2, 3), 2.0, dtype=np.float32))
    changed_shape = backend.asarray(np.ones((4, 3), dtype=np.float32))

    def chain(value):
        return value + 1.0

    compiled = backend.compiled_elementwise("tests.chain", chain, image)
    same_compiled = backend.compiled_elementwise("tests.chain", chain, same_shape)
    changed_compiled = backend.compiled_elementwise("tests.chain", chain, changed_shape)

    assert same_compiled is compiled
    assert changed_compiled is not compiled
    assert len(compile_calls) == 2
    np.testing.assert_allclose(backend.to_numpy(same_compiled(image)), np.full((2, 3), 2.0))


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


def test_mlx_backend_cleanup_clears_cache_after_synchronize(monkeypatch) -> None:
    calls: list[str] = []
    fake_mlx = types.ModuleType("mlx")
    fake_core = types.ModuleType("mlx.core")
    fake_core.float32 = object()
    fake_core.float16 = object()
    fake_core.metal = types.SimpleNamespace(is_available=lambda: True)

    def fake_array(*_args, **_kwargs):
        calls.append("array")
        return object()

    fake_core.array = fake_array
    fake_core.eval = lambda *_values: calls.append("eval")
    fake_core.synchronize = lambda: calls.append("sync")
    fake_core.clear_cache = lambda: calls.append("clear-cache")
    fake_mlx.core = fake_core
    monkeypatch.setitem(sys.modules, "mlx", fake_mlx)
    monkeypatch.setitem(sys.modules, "mlx.core", fake_core)

    backend = MlxBackend()
    backend.cleanup()

    assert calls[-2:] == ["sync", "clear-cache"]


def test_cupy_backend_cleanup_releases_default_memory_pools(monkeypatch) -> None:
    calls: list[str] = []
    fake_cupy = types.ModuleType("cupy")

    class FakeCupyArray:
        pass

    class FakePool:
        def __init__(self, name: str) -> None:
            self._name = name

        def free_all_blocks(self) -> None:
            calls.append(f"{self._name}-free")

    fake_stream = types.SimpleNamespace(synchronize=lambda: calls.append("sync"))
    fake_cupy.ndarray = FakeCupyArray
    fake_cupy.float32 = np.float32
    fake_cupy.float16 = np.float16
    fake_cupy.cuda = types.SimpleNamespace(
        runtime=types.SimpleNamespace(getDeviceCount=lambda: 1),
        get_current_stream=lambda: fake_stream,
    )
    fake_cupy.get_default_memory_pool = lambda: FakePool("device")
    fake_cupy.get_default_pinned_memory_pool = lambda: FakePool("pinned")
    monkeypatch.setitem(sys.modules, "cupy", fake_cupy)

    backend = CupyBackend()
    backend.cleanup()

    assert calls == ["sync", "device-free", "pinned-free"]


@pytest.mark.parametrize("backend_name", ["cupy", "cuda"])
def test_select_backend_cupy_aliases_are_strict_when_requested(backend_name: str) -> None:
    try:
        backend = select_backend(backend_name)
    except BackendUnavailableError:
        return

    assert backend.name == "cupy"
    assert backend.supports_gpu


# ---------------------------------------------------------------------------
# Tiled Processing Tests
# ---------------------------------------------------------------------------


class ToNumpyTrapGpuBackend:
    name = "trap-gpu"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = False

    def asarray(self, value, dtype=None):
        return np.asarray(value, dtype=dtype)

    def to_numpy(self, _value):
        raise AssertionError("GPU tiling must not materialize through to_numpy")


def test_tiled_processing_identity_element_wise() -> None:
    """Element-wise processing with tiling must produce identical results to no tiling."""
    backend = NumpyBackend()
    image = np.random.default_rng(42).random((64, 48, 3), dtype=np.float32)

    result = tiled_processing(image, tile_size=32, process_fn=lambda x: x * 2.0, backend=backend)

    np.testing.assert_allclose(result, image * 2.0, atol=1e-6)


def test_tiled_processing_with_overlap() -> None:
    """Tiling with overlap must produce correct results for operations that need border context."""
    backend = NumpyBackend()
    image = np.random.default_rng(42).random((64, 48, 3), dtype=np.float32)

    def blur_3x3_mean(tile):
        from scipy.ndimage import uniform_filter
        return backend.asarray(
            uniform_filter(backend.to_numpy(tile), size=3, mode="constant", axes=(0, 1))
        )

    result_full = blur_3x3_mean(backend.asarray(image))
    result_tiled = tiled_processing(
        image, tile_size=32, process_fn=blur_3x3_mean, backend=backend, overlap=2,
    )

    np.testing.assert_allclose(result_tiled, result_full, atol=1e-5)


def test_tiled_processing_covers_full_image() -> None:
    """Tiled processing must cover every pixel of the input image."""
    backend = NumpyBackend()
    image = np.ones((50, 70, 3), dtype=np.float32)

    result = tiled_processing(image, tile_size=20, process_fn=lambda x: x * 0.5, backend=backend)

    np.testing.assert_allclose(result, 0.5, atol=1e-6)


def test_tiled_processing_rejects_invalid_tile_size() -> None:
    """tile_size must be greater than 2 * overlap."""
    backend = NumpyBackend()
    image = np.ones((10, 10, 3), dtype=np.float32)

    with pytest.raises(ValueError, match="tile_size"):
        tiled_processing(image, tile_size=4, process_fn=lambda x: x, backend=backend, overlap=3)


def test_tiled_processing_rejects_gpu_backend_before_to_numpy() -> None:
    backend = ToNumpyTrapGpuBackend()
    image = np.ones((10, 10, 3), dtype=np.float32)

    with pytest.raises(RuntimeError, match="CPU fallback"):
        tiled_processing(image, tile_size=4, process_fn=lambda x: x, backend=backend)
