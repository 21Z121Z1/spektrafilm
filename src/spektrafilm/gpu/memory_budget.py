from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BudgetPolicy = Literal["off", "warn", "soft_enforce", "fail"]
ResizePolicy = Literal["cpu_fallback", "warn", "fail", "native_if_available"]


@dataclass(frozen=True, slots=True)
class RuntimeMemoryBudgetEstimate:
    height: int
    width: int
    channels: int
    dtype_bytes: int
    estimated_peak_bytes: int
    estimated_peak_mib: float
    budget_mib: float | None
    over_budget: bool
    contributors: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeMemoryBudgetDecision:
    policy: BudgetPolicy
    estimate: RuntimeMemoryBudgetEstimate
    action: Literal["off", "ok", "warn", "soft_enforce", "fail"]
    warnings: tuple[str, ...] = ()
    reason: str | None = None
    recommended_gpu_tile_rows: int | None = None
    recommended_gpu_spatial_tile_rows: int | None = None
    recommended_hdr_route_sidecar_policy: str | None = None


def estimate_runtime_peak_budget(
    *,
    height: int,
    width: int,
    channels: int = 3,
    compute_backend: str = "cpu",
    gpu_precision: str = "float32",
    materialize_policy: str = "numpy_float64",
    hdr_mode: str | None = None,
    hdr_route_sidecar_policy: str = "minimal",
    upscale_factor: float = 1.0,
    use_lut: bool = False,
    spectral_tiling_enabled: bool = True,
    spatial_tiling_enabled: bool = True,
    hdr_projection_backend_fast_path: bool = True,
    budget_mib: float | None = None,
) -> RuntimeMemoryBudgetEstimate:
    h = max(1, int(round(float(height) * float(upscale_factor))))
    w = max(1, int(round(float(width) * float(upscale_factor))))
    c = max(1, int(channels))
    dtype_bytes = 2 if str(gpu_precision) == "float16" else 4
    base = h * w * c * dtype_bytes
    plane = h * w * dtype_bytes
    contributors = {
        "runtime_rgb_working_set": 4.0 * base,
        "spectral_transients": (1.0 if use_lut else 3.0) * base,
        "spatial_filter_transients": (1.0 if spatial_tiling_enabled else 3.0) * base,
        "route_luminance_planes": 3.0 * plane,
    }
    if materialize_policy != "backend":
        contributors["host_materialized_output"] = h * w * c * (8 if materialize_policy == "numpy_float64" else 4)
    if hdr_mode is not None:
        contributors["hdr_projection_pair"] = (2.0 if hdr_projection_backend_fast_path else 4.0) * base
        if hdr_route_sidecar_policy == "full":
            contributors["hdr_full_sidecars"] = 4.0 * base + 2.0 * plane
        elif hdr_route_sidecar_policy == "on_demand":
            contributors["hdr_on_demand_resident_sidecars"] = 2.0 * base
        else:
            contributors["hdr_minimal_sidecars"] = base + 2.0 * plane
    if spectral_tiling_enabled:
        contributors["spectral_tiling_discount"] = -1.0 * base
    if compute_backend not in {"mlx", "auto"}:
        contributors["non_mlx_conservatism_discount"] = -1.0 * base
    estimated_bytes = max(base, int(sum(contributors.values())))
    estimated_mib = estimated_bytes / (1024.0 * 1024.0)
    warnings = []
    if upscale_factor != 1.0:
        warnings.append("upscale_factor may trigger resize fallback")
    if materialize_policy != "backend":
        warnings.append("materialize_policy requests host output materialization")
    if hdr_route_sidecar_policy == "full":
        warnings.append("full RouteMaster sidecars keep additional full-frame arrays")
    return RuntimeMemoryBudgetEstimate(
        height=h,
        width=w,
        channels=c,
        dtype_bytes=dtype_bytes,
        estimated_peak_bytes=estimated_bytes,
        estimated_peak_mib=estimated_mib,
        budget_mib=None if budget_mib is None else float(budget_mib),
        over_budget=bool(budget_mib is not None and estimated_mib > float(budget_mib)),
        contributors={name: value / (1024.0 * 1024.0) for name, value in contributors.items()},
        warnings=tuple(warnings),
    )


def decide_runtime_memory_budget(
    estimate: RuntimeMemoryBudgetEstimate,
    *,
    policy: BudgetPolicy = "off",
    current_gpu_tile_rows: int | None = None,
    current_gpu_spatial_tile_rows: int | None = None,
    current_hdr_route_sidecar_policy: str = "minimal",
) -> RuntimeMemoryBudgetDecision:
    if policy not in {"off", "warn", "soft_enforce", "fail"}:
        raise ValueError("gpu_budget_policy must be one of: off, warn, soft_enforce, fail")
    if policy == "off":
        return RuntimeMemoryBudgetDecision(policy=policy, estimate=estimate, action="off")
    if not estimate.over_budget:
        return RuntimeMemoryBudgetDecision(policy=policy, estimate=estimate, action="ok", warnings=estimate.warnings)
    reason = f"estimated peak {estimate.estimated_peak_mib:.1f} MiB exceeds budget {estimate.budget_mib:.1f} MiB"
    if policy in {"warn", "fail"}:
        return RuntimeMemoryBudgetDecision(policy=policy, estimate=estimate, action=policy, warnings=estimate.warnings, reason=reason)
    return RuntimeMemoryBudgetDecision(
        policy=policy,
        estimate=estimate,
        action="soft_enforce",
        warnings=estimate.warnings + (reason, "recommended smaller tile rows and minimal RouteMaster sidecars"),
        recommended_gpu_tile_rows=current_gpu_tile_rows or max(128, estimate.height // 12),
        recommended_gpu_spatial_tile_rows=current_gpu_spatial_tile_rows or max(256, estimate.height // 12),
        recommended_hdr_route_sidecar_policy="minimal" if current_hdr_route_sidecar_policy == "full" else current_hdr_route_sidecar_policy,
    )


def validate_resize_policy(
    *,
    compute_backend: str,
    materialize_policy: str,
    upscale_factor: float,
    preview_mode: bool = False,
    gpu_resize_policy: ResizePolicy = "cpu_fallback",
) -> tuple[bool, str | None]:
    if gpu_resize_policy not in {"cpu_fallback", "warn", "fail", "native_if_available"}:
        raise ValueError("invalid gpu_resize_policy")
    if float(upscale_factor) == 1.0:
        return True, None
    breaks_residency = compute_backend == "mlx" and materialize_policy == "backend" and not preview_mode
    if not breaks_residency:
        return True, None
    warning = "MLX backend-resident preprocess resize currently falls back through CPU materialization"
    if gpu_resize_policy == "fail":
        return False, warning
    if gpu_resize_policy in {"warn", "native_if_available"}:
        return True, warning
    return True, None
