from __future__ import annotations

import inspect

import numpy as np
import pytest
from opt_einsum import contract

from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.gpu.kernels.density import (
    cmy_to_log_xyz_backend,
    compute_density_spectral as compute_density_spectral_backend,
    density_to_light as density_to_light_backend,
    interpolate_density_cmy_layer_backend,
    interpolate_density_cmy_layers_backend,
    interpolate_exposure_to_density_backend,
    light_to_raw,
    safe_log10_backend,
)
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend
from spektrafilm.gpu.residency import record_backend_residency
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


def _reference_mlx_cmy_to_log_raw_kernel(
    density_cmy: np.ndarray,
    channel_density: np.ndarray,
    base_density: np.ndarray,
    print_illuminant: np.ndarray,
    sensitivity: np.ndarray,
    exposure_factor,
    preflash,
) -> np.ndarray:
    density = np.asarray(density_cmy, dtype=np.float32)
    channel_density = np.asarray(channel_density, dtype=np.float32)
    base_density = np.asarray(base_density, dtype=np.float32)
    print_illuminant = np.asarray(print_illuminant, dtype=np.float32)
    sensitivity = np.asarray(sensitivity, dtype=np.float32)
    exposure_scalar = float(np.asarray(exposure_factor, dtype=np.float32).reshape(-1)[0])
    preflash = np.asarray(preflash, dtype=np.float32).reshape(-1)

    out = np.empty_like(density, dtype=np.float32)
    for y in range(density.shape[0]):
        for x in range(density.shape[1]):
            c0, c1, c2 = density[y, x]
            for c in range(3):
                raw = np.float32(0.0)
                for k in range(channel_density.shape[0]):
                    d = (
                        c0 * channel_density[k, 0]
                        + c1 * channel_density[k, 1]
                        + c2 * channel_density[k, 2]
                        + base_density[k]
                    )
                    if not bool(d == d):
                        continue
                    if d < -35.0:
                        d = np.float32(-35.0)
                    light = np.float32(10.0) ** np.float32(-d)
                    light = light * print_illuminant[k]
                    raw = raw + light * sensitivity[k, c]
                raw = raw * exposure_scalar + preflash[c]
                if not bool(raw == raw):
                    raw = np.float32(0.0)
                if raw < 0.0:
                    raw = np.float32(0.0)
                out[y, x, c] = np.log10(raw + np.float32(1e-10))
    return out.astype(np.float32)


def _reference_mlx_cmy_to_log_xyz_kernel(
    density_cmy: np.ndarray,
    channel_density: np.ndarray,
    base_density: np.ndarray | None,
    scan_illuminant: np.ndarray,
    cmfs: np.ndarray,
    normalization: float,
) -> np.ndarray:
    density = np.asarray(density_cmy, dtype=np.float32)
    channel_density = np.asarray(channel_density, dtype=np.float32)
    if base_density is None:
        base_density = np.zeros((channel_density.shape[0],), dtype=np.float32)
    else:
        base_density = np.asarray(base_density, dtype=np.float32)
    scan_illuminant = np.asarray(scan_illuminant, dtype=np.float32)
    cmfs = np.asarray(cmfs, dtype=np.float32)

    out = np.empty_like(density, dtype=np.float32)
    for y in range(density.shape[0]):
        for x in range(density.shape[1]):
            c0, c1, c2 = density[y, x]
            xyz = np.zeros((3,), dtype=np.float32)
            for k in range(channel_density.shape[0]):
                d = (
                    c0 * channel_density[k, 0]
                    + c1 * channel_density[k, 1]
                    + c2 * channel_density[k, 2]
                    + base_density[k]
                )
                if not bool(d == d):
                    continue
                if d < -35.0:
                    d = np.float32(-35.0)
                light = np.float32(10.0) ** np.float32(-d)
                light = light * scan_illuminant[k]
                xyz += light * cmfs[k]
            vals = xyz / np.float32(normalization)
            vals = np.maximum(vals, np.float32(0.0))
            out[y, x] = np.log10(vals + np.float32(1e-10))
    return out.astype(np.float32)


def test_mlx_custom_cmy_kernel_has_no_default_nan_debug_readbacks() -> None:
    """Default MLX custom-kernel path must not read full arrays back for debug prints."""
    from spektrafilm.gpu.kernels import density as density_module

    source = inspect.getsource(density_module.cmy_to_log_xyz_backend)
    forbidden = (
        "np.array(density_cmy_flat)",
        "np.array(channel_density_flat)",
        "np.array(base_density_flat)",
        "np.array(scan_illuminant_flat)",
        "np.array(cmfs_flat)",
        "np.array(normalization_mx)",
        "np.array(outputs[0])",
    )

    for needle in forbidden:
        assert needle not in source


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


@pytest.mark.parametrize("base_density_mode", ["none", "present"])
def test_mlx_cmy_to_log_xyz_direct_custom_kernel_matches_manual_cpu_chain(base_density_mode: str) -> None:
    backend = _mlx_backend_or_skip()
    cmfs = STANDARD_OBSERVER_CMFS[:].astype(np.float32)
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.40, 0.10, 0.05]],
            [[0.15, 0.25, 0.35], [0.60, 0.70, 0.20]],
        ],
        dtype=np.float32,
    )
    channel_density = np.linspace(0.05, 1.2, cmfs.shape[0] * 3, dtype=np.float32).reshape(-1, 3)
    base_density = (
        None
        if base_density_mode == "none"
        else np.linspace(0.01, 0.05, cmfs.shape[0], dtype=np.float32)
    )
    scan_illuminant = np.linspace(0.2, 1.0, cmfs.shape[0], dtype=np.float32)
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))

    result = cmy_to_log_xyz_backend(
        backend.asarray(density_cmy),
        backend.asarray(channel_density),
        None if base_density is None else backend.asarray(base_density),
        backend.asarray(scan_illuminant),
        backend.asarray(cmfs),
        normalization,
        backend,
    )
    actual = backend.to_numpy(result)
    expected = _reference_mlx_cmy_to_log_xyz_kernel(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)


@pytest.mark.parametrize("table_kind", ["scan_film", "print_scan"])
def test_mlx_cmy_to_log_xyz_direct_custom_kernel_profile_table_shapes(table_kind: str) -> None:
    backend = _mlx_backend_or_skip()
    from spektrafilm.model.illuminants import standard_illuminant
    from spektrafilm.profiles.io import load_profile

    film = load_profile("kodak_portra_400")
    paper = load_profile("kodak_portra_endura")
    if table_kind == "scan_film":
        profile = film
    else:
        profile = paper
    channel_density = np.nan_to_num(
        np.asarray(profile.data.channel_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    base_density = np.nan_to_num(
        np.asarray(profile.data.base_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    scan_illuminant = np.asarray(standard_illuminant(profile.info.viewing_illuminant), dtype=np.float32)
    cmfs = STANDARD_OBSERVER_CMFS[:].astype(np.float32)
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))
    density_cmy = np.linspace(0.0, 1.4, 5 * 7 * 3, dtype=np.float32).reshape(5, 7, 3)

    actual = backend.to_numpy(
        cmy_to_log_xyz_backend(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(scan_illuminant),
            backend.asarray(cmfs),
            normalization,
            backend,
        )
    )
    expected = _reference_mlx_cmy_to_log_xyz_kernel(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    assert channel_density.shape[1] == 3
    assert channel_density.shape[0] == cmfs.shape[0] == scan_illuminant.shape[0]
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)


def test_mlx_cmy_to_log_xyz_direct_custom_kernel_non_divisible_pixel_count() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(91)
    density_cmy = rng.uniform(0.0, 1.4, size=(5, 7, 3)).astype(np.float32)
    channel_density = rng.uniform(0.02, 1.0, size=(13, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.05, size=(13,)).astype(np.float32)
    scan_illuminant = rng.uniform(0.1, 1.0, size=(13,)).astype(np.float32)
    cmfs = rng.uniform(0.01, 1.1, size=(13, 3)).astype(np.float32)
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))

    actual = backend.to_numpy(
        cmy_to_log_xyz_backend(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(scan_illuminant),
            backend.asarray(cmfs),
            normalization,
            backend,
        )
    )
    expected = _reference_mlx_cmy_to_log_xyz_kernel(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)


def test_mlx_cmy_to_log_xyz_direct_custom_kernel_random_inputs() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260620)
    density_cmy = rng.uniform(-0.1, 2.0, size=(6, 8, 3)).astype(np.float32)
    channel_density = rng.uniform(0.02, 1.2, size=(19, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.05, size=(19,)).astype(np.float32)
    scan_illuminant = rng.uniform(0.1, 1.0, size=(19,)).astype(np.float32)
    cmfs = rng.uniform(0.01, 1.1, size=(19, 3)).astype(np.float32)
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))

    actual = backend.to_numpy(
        cmy_to_log_xyz_backend(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(scan_illuminant),
            backend.asarray(cmfs),
            normalization,
            backend,
        )
    )
    expected = _reference_mlx_cmy_to_log_xyz_kernel(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)


def test_mlx_cmy_to_log_xyz_nan_tables_preserve_skip_behavior() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]],
        ],
        dtype=np.float32,
    )
    channel_density = np.array(
        [
            [0.3, 0.2, 0.1],
            [0.4, np.nan, 0.2],
            [0.1, 0.5, 0.7],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.02, 0.03, np.nan], dtype=np.float32)
    scan_illuminant = np.array([1.0, 0.5, 0.25], dtype=np.float32)
    cmfs = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.2, 0.4, 0.6],
            [0.7, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))

    actual = backend.to_numpy(
        cmy_to_log_xyz_backend(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(scan_illuminant),
            backend.asarray(cmfs),
            normalization,
            backend,
        )
    )
    expected = _reference_mlx_cmy_to_log_xyz_kernel(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-5)


def test_mlx_cmy_to_log_raw_fused_kernel_matches_cpu_without_readback() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.35, 0.18, 0.08]],
            [[0.05, 0.42, 0.16], [0.62, 0.55, 0.20]],
        ],
        dtype=np.float32,
    )
    channel_density = np.array(
        [
            [0.80, 0.10, 0.20],
            [0.20, 0.90, 0.10],
            [0.05, 0.30, 1.10],
            [0.40, 0.50, 0.20],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.03, np.nan, 0.05, 0.06], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.8, 0.6, 0.4], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.1, 0.6, 0.2],
            [0.2, 0.1, 0.7],
            [0.4, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    exposure_factor = np.array([1.25], dtype=np.float32)
    preflash = np.array([0.01, 0.02, 0.03], dtype=np.float32)

    with record_backend_residency() as recorder:
        actual_backend = backend.cmy_to_log_raw(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
        backend.eval(actual_backend)

    density_spectral = compute_density_spectral(channel_density, density_cmy, base_density)
    light = density_to_light(density_spectral, print_illuminant)
    raw = contract("ijk,kl->ijl", light, sensitivity)
    raw = raw * exposure_factor.reshape(1, 1, 1) + preflash.reshape(1, 1, 3)
    expected = np.log10(np.fmax(raw, 0.0) + 1e-10).astype(np.float32)

    actual = backend.to_numpy(actual_backend)
    assert recorder.unallowed_to_numpy_events() == []
    assert getattr(actual_backend, "dtype", None) == backend.mx.float32
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize(
    "case_name,density_cmy",
    [
        (
            "deterministic_small",
            np.array(
                [
                    [[0.10, 0.20, 0.30], [0.35, 0.18, 0.08]],
                    [[0.05, 0.42, 0.16], [0.62, 0.55, 0.20]],
                ],
                dtype=np.float32,
            ),
        ),
        (
            "non_divisible_thread_count",
            np.linspace(-0.1, 1.1, 5 * 7 * 3, dtype=np.float32).reshape(5, 7, 3),
        ),
        (
            "zero_density",
            np.zeros((3, 5, 3), dtype=np.float32),
        ),
        (
            "large_density",
            np.full((3, 5, 3), 8.0, dtype=np.float32),
        ),
        (
            "negative_density",
            np.full((3, 5, 3), -2.0, dtype=np.float32),
        ),
    ],
)
def test_mlx_cmy_to_log_raw_focused_cases_match_kernel_reference(case_name: str, density_cmy: np.ndarray) -> None:
    backend = _mlx_backend_or_skip()
    del case_name
    channel_density = np.array(
        [
            [0.80, 0.10, 0.20],
            [0.20, 0.90, 0.10],
            [0.05, 0.30, 1.10],
            [0.40, 0.50, 0.20],
            [0.25, 0.15, 0.75],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.03, 0.04, 0.05, 0.06, 0.02], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.8, 0.6, 0.4, 0.2], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.1, 0.6, 0.2],
            [0.2, 0.1, 0.7],
            [0.4, 0.3, 0.2],
            [0.3, 0.4, 0.5],
        ],
        dtype=np.float32,
    )
    exposure_factor = np.array([1.25], dtype=np.float32)
    preflash = np.array([0.01, 0.02, 0.03], dtype=np.float32)

    actual = backend.to_numpy(
        backend.cmy_to_log_raw(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_random_inputs_match_kernel_reference() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260619)
    density_cmy = rng.uniform(-0.25, 2.0, size=(6, 8, 3)).astype(np.float32)
    channel_density = rng.uniform(0.01, 1.4, size=(17, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.08, size=(17,)).astype(np.float32)
    print_illuminant = rng.uniform(0.05, 1.2, size=(17,)).astype(np.float32)
    sensitivity = rng.uniform(0.01, 0.9, size=(17, 3)).astype(np.float32)
    exposure_factor = np.array([0.85], dtype=np.float32)
    preflash = np.array([0.0, 0.01, 0.04], dtype=np.float32)

    actual = backend.to_numpy(
        backend.cmy_to_log_raw(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(print_illuminant),
            backend.asarray(sensitivity),
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_nan_tables_preserve_current_skip_behavior() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]],
        ],
        dtype=np.float32,
    )
    channel_density = np.array(
        [
            [0.3, 0.2, 0.1],
            [0.4, np.nan, 0.2],
            [0.1, 0.5, 0.7],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.02, 0.03, np.nan], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.5, 0.25], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.2, 0.4, 0.6],
            [0.7, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    exposure_factor = np.array([1.0], dtype=np.float32)
    preflash = np.zeros((3,), dtype=np.float32)

    actual = backend.to_numpy(
        backend.cmy_to_log_raw(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_table_cache_matches_pixel_thread_v1() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260622)
    density_cmy = rng.uniform(-0.25, 2.0, size=(6, 8, 3)).astype(np.float32)
    channel_density = rng.uniform(0.01, 1.4, size=(17, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.08, size=(17,)).astype(np.float32)
    print_illuminant = rng.uniform(0.05, 1.2, size=(17,)).astype(np.float32)
    sensitivity = rng.uniform(0.01, 0.9, size=(17, 3)).astype(np.float32)
    exposure_factor = np.array([0.85], dtype=np.float32)
    preflash = np.array([0.0, 0.01, 0.04], dtype=np.float32)

    table_cache = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_table_cache(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(print_illuminant),
            backend.asarray(sensitivity),
            exposure_factor,
            preflash,
        )
    )
    pixel_thread = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_v1(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(print_illuminant),
            backend.asarray(sensitivity),
            exposure_factor,
            preflash,
        )
    )

    np.testing.assert_allclose(table_cache, pixel_thread, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize(
    "preflash,exposure_factor",
    [
        (np.zeros((3,), dtype=np.float32), np.array([1.0], dtype=np.float32)),
        (np.array([0.001, 0.002, 0.003], dtype=np.float32), np.array([1.4], dtype=np.float32)),
        (np.array([0.004, 0.005, 0.006], dtype=np.float32), np.array([0.7, 1.1, 1.6], dtype=np.float32)),
    ],
)
def test_mlx_cmy_to_log_raw_preflash_and_exposure_factor_existing_behavior(
    preflash: np.ndarray,
    exposure_factor: np.ndarray,
) -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array([[[0.2, 0.3, 0.4], [0.5, 0.4, 0.3]]], dtype=np.float32)
    channel_density = np.array(
        [
            [0.6, 0.2, 0.1],
            [0.2, 0.7, 0.3],
            [0.1, 0.2, 0.8],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.01, 0.02, 0.03], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.6, 0.3], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.3, 0.4, 0.5],
            [0.5, 0.3, 0.4],
            [0.4, 0.5, 0.3],
        ],
        dtype=np.float32,
    )

    actual = backend.to_numpy(
        backend.cmy_to_log_raw(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_pixel_thread_v1_matches_reference_without_readback() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.10, 0.20, 0.30], [0.35, 0.18, 0.08]],
            [[0.05, 0.42, 0.16], [0.62, 0.55, 0.20]],
        ],
        dtype=np.float32,
    )
    channel_density = np.array(
        [
            [0.80, 0.10, 0.20],
            [0.20, 0.90, 0.10],
            [0.05, 0.30, 1.10],
            [0.40, 0.50, 0.20],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.03, np.nan, 0.05, 0.06], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.8, 0.6, 0.4], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.1, 0.6, 0.2],
            [0.2, 0.1, 0.7],
            [0.4, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    exposure_factor = backend.asarray(np.array([1.25], dtype=np.float32))
    preflash = backend.asarray(np.array([0.01, 0.02, 0.03], dtype=np.float32))

    original_asarray = np.asarray

    def guard_asarray(value, dtype=None):
        if type(value).__module__.startswith("mlx."):
            raise AssertionError("cmy_to_log_raw_pixel_thread_v1 must not call np.asarray on an MLX array")
        return original_asarray(value, dtype=dtype)

    np.asarray = guard_asarray
    try:
        with record_backend_residency() as recorder:
            actual_backend = backend.cmy_to_log_raw_pixel_thread_v1(
                density_cmy,
                channel_density,
                base_density,
                print_illuminant,
                sensitivity,
                exposure_factor,
                preflash,
            )
            backend.eval(actual_backend)
    finally:
        np.asarray = original_asarray

    actual = backend.to_numpy(actual_backend)
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    assert recorder.unallowed_to_numpy_events() == []
    assert getattr(actual_backend, "dtype", None) == backend.mx.float32
    assert actual.shape == density_cmy.shape
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize(
    "case_name,density_cmy",
    [
        (
            "deterministic_small",
            np.array(
                [
                    [[0.10, 0.20, 0.30], [0.35, 0.18, 0.08]],
                    [[0.05, 0.42, 0.16], [0.62, 0.55, 0.20]],
                ],
                dtype=np.float32,
            ),
        ),
        (
            "non_divisible_pixel_count",
            np.linspace(-0.1, 1.1, 5 * 7 * 3, dtype=np.float32).reshape(5, 7, 3),
        ),
        (
            "zero_density",
            np.zeros((3, 5, 3), dtype=np.float32),
        ),
        (
            "large_density",
            np.full((3, 5, 3), 8.0, dtype=np.float32),
        ),
        (
            "negative_density",
            np.full((3, 5, 3), -2.0, dtype=np.float32),
        ),
    ],
)
def test_mlx_cmy_to_log_raw_pixel_thread_v1_focused_cases_match_reference(
    case_name: str,
    density_cmy: np.ndarray,
) -> None:
    backend = _mlx_backend_or_skip()
    del case_name
    channel_density = np.array(
        [
            [0.80, 0.10, 0.20],
            [0.20, 0.90, 0.10],
            [0.05, 0.30, 1.10],
            [0.40, 0.50, 0.20],
            [0.25, 0.15, 0.75],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.03, 0.04, 0.05, 0.06, 0.02], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.8, 0.6, 0.4, 0.2], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.1, 0.6, 0.2],
            [0.2, 0.1, 0.7],
            [0.4, 0.3, 0.2],
            [0.3, 0.4, 0.5],
        ],
        dtype=np.float32,
    )
    exposure_factor = np.array([1.25], dtype=np.float32)
    preflash = np.array([0.01, 0.02, 0.03], dtype=np.float32)

    actual = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_v1(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_pixel_thread_v1_random_inputs_match_current_kernel() -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(20260621)
    density_cmy = rng.uniform(-0.25, 2.0, size=(6, 8, 3)).astype(np.float32)
    channel_density = rng.uniform(0.01, 1.4, size=(17, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.08, size=(17,)).astype(np.float32)
    print_illuminant = rng.uniform(0.05, 1.2, size=(17,)).astype(np.float32)
    sensitivity = rng.uniform(0.01, 0.9, size=(17, 3)).astype(np.float32)
    exposure_factor = np.array([0.85], dtype=np.float32)
    preflash = np.array([0.0, 0.01, 0.04], dtype=np.float32)

    current = backend.to_numpy(
        backend.cmy_to_log_raw(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(print_illuminant),
            backend.asarray(sensitivity),
            exposure_factor,
            preflash,
        )
    )
    v1 = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_v1(
            backend.asarray(density_cmy),
            backend.asarray(channel_density),
            backend.asarray(base_density),
            backend.asarray(print_illuminant),
            backend.asarray(sensitivity),
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(v1, expected, rtol=0.0, atol=1e-6)
    np.testing.assert_allclose(v1, current, rtol=0.0, atol=1e-6)


def test_mlx_cmy_to_log_raw_pixel_thread_v1_nan_tables_preserve_current_skip_behavior() -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array(
        [
            [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],
            [[0.7, 0.8, 0.9], [1.0, 1.1, 1.2]],
        ],
        dtype=np.float32,
    )
    channel_density = np.array(
        [
            [0.3, 0.2, 0.1],
            [0.4, np.nan, 0.2],
            [0.1, 0.5, 0.7],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.02, 0.03, np.nan], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.5, 0.25], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.5, 0.2, 0.1],
            [0.2, 0.4, 0.6],
            [0.7, 0.3, 0.2],
        ],
        dtype=np.float32,
    )
    exposure_factor = np.array([1.0], dtype=np.float32)
    preflash = np.zeros((3,), dtype=np.float32)

    actual = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_v1(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


@pytest.mark.parametrize(
    "preflash,exposure_factor",
    [
        (np.zeros((3,), dtype=np.float32), np.array([1.0], dtype=np.float32)),
        (np.array([0.001, 0.002, 0.003], dtype=np.float32), np.array([1.4], dtype=np.float32)),
        (np.array([0.004, 0.005, 0.006], dtype=np.float32), np.array([0.7, 1.1, 1.6], dtype=np.float32)),
    ],
)
def test_mlx_cmy_to_log_raw_pixel_thread_v1_preflash_and_exposure_factor_existing_behavior(
    preflash: np.ndarray,
    exposure_factor: np.ndarray,
) -> None:
    backend = _mlx_backend_or_skip()
    density_cmy = np.array([[[0.2, 0.3, 0.4], [0.5, 0.4, 0.3]]], dtype=np.float32)
    channel_density = np.array(
        [
            [0.6, 0.2, 0.1],
            [0.2, 0.7, 0.3],
            [0.1, 0.2, 0.8],
        ],
        dtype=np.float32,
    )
    base_density = np.array([0.01, 0.02, 0.03], dtype=np.float32)
    print_illuminant = np.array([1.0, 0.6, 0.3], dtype=np.float32)
    sensitivity = np.array(
        [
            [0.3, 0.4, 0.5],
            [0.5, 0.3, 0.4],
            [0.4, 0.5, 0.3],
        ],
        dtype=np.float32,
    )

    actual = backend.to_numpy(
        backend.cmy_to_log_raw_pixel_thread_v1(
            density_cmy,
            channel_density,
            base_density,
            print_illuminant,
            sensitivity,
            exposure_factor,
            preflash,
        )
    )
    expected = _reference_mlx_cmy_to_log_raw_kernel(
        density_cmy,
        channel_density,
        base_density,
        print_illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    np.testing.assert_allclose(actual, expected, rtol=0.0, atol=1e-6)


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


@pytest.mark.parametrize("positive_film", [False, True])
def test_interpolate_density_cmy_layer_mlx_is_exact_slice_of_full_kernel(
    positive_film: bool,
) -> None:
    backend = _mlx_backend_or_skip()
    rng = np.random.default_rng(382)
    density_cmy = rng.random((17, 19, 3), dtype=np.float32) * np.float32(1.8)
    density_curves = np.column_stack(
        [
            np.linspace(0.0, 2.1, 16),
            np.linspace(0.0, 1.9, 16),
            np.linspace(0.0, 1.7, 16),
        ]
    ).astype(np.float32)
    density_curves_layers = np.stack(
        [
            density_curves * np.array([0.55, 0.50, 0.45], dtype=np.float32),
            density_curves * np.array([0.30, 0.33, 0.35], dtype=np.float32),
            density_curves * np.array([0.15, 0.17, 0.20], dtype=np.float32),
        ],
        axis=1,
    )
    full = interpolate_density_cmy_layers_backend(
        backend.asarray(density_cmy),
        density_curves,
        density_curves_layers,
        positive_film=positive_film,
        backend=backend,
    )
    backend.eval(full)
    full_np = backend.to_numpy(full)

    for layer in range(3):
        for channel in range(3):
            plane = interpolate_density_cmy_layer_backend(
                backend.asarray(density_cmy),
                density_curves,
                density_curves_layers,
                layer,
                channel,
                positive_film=positive_film,
                backend=backend,
            )
            backend.eval(plane)
            np.testing.assert_array_equal(backend.to_numpy(plane), full_np[..., layer, channel])


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
    # Tolerance is 1e-5 rather than L1's 1e-6 because the current MLX einsum
    # uses simple float32 accumulation. Measured worst-case error on random
    # inputs is ~7.6e-6. A compensated-sum kernel is required for L1 parity.
    assert np.allclose(result_np, expected, atol=1e-5), (
        f"backend={backend_name!r} light_to_raw mismatch: max_abs_diff={max_abs_diff:.2e}"
    )
