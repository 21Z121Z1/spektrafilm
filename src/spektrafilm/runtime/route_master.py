from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


HDRMode = Literal["light_table", "paper"]
RouteKind = Literal["film_scan", "print_scan"]


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
