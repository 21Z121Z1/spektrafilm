from __future__ import annotations

import copy

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = pytest.mark.integration


def _available_backends() -> list[str]:
    """Return ['cpu'] plus array backends covered by this pipeline parity slice."""
    backends = ["cpu"]
    for name in ("mlx", "cupy"):
        try:
            select_backend(name)
            backends.append(name)
        except (BackendUnavailableError, Exception):
            pass
    return backends


def _require_mlx_backend() -> None:
    try:
        select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _run_cpu_reference(image, params) -> np.ndarray:
    """Run the same pipeline with the numpy CPU backend for comparison."""
    cpu_params = copy.deepcopy(params)
    cpu_params.settings.compute_backend = "cpu"
    cpu_pipeline = SimulationPipeline(cpu_params)
    assert cpu_pipeline._array_backend.name == "cpu"
    return cpu_pipeline.process(image)


def test_pipeline_processes_small_image_with_mlx_backend() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184

    # CPU reference first (independent of MLX)
    cpu_result = _run_cpu_reference(image, params)

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    assert pipeline._array_backend.name == "mlx"
    assert result.shape == (4, 4, 3)
    assert np.all(np.isfinite(result))
    assert np.all(result >= 0.0)
    assert np.all(result <= 1.0)

    # GPU result must match CPU reference within float32 tolerance
    assert np.allclose(result, cpu_result, atol=1e-5), (
        f"MLX result diverges from CPU reference: "
        f"max abs diff = {np.max(np.abs(result - cpu_result)):.2e}"
    )


def test_filming_rgb_to_raw_keeps_mlx_array_after_lut_when_available() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    pipeline = SimulationPipeline(params)
    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184

    raw = pipeline._filming_stage._rgb_to_film_raw(image)

    assert pipeline._array_backend._is_mlx_array(raw)


def test_printing_non_lut_gpu_path_does_not_materialize_to_numpy(monkeypatch) -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.use_enlarger_lut = False

    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    density = backend.asarray(np.full((4, 4, 3), 0.2, dtype=np.float32))

    def fail_to_numpy(_value):
        raise AssertionError("unexpected MLX to NumPy transfer")

    monkeypatch.setattr(backend, "to_numpy", fail_to_numpy)
    result = pipeline._printing_stage._spectral_compute_enlarger_gpu(density)

    assert backend._is_mlx_array(result)


def test_pipeline_processes_small_image_with_mlx_lut_backend() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    # lut_resolution=32 keeps the test fast (32^3 LUT entries) while providing
    # enough precision for meaningful GPU/CPU comparison.  Very coarse LUT grids
    # (e.g. 5) amplify trilinear-interpolation rounding differences between
    # backends to ~1e-2, which is expected and not a correctness bug.
    params.settings.lut_resolution = 32

    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184

    # CPU reference first (independent of MLX)
    cpu_result = _run_cpu_reference(image, params)

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    assert pipeline._array_backend.name == "mlx"
    assert result.shape == (4, 4, 3)
    assert np.all(np.isfinite(result))
    assert np.all(result >= 0.0)
    assert np.all(result <= 1.0)

    # GPU result must match CPU reference.  Tolerance is 2e-4 because
    # trilinear LUT interpolation across backends introduces small
    # float32-vs-float64 rounding differences that shrink with higher
    # lut_resolution but never fully vanish.
    assert np.allclose(result, cpu_result, atol=2e-4), (
        f"MLX LUT result diverges from CPU reference: "
        f"max abs diff = {np.max(np.abs(result - cpu_result)):.2e}"
    )


# ---------------------------------------------------------------------------
# Parametrized pipeline parity: gray ramp
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_pipeline_gpu_matches_cpu_reference_gray_ramp(backend_name: str) -> None:
    """Full pipeline on a 64x64 gray ramp must match CPU reference."""
    if backend_name == "cpu":
        pytest.skip("trivial self-comparison")
    params = make_fast_test_params()
    params.settings.compute_backend = backend_name
    params.settings.gpu_precision = "float32"

    ramp = np.linspace(0.01, 1.0, 64, dtype=np.float64)
    image = np.ones((64, 64, 3), dtype=np.float64) * ramp[None, :, None]

    cpu_result = _run_cpu_reference(image, params)

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    max_abs_diff = float(np.max(np.abs(result - cpu_result)))
    assert np.allclose(result, cpu_result, atol=1e-5), (
        f"backend={backend_name!r} gray ramp pipeline mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Parametrized pipeline parity: random image
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_pipeline_gpu_matches_cpu_reference_random(backend_name: str) -> None:
    """Full pipeline on a 64x64 random image must match CPU reference."""
    if backend_name == "cpu":
        pytest.skip("trivial self-comparison")
    params = make_fast_test_params()
    params.settings.compute_backend = backend_name
    params.settings.gpu_precision = "float32"

    rng = np.random.default_rng(42)
    image = rng.random((64, 64, 3), dtype=np.float64) * 0.8 + 0.1

    cpu_result = _run_cpu_reference(image, params)

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    max_abs_diff = float(np.max(np.abs(result - cpu_result)))
    assert np.allclose(result, cpu_result, atol=1e-5), (
        f"backend={backend_name!r} random pipeline mismatch: max_abs_diff={max_abs_diff:.2e}"
    )
