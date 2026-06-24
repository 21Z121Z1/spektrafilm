from __future__ import annotations

import numpy as np

from spektrafilm.gpu.memory_budget import (
    decide_runtime_memory_budget,
    estimate_runtime_peak_budget,
    validate_resize_policy,
)
from spektrafilm.gpu.residency_profile import (
    ProfilingBackendProxy,
    record_residency_profile,
    scan_direct_numpy_materialization,
)
from spektrafilm.runtime.params_schema import SettingsParams
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.runtime.route_sidecars import get_material_detail_y, get_route_look_chroma


class DummyBackend:
    name = "dummy"
    supports_gpu = True
    fallback_reason = None
    requires_serial_runtime = False
    precision = "float32"
    default_dtype = np.float32

    @staticmethod
    def _is_mlx_array(value):
        return False

    def asarray(self, value, dtype=None):
        return np.asarray(value, dtype=dtype or np.float32)

    def to_numpy(self, value):
        return np.asarray(value)

    def eval(self, *values):
        return None

    def synchronize(self):
        return None

    def cleanup(self):
        return None

    def maximum(self, x, y):
        return np.maximum(x, y)


def test_residency_proxy_records_required_boundary_counts() -> None:
    backend = ProfilingBackendProxy(DummyBackend(), label_prefix="unit")
    with record_residency_profile() as recorder:
        arr = backend.asarray([[1.0, 2.0]], label="upload")
        backend.eval(arr, label="eval")
        backend.synchronize(label="sync")
        out = backend.to_numpy(arr, label="download")
        backend.clear_cache(label="clear")
        backend.cleanup(label="cleanup")

    assert out.shape == (1, 2)
    summary = recorder.summary()
    assert summary["backend.asarray"] >= 1
    assert summary["backend.to_numpy"] >= 1
    assert summary["backend.eval"] == 1
    assert summary["backend.synchronize"] == 1
    assert summary["backend.clear_cache"] == 1
    assert summary["backend.cleanup"] == 1


def test_runtime_memory_budget_decisions() -> None:
    estimate = estimate_runtime_peak_budget(
        height=3000,
        width=4000,
        compute_backend="mlx",
        materialize_policy="backend",
        hdr_mode="paper",
        hdr_route_sidecar_policy="full",
        budget_mib=128.0,
    )
    assert estimate.over_budget
    assert decide_runtime_memory_budget(estimate, policy="warn").action == "warn"
    soft = decide_runtime_memory_budget(estimate, policy="soft_enforce", current_hdr_route_sidecar_policy="full")
    assert soft.action == "soft_enforce"
    assert soft.recommended_gpu_tile_rows is not None
    assert soft.recommended_gpu_spatial_tile_rows is not None
    assert soft.recommended_hdr_route_sidecar_policy == "minimal"
    assert decide_runtime_memory_budget(estimate, policy="fail").action == "fail"


def test_resize_policy_makes_backend_residency_break_explicit() -> None:
    allowed, warning = validate_resize_policy(
        compute_backend="mlx",
        materialize_policy="backend",
        upscale_factor=1.25,
        preview_mode=False,
        gpu_resize_policy="warn",
    )
    assert allowed is True
    assert warning and "falls back" in warning
    allowed, warning = validate_resize_policy(
        compute_backend="mlx",
        materialize_policy="backend",
        upscale_factor=1.25,
        preview_mode=False,
        gpu_resize_policy="fail",
    )
    assert allowed is False
    assert warning
    allowed, warning = validate_resize_policy(
        compute_backend="mlx",
        materialize_policy="backend",
        upscale_factor=1.25,
        preview_mode=True,
        gpu_resize_policy="fail",
    )
    assert allowed is True
    assert warning is None


def test_route_master_on_demand_numpy_helpers_do_not_mutate_existing_fields() -> None:
    route_rgb = np.array(
        [[[0.2, 0.4, 0.6], [1.0, 1.0, 1.0]], [[0.1, 0.2, 0.3], [0.6, 0.3, 0.2]]],
        dtype=np.float32,
    )
    route_y = route_rgb[..., 1]
    master = RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_rgb,
        route_luminance_y=route_y,
        sdr_legacy_rgb=np.clip(route_rgb, 0.0, 1.0),
        scene_y_raw=route_y,
        post_halation_y=route_y,
        diagnostics={"hdr_route_sidecar_policy": "minimal"},
    )
    chroma = get_route_look_chroma(master, backend_policy="numpy")
    detail = get_material_detail_y(master, backend_policy="numpy")
    assert chroma.shape == route_rgb.shape
    assert detail.shape == route_y.shape
    assert master.route_look_chroma is None
    assert master.material_detail_y is None
    assert master.diagnostics["route_sidecar_on_demand_count"] == 2
    assert master.diagnostics["route_sidecar_materialization_count"] == 2


def test_new_policy_defaults_are_compatible() -> None:
    settings = SettingsParams()
    assert settings.gpu_peak_budget_mb is None
    assert settings.gpu_budget_policy == "off"
    assert settings.gpu_resize_policy == "cpu_fallback"
    assert settings.hdr_route_sidecar_policy == "minimal"


def test_static_guard_can_find_direct_numpy_materialization(tmp_path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("import numpy as np\nvalue = np.asarray(x)\n", encoding="utf-8")
    hits = scan_direct_numpy_materialization([sample])
    assert len(hits) == 1
    assert hits[0]["line"] == 2
