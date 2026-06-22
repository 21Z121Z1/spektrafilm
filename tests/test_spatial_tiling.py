from __future__ import annotations

import numpy as np
import pytest

from tests.conftest import make_fast_test_params

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.tile_utils import (
    default_spatial_tile_rows,
    process_spatial_rows_tiled,
    resolve_spatial_tile_rows,
)
from spektrafilm.model.diffusion import (
    apply_diffusion_filter_um,
    apply_gaussian_blur,
    apply_gaussian_blur_um,
    apply_halation_um,
    apply_unsharp_mask,
)
from spektrafilm.runtime.params_schema import DiffusionFilterParams, HalationParams
from spektrafilm.runtime.pipeline import SimulationPipeline


pytestmark = [pytest.mark.integration, pytest.mark.unit]


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _make_spatial_params(disable: bool = False, tile_rows: int | None = None):
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.gpu_disable_spatial_tiling = disable
    params.settings.gpu_spatial_tile_rows = tile_rows
    return params


# ---------------------------------------------------------------------------
# Generic spatial tiling utility tests
# ---------------------------------------------------------------------------


def test_default_spatial_tile_rows() -> None:
    assert default_spatial_tile_rows(100) == 512
    assert default_spatial_tile_rows(4096) == 512
    assert default_spatial_tile_rows(8192) == 1024


def test_resolve_spatial_tile_rows_enforces_overlap_ratio() -> None:
    backend = _mlx_backend_or_skip()
    # overlap=200 -> tile_rows must be at least 800
    assert resolve_spatial_tile_rows(2000, 200, backend=backend) == 800
    # image too small to fit two tiles with halos
    assert resolve_spatial_tile_rows(1000, 200, backend=backend) is None


def test_process_spatial_rows_tiled_identity_matches_full() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260628)
    image = backend.asarray(rng.uniform(0.0, 1.0, size=(600, 800, 3)).astype(np.float32))

    def process_fn(tile_ext):
        return tile_ext * 2.0 - 0.5

    tiled = backend.to_numpy(
        process_spatial_rows_tiled(image, process_fn, backend, overlap=16, tile_rows=128)
    )
    full = backend.to_numpy(process_fn(image))
    np.testing.assert_allclose(tiled, full, rtol=0.0, atol=1e-6)


def test_process_spatial_rows_tiled_boundary_is_seamless() -> None:
    backend = _mlx_backend_or_skip()
    image = backend.asarray(np.zeros((512, 512, 3), dtype=np.float32))
    image = image.at[:, 256:].add(1.0)

    def process_fn(tile_ext):
        # A simple horizontal box filter that needs overlap to be correct.
        return backend.einsum(
            "ijkl,lm->ijkm",
            backend.asarray(np.ones((1, 31, 1, 1), dtype=np.float32)) / 31.0,
            tile_ext,
        )

    # This process_fn signature doesn't match (it expects 4D), so use a simpler one.
    def blur_tile(tile_ext):
        from spektrafilm.gpu.kernels.filters import gaussian_filter_backend
        return gaussian_filter_backend(tile_ext, 5.0, backend)

    tiled = backend.to_numpy(
        process_spatial_rows_tiled(image, blur_tile, backend, overlap=16, tile_rows=128)
    )
    full = backend.to_numpy(blur_tile(image))
    np.testing.assert_allclose(tiled, full, rtol=0.0, atol=1e-5)


# ---------------------------------------------------------------------------
# Per-filter parity: tiled vs full-image
# ---------------------------------------------------------------------------


def _synthetic_image(shape: tuple[int, int, int], rng: np.random.Generator) -> np.ndarray:
    return rng.uniform(0.05, 0.95, size=shape).astype(np.float32)


def test_tiled_diffusion_matches_full_image() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260629)
    image = _synthetic_image((512, 640, 3), rng)
    diffusion = DiffusionFilterParams(active=True, strength=0.5, spatial_scale=1.0)
    pixel_size_um = 5.0

    params_disable = _make_spatial_params(disable=True)
    full = apply_diffusion_filter_um(
        backend.asarray(image), diffusion, pixel_size_um, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 128
    tiled = apply_diffusion_filter_um(
        backend.asarray(image), diffusion, pixel_size_um, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


def test_tiled_diffusion_no_boundary_artifacts() -> None:
    backend = _mlx_backend_or_skip()
    image = np.zeros((512, 512, 3), dtype=np.float32)
    image[:, 256:] = 1.0
    diffusion = DiffusionFilterParams(active=True, strength=0.8, spatial_scale=1.0)

    params_disable = _make_spatial_params(disable=True)
    full = apply_diffusion_filter_um(
        backend.asarray(image), diffusion, 5.0, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 96
    tiled = apply_diffusion_filter_um(
        backend.asarray(image), diffusion, 5.0, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


def test_tiled_gaussian_blur_matches_full() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260630)
    image = _synthetic_image((512, 640, 3), rng)
    sigma = 2.5

    params_disable = _make_spatial_params(disable=True)
    full = apply_gaussian_blur(
        backend.asarray(image), sigma, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 128
    tiled = apply_gaussian_blur(
        backend.asarray(image), sigma, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


def test_tiled_unsharp_mask_matches_full() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260701)
    image = _synthetic_image((512, 640, 3), rng)

    params_disable = _make_spatial_params(disable=True)
    full = apply_unsharp_mask(
        backend.asarray(image), sigma=1.5, amount=0.7, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 128
    tiled = apply_unsharp_mask(
        backend.asarray(image), sigma=1.5, amount=0.7, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


def test_tiled_gaussian_blur_um_matches_full() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260702)
    image = _synthetic_image((512, 640, 3), rng)

    params_disable = _make_spatial_params(disable=True)
    full = apply_gaussian_blur_um(
        backend.asarray(image), 12.5, 5.0, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 128
    tiled = apply_gaussian_blur_um(
        backend.asarray(image), 12.5, 5.0, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


def test_tiled_halation_matches_full() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260703)
    image = _synthetic_image((512, 640, 3), rng)
    halation = HalationParams(active=True)

    params_disable = _make_spatial_params(disable=True)
    full = apply_halation_um(
        backend.asarray(image), halation, 5.0, backend=backend, settings=params_disable.settings
    )

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 256
    tiled = apply_halation_um(
        backend.asarray(image), halation, 5.0, backend=backend, settings=params_enable.settings
    )

    np.testing.assert_allclose(
        backend.to_numpy(tiled), backend.to_numpy(full), rtol=0.0, atol=1e-5
    )


# ---------------------------------------------------------------------------
# End-to-end pipeline parity
# ---------------------------------------------------------------------------


def test_pipeline_spatial_tiling_matches_untiled() -> None:
    # Scanning-stage Gaussian blur / unsharp are tiled; fused filming filters
    # remain untiled in this phase, so we exercise the tiled scanning path here.
    params_disable = _make_spatial_params(disable=True)
    params_disable.settings.use_enlarger_lut = False
    params_disable.settings.use_scanner_lut = False
    params_disable.debug.deactivate_spatial_effects = False
    params_disable.debug.deactivate_stochastic_effects = True
    params_disable.camera.diffusion_filter.active = False
    params_disable.camera.lens_blur_um = 0.0
    params_disable.scanner.lens_blur = 1.5
    params_disable.scanner.unsharp_mask = (1.0, 0.5)

    pipeline_disable = SimulationPipeline(params_disable)
    backend = pipeline_disable._array_backend
    if backend.name != "mlx" or backend.precision != "float32":
        pytest.skip("requires MLX float32")

    rng = np.random.default_rng(20260705)
    image = rng.uniform(0.05, 0.95, size=(64, 80, 3)).astype(np.float64)

    untiled = pipeline_disable.process(image)

    params_enable = _make_spatial_params(disable=False)
    params_enable.settings.gpu_spatial_tile_rows = 32
    params_enable.settings.use_enlarger_lut = False
    params_enable.settings.use_scanner_lut = False
    params_enable.debug.deactivate_spatial_effects = False
    params_enable.debug.deactivate_stochastic_effects = True
    params_enable.camera.diffusion_filter.active = False
    params_enable.camera.lens_blur_um = 0.0
    params_enable.scanner.lens_blur = 1.5
    params_enable.scanner.unsharp_mask = (1.0, 0.5)
    pipeline_enable = SimulationPipeline(params_enable)
    tiled = pipeline_enable.process(image)

    np.testing.assert_allclose(tiled, untiled, rtol=0.0, atol=1e-5)


# ---------------------------------------------------------------------------
# Memory: tiling should reduce peak active memory for large spatial filters
# ---------------------------------------------------------------------------


def test_tiled_diffusion_reduces_peak_memory_when_activates() -> None:
    backend = _mlx_backend_or_skip()
    mx = backend.mx

    rng = np.random.default_rng(20260706)
    # Tall portrait geometry so that the diffusion overlap is much smaller
    # than the image height and row tiling can actually split the work.
    height, width = 2000, 500
    image = backend.asarray(rng.uniform(0.0, 1.0, size=(height, width, 3)).astype(np.float32))
    diffusion = DiffusionFilterParams(active=True, strength=0.1, spatial_scale=1.0)

    # Non-tiled peak.
    mx.reset_peak_memory()
    out_full = apply_diffusion_filter_um(
        image, diffusion, 5.0, backend=backend, settings=_make_spatial_params(disable=True).settings
    )
    backend.eval(out_full)
    peak_full = mx.get_peak_memory()
    del out_full
    backend.cleanup()

    # Tiled peak.
    mx.reset_peak_memory()
    out_tiled = apply_diffusion_filter_um(
        image, diffusion, 5.0, backend=backend, settings=_make_spatial_params(disable=False).settings
    )
    backend.eval(out_tiled)
    peak_tiled = mx.get_peak_memory()
    del out_tiled
    backend.cleanup()

    assert peak_tiled < peak_full, (
        f"tiled peak memory ({peak_tiled / 1024**2:.1f} MiB) "
        f"should be lower than non-tiled ({peak_full / 1024**2:.1f} MiB)"
    )
