from __future__ import annotations

import copy

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.stages import filming as filming_module


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


def test_pipeline_gpu_validate_hanatos2025_mlx_float32_records_report() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.gpu_validate = True

    image = np.array(
        [
            [[0.02, 0.02, 0.02], [0.184, 0.184, 0.184], [0.9, 0.2, 0.1], [1.2, 1.1, 0.9]],
            [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            [[0.4, 0.6, 0.8], [0.8, 0.6, 0.4], [1.0, 0.5, 0.25], [0.25, 0.5, 1.0]],
            [[0.1, 0.3, 0.7], [0.7, 0.3, 0.1], [1.4, 0.1, 0.2], [0.2, 1.4, 0.1]],
        ],
        dtype=np.float64,
    )

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)
    report = pipeline.validation_report

    assert pipeline._array_backend.name == "mlx"
    assert result.shape == image.shape
    assert report["status"] == "ok"
    assert report["backend"] == "mlx"
    assert report["reference_backend"] == "cpu"
    assert report["precision"] == "float32"
    assert report["max_abs_diff"] <= report["tolerance"]


def test_filming_rgb_to_raw_keeps_mlx_array_after_lut_when_available() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    pipeline = SimulationPipeline(params)
    image = np.ones((4, 4, 3), dtype=np.float64) * 0.184

    raw = pipeline._filming_stage._rgb_to_film_raw(image)

    assert pipeline._array_backend._is_mlx_array(raw)


def test_filming_gpu_rgb_to_raw_does_not_call_cpu_rgb_to_tc_b(monkeypatch) -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    pipeline = SimulationPipeline(params)
    image = np.ones((4, 4, 3), dtype=np.float32) * 0.184

    def fail_cpu_rgb_to_tc_b(*_args, **_kwargs):
        raise AssertionError("GPU filming path must use backend-resident rgb_to_tc_b_backend")

    monkeypatch.setattr(filming_module, "_rgb_to_tc_b", fail_cpu_rgb_to_tc_b)

    raw = pipeline._filming_stage._rgb_to_film_raw(image)

    assert pipeline._array_backend._is_mlx_array(raw)


def test_mlx_preprocess_without_resize_keeps_backend_array() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False

    pipeline = SimulationPipeline(params)
    image = np.ones((8, 10, 4), dtype=np.float64) * 0.184

    preprocessed, auto_ev = pipeline._preprocess_base(image)

    assert auto_ev is None
    assert pipeline._array_backend._is_mlx_array(preprocessed)
    assert tuple(preprocessed.shape) == (8, 10, 3)


def test_mlx_preprocess_resize_fallback_rewraps_backend_array() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.io.crop = False
    params.io.upscale_factor = 0.5
    params.camera.auto_exposure = False

    pipeline = SimulationPipeline(params)
    image = np.ones((8, 10, 3), dtype=np.float64) * 0.184

    preprocessed, auto_ev = pipeline._preprocess_base(image)

    assert auto_ev is None
    assert pipeline._array_backend._is_mlx_array(preprocessed)
    assert tuple(preprocessed.shape[:2]) == (4, 5)
    assert "SimulationPipeline.preprocess.resize_cpu_fallback" in pipeline.timings


def test_process_default_materializes_numpy_float64(default_params) -> None:
    default_params.settings.compute_backend = "cpu"
    image = np.ones((4, 4, 3), dtype=np.float32) * 0.184

    result = SimulationPipeline(default_params).process(image)

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float64


def test_process_numpy_float32_materialize_policy(default_params) -> None:
    default_params.settings.compute_backend = "cpu"
    default_params.settings.materialize_policy = "numpy_float32"
    image = np.ones((4, 4, 3), dtype=np.float32) * 0.184

    result = SimulationPipeline(default_params).process(image)

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.float32


def test_process_backend_materialize_policy_returns_mlx_array() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    image = np.ones((4, 4, 3), dtype=np.float32) * 0.184

    pipeline = SimulationPipeline(params)
    result = pipeline.process(image)

    assert pipeline._array_backend._is_mlx_array(result)


def test_cpu_backend_materialize_policy_returns_numpy(default_params) -> None:
    default_params.settings.compute_backend = "cpu"
    default_params.settings.materialize_policy = "backend"
    image = np.ones((4, 4, 3), dtype=np.float32) * 0.184

    result = SimulationPipeline(default_params).process(image)

    assert isinstance(result, np.ndarray)


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


def test_printing_develop_keeps_mlx_array_when_available() -> None:
    _require_mlx_backend()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"

    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    log_raw = backend.asarray(np.full((4, 4, 3), -0.2, dtype=np.float32))

    density = pipeline._printing_stage.develop(log_raw)

    assert backend._is_mlx_array(density)


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


def test_mlx_lut_65_approximation_is_bounded() -> None:
    """GPU trilinear LUT at resolution 65 must approximate direct spectral.

    This isolates the LUT sampling error from float32-vs-float64 differences
    by comparing the same MLX backend with and without LUT.
    """
    _require_mlx_backend()

    rng = np.random.default_rng(42)
    image = rng.random((16, 16, 3), dtype=np.float64) * 0.8 + 0.1

    # Direct spectral reference on MLX (LUT disabled)
    direct_params = make_fast_test_params()
    direct_params.settings.compute_backend = "mlx"
    direct_params.settings.gpu_precision = "float32"
    direct_params.settings.use_enlarger_lut = False
    direct_params.settings.use_scanner_lut = False
    direct = SimulationPipeline(direct_params).process(image)

    # LUT path on MLX at the new default resolution
    lut_params = make_fast_test_params()
    lut_params.settings.compute_backend = "mlx"
    lut_params.settings.gpu_precision = "float32"
    lut_params.settings.use_enlarger_lut = True
    lut_params.settings.use_scanner_lut = True
    lut_params.settings.lut_resolution = 65
    lut = SimulationPipeline(lut_params).process(image)

    max_abs_diff = float(np.max(np.abs(lut - direct)))
    # Empirically the per-sampling LUT error at res=65 is ~2e-5; allow a
    # generous margin for full-pipeline float32 accumulation.
    assert max_abs_diff <= 5e-4, (
        f"MLX LUT (res=65) diverges from direct spectral: "
        f"max_abs_diff={max_abs_diff:.2e}"
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
