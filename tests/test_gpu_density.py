from __future__ import annotations

import numpy as np
import pytest
from opt_einsum import contract

from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.gpu.kernels.density import (
    cmy_to_log_xyz_backend,
    compute_density_spectral as compute_density_spectral_backend,
    density_to_light as density_to_light_backend,
    interpolate_density_cmy_layers_backend,
    interpolate_exposure_to_density_backend,
    light_to_raw,
    safe_log10_backend,
)
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.model.couplers import compute_exposure_correction_dir_couplers
from spektrafilm.model.density_curves import interp_density_cmy_layers, interpolate_exposure_to_density
from spektrafilm.model.emulsion import compute_density_spectral
from spektrafilm.utils.conversions import density_to_light


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


def _mlx_backend_or_skip():
    try:
        return select_backend("mlx")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _cupy_backend_or_skip():
    try:
        return select_backend("cupy")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_density_spectral_backend_matches_cpu_reference() -> None:
    backend = NumpyBackend()
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.40, 0.10, 0.05]],
            [[0.15, 0.25, 0.35], [0.60, 0.70, 0.20]],
        ],
        dtype=np.float64,
    )
    channel_density = np.array(
        [
            [0.80, 0.10, 0.20],
            [0.20, 0.90, 0.10],
            [0.05, 0.30, 1.10],
            [0.40, 0.50, 0.20],
        ],
        dtype=np.float64,
    )
    base_density = np.array([0.03, 0.04, 0.05, 0.06], dtype=np.float64)

    actual = compute_density_spectral_backend(
        channel_density,
        density_cmy,
        base_density,
        backend,
    )
    expected = compute_density_spectral(channel_density, density_cmy, base_density)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_density_to_light_and_light_to_raw_match_cpu_reference() -> None:
    backend = NumpyBackend()
    density = np.array(
        [
            [[0.1, 0.2, 0.3, np.nan], [0.4, 0.3, 0.2, 0.1]],
            [[0.0, 1.0, 2.0, 3.0], [0.7, 0.8, 0.9, 1.0]],
        ],
        dtype=np.float64,
    )
    illuminant = np.array([1.0, 0.8, 0.6, 0.4], dtype=np.float64)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.1, 0.6, 0.2],
            [0.2, 0.1, 0.7],
            [0.4, 0.3, 0.2],
        ],
        dtype=np.float64,
    )

    light_actual = density_to_light_backend(density, illuminant, backend)
    light_expected = density_to_light(density.copy(), illuminant)
    raw_actual = light_to_raw(light_actual, sensitivity, backend)
    raw_expected = contract("ijk,kl->ijl", light_expected, sensitivity)

    np.testing.assert_allclose(light_actual, light_expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_allclose(raw_actual, raw_expected, rtol=1e-12, atol=1e-12)


def test_safe_log10_backend_matches_numpy_reference() -> None:
    backend = NumpyBackend()
    values = np.array(
        [
            [[-1.0, 0.0, 1e-12], [1e-4, 0.5, 1.0]],
            [[2.0, 4.0, 8.0], [16.0, -0.25, 0.25]],
        ],
        dtype=np.float64,
    )

    actual = safe_log10_backend(values, backend)
    expected = np.log10(np.fmax(values, 0.0) + 1e-10)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_cmy_to_log_xyz_backend_matches_manual_chain() -> None:
    backend = NumpyBackend()
    cmfs = STANDARD_OBSERVER_CMFS[:]
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.40, 0.10, 0.05]],
            [[0.15, 0.25, 0.35], [0.60, 0.70, 0.20]],
        ],
        dtype=np.float64,
    )
    channel_density = np.linspace(0.05, 1.2, cmfs.shape[0] * 3).reshape(-1, 3)
    base_density = np.linspace(0.01, 0.05, cmfs.shape[0])
    scan_illuminant = np.linspace(0.2, 1.0, cmfs.shape[0])
    normalization = np.sum(scan_illuminant * cmfs[:, 1], axis=0)

    actual = cmy_to_log_xyz_backend(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
        backend,
    )
    density_spectral = compute_density_spectral(channel_density, density_cmy, base_density)
    light = density_to_light(density_spectral, scan_illuminant)
    xyz = contract("ijk,kl->ijl", light, cmfs) / normalization
    expected = np.log10(np.fmax(xyz, 0.0) + 1e-10)

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_cmy_to_log_xyz_backend_prefers_specialized_backend_method() -> None:
    class SpecializedBackend:
        name = "specialized"
        supports_gpu = True

        def __init__(self) -> None:
            self.calls = []

        def cmy_to_log_xyz(
            self,
            density_cmy,
            channel_density,
            base_density,
            scan_illuminant,
            cmfs,
            normalization,
        ):
            self.calls.append(
                (
                    density_cmy,
                    channel_density,
                    base_density,
                    scan_illuminant,
                    cmfs,
                    normalization,
                )
            )
            return np.array([[[1.0, 2.0, 3.0]]], dtype=np.float32)

    backend = SpecializedBackend()
    density_cmy = np.zeros((1, 1, 3), dtype=np.float32)
    channel_density = np.zeros((4, 3), dtype=np.float32)
    base_density = np.zeros((4,), dtype=np.float32)
    scan_illuminant = np.ones((4,), dtype=np.float32)
    cmfs = np.ones((4, 3), dtype=np.float32)

    actual = cmy_to_log_xyz_backend(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        1.0,
        backend,
    )

    np.testing.assert_array_equal(actual, np.array([[[1.0, 2.0, 3.0]]], dtype=np.float32))
    assert len(backend.calls) == 1
    assert backend.calls[0][0] is density_cmy


def test_interpolate_exposure_to_density_backend_matches_cpu_reference() -> None:
    backend = NumpyBackend()
    log_exposure = np.linspace(-3.0, 2.0, 9, dtype=np.float64)
    density_curves = np.stack(
        [
            np.linspace(0.05, 1.40, 9),
            np.linspace(0.08, 1.30, 9) ** 1.05,
            np.linspace(0.10, 1.20, 9) ** 1.10,
        ],
        axis=1,
    )
    log_raw = np.array(
        [
            [[-2.5, -2.0, -1.5], [-1.0, -0.5, 0.0]],
            [[0.5, 1.0, 1.5], [1.8, -2.2, 0.25]],
        ],
        dtype=np.float64,
    )
    gamma = np.array([1.0, 1.1, 0.9], dtype=np.float64)

    actual = interpolate_exposure_to_density_backend(
        log_raw,
        log_exposure,
        density_curves,
        gamma,
        backend=backend,
    )
    expected = interpolate_exposure_to_density(
        log_raw,
        density_curves,
        log_exposure,
        gamma,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


@pytest.mark.parametrize("profile_type", ["negative", "positive"])
def test_interpolate_density_cmy_layers_backend_matches_cpu_reference(profile_type: str) -> None:
    backend = NumpyBackend()
    density_cmy = np.array(
        [
            [[0.15, 0.25, 0.35], [0.40, 0.50, 0.60]],
            [[0.70, 0.80, 0.90], [1.00, 1.10, 1.20]],
        ],
        dtype=np.float64,
    )
    density_curves = np.column_stack([
        np.linspace(0.0, 2.1, 10),
        np.linspace(0.0, 1.9, 10),
        np.linspace(0.0, 1.7, 10),
    ])
    density_curves_layers = np.stack([
        density_curves * np.array([0.55, 0.50, 0.45]),
        density_curves * np.array([0.30, 0.33, 0.35]),
        density_curves * np.array([0.15, 0.17, 0.20]),
    ], axis=1)
    positive = profile_type == "positive"

    actual = interpolate_density_cmy_layers_backend(
        density_cmy,
        density_curves,
        density_curves_layers,
        positive_film=positive,
        backend=backend,
    )
    expected = interp_density_cmy_layers(
        density_cmy,
        density_curves,
        density_curves_layers,
        positive_film=positive,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


def test_interpolate_density_cmy_layers_mlx_matches_cpu_reference_when_available() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.15, 0.25, 0.35], [0.40, 0.50, 0.60]],
            [[0.70, 0.80, 0.90], [1.00, 1.10, 1.20]],
        ],
        dtype=np.float32,
    )
    density_curves = np.column_stack([
        np.linspace(0.0, 2.1, 10),
        np.linspace(0.0, 1.9, 10),
        np.linspace(0.0, 1.7, 10),
    ]).astype(np.float32)
    density_curves_layers = np.stack([
        density_curves * np.array([0.55, 0.50, 0.45], dtype=np.float32),
        density_curves * np.array([0.30, 0.33, 0.35], dtype=np.float32),
        density_curves * np.array([0.15, 0.17, 0.20], dtype=np.float32),
    ], axis=1)

    actual = interpolate_density_cmy_layers_backend(
        backend.asarray(density_cmy),
        density_curves,
        density_curves_layers,
        positive_film=False,
        backend=backend,
    )
    expected = interp_density_cmy_layers(
        density_cmy,
        density_curves,
        density_curves_layers,
        positive_film=False,
    )

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)


def test_interpolate_exposure_to_density_cupy_matches_cpu_reference_when_available() -> None:
    backend = _cupy_backend_or_skip()
    log_exposure = np.linspace(-3.0, 2.0, 9, dtype=np.float32)
    density_curves = np.stack(
        [
            np.linspace(0.05, 1.40, 9),
            np.linspace(0.08, 1.30, 9) ** 1.05,
            np.linspace(0.10, 1.20, 9) ** 1.10,
        ],
        axis=1,
    ).astype(np.float32)
    log_raw = np.array(
        [
            [[-2.5, -2.0, -1.5], [-1.0, -0.5, 0.0]],
            [[0.5, 1.0, 1.5], [1.8, -2.2, 0.25]],
        ],
        dtype=np.float32,
    )
    gamma = np.array([1.0, 1.1, 0.9], dtype=np.float32)

    actual = interpolate_exposure_to_density_backend(
        backend.asarray(log_raw),
        log_exposure,
        density_curves,
        gamma,
        backend=backend,
    )
    expected = interpolate_exposure_to_density(
        log_raw,
        density_curves,
        log_exposure,
        gamma,
    )

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)


def test_interpolate_density_cmy_layers_cupy_matches_cpu_reference_when_available() -> None:
    backend = _cupy_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.15, 0.25, 0.35], [0.40, 0.50, 0.60]],
            [[0.70, 0.80, 0.90], [1.00, 1.10, 1.20]],
        ],
        dtype=np.float32,
    )
    density_curves = np.column_stack([
        np.linspace(0.0, 2.1, 10),
        np.linspace(0.0, 1.9, 10),
        np.linspace(0.0, 1.7, 10),
    ]).astype(np.float32)
    density_curves_layers = np.stack([
        density_curves * np.array([0.55, 0.50, 0.45], dtype=np.float32),
        density_curves * np.array([0.30, 0.33, 0.35], dtype=np.float32),
        density_curves * np.array([0.15, 0.17, 0.20], dtype=np.float32),
    ], axis=1)

    actual = interpolate_density_cmy_layers_backend(
        backend.asarray(density_cmy),
        density_curves,
        density_curves_layers,
        positive_film=True,
        backend=backend,
    )
    expected = interp_density_cmy_layers(
        density_cmy,
        density_curves,
        density_curves_layers,
        positive_film=True,
    )

    np.testing.assert_allclose(backend.to_numpy(actual), expected, rtol=2e-6, atol=2e-6)


def test_dir_coupler_exposure_correction_backend_matches_cpu_without_diffusion() -> None:
    backend = NumpyBackend()
    backend.supports_gpu = True
    log_raw = np.array(
        [
            [[-1.0, -0.8, -0.6], [-0.4, -0.2, 0.0]],
            [[0.2, 0.4, 0.6], [0.8, 1.0, 1.2]],
        ],
        dtype=np.float64,
    )
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.40, 0.10, 0.05]],
            [[0.15, 0.25, 0.35], [0.60, 0.70, 0.20]],
        ],
        dtype=np.float64,
    )
    density_max = np.array([1.5, 1.4, 1.3], dtype=np.float64)
    matrix = np.array(
        [
            [0.10, 0.05, 0.02],
            [0.03, 0.12, 0.04],
            [0.02, 0.06, 0.14],
        ],
        dtype=np.float64,
    )

    actual = compute_exposure_correction_dir_couplers(
        log_raw,
        density_cmy,
        density_max,
        matrix,
        diffusion_size_pixel=0.0,
        backend=backend,
    )
    expected = compute_exposure_correction_dir_couplers(
        log_raw,
        density_cmy,
        density_max,
        matrix,
        diffusion_size_pixel=0.0,
        backend=None,
    )

    np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)


# ---------------------------------------------------------------------------
# Parity: CMY -> log(XYZ) full chain vs CPU reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_cmy_to_log_xyz_backend_matches_cpu_reference(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    cmfs = STANDARD_OBSERVER_CMFS[:]
    rng = np.random.default_rng(42)
    density_cmy = rng.uniform(0.0, 2.1, (16, 16, 3))
    channel_density = np.linspace(0.05, 1.2, cmfs.shape[0] * 3).reshape(-1, 3)
    base_density = np.linspace(0.01, 0.05, cmfs.shape[0])
    scan_illuminant = np.linspace(0.2, 1.0, cmfs.shape[0])
    normalization = np.sum(scan_illuminant * cmfs[:, 1], axis=0)
    dtype = np.float64 if backend_name == "cpu" else np.float32

    result = cmy_to_log_xyz_backend(
        backend.asarray(density_cmy.astype(dtype)),
        channel_density.astype(dtype),
        base_density.astype(dtype),
        scan_illuminant.astype(dtype),
        cmfs.astype(dtype),
        float(normalization),
        backend,
    )
    result_np = backend.to_numpy(result)

    density_spectral = compute_density_spectral(channel_density.astype(dtype), density_cmy.astype(dtype), base_density.astype(dtype))
    light = density_to_light(density_spectral, scan_illuminant.astype(dtype))
    xyz = contract("ijk,kl->ijl", light, cmfs.astype(dtype)) / float(normalization)
    expected = np.log10(np.fmax(xyz, 0.0) + 1e-10)

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=1e-5), (
        f"backend={backend_name!r} cmy_to_log_xyz mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Parity: density_to_light vs CPU reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_density_to_light_matches_cpu_reference(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    density_spectral = rng.uniform(0.0, 3.0, (16, 16, 81))
    illuminant = rng.uniform(0.1, 1.0, (81,))
    dtype = np.float64 if backend_name == "cpu" else np.float32

    result = density_to_light_backend(
        backend.asarray(density_spectral.astype(dtype)),
        illuminant.astype(dtype),
        backend,
    )
    result_np = backend.to_numpy(result)
    expected = 10.0 ** (-density_spectral.astype(dtype)) * illuminant.astype(dtype)

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=1e-6), (
        f"backend={backend_name!r} density_to_light mismatch: max_abs_diff={max_abs_diff:.2e}"
    )


# ---------------------------------------------------------------------------
# Parity: light_to_raw vs CPU reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("backend_name", _available_backends())
def test_light_to_raw_matches_cpu_reference(backend_name: str) -> None:
    backend = _get_backend(backend_name)
    rng = np.random.default_rng(42)
    light = rng.uniform(0.0, 1.0, (16, 16, 81))
    sensitivity = rng.uniform(0.0, 1.0, (81, 3))
    dtype = np.float64 if backend_name == "cpu" else np.float32

    result = light_to_raw(
        backend.asarray(light.astype(dtype)),
        sensitivity.astype(dtype),
        backend,
    )
    result_np = backend.to_numpy(result)
    expected = contract("ijk,kl->ijl", light.astype(dtype), sensitivity.astype(dtype))

    max_abs_diff = float(np.max(np.abs(result_np - expected)))
    assert np.allclose(result_np, expected, atol=1e-5), (
        f"backend={backend_name!r} light_to_raw mismatch: max_abs_diff={max_abs_diff:.2e}"
    )
