"""Halide JIT tests for spectral kernels: density_to_light, light_to_raw, compute_density_spectral."""
from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.halide_backend import HalideBackend

pytestmark = pytest.mark.unit

halide = pytest.importorskip("halide")


@pytest.fixture()
def backend():
    return HalideBackend(halide_module=halide)


def _reference_density_to_light(density_chw, illuminant):
    """NumPy reference: light[c,h,wl] = 10^(-density[c,h,wl]) * illuminant[wl,c]."""
    # density is [C=3, H, W=81], illuminant is [81, 3]
    # illuminant[wl, c] -> broadcast over H dimension
    transmitted = np.power(10.0, -density_chw) * illuminant.T[:, None, :]
    return np.nan_to_num(transmitted, nan=0.0).astype(np.float32)


def _reference_light_to_raw(light_chw, sensitivity):
    """NumPy reference: raw[c_out,y,c_in] = sum_wl light[c_out,y,wl] * sensitivity[wl,c_in]."""
    # light [3, H, 81], sensitivity [81, 3]
    C_out, H, _ = light_chw.shape
    C_in = sensitivity.shape[1]
    result = np.zeros((C_out, H, C_in), dtype=np.float32)
    for co in range(C_out):
        for ci in range(C_in):
            result[co, :, ci] = light_chw[co, :, :] @ sensitivity[:, ci]
    return result


def _reference_compute_density_spectral(density_cmy_chw, channel_density):
    """NumPy reference: result[c,y,wl] = sum_k density_cmy[k,y,wl] * channel_density[k,wl]."""
    # density_cmy [3, H, 81], channel_density [3, 81]
    C, H, W = density_cmy_chw.shape
    result = np.zeros((C, H, W), dtype=np.float32)
    for c in range(C):
        for k in range(3):
            result[c] += density_cmy_chw[k] * channel_density[k][None, :]
    return result


def _reference_cmy_to_log_xyz_hwc(
    density_cmy,
    channel_density,
    base_density,
    scan_illuminant,
    cmfs,
    normalization,
):
    density_spectral = np.einsum("hwk,lk->hwl", density_cmy, channel_density)
    density_spectral = density_spectral + base_density
    light = np.power(10.0, -density_spectral) * scan_illuminant
    light = np.nan_to_num(light, nan=0.0)
    xyz = np.einsum("hwl,lc->hwc", light, cmfs) / normalization
    return np.log10(np.fmax(xyz, 0.0) + 1e-10).astype(np.float32)


def _reference_cmy_to_log_raw_hwc(
    density_cmy,
    channel_density,
    base_density,
    illuminant,
    sensitivity,
    exposure_factor,
    preflash,
):
    density_spectral = np.einsum("hwk,lk->hwl", density_cmy, channel_density)
    density_spectral = density_spectral + base_density
    light = np.power(10.0, -density_spectral) * illuminant
    light = np.nan_to_num(light, nan=0.0)
    raw = np.einsum("hwl,lc->hwc", light, sensitivity)
    raw = raw * exposure_factor + preflash
    return np.log10(np.fmax(raw, 0.0) + 1e-10).astype(np.float32)


def test_density_to_light_matches_numpy(backend) -> None:
    rng = np.random.default_rng(42)
    H = 16
    density = rng.random((3, H, 81), dtype=np.float32) * 2.0
    illuminant = rng.random((81, 3), dtype=np.float32) + 0.1

    expected = _reference_density_to_light(density, illuminant)
    actual = backend.density_to_light(density, illuminant)

    assert actual.shape == (3, H, 81)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_density_to_light_various_sizes(backend) -> None:
    rng = np.random.default_rng(123)
    for H in [1, 7, 32]:
        density = rng.random((3, H, 81), dtype=np.float32)
        illuminant = rng.random((81, 3), dtype=np.float32) + 0.01
        expected = _reference_density_to_light(density, illuminant)
        actual = backend.density_to_light(density, illuminant)
        np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_density_to_light_invalid_shapes(backend) -> None:
    with pytest.raises(ValueError, match="density must have shape"):
        backend.density_to_light(np.zeros((2, 8, 81), dtype=np.float32), np.zeros((81, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="illuminant must have shape"):
        backend.density_to_light(np.zeros((3, 8, 81), dtype=np.float32), np.zeros((80, 3), dtype=np.float32))


def test_light_to_raw_matches_numpy(backend) -> None:
    rng = np.random.default_rng(43)
    H = 16
    light = rng.random((3, H, 81), dtype=np.float32)
    sensitivity = rng.random((81, 3), dtype=np.float32) + 0.01

    expected = _reference_light_to_raw(light, sensitivity)
    actual = backend.light_to_raw(light, sensitivity)

    assert actual.shape == (3, H, 3)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-5)


def test_light_to_raw_various_heights(backend) -> None:
    rng = np.random.default_rng(44)
    for H in [1, 5, 20]:
        light = rng.random((3, H, 81), dtype=np.float32)
        sensitivity = rng.random((81, 3), dtype=np.float32) + 0.01
        expected = _reference_light_to_raw(light, sensitivity)
        actual = backend.light_to_raw(light, sensitivity)
        np.testing.assert_allclose(actual, expected, atol=1e-5)


def test_light_to_raw_invalid_shapes(backend) -> None:
    with pytest.raises(ValueError, match="light must have shape"):
        backend.light_to_raw(np.zeros((2, 8, 81), dtype=np.float32), np.zeros((81, 3), dtype=np.float32))
    with pytest.raises(ValueError, match="sensitivity must have shape"):
        backend.light_to_raw(np.zeros((3, 8, 81), dtype=np.float32), np.zeros((80, 3), dtype=np.float32))


def test_compute_density_spectral_matches_numpy(backend) -> None:
    rng = np.random.default_rng(45)
    H = 16
    density_cmy = rng.random((3, H, 81), dtype=np.float32)
    channel_density = rng.random((3, 81), dtype=np.float32)

    expected = _reference_compute_density_spectral(density_cmy, channel_density)
    actual = backend.compute_density_spectral(density_cmy, channel_density)

    assert actual.shape == (3, H, 81)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_compute_density_spectral_various_heights(backend) -> None:
    rng = np.random.default_rng(46)
    for H in [1, 4, 20]:
        density_cmy = rng.random((3, H, 81), dtype=np.float32)
        channel_density = rng.random((3, 81), dtype=np.float32)
        expected = _reference_compute_density_spectral(density_cmy, channel_density)
        actual = backend.compute_density_spectral(density_cmy, channel_density)
        np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_compute_density_spectral_invalid_shapes(backend) -> None:
    with pytest.raises(ValueError, match="density_cmy must have shape"):
        backend.compute_density_spectral(np.zeros((2, 8, 81), dtype=np.float32), np.zeros((3, 81), dtype=np.float32))
    with pytest.raises(ValueError, match="channel_density must have shape"):
        backend.compute_density_spectral(np.zeros((3, 8, 81), dtype=np.float32), np.zeros((3, 80), dtype=np.float32))


def test_fused_cmy_to_log_xyz_matches_numpy_for_hwc_runtime_shape(backend) -> None:
    rng = np.random.default_rng(91)
    density_cmy = rng.random((5, 7, 3), dtype=np.float32) * 1.4
    channel_density = rng.random((13, 3), dtype=np.float32) + 0.02
    base_density = rng.random(13, dtype=np.float32) * 0.05
    scan_illuminant = rng.random(13, dtype=np.float32) + 0.1
    cmfs = rng.random((13, 3), dtype=np.float32) + 0.01
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1]))

    expected = _reference_cmy_to_log_xyz_hwc(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )
    actual = backend.cmy_to_log_xyz(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    assert actual.shape == (5, 7, 3)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-5)


def test_fused_cmy_to_log_xyz_zeroes_nan_light_like_generic_backend(backend) -> None:
    rng = np.random.default_rng(93)
    density_cmy = rng.random((3, 4, 3), dtype=np.float32) * 1.4
    channel_density = rng.random((9, 3), dtype=np.float32) + 0.02
    channel_density[2, 1] = np.nan
    base_density = rng.random(9, dtype=np.float32) * 0.05
    base_density[5] = np.nan
    scan_illuminant = rng.random(9, dtype=np.float32) + 0.1
    cmfs = rng.random((9, 3), dtype=np.float32) + 0.01
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1]))

    expected = _reference_cmy_to_log_xyz_hwc(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )
    actual = backend.cmy_to_log_xyz(
        density_cmy,
        channel_density,
        base_density,
        scan_illuminant,
        cmfs,
        normalization,
    )

    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-5)


def test_fused_cmy_to_log_raw_matches_numpy_for_printing_chain(backend) -> None:
    rng = np.random.default_rng(92)
    density_cmy = rng.random((6, 4, 3), dtype=np.float32) * 1.2
    channel_density = rng.random((11, 3), dtype=np.float32) + 0.02
    base_density = rng.random(11, dtype=np.float32) * 0.04
    illuminant = rng.random(11, dtype=np.float32) + 0.1
    sensitivity = rng.random((11, 3), dtype=np.float32) + 0.01
    exposure_factor = np.array([0.8, 1.1, 1.3], dtype=np.float32)
    preflash = np.array([0.001, 0.002, 0.003], dtype=np.float32)

    expected = _reference_cmy_to_log_raw_hwc(
        density_cmy,
        channel_density,
        base_density,
        illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )
    actual = backend.cmy_to_log_raw(
        density_cmy,
        channel_density,
        base_density,
        illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    assert actual.shape == (6, 4, 3)
    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-5)


def test_fused_cmy_to_log_raw_zeroes_nan_light_like_generic_backend(backend) -> None:
    rng = np.random.default_rng(94)
    density_cmy = rng.random((4, 3, 3), dtype=np.float32) * 1.2
    channel_density = rng.random((10, 3), dtype=np.float32) + 0.02
    channel_density[1, 2] = np.nan
    base_density = rng.random(10, dtype=np.float32) * 0.04
    base_density[7] = np.nan
    illuminant = rng.random(10, dtype=np.float32) + 0.1
    sensitivity = rng.random((10, 3), dtype=np.float32) + 0.01
    exposure_factor = np.array([0.8, 1.1, 1.3], dtype=np.float32)
    preflash = np.array([0.001, 0.002, 0.003], dtype=np.float32)

    expected = _reference_cmy_to_log_raw_hwc(
        density_cmy,
        channel_density,
        base_density,
        illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )
    actual = backend.cmy_to_log_raw(
        density_cmy,
        channel_density,
        base_density,
        illuminant,
        sensitivity,
        exposure_factor,
        preflash,
    )

    assert np.isfinite(actual).all()
    np.testing.assert_allclose(actual, expected, rtol=2e-5, atol=2e-5)


def test_pipeline_caching_reuses_same_pipeline(backend) -> None:
    density = np.random.default_rng(47).random((3, 4, 81), dtype=np.float32)
    illuminant = np.random.default_rng(48).random((81, 3), dtype=np.float32) + 0.1

    backend.density_to_light(density, illuminant)
    pipeline1 = backend._density_to_light_pipeline
    backend.density_to_light(density, illuminant)
    pipeline2 = backend._density_to_light_pipeline

    assert pipeline1 is pipeline2


def test_cleanup_clears_spectral_pipelines(backend) -> None:
    density = np.random.default_rng(49).random((3, 4, 81), dtype=np.float32)
    illuminant = np.random.default_rng(50).random((81, 3), dtype=np.float32) + 0.1
    backend.density_to_light(density, illuminant)
    assert backend._density_to_light_pipeline is not None
    backend.cleanup()
    assert backend._density_to_light_pipeline is None
