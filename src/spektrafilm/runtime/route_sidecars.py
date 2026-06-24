from __future__ import annotations

from typing import Any, Literal

import numpy as np

from spektrafilm.runtime.route_master import RouteMaster

SidecarBackendPolicy = Literal["backend", "numpy"]


def get_route_look_chroma(
    master: RouteMaster,
    *,
    backend_policy: SidecarBackendPolicy = "backend",
    backend: Any | None = None,
):
    """Return route chroma explicitly as backend-resident or NumPy data.

    Existing RouteMaster field access is not changed.  The NumPy path is an
    explicit materialization request; the backend path computes from
    route_linear_rgb when possible and does not call backend.to_numpy.
    """

    _validate_policy(backend_policy)
    if master.route_look_chroma is not None:
        return _coerce(master.route_look_chroma, backend_policy=backend_policy, backend=backend, field="route_look_chroma")
    if backend_policy == "backend" and backend is not None and _is_backend_array(master.route_linear_rgb, backend):
        result = _route_look_chroma_backend(master.route_linear_rgb, backend)
        _increment_counter(master, "route_look_chroma", materialized=False)
        return result
    result = _route_look_chroma_numpy(_to_numpy(master.route_linear_rgb, backend=backend, field="route_linear_rgb"))
    _increment_counter(master, "route_look_chroma", materialized=True)
    return result


def get_material_detail_y(
    master: RouteMaster,
    *,
    backend_policy: SidecarBackendPolicy = "backend",
    backend: Any | None = None,
):
    """Return material-detail sidecar explicitly.

    For a backend-resident RouteMaster without a stored material_detail_y, the
    backend path returns the same neutral ones fallback used by HDR projection,
    avoiding a hidden median materialization.
    """

    _validate_policy(backend_policy)
    if master.material_detail_y is not None:
        return _coerce(master.material_detail_y, backend_policy=backend_policy, backend=backend, field="material_detail_y")
    if backend_policy == "backend" and backend is not None and _is_backend_array(master.route_luminance_y, backend):
        mx = getattr(backend, "mx", None)
        if mx is not None:
            result = mx.ones(master.route_luminance_y.shape, dtype=getattr(master.route_luminance_y, "dtype", None))
        else:
            result = backend.asarray(np.ones(tuple(int(dim) for dim in master.route_luminance_y.shape), dtype=np.float32))
        _increment_counter(master, "material_detail_y", materialized=False)
        return result
    result = _material_detail_y_numpy(_to_numpy(master.route_luminance_y, backend=backend, field="route_luminance_y"))
    _increment_counter(master, "material_detail_y", materialized=True)
    return result


def get_route_linear_xyz(
    master: RouteMaster,
    *,
    backend_policy: SidecarBackendPolicy = "backend",
    backend: Any | None = None,
):
    _validate_policy(backend_policy)
    if master.route_linear_xyz is None:
        raise ValueError("route_linear_xyz is not present on this RouteMaster; request full/on-demand sidecars upstream")
    return _coerce(master.route_linear_xyz, backend_policy=backend_policy, backend=backend, field="route_linear_xyz")


def get_density_cmy(
    master: RouteMaster,
    *,
    backend_policy: SidecarBackendPolicy = "backend",
    backend: Any | None = None,
):
    _validate_policy(backend_policy)
    if master.density_cmy is None:
        raise ValueError("density_cmy is not present on this RouteMaster; request full/on-demand sidecars upstream")
    return _coerce(master.density_cmy, backend_policy=backend_policy, backend=backend, field="density_cmy")


def _route_look_chroma_numpy(route_rgb: Any) -> np.ndarray:
    route_rgb = np.asarray(route_rgb, dtype=np.float32)
    route_y = route_rgb[..., 0] * np.float32(0.2126) + route_rgb[..., 1] * np.float32(0.7152) + route_rgb[..., 2] * np.float32(0.0722)
    return np.divide(
        route_rgb,
        np.maximum(route_y[..., None], np.float32(1e-8)),
        out=np.zeros_like(route_rgb, dtype=np.float32),
        where=route_y[..., None] > np.float32(1e-8),
    )


def _material_detail_y_numpy(route_y: Any) -> np.ndarray:
    y = np.asarray(route_y, dtype=np.float32)
    finite = y[np.isfinite(y) & (y > 0.0)]
    if finite.size == 0:
        return np.ones_like(y, dtype=np.float32)
    detail = y / np.float32(max(float(np.median(finite)), 1e-8))
    return np.clip(detail, 0.5, 2.0).astype(np.float32)


def _route_look_chroma_backend(route_rgb: Any, backend: Any):
    rgb = backend.maximum(route_rgb, np.float32(0.0))
    y = rgb[..., 0] * np.float32(0.2126) + rgb[..., 1] * np.float32(0.7152) + rgb[..., 2] * np.float32(0.0722)
    y = backend.maximum(y, np.float32(1e-8))
    return rgb / y[..., None]


def _validate_policy(policy: str) -> None:
    if policy not in {"backend", "numpy"}:
        raise ValueError("backend_policy must be either 'backend' or 'numpy'")


def _is_backend_array(value: Any, backend: Any | None) -> bool:
    if backend is None:
        return False
    checker = getattr(backend, "_is_mlx_array", None)
    if callable(checker):
        return bool(checker(value))
    return bool(getattr(value, "__class__", type(value)).__module__.startswith("mlx."))


def _to_numpy(value: Any, *, backend: Any | None, field: str) -> np.ndarray:
    if backend is not None and _is_backend_array(value, backend):
        to_numpy = getattr(backend, "to_numpy", None)
        if not callable(to_numpy):
            raise TypeError(f"{field} is backend-resident but backend.to_numpy is unavailable")
        return np.asarray(to_numpy(value), dtype=np.float32)
    return np.asarray(value, dtype=np.float32)


def _coerce(value: Any, *, backend_policy: SidecarBackendPolicy, backend: Any | None, field: str):
    if backend_policy == "backend":
        return value
    return _to_numpy(value, backend=backend, field=field)


def _increment_counter(master: RouteMaster, field: str, *, materialized: bool) -> None:
    diagnostics = master.diagnostics
    diagnostics["route_sidecar_on_demand_count"] = int(diagnostics.get("route_sidecar_on_demand_count", 0)) + 1
    if materialized:
        diagnostics["route_sidecar_materialization_count"] = int(diagnostics.get("route_sidecar_materialization_count", 0)) + 1
    fields = diagnostics.setdefault("route_sidecar_on_demand_fields", [])
    if isinstance(fields, list):
        fields.append(field)
