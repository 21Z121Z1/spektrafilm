from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils import hdr_photo
from spektrafilm.utils.hdr_curve_profiles import luminance_y

_EPS32 = np.float32(1e-8)


@dataclass(frozen=True, slots=True)
class HDRProjectionConfig:
    max_headroom: float = 4.0
    headroom_percentile: float = 99.9
    paper_white: float = 1.0
    light_table_extension_strength: float = 0.75
    paper_extension_strength: float = 0.55
    min_detail: float = 0.75
    max_detail: float = 1.25
    light_table_path_to_white_strength: float = 0.0
    paper_path_to_white_strength: float = 0.12
    gain_map_mode: Literal["luma", "rgb"] = "rgb"

    def __post_init__(self) -> None:
        if not math.isfinite(self.max_headroom) or self.max_headroom <= 1.0:
            raise ValueError("max_headroom must be a finite value greater than 1.0.")
        if not math.isfinite(self.headroom_percentile) or not (0.0 < self.headroom_percentile <= 100.0):
            raise ValueError("headroom_percentile must be in (0, 100].")
        if not math.isfinite(self.paper_white) or self.paper_white <= 0.0:
            raise ValueError("paper_white must be a finite positive value.")
        if self.gain_map_mode not in ("luma", "rgb"):
            raise ValueError("gain_map_mode must be 'luma' or 'rgb'.")


@dataclass(frozen=True, slots=True)
class HDRProjectionResult:
    mode: Literal["light_table", "paper"]
    sdr_rgb: np.ndarray
    hdr_rgb: np.ndarray
    hdr_luminance_y: np.ndarray
    headroom: float
    gain_map: np.ndarray
    gain_map_metadata: hdr_photo.ISO21496GainMapMetadata
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _as_rgb(image: np.ndarray, *, field: str) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float32)
    if arr.ndim != 3 or arr.shape[2] != 3:
        raise ValueError(f"{field} must have shape (height, width, 3).")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{field} contains non-finite values.")
    return arr


def _as_y(image: np.ndarray, *, field: str, shape: tuple[int, int]) -> np.ndarray:
    arr = np.asarray(image, dtype=np.float32)
    if arr.shape != shape:
        raise ValueError(f"{field} must have shape {shape}, got {arr.shape}.")
    if not np.all(np.isfinite(arr)):
        raise ValueError(f"{field} contains non-finite values.")
    return np.maximum(arr, 0.0)


def _sdr_rgb(master: RouteMaster) -> np.ndarray:
    return np.clip(_as_rgb(master.sdr_legacy_rgb, field="sdr_legacy_rgb"), 0.0, 1.0)


def _route_luminance(master: RouteMaster, shape: tuple[int, int]) -> np.ndarray:
    if master.route_luminance_y is not None:
        return _as_y(master.route_luminance_y, field="route_luminance_y", shape=shape)
    return luminance_y(_as_rgb(master.route_linear_rgb, field="route_linear_rgb"))


def _route_chroma(master: RouteMaster, shape: tuple[int, int]) -> np.ndarray:
    if master.route_look_chroma is not None:
        chroma = _as_rgb(master.route_look_chroma, field="route_look_chroma")
        if chroma.shape[:2] != shape:
            raise ValueError(f"route_look_chroma must have shape {shape + (3,)}, got {chroma.shape}.")
        return chroma
    route_rgb = np.maximum(_as_rgb(master.route_linear_rgb, field="route_linear_rgb"), 0.0)
    route_y = np.maximum(luminance_y(route_rgb), _EPS32)
    return np.divide(
        route_rgb,
        route_y[..., None],
        out=np.zeros_like(route_rgb, dtype=np.float32),
        where=route_y[..., None] > _EPS32,
    )


def _scene_authority(master: RouteMaster, shape: tuple[int, int]) -> np.ndarray:
    return _as_y(master.scene_y_raw, field="scene_y_raw", shape=shape)


def _spatial_authority(master: RouteMaster, shape: tuple[int, int]) -> np.ndarray:
    if master.post_halation_y is None:
        return _scene_authority(master, shape)
    return _as_y(master.post_halation_y, field="post_halation_y", shape=shape)


def _material_detail(master: RouteMaster, shape: tuple[int, int], config: HDRProjectionConfig) -> np.ndarray:
    if master.material_detail_y is None:
        return np.ones(shape, dtype=np.float32)
    detail = _as_y(master.material_detail_y, field="material_detail_y", shape=shape)
    return np.clip(detail, np.float32(config.min_detail), np.float32(config.max_detail))


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= np.float32(edge1)).astype(np.float32)
    t = np.clip((x - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)


def _authority_ratio(scene_y: np.ndarray, *, white: float) -> np.ndarray:
    anchor = np.float32(max(white, 1e-8))
    return np.maximum(scene_y, 0.0) / anchor


def _extension_gain(
    ratio: np.ndarray,
    *,
    max_headroom: float,
    strength: float,
) -> np.ndarray:
    ratio = np.maximum(np.asarray(ratio, dtype=np.float32), 0.0)
    if not np.any(ratio > 1.0):
        return np.ones_like(ratio, dtype=np.float32)
    peak = float(np.nanpercentile(ratio, 99.9))
    span_end = max(1.25, min(float(max_headroom), peak))
    progress = _smoothstep(1.0, span_end, ratio)
    excess = np.clip((ratio - np.float32(1.0)) / np.float32(max(span_end - 1.0, 1e-8)), 0.0, 1.0)
    target_gain = np.float32(1.0) + progress * excess * np.float32(max(max_headroom - 1.0, 0.0)) * np.float32(strength)
    return np.clip(target_gain, 1.0, max_headroom).astype(np.float32, copy=False)


def _apply_path_to_white(rgb: np.ndarray, hdr_y: np.ndarray, strength: float, max_headroom: float) -> np.ndarray:
    if strength <= 0.0:
        return rgb
    progress = _smoothstep(1.0, max(1.01, max_headroom), hdr_y)
    blend = np.clip(progress * np.float32(strength), 0.0, 1.0)[..., None]
    white = np.repeat(hdr_y[..., None], 3, axis=2)
    return rgb * (np.float32(1.0) - blend) + white * blend


def _headroom(hdr_rgb: np.ndarray, config: HDRProjectionConfig) -> float:
    content = hdr_photo._content_headroom(hdr_rgb, percentile=config.headroom_percentile)
    if content <= 1.0 + 1e-5:
        return 1.0
    return float(min(config.max_headroom, max(2.0, content)))


def _clip_hdr(rgb: np.ndarray, headroom: float) -> np.ndarray:
    return np.clip(rgb, 0.0, max(1.0, headroom)).astype(np.float32, copy=False)


def _build_result(
    *,
    master: RouteMaster,
    mode: Literal["light_table", "paper"],
    hdr_y: np.ndarray,
    config: HDRProjectionConfig,
    path_to_white_strength: float,
    diagnostics: dict[str, Any],
) -> HDRProjectionResult:
    sdr = _sdr_rgb(master)
    shape = sdr.shape[:2]
    chroma = _route_chroma(master, shape)
    hdr_rgb = np.maximum(chroma * np.maximum(hdr_y, 0.0)[..., None], 0.0)
    initial_headroom = _headroom(hdr_rgb, config)
    hdr_rgb = _apply_path_to_white(hdr_rgb, hdr_y, path_to_white_strength, config.max_headroom)
    headroom = max(initial_headroom, _headroom(hdr_rgb, config))
    hdr_rgb = _clip_hdr(hdr_rgb, headroom)
    hdr_luma = luminance_y(hdr_rgb)
    gain_map = hdr_photo.encode_gain_map_log2(sdr, hdr_rgb, headroom=headroom)
    renditions = hdr_photo.HDRPhotoRenditions(
        hdr_rgb=np.ascontiguousarray(hdr_rgb),
        sdr_rgb=np.ascontiguousarray(sdr),
        headroom=float(headroom),
        mapping_mode_used="generic",
        diagnostics=("routemaster_pair",),
    )
    metadata = hdr_photo.build_iso_21496_1_gain_map_metadata(renditions)
    diagnostics = {
        **diagnostics,
        "route_kind": master.route_kind,
        "route_render_count": master.diagnostics.get("route_render_count"),
        "source_chroma_default": "route_look_chroma",
    }
    return HDRProjectionResult(
        mode=mode,
        sdr_rgb=np.ascontiguousarray(sdr),
        hdr_rgb=np.ascontiguousarray(hdr_rgb),
        hdr_luminance_y=np.ascontiguousarray(hdr_luma),
        headroom=float(headroom),
        gain_map=np.ascontiguousarray(gain_map),
        gain_map_metadata=metadata,
        diagnostics=diagnostics,
    )


def build_hdr_y_from_route(
    master: RouteMaster,
    config: HDRProjectionConfig,
    *,
    authority_y: np.ndarray,
    white: float,
    strength: float,
) -> np.ndarray:
    sdr = _sdr_rgb(master)
    shape = sdr.shape[:2]
    base_y = np.maximum(luminance_y(sdr), _EPS32)
    ratio = _authority_ratio(authority_y, white=white)
    gain = _extension_gain(ratio, max_headroom=config.max_headroom, strength=strength)
    detail = _material_detail(master, shape, config)
    low_frequency_gain = gain / np.maximum(detail, _EPS32)
    return np.maximum(base_y * low_frequency_gain * detail, base_y).astype(np.float32, copy=False)


__all__ = [
    "HDRProjectionConfig",
    "HDRProjectionResult",
    "build_hdr_y_from_route",
    "_build_result",
    "_route_luminance",
    "_scene_authority",
    "_spatial_authority",
]
