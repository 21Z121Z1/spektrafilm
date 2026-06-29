from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np


HDRMode = Literal["light_table", "paper"]
RouteKind = Literal["film_scan", "print_scan"]


ROUTE_MASTER_MINIMAL_FIELDS: tuple[str, ...] = (
    "route_linear_rgb",
    "route_luminance_y",
    "sdr_legacy_rgb",
    "scene_y_raw",
    "post_halation_y",
)

ROUTE_MASTER_FULL_FIELDS: tuple[str, ...] = (
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


def route_master_sidecar_fields(policy: str = "minimal") -> tuple[str, ...]:
    if policy == "minimal":
        return ROUTE_MASTER_MINIMAL_FIELDS
    if policy == "full":
        return ROUTE_MASTER_FULL_FIELDS
    raise ValueError("hdr_route_sidecar_policy must be either 'minimal' or 'full'")


def iter_route_master_sidecars(
    route_master: "RouteMaster | None",
    *,
    policy: str | None = None,
    include_missing: bool = False,
):
    if route_master is None:
        return
    field_names = (
        route_master_sidecar_fields(policy)
        if policy is not None
        else ROUTE_MASTER_FULL_FIELDS
    )
    for name in field_names:
        value = getattr(route_master, name, None)
        if value is None and not include_missing:
            continue
        yield name, value


def route_master_sidecar_nbytes(route_master: "RouteMaster | None", *, policy: str | None = None) -> int:
    if route_master is None:
        return 0
    total = 0
    seen: set[int] = set()
    for _name, value in iter_route_master_sidecars(route_master, policy=policy):
        if value is None:
            continue
        identity = id(value)
        if identity in seen:
            continue
        seen.add(identity)
        total += _array_nbytes(value)
    return total


def _array_nbytes(value: Any) -> int:
    nbytes = getattr(value, "nbytes", None)
    if nbytes is not None:
        try:
            return int(nbytes)
        except (TypeError, ValueError):
            pass
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is None or dtype is None:
        return 0
    try:
        return int(np.prod(tuple(int(dim) for dim in shape), dtype=np.int64)) * int(np.dtype(dtype).itemsize)
    except (TypeError, ValueError):
        text = str(dtype)
        if "float64" in text or "int64" in text:
            itemsize = 8
        elif "float32" in text or "int32" in text:
            itemsize = 4
        elif "float16" in text or "int16" in text:
            itemsize = 2
        elif "bool" in text or "int8" in text:
            itemsize = 1
        else:
            return 0
        try:
            return int(np.prod(tuple(int(dim) for dim in shape), dtype=np.int64)) * itemsize
        except (TypeError, ValueError):
            return 0


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
