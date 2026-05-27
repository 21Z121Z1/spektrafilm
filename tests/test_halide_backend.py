from __future__ import annotations

import sys

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.color import precompute_rgb_to_xyz_matrix, rgb_to_xyz


pytestmark = pytest.mark.unit


def test_select_backend_halide_is_strict_when_dependency_missing(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "halide", None)

    with pytest.raises(BackendUnavailableError, match="compute_backend='halide' requires"):
        select_backend("halide")


def test_halide_backend_rejects_non_float32_precision() -> None:
    halide = pytest.importorskip("halide")

    from spektrafilm.gpu.halide_backend import HalideBackend

    with pytest.raises(BackendUnavailableError, match="float32"):
        HalideBackend(precision="float64", halide_module=halide)


def test_halide_backend_cleanup_clears_cached_pipelines() -> None:
    from spektrafilm.gpu.halide_backend import HalideBackend

    class FakeHalide:
        @staticmethod
        def get_host_target() -> object:
            return object()

    backend = HalideBackend(halide_module=FakeHalide)
    backend._trilinear_3d_cache[17] = object()
    backend._rgb_matrix_pipeline = (object(), object(), object())

    backend.cleanup()

    assert backend._trilinear_3d_cache == {}
    assert backend._rgb_matrix_pipeline is None


def test_halide_backend_rgb_to_xyz_matches_numpy_reference_when_available() -> None:
    halide = pytest.importorskip("halide")

    from spektrafilm.gpu.halide_backend import HalideBackend

    rng = np.random.default_rng(1234)
    rgb = rng.random((7, 11, 3), dtype=np.float32)
    matrix = precompute_rgb_to_xyz_matrix("sRGB").astype(np.float32)

    backend = HalideBackend(halide_module=halide)
    actual = rgb_to_xyz(rgb, matrix, backend)
    expected = np.matmul(rgb, matrix.T)

    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected, rtol=1e-6, atol=1e-6)


def test_probe_halide_reports_injected_module() -> None:
    from spektrafilm.halide.availability import probe_halide

    class FakeHalide:
        __version__ = "21.0.0"

        @staticmethod
        def install_dir() -> str:
            return "/tmp/fake-halide"

    availability = probe_halide(import_module=lambda _name: FakeHalide)

    assert availability.installed is True
    assert availability.version == "21.0.0"
    assert availability.install_dir == "/tmp/fake-halide"


def test_probe_halide_reports_missing_dependency() -> None:
    from spektrafilm.halide.availability import probe_halide

    def fail_import(_name: str):
        raise ModuleNotFoundError("No module named 'halide'")

    availability = probe_halide(import_module=fail_import)

    assert availability.installed is False
    assert availability.version is None
    assert "No module named 'halide'" in availability.error
