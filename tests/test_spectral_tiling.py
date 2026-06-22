from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.tile_utils import default_tile_rows, process_rows_tiled
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = [pytest.mark.integration, pytest.mark.unit]


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _make_tiling_params(disable: bool = False, tile_rows: int | None = None):
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.gpu_disable_spectral_tiling = disable
    params.settings.gpu_tile_rows = tile_rows
    return params


# ---------------------------------------------------------------------------
# Generic tiling utility tests
# ---------------------------------------------------------------------------


def test_default_tile_rows() -> None:
    assert default_tile_rows(100) == 256
    assert default_tile_rows(1024) == 256
    assert default_tile_rows(2048) == 256
    assert default_tile_rows(4096) == 512
    assert default_tile_rows(8192) == 1024


def test_process_rows_tiled_identity_matches_full_processing() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260622)
    image = backend.asarray(rng.uniform(0.0, 1.0, size=(600, 800, 3)).astype(np.float32))

    def process_fn(tile):
        return tile * 2.0 - 0.5

    tiled = backend.to_numpy(process_rows_tiled(image, process_fn, backend, tile_rows=128))
    full = backend.to_numpy(process_fn(image))
    np.testing.assert_allclose(tiled, full, rtol=0.0, atol=1e-6)


def test_process_rows_tiled_can_change_channel_count() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260623)
    image = backend.asarray(rng.uniform(0.0, 1.0, size=(256, 256, 3)).astype(np.float32))

    def process_fn(tile):
        return backend.einsum("ijk,kl->ijl", tile, backend.asarray(np.ones((3, 7), dtype=np.float32)))

    tiled = process_rows_tiled(image, process_fn, backend, tile_rows=64)
    backend.eval(tiled)
    assert tiled.shape == (256, 256, 7)
    full = process_fn(image)
    np.testing.assert_allclose(backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5)


def test_process_rows_tiled_no_tiling_when_tile_rows_none() -> None:
    backend = _mlx_backend_or_skip()
    image = backend.asarray(np.ones((10, 10, 3), dtype=np.float32))

    calls = []

    def process_fn(tile):
        calls.append(tile.shape)
        return tile

    result = process_rows_tiled(image, process_fn, backend, tile_rows=None)
    assert len(calls) == 1
    np.testing.assert_array_equal(backend.to_numpy(result), np.ones((10, 10, 3), dtype=np.float32))


def test_process_rows_tiled_no_tiling_when_image_smaller_than_tile() -> None:
    backend = _mlx_backend_or_skip()
    image = backend.asarray(np.ones((100, 100, 3), dtype=np.float32))

    calls = []

    def process_fn(tile):
        calls.append(tile.shape)
        return tile

    result = process_rows_tiled(image, process_fn, backend, tile_rows=256)
    assert len(calls) == 1
    assert calls[0][0] == 100


# ---------------------------------------------------------------------------
# Stage parity: tiled vs untiled
# ---------------------------------------------------------------------------


def _synthetic_cmy_density(shape: tuple[int, int, int], rng: np.random.Generator) -> np.ndarray:
    """Return a deterministic synthetic CMY density image."""
    return rng.uniform(-0.1, 1.5, size=shape).astype(np.float32)


def test_printing_stage_tiled_matches_untiled() -> None:
    params = _make_tiling_params(disable=True)
    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    if backend.name != "mlx" or backend.precision != "float32":
        pytest.skip("requires MLX float32")

    rng = np.random.default_rng(20260624)
    density = _synthetic_cmy_density((512, 640, 3), rng)

    # Force the unfused path by hiding the fused kernel on this backend instance.
    original_fused = getattr(backend, "cmy_to_log_raw", None)
    backend.cmy_to_log_raw = None
    try:
        untiled = pipeline._printing_stage._film_cmy_to_print_log_raw(density)

        params.settings.gpu_disable_spectral_tiling = False
        params.settings.gpu_tile_rows = 128
        tiled = pipeline._printing_stage._film_cmy_to_print_log_raw(density)
    finally:
        backend.cmy_to_log_raw = original_fused

    np.testing.assert_allclose(tiled, untiled, rtol=0.0, atol=1e-5)


def test_scanning_stage_tiled_matches_untiled() -> None:
    params = _make_tiling_params(disable=True)
    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    if backend.name != "mlx" or backend.precision != "float32":
        pytest.skip("requires MLX float32")

    rng = np.random.default_rng(20260625)
    density = _synthetic_cmy_density((512, 640, 3), rng)

    untiled = backend.to_numpy(pipeline._scanning_stage.cmy_to_log_xyz(density))

    params.settings.gpu_disable_spectral_tiling = False
    params.settings.gpu_tile_rows = 128
    tiled = backend.to_numpy(pipeline._scanning_stage.cmy_to_log_xyz(density))

    np.testing.assert_allclose(tiled, untiled, rtol=0.0, atol=1e-5)


def test_pipeline_output_tiled_matches_untiled() -> None:
    params = _make_tiling_params(disable=True)
    pipeline = SimulationPipeline(params)
    backend = pipeline._array_backend
    if backend.name != "mlx" or backend.precision != "float32":
        pytest.skip("requires MLX float32")

    rng = np.random.default_rng(20260626)
    image = rng.uniform(0.05, 0.95, size=(64, 80, 3)).astype(np.float64)

    untiled = pipeline.process(image)

    params.settings.gpu_disable_spectral_tiling = False
    params.settings.gpu_tile_rows = 32
    tiled = pipeline.process(image)

    np.testing.assert_allclose(tiled, untiled, rtol=0.0, atol=1e-5)


# ---------------------------------------------------------------------------
# Memory: tiling should reduce peak active memory for large spectral chains
# ---------------------------------------------------------------------------


def test_tiled_spectral_chain_reduces_peak_memory() -> None:
    backend = _mlx_backend_or_skip()
    mx = backend.mx

    rng = np.random.default_rng(20260627)
    height, width = 1536, 2048
    density = backend.asarray(rng.uniform(0.0, 1.2, size=(height, width, 3)).astype(np.float32))
    channel_density = backend.asarray(rng.uniform(0.02, 1.0, size=(81, 3)).astype(np.float32))
    illuminant = backend.asarray(rng.uniform(0.1, 1.0, size=(81,)).astype(np.float32))
    sensitivity = backend.asarray(rng.uniform(0.01, 0.9, size=(81, 3)).astype(np.float32))

    from spektrafilm.gpu.kernels.density import (
        compute_density_spectral as compute_density_spectral_backend,
        density_to_light as density_to_light_backend,
        light_to_raw,
    )

    def _spectral_chain(tile):
        density_spectral = compute_density_spectral_backend(
            channel_density, tile, base_density=None, backend=backend
        )
        light = density_to_light_backend(density_spectral, illuminant, backend)
        return light_to_raw(light, sensitivity, backend)

    # Non-tiled peak.
    mx.reset_peak_memory()
    out_full = _spectral_chain(density)
    backend.eval(out_full)
    peak_full = mx.get_peak_memory()
    del out_full
    backend.cleanup()

    # Tiled peak.
    mx.reset_peak_memory()
    out_tiled = process_rows_tiled(density, _spectral_chain, backend, tile_rows=256)
    backend.eval(out_tiled)
    peak_tiled = mx.get_peak_memory()
    del out_tiled
    backend.cleanup()

    assert peak_tiled < peak_full, (
        f"tiled peak memory ({peak_full / 1024**2:.1f} MiB) "
        f"should be lower than non-tiled ({peak_tiled / 1024**2:.1f} MiB)"
    )
