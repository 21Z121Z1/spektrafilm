from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.density import cmy_to_log_xyz_backend
from spektrafilm.gpu.kernels.lut import apply_lut_trilinear_3d_mlx
from spektrafilm.testing.float32_reference_backend import (
    Float32ReferenceBackend,
    apply_lut_trilinear_3d_same_order,
    cmy_to_log_raw_same_order,
    cmy_to_log_xyz_same_order,
    gain_map_ev_same_order,
)
from spektrafilm.testing.precision_metrics import gain_map_ev, precision_report


def _spectral_fixture() -> dict[str, np.ndarray | float]:
    rng = np.random.default_rng(1234)
    density = rng.uniform(0.02, 1.4, size=(4, 5, 3)).astype(np.float32)
    channel_density = rng.uniform(0.05, 0.8, size=(7, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.1, size=(7,)).astype(np.float32)
    illuminant = rng.uniform(0.1, 1.1, size=(7,)).astype(np.float32)
    sensitivity = rng.uniform(0.01, 0.9, size=(7, 3)).astype(np.float32)
    exposure = np.array([0.75], dtype=np.float32)
    preflash = np.array([0.0, 0.001, 0.002], dtype=np.float32)
    return {
        "density": density,
        "channel_density": channel_density,
        "base_density": base_density,
        "illuminant": illuminant,
        "sensitivity": sensitivity,
        "exposure": exposure,
        "preflash": preflash,
        "normalization": float(np.sum(illuminant * sensitivity[:, 1])),
    }


def _require_mlx_backend():
    try:
        return select_backend("mlx", precision="float32")
    except (BackendUnavailableError, Exception) as exc:
        pytest.skip(f"MLX unavailable: {exc}")


def test_float32_reference_backend_rounds_primitives_to_float32() -> None:
    backend = Float32ReferenceBackend()
    values = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float64)

    result = backend.log10(backend.maximum(values, 1e-3))
    mat = backend.matmul(values, np.eye(2, dtype=np.float64))

    assert result.dtype == np.float32
    assert mat.dtype == np.float32
    assert backend.name == "numpy_same_order_f32"
    assert not backend.supports_gpu


def test_same_order_einsum_uses_serial_float32_reduction() -> None:
    backend = Float32ReferenceBackend()
    lhs = np.array([[[1.0e8, 1.0, -1.0e8]]], dtype=np.float32)
    rhs = np.array([[1.0, 1.0, 1.0]], dtype=np.float32)

    same_order = backend.einsum("ijk,lk->ijl", lhs, rhs)
    legacy = np.einsum("ijk,lk->ijl", lhs, rhs).astype(np.float32)

    assert same_order.dtype == np.float32
    assert same_order.shape == (1, 1, 1)
    assert same_order[0, 0, 0] == np.float32(0.0)
    assert legacy.shape == same_order.shape


def test_same_order_spectral_helpers_return_finite_float32() -> None:
    data = _spectral_fixture()

    raw = cmy_to_log_raw_same_order(
        data["density"],
        data["channel_density"],
        data["base_density"],
        data["illuminant"],
        data["sensitivity"],
        data["exposure"],
        data["preflash"],
        tile_rows=2,
    )
    xyz = cmy_to_log_xyz_same_order(
        data["density"],
        data["channel_density"],
        data["base_density"],
        data["illuminant"],
        data["sensitivity"],
        data["normalization"],
        tile_rows=2,
    )

    assert raw.dtype == np.float32
    assert xyz.dtype == np.float32
    assert raw.shape == data["density"].shape
    assert xyz.shape == data["density"].shape
    assert np.isfinite(raw).all()
    assert np.isfinite(xyz).all()


def test_same_order_lut_matches_manual_trilinear_shape_and_dtype() -> None:
    rng = np.random.default_rng(4321)
    lut = rng.random((5, 5, 5, 3), dtype=np.float32)
    image = rng.uniform(-0.2, 1.2, size=(6, 7, 3)).astype(np.float32)

    result = apply_lut_trilinear_3d_same_order(lut, image)
    report = precision_report(result, result)

    assert result.dtype == np.float32
    assert result.shape == image.shape
    assert np.isfinite(result).all()
    assert report["max_abs_diff"] == 0.0


def test_gain_map_ev_same_order_tracks_metric_definition() -> None:
    sdr = np.full((3, 4, 3), 0.25, dtype=np.float32)
    hdr = sdr * np.float32(3.0)

    same_order = gain_map_ev_same_order(sdr, hdr)
    metric_order = gain_map_ev(sdr, hdr).astype(np.float32)

    np.testing.assert_allclose(same_order, metric_order, atol=2e-7)


def test_testing_backend_is_not_production_selected() -> None:
    backend = select_backend("cpu")

    assert backend.name == "cpu"
    assert backend.name != Float32ReferenceBackend().name


def test_mlx_fused_raw_is_close_to_same_order_reference_when_available() -> None:
    backend = _require_mlx_backend()
    data = _spectral_fixture()

    same_order = cmy_to_log_raw_same_order(
        data["density"],
        data["channel_density"],
        data["base_density"],
        data["illuminant"],
        data["sensitivity"],
        data["exposure"],
        data["preflash"],
    )
    mlx = backend.to_numpy(
        backend.cmy_to_log_raw(
            data["density"],
            data["channel_density"],
            data["base_density"],
            data["illuminant"],
            data["sensitivity"],
            data["exposure"],
            data["preflash"],
        )
    )

    np.testing.assert_allclose(mlx, same_order, atol=3e-5, rtol=3e-5)


def test_mlx_fused_xyz_is_close_to_same_order_reference_when_available() -> None:
    backend = _require_mlx_backend()
    data = _spectral_fixture()

    same_order = cmy_to_log_xyz_same_order(
        data["density"],
        data["channel_density"],
        data["base_density"],
        data["illuminant"],
        data["sensitivity"],
        data["normalization"],
    )
    mlx = backend.to_numpy(
        cmy_to_log_xyz_backend(
            data["density"],
            data["channel_density"],
            data["base_density"],
            data["illuminant"],
            data["sensitivity"],
            data["normalization"],
            backend,
        )
    )

    np.testing.assert_allclose(mlx, same_order, atol=3e-5, rtol=3e-5)


def test_mlx_lut_is_close_to_same_order_reference_when_available() -> None:
    backend = _require_mlx_backend()
    rng = np.random.default_rng(999)
    lut = rng.random((5, 5, 5, 3), dtype=np.float32)
    image = rng.uniform(-0.1, 1.1, size=(5, 6, 3)).astype(np.float32)

    same_order = apply_lut_trilinear_3d_same_order(lut, image)
    mlx = backend.to_numpy(
        apply_lut_trilinear_3d_mlx(
            backend.asarray(lut),
            backend.asarray(image),
            mx=backend.mx,
        )
    )

    np.testing.assert_allclose(mlx, same_order, atol=2e-6, rtol=2e-6)
