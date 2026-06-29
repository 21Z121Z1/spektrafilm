from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np


HDRMode = Literal["light_table", "paper"]
RouteKind = Literal["film_scan", "print_scan"]
BackendPolicy = Literal["backend", "numpy"]


@dataclass(slots=True)
class FilmingExposureResult:
    log_raw: Any
    scene_y_raw: Any
    post_halation_y: Any
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ScanMasterResult:
    route_linear_rgb: Any
    route_linear_xyz: Any
    route_luminance_y: Any
    density_cmy: Any
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RouteMaster:
    mode: HDRMode
    route_kind: RouteKind
    route_linear_rgb: Any
    route_luminance_y: Any
    sdr_legacy_rgb: Any
    scene_y_raw: Any
    post_halation_y: Any | None = None
    route_linear_xyz: Any | None = None
    density_cmy: Any | None = None
    route_look_chroma: Any | None = None
    material_detail_y: Any | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)


def get_route_look_chroma(
    master: RouteMaster,
    *,
    backend_policy: BackendPolicy = "backend",
    backend: Any | None = None,
) -> Any:
    """Return or derive route chroma without implicit backend-to-host materialization."""
    if backend_policy not in {"backend", "numpy"}:
        raise ValueError("backend_policy must be either 'backend' or 'numpy'")
    if master.route_look_chroma is not None:
        return _coerce_policy(master.route_look_chroma, backend_policy, backend)

    route_rgb = _coerce_policy(master.route_linear_rgb, backend_policy, backend)
    if _is_mlx_array(route_rgb):
        mx = _mlx_core()
        route_y = _route_luminance_backend(route_rgb, mx)
        return mx.divide(
            route_rgb,
            mx.maximum(route_y[..., None], mx.array(1e-8, dtype=route_rgb.dtype)),
        ) * (route_y[..., None] > mx.array(1e-8, dtype=route_rgb.dtype))

    route_rgb_np = np.asarray(route_rgb, dtype=np.float32)
    route_y_np = _route_luminance_numpy(route_rgb_np)
    return np.divide(
        route_rgb_np,
        np.maximum(route_y_np[..., None], np.float32(1e-8)),
        out=np.zeros_like(route_rgb_np, dtype=np.float32),
        where=route_y_np[..., None] > np.float32(1e-8),
    )


def get_material_detail_y(
    master: RouteMaster,
    *,
    backend_policy: BackendPolicy = "backend",
    backend: Any | None = None,
) -> Any:
    """Return or derive material detail without implicit backend-to-host materialization."""
    if backend_policy not in {"backend", "numpy"}:
        raise ValueError("backend_policy must be either 'backend' or 'numpy'")
    if master.material_detail_y is not None:
        return _coerce_policy(master.material_detail_y, backend_policy, backend)

    route_y = _coerce_policy(master.route_luminance_y, backend_policy, backend)
    if _is_mlx_array(route_y):
        mx = _mlx_core()
        finite = mx.isfinite(route_y) & (route_y > mx.array(0.0, dtype=route_y.dtype))
        positive_or_inf = mx.where(finite, route_y, mx.array(float("inf"), dtype=route_y.dtype))
        sorted_positive = mx.sort(mx.reshape(positive_or_inf, (-1,)))
        count = mx.sum(finite)
        safe_count = mx.maximum(count, mx.array(1, dtype=count.dtype))
        lower = (safe_count - 1) // 2
        upper = safe_count // 2
        anchor = (mx.take(sorted_positive, lower) + mx.take(sorted_positive, upper)) * mx.array(
            0.5,
            dtype=route_y.dtype,
        )
        anchor = mx.where(count > 0, anchor, mx.array(1.0, dtype=route_y.dtype))
        anchor = mx.maximum(anchor, mx.array(1e-8, dtype=route_y.dtype))
        detail = route_y / anchor
        return mx.where(
            count > 0,
            mx.clip(detail, 0.5, 2.0),
            mx.ones_like(route_y),
        ).astype(route_y.dtype)

    y = np.asarray(route_y, dtype=np.float32)
    finite_np = y[np.isfinite(y) & (y > 0.0)]
    if finite_np.size == 0:
        return np.ones_like(y, dtype=np.float32)
    anchor_np = float(np.median(finite_np))
    detail_np = y / np.float32(max(anchor_np, 1e-8))
    return np.clip(detail_np, 0.5, 2.0).astype(np.float32)


def _coerce_policy(value: Any, backend_policy: BackendPolicy, backend: Any | None) -> Any:
    if backend_policy == "backend":
        return value
    if not _is_mlx_array(value):
        return np.asarray(value)
    if backend is None or not hasattr(backend, "to_numpy"):
        raise ValueError(
            "backend_policy='numpy' for backend-resident RouteMaster fields requires "
            "an explicit backend with to_numpy()."
        )
    return backend.to_numpy(value)


def _is_mlx_array(value: Any) -> bool:
    return type(value).__module__.startswith("mlx.")


def _mlx_core():
    import mlx.core as mx

    return mx


def _route_luminance_numpy(route_rgb: np.ndarray) -> np.ndarray:
    return np.tensordot(
        route_rgb,
        np.array([0.2126, 0.7152, 0.0722], dtype=np.float32),
        axes=([-1], [0]),
    ).astype(np.float32)


def _route_luminance_backend(route_rgb: Any, mx: Any) -> Any:
    weights = mx.array([0.2126, 0.7152, 0.0722], dtype=route_rgb.dtype)
    return mx.sum(route_rgb * weights, axis=-1)
