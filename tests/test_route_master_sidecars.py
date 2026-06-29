from __future__ import annotations

import copy

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.process import Simulator
from spektrafilm.runtime.route_master import get_material_detail_y, get_route_look_chroma
from tests.conftest import make_fast_test_params


pytestmark = pytest.mark.integration


def _image(size: int = 6) -> np.ndarray:
    ramp = np.linspace(0.03, 1.5, size, dtype=np.float64)
    image = np.ones((size, size, 3), dtype=np.float64)
    image *= ramp[None, :, None]
    image[:, size // 2 :, 0] *= 1.15
    image[:, : size // 2, 2] *= 0.85
    return image


def _present_shaped_fields(master) -> set[str]:
    return {
        field
        for field in (
            "route_linear_rgb",
            "route_linear_xyz",
            "route_luminance_y",
            "sdr_legacy_rgb",
            "scene_y_raw",
            "post_halation_y",
            "density_cmy",
            "route_look_chroma",
            "material_detail_y",
        )
        if getattr(getattr(master, field), "shape", None) is not None
    }


def _mlx_available_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def test_process_with_master_uses_minimal_route_sidecars_by_default() -> None:
    result = Simulator(make_fast_test_params()).process_with_master(_image(), hdr_mode="paper")

    master = result.route_master
    assert master is not None
    assert master.route_linear_rgb.shape == (6, 6, 3)
    assert master.route_luminance_y.shape == (6, 6)
    assert master.sdr_legacy_rgb.shape == (6, 6, 3)
    assert master.scene_y_raw.shape == (6, 6)
    assert master.post_halation_y.shape == (6, 6)
    assert master.route_linear_xyz is None
    assert master.density_cmy is None
    assert master.route_look_chroma is None
    assert master.material_detail_y is None
    assert master.diagnostics["hdr_route_sidecar_policy"] == "minimal"


def test_full_route_sidecar_policy_restores_debug_arrays() -> None:
    params = make_fast_test_params()
    params.settings.hdr_route_sidecar_policy = "full"

    result = Simulator(params).process_with_master(_image(), hdr_mode="paper")

    master = result.route_master
    assert master is not None
    assert master.route_linear_xyz.shape == (6, 6, 3)
    assert master.density_cmy.shape == (6, 6, 3)
    assert master.route_look_chroma.shape == (6, 6, 3)
    assert master.material_detail_y.shape == (6, 6)
    assert master.diagnostics["hdr_route_sidecar_policy"] == "full"


def test_on_demand_route_sidecar_policy_keeps_fields_lazy_and_helpers_compute() -> None:
    params = make_fast_test_params()
    params.settings.hdr_route_sidecar_policy = "on_demand"

    result = Simulator(params).process_with_master(_image(), hdr_mode="paper")

    master = result.route_master
    assert master is not None
    assert master.route_linear_xyz is None
    assert master.density_cmy is None
    assert master.route_look_chroma is None
    assert master.material_detail_y is None
    assert master.diagnostics["hdr_route_sidecar_policy"] == "on_demand"

    chroma = get_route_look_chroma(master, backend_policy="numpy")
    detail = get_material_detail_y(master, backend_policy="numpy")
    assert chroma.shape == master.route_linear_rgb.shape
    assert detail.shape == master.route_luminance_y.shape
    assert np.all(np.isfinite(chroma))
    assert np.all(np.isfinite(detail))


def test_minimal_route_sidecars_have_fewer_full_resolution_arrays_than_full() -> None:
    minimal_params = make_fast_test_params()
    full_params = copy.deepcopy(minimal_params)
    full_params.settings.hdr_route_sidecar_policy = "full"

    minimal = Simulator(copy.deepcopy(minimal_params)).process_master(_image(), hdr_mode="paper")
    full = Simulator(copy.deepcopy(full_params)).process_master(_image(), hdr_mode="paper")

    minimal_fields = _present_shaped_fields(minimal)
    full_fields = _present_shaped_fields(full)
    assert {
        "route_linear_xyz",
        "density_cmy",
        "route_look_chroma",
        "material_detail_y",
    }.isdisjoint(minimal_fields)
    assert {
        "route_linear_xyz",
        "density_cmy",
        "route_look_chroma",
        "material_detail_y",
    } <= full_fields
    assert len(minimal_fields) < len(full_fields)


def test_mlx_backend_policy_keeps_minimal_route_sidecars_backend_resident() -> None:
    _mlx_available_or_skip()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.hdr_route_sidecar_policy = "minimal"
    pipeline = SimulationPipeline(params)

    result = pipeline.process_with_master(_image(), hdr_mode="paper")

    master = result.route_master
    assert master is not None
    for field in (
        "route_linear_rgb",
        "route_luminance_y",
        "sdr_legacy_rgb",
        "scene_y_raw",
        "post_halation_y",
    ):
        assert pipeline._array_backend._is_mlx_array(getattr(master, field)), field
    assert master.route_linear_xyz is None
    assert master.density_cmy is None
    assert master.route_look_chroma is None
    assert master.material_detail_y is None


def test_mlx_on_demand_route_sidecar_helpers_can_stay_backend_resident() -> None:
    _mlx_available_or_skip()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.hdr_route_sidecar_policy = "on_demand"
    pipeline = SimulationPipeline(params)

    result = pipeline.process_with_master(_image(), hdr_mode="paper")

    master = result.route_master
    assert master is not None
    chroma = get_route_look_chroma(master, backend_policy="backend")
    detail = get_material_detail_y(master, backend_policy="backend")
    assert pipeline._array_backend._is_mlx_array(chroma)
    assert pipeline._array_backend._is_mlx_array(detail)
    assert chroma.shape == master.route_linear_rgb.shape
    assert detail.shape == master.route_luminance_y.shape


def test_mlx_on_demand_numpy_helper_requires_explicit_backend() -> None:
    _mlx_available_or_skip()
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.hdr_route_sidecar_policy = "on_demand"
    pipeline = SimulationPipeline(params)
    master = pipeline.process_with_master(_image(), hdr_mode="paper").route_master

    assert master is not None
    with pytest.raises(ValueError, match="requires an explicit backend"):
        get_route_look_chroma(master, backend_policy="numpy")
    chroma = get_route_look_chroma(master, backend_policy="numpy", backend=pipeline._backend)
    assert isinstance(chroma, np.ndarray)
