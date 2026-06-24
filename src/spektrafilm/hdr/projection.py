from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import colour
import numpy as np

from spektrafilm.hdr.reference_white import HDRReferenceWhiteCalibration
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.hdr.standards import HDRStandardsMetadata, build_hdr_standards_metadata
from spektrafilm.utils import hdr_photo
from spektrafilm.utils.hdr_curve_profiles import luminance_y

_EPS32 = np.float32(1e-8)


@dataclass(frozen=True, slots=True)
class HDRProjectionConfig:
    max_headroom: float = 4.0
    headroom_percentile: float = 99.9
    diffuse_white_scene_anchor: float | None = None
    output_diffuse_white: float = 1.0
    paper_white: float | None = None
    reference_white_mode: Literal["manual_scene_anchor"] = "manual_scene_anchor"
    reference_white_ev: float = 0.0
    display_reference_white_nits: float = 203.0
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
        scene_anchor = self.diffuse_white_scene_anchor
        if scene_anchor is None:
            scene_anchor = 1.0 if self.paper_white is None else self.paper_white
        elif self.paper_white is not None and not math.isclose(float(scene_anchor), float(self.paper_white), rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError("diffuse_white_scene_anchor and paper_white must match when both are provided.")
        if not math.isfinite(float(scene_anchor)) or float(scene_anchor) <= 0.0:
            raise ValueError("diffuse_white_scene_anchor must be a finite positive value.")
        if self.reference_white_mode != "manual_scene_anchor":
            raise ValueError("reference_white_mode must be 'manual_scene_anchor'.")
        if not math.isfinite(float(self.reference_white_ev)):
            raise ValueError("reference_white_ev must be finite.")
        if not math.isfinite(float(self.display_reference_white_nits)) or float(self.display_reference_white_nits) <= 0.0:
            raise ValueError("display_reference_white_nits must be a finite positive value.")
        effective_scene_anchor = float(scene_anchor) * (2.0 ** float(self.reference_white_ev))
        if not math.isfinite(effective_scene_anchor) or effective_scene_anchor <= 0.0:
            raise ValueError("effective reference white must be a finite positive value.")
        if not math.isfinite(self.output_diffuse_white) or self.output_diffuse_white <= 0.0:
            raise ValueError("output_diffuse_white must be a finite positive value.")
        if self.gain_map_mode not in ("luma", "rgb"):
            raise ValueError("gain_map_mode must be 'luma' or 'rgb'.")
        object.__setattr__(self, "diffuse_white_scene_anchor", effective_scene_anchor)
        # Backward-compatible alias for older tests/callers. New code should use
        # diffuse_white_scene_anchor so the scene anchor is not mistaken for an
        # output diffuse-white target.
        object.__setattr__(self, "paper_white", effective_scene_anchor)


@dataclass(frozen=True, slots=True)
class HDRProjectionResult:
    mode: Literal["light_table", "paper"]
    sdr_rgb: Any
    hdr_rgb: Any
    hdr_luminance_y: Any
    headroom: float
    gain_map: Any
    gain_map_metadata: hdr_photo.ISO21496GainMapMetadata
    standards_metadata: HDRStandardsMetadata
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


def _hdr_pair_debug_enabled() -> bool:
    return os.environ.get("SPEKTRAFILM_HDR_PAIR_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_mlx_array(value: Any) -> bool:
    return type(value).__module__.startswith("mlx.")


def _mx():
    import mlx.core as mx

    return mx


def _backend_scalar_float(value: Any) -> float:
    return float(np.asarray(value))


def _backend_scalar_bool(value: Any) -> bool:
    return bool(np.asarray(value))


def _validate_backend_finite(value: Any, *, field: str) -> None:
    mx = _mx()
    if not _backend_scalar_bool(mx.all(mx.isfinite(value))):
        raise ValueError(f"{field} contains non-finite values.")


def _as_rgb_backend(image: Any, *, field: str):
    if not _is_mlx_array(image):
        return None
    if len(image.shape) != 3 or int(image.shape[2]) != 3:
        raise ValueError(f"{field} must have shape (height, width, 3).")
    _validate_backend_finite(image, field=field)
    return image


def _as_y_backend(image: Any, *, field: str, shape: tuple[int, int]):
    if not _is_mlx_array(image):
        return None
    actual_shape = tuple(int(dim) for dim in image.shape)
    if actual_shape != shape:
        raise ValueError(f"{field} must have shape {shape}, got {actual_shape}.")
    _validate_backend_finite(image, field=field)
    return _mx().maximum(image, np.float32(0.0))


def _sdr_rgb_backend(master: RouteMaster):
    if bool(master.diagnostics.get("output_cctf_encoding", True)):
        return None
    sdr = _as_rgb_backend(master.sdr_legacy_rgb, field="sdr_legacy_rgb")
    if sdr is None:
        return None
    return _mx().clip(sdr, np.float32(0.0), np.float32(1.0))


def _luminance_y_backend(rgb: Any):
    return (
        rgb[..., 0] * np.float32(0.2126)
        + rgb[..., 1] * np.float32(0.7152)
        + rgb[..., 2] * np.float32(0.0722)
    )


def _scene_authority_backend(master: RouteMaster, shape: tuple[int, int]):
    return _as_y_backend(master.scene_y_raw, field="scene_y_raw", shape=shape)


def _spatial_authority_for_projection(master: RouteMaster, shape: tuple[int, int]):
    if master.post_halation_y is not None:
        authority = _as_y_backend(master.post_halation_y, field="post_halation_y", shape=shape)
        if authority is not None:
            return authority
    if master.post_halation_y is None:
        authority = _scene_authority_backend(master, shape)
        if authority is not None:
            return authority
    return _spatial_authority(master, shape)


def _route_chroma_backend(master: RouteMaster, shape: tuple[int, int]):
    mx = _mx()
    if master.route_look_chroma is not None:
        chroma = _as_rgb_backend(master.route_look_chroma, field="route_look_chroma")
        if chroma is None:
            return None
        if tuple(int(dim) for dim in chroma.shape[:2]) != shape:
            raise ValueError(f"route_look_chroma must have shape {shape + (3,)}, got {chroma.shape}.")
        return chroma
    route_rgb = _as_rgb_backend(master.route_linear_rgb, field="route_linear_rgb")
    if route_rgb is None:
        return None
    route_rgb = mx.maximum(route_rgb, np.float32(0.0))
    route_y = mx.maximum(_luminance_y_backend(route_rgb), _EPS32)
    return route_rgb / route_y[..., None]


def _material_detail_backend(master: RouteMaster, shape: tuple[int, int], config: HDRProjectionConfig):
    mx = _mx()
    if master.material_detail_y is None:
        return mx.ones(shape, dtype=mx.float32)
    detail = _as_y_backend(master.material_detail_y, field="material_detail_y", shape=shape)
    if detail is None:
        return None
    return mx.clip(detail, np.float32(config.min_detail), np.float32(config.max_detail))


def _smoothstep_backend(edge0: float, edge1: float, x: Any):
    mx = _mx()
    if edge1 <= edge0:
        return (x >= np.float32(edge1)).astype(mx.float32)
    t = mx.clip((x - np.float32(edge0)) / np.float32(edge1 - edge0), np.float32(0.0), np.float32(1.0))
    return t * t * (t * np.float32(-2.0) + np.float32(3.0))


def _percentile_backend(values: Any, percentile: float) -> float:
    mx = _mx()
    flat = mx.reshape(values, (-1,))
    size = int(flat.size)
    if size == 0:
        return float("nan")
    ordered = mx.sort(flat)
    position = (size - 1) * float(percentile) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return _backend_scalar_float(ordered[lower])
    weight = np.float32(position - lower)
    value = ordered[lower] * (np.float32(1.0) - weight) + ordered[upper] * weight
    return _backend_scalar_float(value)


def _authority_ratio_backend(scene_y: Any, *, white: float):
    anchor = np.float32(max(white, 1e-8))
    return _mx().maximum(scene_y, np.float32(0.0)) / anchor


def _extension_gain_backend(
    ratio: Any,
    *,
    max_headroom: float,
    headroom_percentile: float,
    strength: float,
):
    mx = _mx()
    ratio = mx.maximum(ratio, np.float32(0.0))
    if not _backend_scalar_bool(mx.any(ratio > np.float32(1.0))):
        return mx.ones_like(ratio)
    peak = _percentile_backend(ratio, headroom_percentile)
    span_end = max(1.25, min(float(max_headroom), peak))
    progress = _smoothstep_backend(1.0, span_end, ratio)
    excess = mx.clip((ratio - np.float32(1.0)) / np.float32(max(span_end - 1.0, 1e-8)), np.float32(0.0), np.float32(1.0))
    target_gain = progress * excess * np.float32(max(max_headroom - 1.0, 0.0)) * np.float32(strength) + np.float32(1.0)
    return mx.clip(target_gain, np.float32(1.0), np.float32(max_headroom))


def _apply_path_to_white_backend(rgb: Any, hdr_y: Any, strength: float, max_headroom: float):
    if strength <= 0.0:
        return rgb
    mx = _mx()
    progress = _smoothstep_backend(1.0, max(1.01, max_headroom), hdr_y)
    blend = mx.clip(progress * np.float32(strength), np.float32(0.0), np.float32(1.0))[..., None]
    white = mx.repeat(hdr_y[..., None], repeats=3, axis=2)
    return rgb * (blend * np.float32(-1.0) + np.float32(1.0)) + white * blend


def _apply_output_diffuse_white_backend(rgb: Any, sdr: Any, config: HDRProjectionConfig):
    target = np.float32(config.output_diffuse_white)
    if np.isclose(target, np.float32(1.0), rtol=0.0, atol=np.float32(1e-7)):
        return rgb
    delta = rgb - sdr
    return _mx().maximum(sdr + delta * target, np.float32(0.0))


def _headroom_backend(hdr_rgb: Any, config: HDRProjectionConfig) -> float:
    intensity = _mx().max(hdr_rgb, axis=2)
    content = _percentile_backend(intensity, config.headroom_percentile)
    if not math.isfinite(content) or content <= 1.0 + 1e-5:
        return 1.0
    return float(min(config.max_headroom, max(2.0, content)))


def _clip_hdr_backend(rgb: Any, headroom: float):
    return _mx().clip(rgb, np.float32(0.0), np.float32(max(1.0, headroom)))


def _encode_gain_map_log2_backend(sdr_rgb: Any, hdr_rgb: Any, *, headroom: float | None = None):
    mx = _mx()
    sdr = mx.maximum(sdr_rgb, _EPS32)
    hdr = mx.maximum(hdr_rgb, _EPS32)
    sdr_luma = mx.maximum(_luminance_y_backend(sdr), np.float32(1e-3))
    hdr_luma = _luminance_y_backend(hdr)
    if headroom is None:
        headroom = _backend_scalar_float(mx.max(hdr_luma))
    log_gain = mx.log2(hdr_luma / sdr_luma)
    max_log_gain = math.log2(max(float(headroom), 1.0 + 1e-6))
    return mx.clip(log_gain / np.float32(max(max_log_gain, float(_EPS32))), np.float32(0.0), np.float32(1.0))


def _sdr_rgb(master: RouteMaster) -> np.ndarray:
    sdr_val = np.clip(_as_rgb(master.sdr_legacy_rgb, field="sdr_legacy_rgb"), 0.0, 1.0)
    if not bool(master.diagnostics.get("output_cctf_encoding", True)):
        return sdr_val.astype(np.float32, copy=False)
    color_space = master.diagnostics.get("output_color_space", "Display P3")
    return np.asarray(
        colour.RGB_to_RGB(
            sdr_val,
            color_space,
            color_space,
            apply_cctf_decoding=True,
            apply_cctf_encoding=False,
        ),
        dtype=np.float32,
    )


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
    headroom_percentile: float,
    strength: float,
) -> np.ndarray:
    ratio = np.maximum(np.asarray(ratio, dtype=np.float32), 0.0)
    if not np.any(ratio > 1.0):
        return np.ones_like(ratio, dtype=np.float32)
    peak = float(np.nanpercentile(ratio, headroom_percentile))
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


def _apply_output_diffuse_white(rgb: np.ndarray, sdr: np.ndarray, config: HDRProjectionConfig) -> np.ndarray:
    target = np.float32(config.output_diffuse_white)
    if np.isclose(target, np.float32(1.0), rtol=0.0, atol=np.float32(1e-7)):
        return rgb
    delta = np.asarray(rgb, dtype=np.float32) - np.asarray(sdr, dtype=np.float32)
    return np.maximum(sdr + delta * target, 0.0).astype(np.float32, copy=False)


def _headroom(hdr_rgb: np.ndarray, config: HDRProjectionConfig) -> float:
    content = hdr_photo._content_headroom(hdr_rgb, percentile=config.headroom_percentile)
    if content <= 1.0 + 1e-5:
        return 1.0
    return float(min(config.max_headroom, max(2.0, content)))


def _clip_hdr(rgb: np.ndarray, headroom: float) -> np.ndarray:
    return np.clip(rgb, 0.0, max(1.0, headroom)).astype(np.float32, copy=False)


def _debug_hdr_pair(
    *,
    master: RouteMaster,
    sdr: np.ndarray,
    hdr_rgb: np.ndarray,
    hdr_luma: np.ndarray,
    scene_y: np.ndarray,
    calibration: HDRReferenceWhiteCalibration,
) -> dict[str, Any]:
    if not _hdr_pair_debug_enabled():
        return {}

    sdr_y = luminance_y(sdr)
    eps = np.float32(1e-6)
    log_gain = np.log2(np.maximum(hdr_luma, eps) / np.maximum(sdr_y, eps)).astype(np.float32, copy=False)
    target_mask = scene_y > np.float32(calibration.scene_diffuse_white_y)
    bad = (target_mask & (hdr_luma + np.float32(1e-4) < sdr_y)).astype(np.uint8, copy=False)

    output_path = Path(
        os.environ.get(
            "SPEKTRAFILM_HDR_PAIR_DEBUG_PATH",
            "/tmp/spektrafilm_hdr_pair_debug.npz",
        )
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output_path,
        sdr=np.asarray(sdr, dtype=np.float32),
        hdr=np.asarray(hdr_rgb, dtype=np.float32),
        sdr_y=np.asarray(sdr_y, dtype=np.float32),
        hdr_y=np.asarray(hdr_luma, dtype=np.float32),
        scene_y=np.asarray(scene_y, dtype=np.float32),
        log_gain=log_gain,
        target_mask=target_mask.astype(np.uint8, copy=False),
        bad=bad,
    )

    return {
        "hdr_pair_debug_path": str(output_path),
        "hdr_pair_bad_pixels": int(np.count_nonzero(bad)),
        "hdr_pair_bad_fraction": float(np.mean(bad)),
        "hdr_pair_target_fraction": float(np.mean(target_mask)),
        "hdr_pair_sdr_y_p99": float(np.percentile(sdr_y, 99.0)),
        "hdr_pair_hdr_y_p99": float(np.percentile(hdr_luma, 99.0)),
        "hdr_pair_log_gain_min": float(np.min(log_gain)),
        "hdr_pair_log_gain_p01": float(np.percentile(log_gain, 1.0)),
        "hdr_pair_log_gain_p50": float(np.percentile(log_gain, 50.0)),
        "hdr_pair_log_gain_p99": float(np.percentile(log_gain, 99.0)),
    }


def _build_standards_metadata(
    *,
    master: RouteMaster,
    config: HDRProjectionConfig,
    calibration: HDRReferenceWhiteCalibration,
    headroom: float,
    scene_luminance=None,
    render_rgb=None,
    include_statistics: bool,
    source_role: str,
) -> HDRStandardsMetadata:
    return build_hdr_standards_metadata(
        color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        eotf="scene-linear",
        encoded_color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        reference_white_nits=float(config.display_reference_white_nits),
        hdr_headroom=float(headroom),
        min_mastering_luminance_nits=0.005,
        mastering_scene_white=float(calibration.scene_diffuse_white_y),
        mastering_display_white_nits=float(config.display_reference_white_nits),
        mastering_target_peak_ev=float(math.log2(max(float(headroom), 1.0))),
        mastering_curve_budget_ev=float(math.log2(max(float(headroom), 1.0))),
        target_display_color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        target_display_min_luminance_nits=0.005,
        target_display_max_luminance_nits=float(config.display_reference_white_nits) * float(headroom),
        scene_luminance=scene_luminance if include_statistics else None,
        render_rgb=render_rgb if include_statistics else None,
        source_role=source_role,
    )


def _build_result_backend(
    *,
    master: RouteMaster,
    mode: Literal["light_table", "paper"],
    hdr_y,
    config: HDRProjectionConfig,
    calibration: HDRReferenceWhiteCalibration,
    path_to_white_strength: float,
    diagnostics: dict[str, Any],
) -> HDRProjectionResult | None:
    if _hdr_pair_debug_enabled() or not _is_mlx_array(hdr_y):
        return None
    sdr = _sdr_rgb_backend(master)
    if sdr is None:
        return None
    shape = tuple(int(dim) for dim in sdr.shape[:2])
    hdr_y = _as_y_backend(hdr_y, field="hdr_y", shape=shape)
    if hdr_y is None:
        return None
    chroma = _route_chroma_backend(master, shape)
    if chroma is None:
        return None
    mx = _mx()
    hdr_rgb = mx.maximum(chroma * mx.maximum(hdr_y, np.float32(0.0))[..., None], np.float32(0.0))
    scene_y = _scene_authority_backend(master, shape)
    if scene_y is None:
        return None
    if mode == "paper":
        mask = (scene_y <= np.float32(calibration.scene_diffuse_white_y))[..., None]
        hdr_rgb = mx.where(mask, sdr, hdr_rgb)
    hdr_rgb = _apply_path_to_white_backend(hdr_rgb, hdr_y, path_to_white_strength, config.max_headroom)
    hdr_rgb = _apply_output_diffuse_white_backend(hdr_rgb, sdr, config)
    headroom = _headroom_backend(hdr_rgb, config)
    hdr_rgb = _clip_hdr_backend(hdr_rgb, headroom)
    hdr_luma = _luminance_y_backend(hdr_rgb)
    gain_map = _encode_gain_map_log2_backend(sdr, hdr_rgb, headroom=headroom)
    renditions = hdr_photo.HDRPhotoRenditions(
        hdr_rgb=hdr_rgb,
        sdr_rgb=sdr,
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
        "diffuse_white_scene_anchor": float(config.diffuse_white_scene_anchor),
        "output_diffuse_white": float(config.output_diffuse_white),
        "output_diffuse_white_effect": "hdr_delta_from_sdr",
        "reference_white": dict(calibration.diagnostics),
        "preserve_sdr_base": True,
        "projection_backend": "mlx",
        "projection_metadata_statistics": "omitted_backend_fast_path",
    }
    return HDRProjectionResult(
        mode=mode,
        sdr_rgb=sdr,
        hdr_rgb=hdr_rgb,
        hdr_luminance_y=hdr_luma,
        headroom=float(headroom),
        gain_map=gain_map,
        gain_map_metadata=metadata,
        standards_metadata=_build_standards_metadata(
            master=master,
            config=config,
            calibration=calibration,
            headroom=float(headroom),
            include_statistics=False,
            source_role=f"routemaster_{mode}",
        ),
        diagnostics=diagnostics,
    )


def _build_paper_generic_result_backend(
    *,
    master: RouteMaster,
    config: HDRProjectionConfig,
    calibration: HDRReferenceWhiteCalibration,
    path_to_white_strength: float,
    diagnostics: dict[str, Any],
) -> HDRProjectionResult | None:
    if _hdr_pair_debug_enabled():
        return None
    sdr = _sdr_rgb_backend(master)
    if sdr is None:
        return None
    shape = tuple(int(dim) for dim in sdr.shape[:2])
    scene_y = _scene_authority_backend(master, shape)
    if scene_y is None:
        return None
    scene_white = float(calibration.scene_diffuse_white_y)
    sdr_y = _luminance_y_backend(sdr)
    hdr_y = build_hdr_y_from_route(
        master,
        config,
        authority_y=scene_y,
        white=scene_white,
        strength=config.paper_extension_strength,
    )
    if not _is_mlx_array(hdr_y):
        return None
    hdr_y = _mx().where(scene_y <= np.float32(scene_white), sdr_y, hdr_y)
    return _build_result(
        master=master,
        mode="paper",
        hdr_y=hdr_y,
        config=config,
        calibration=calibration,
        path_to_white_strength=path_to_white_strength,
        diagnostics=diagnostics,
    )


def _build_result(
    *,
    master: RouteMaster,
    mode: Literal["light_table", "paper"],
    hdr_y: np.ndarray,
    config: HDRProjectionConfig,
    calibration: HDRReferenceWhiteCalibration,
    path_to_white_strength: float,
    diagnostics: dict[str, Any],
) -> HDRProjectionResult:
    backend_result = _build_result_backend(
        master=master,
        mode=mode,
        hdr_y=hdr_y,
        config=config,
        calibration=calibration,
        path_to_white_strength=path_to_white_strength,
        diagnostics=diagnostics,
    )
    if backend_result is not None:
        return backend_result

    sdr = _sdr_rgb(master)
    shape = sdr.shape[:2]
    chroma = _route_chroma(master, shape)
    hdr_rgb = np.maximum(chroma * np.maximum(hdr_y, 0.0)[..., None], 0.0)
    if mode == "paper":
        scene_y = _scene_authority(master, shape)
        mask = (scene_y <= np.float32(calibration.scene_diffuse_white_y))[..., None]
        hdr_rgb = np.where(mask, sdr, hdr_rgb)
    hdr_rgb = _apply_path_to_white(hdr_rgb, hdr_y, path_to_white_strength, config.max_headroom)
    hdr_rgb = _apply_output_diffuse_white(hdr_rgb, sdr, config)
    headroom = _headroom(hdr_rgb, config)
    hdr_rgb = _clip_hdr(hdr_rgb, headroom)
    hdr_luma = luminance_y(hdr_rgb)
    scene_y = _scene_authority(master, shape)
    debug_diagnostics = _debug_hdr_pair(
        master=master,
        sdr=sdr,
        hdr_rgb=hdr_rgb,
        hdr_luma=hdr_luma,
        scene_y=scene_y,
        calibration=calibration,
    )
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
        **debug_diagnostics,
        "route_kind": master.route_kind,
        "route_render_count": master.diagnostics.get("route_render_count"),
        "source_chroma_default": "route_look_chroma",
        "diffuse_white_scene_anchor": float(config.diffuse_white_scene_anchor),
        "output_diffuse_white": float(config.output_diffuse_white),
        "output_diffuse_white_effect": "hdr_delta_from_sdr",
        "reference_white": dict(calibration.diagnostics),
        "preserve_sdr_base": True,
    }
    return HDRProjectionResult(
        mode=mode,
        sdr_rgb=np.ascontiguousarray(sdr),
        hdr_rgb=np.ascontiguousarray(hdr_rgb),
        hdr_luminance_y=np.ascontiguousarray(hdr_luma),
        headroom=float(headroom),
        gain_map=np.ascontiguousarray(gain_map),
        gain_map_metadata=metadata,
        standards_metadata=_build_standards_metadata(
            master=master,
            config=config,
            calibration=calibration,
            headroom=float(headroom),
            scene_luminance=scene_y,
            render_rgb=hdr_rgb,
            include_statistics=True,
            source_role=f"routemaster_{mode}",
        ),
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
    backend_result = _build_hdr_y_from_route_backend(
        master,
        config,
        authority_y=authority_y,
        white=white,
        strength=strength,
    )
    if backend_result is not None:
        return backend_result

    sdr = _sdr_rgb(master)
    shape = sdr.shape[:2]
    base_y = np.maximum(luminance_y(sdr), _EPS32)
    ratio = _authority_ratio(authority_y, white=white)
    gain = _extension_gain(
        ratio,
        max_headroom=config.max_headroom,
        headroom_percentile=config.headroom_percentile,
        strength=strength,
    )
    detail = _material_detail(master, shape, config)
    low_frequency_gain = gain / np.maximum(detail, _EPS32)
    return np.maximum(base_y * low_frequency_gain * detail, base_y).astype(np.float32, copy=False)


def _build_hdr_y_from_route_backend(
    master: RouteMaster,
    config: HDRProjectionConfig,
    *,
    authority_y,
    white: float,
    strength: float,
):
    if not _is_mlx_array(authority_y):
        return None
    sdr = _sdr_rgb_backend(master)
    if sdr is None:
        return None
    shape = tuple(int(dim) for dim in sdr.shape[:2])
    authority_y = _as_y_backend(authority_y, field="authority_y", shape=shape)
    if authority_y is None:
        return None
    base_y = _mx().maximum(_luminance_y_backend(sdr), _EPS32)
    ratio = _authority_ratio_backend(authority_y, white=white)
    gain = _extension_gain_backend(
        ratio,
        max_headroom=config.max_headroom,
        headroom_percentile=config.headroom_percentile,
        strength=strength,
    )
    detail = _material_detail_backend(master, shape, config)
    if detail is None:
        return None
    low_frequency_gain = gain / _mx().maximum(detail, _EPS32)
    return _mx().maximum(base_y * low_frequency_gain * detail, base_y)


__all__ = [
    "HDRProjectionConfig",
    "HDRProjectionResult",
    "build_hdr_y_from_route",
    "_build_result",
    "_route_luminance",
    "_scene_authority",
    "_spatial_authority",
]
