from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np


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
    route_linear_rgb: np.ndarray
    route_linear_xyz: np.ndarray
    route_luminance_y: np.ndarray
    sdr_legacy_rgb: np.ndarray
    scene_y_raw: np.ndarray
    post_halation_y: np.ndarray | None
    density_cmy: np.ndarray | None
    route_look_chroma: np.ndarray | None = None
    material_detail_y: np.ndarray | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
