from __future__ import annotations

import math
import os
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import colour
import numpy as np

from spektrafilm.hdr.reference_white import HDRReferenceWhiteCalibration
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.hdr.standards import HDRStandardsMetadata, build_hdr_standards_metadata
from spektrafilm.utils import hdr_photo
from spektrafilm.utils.hdr_curve_profiles import luminance_y

_EPS32 = np.float32(1e-8)
_PROFILE_ENV = "SPEKTRAFILM_HDR_PROJECTION_PROFILE"
_CHUNKED_PROJECTION_MIN_PIXELS = 24_000_000
_CHUNKED_PROJECTION_ROWS = 128
# Path-to-white strengths are tuned at the HDRProjectionConfig default
# headroom (4.0 == 2 stops). Perceived colorfulness grows with luminance
# (Hunt effect), so the desaturation strength scales with the log2 distance
# from that reference headroom instead of staying constant.
_PATH_TO_WHITE_REFERENCE_HEADROOM = 4.0
_PATH_TO_WHITE_HEADROOM_GAIN_PER_STOP = 0.5
HDRTransferFunction = Literal["linear", "pq", "hlg", "gain-map-linear-pair"]


def _effective_path_to_white_strength(strength: float, max_headroom: float) -> float:
    if strength <= 0.0:
        return 0.0
    stops_from_reference = math.log2(
        max(float(max_headroom), 1.0 + 1e-6) / _PATH_TO_WHITE_REFERENCE_HEADROOM
    )
    scaled = float(strength) * (1.0 + _PATH_TO_WHITE_HEADROOM_GAIN_PER_STOP * stops_from_reference)
    return float(min(max(scaled, 0.0), 1.0))


@dataclass(slots=True)
class _BackendProjectionProfile:
    percentile_calls: list[dict[str, Any]] = field(default_factory=list)
    mlx_peak_memory_bytes: int | None = None
    mlx_cache_memory_start_bytes: int | None = None
    mlx_cache_memory_end_bytes: int | None = None

    def begin(self) -> None:
        _reset_mlx_peak_memory()
        self.mlx_cache_memory_start_bytes = _mlx_memory_bytes("get_cache_memory")

    def refresh_memory(self) -> None:
        self.mlx_peak_memory_bytes = _mlx_memory_bytes("get_peak_memory")
        self.mlx_cache_memory_end_bytes = _mlx_memory_bytes("get_cache_memory")

    def record_percentile(
        self,
        *,
        label: str,
        percentile: float,
        size: int,
        elapsed_seconds: float,
    ) -> None:
        self.percentile_calls.append(
            {
                "label": str(label),
                "operation": "mx.sort_percentile",
                "percentile": float(percentile),
                "size": int(size),
                "sort_to_scalar_ms": float(elapsed_seconds) * 1000.0,
            }
        )

    def diagnostics(self) -> dict[str, Any]:
        self.refresh_memory()
        return {
            "enabled": True,
            "percentile_calls": [dict(call) for call in self.percentile_calls],
            "percentile_sort_ms_total": float(
                sum(float(call["sort_to_scalar_ms"]) for call in self.percentile_calls)
            ),
            "mlx_peak_memory_bytes": self.mlx_peak_memory_bytes,
            "mlx_cache_memory_start_bytes": self.mlx_cache_memory_start_bytes,
            "mlx_cache_memory_end_bytes": self.mlx_cache_memory_end_bytes,
        }


_ACTIVE_BACKEND_PROFILE: ContextVar[_BackendProjectionProfile | None] = ContextVar(
    "spektrafilm_hdr_backend_projection_profile",
    default=None,
)


@dataclass(frozen=True, slots=True)
class HDRDisplayProfile:
    profile_id: str = "spektrafilm-gain-map-display-p3"
    color_primaries: str = "Display P3"
    output_color_volume: str = "Display P3 linear HDR pair"
    transfer_function: HDRTransferFunction = "gain-map-linear-pair"
    reference_white_nits: float = 203.0
    peak_nits: float | None = None
    max_headroom: float = 4.0
    black_nits: float = 0.005
    output_diffuse_white: float = 1.0
    content_headroom_percentile: float = 99.9

    def __post_init__(self) -> None:
        if not isinstance(self.profile_id, str) or not self.profile_id:
            raise ValueError("display profile id must be a non-empty string.")
        if not isinstance(self.color_primaries, str) or not self.color_primaries:
            raise ValueError("color_primaries must be a non-empty string.")
        if not isinstance(self.output_color_volume, str) or not self.output_color_volume:
            raise ValueError("output_color_volume must be a non-empty string.")
        if self.transfer_function not in ("linear", "pq", "hlg", "gain-map-linear-pair"):
            raise ValueError("transfer_function must be 'linear', 'pq', 'hlg', or 'gain-map-linear-pair'.")
        if not math.isfinite(float(self.reference_white_nits)) or float(self.reference_white_nits) <= 0.0:
            raise ValueError("reference_white_nits must be a finite positive value.")
        if not math.isfinite(float(self.max_headroom)) or float(self.max_headroom) <= 1.0:
            raise ValueError("max_headroom must be a finite value greater than 1.0.")
        peak_nits = self.peak_nits
        if peak_nits is None:
            peak_nits = float(self.reference_white_nits) * float(self.max_headroom)
        if not math.isfinite(float(peak_nits)) or float(peak_nits) <= float(self.reference_white_nits):
            raise ValueError("peak_nits must be finite and greater than reference_white_nits.")
        max_headroom = float(peak_nits) / float(self.reference_white_nits)
        if not math.isclose(max_headroom, float(self.max_headroom), rel_tol=1e-5, abs_tol=1e-5):
            object.__setattr__(self, "max_headroom", max_headroom)
        object.__setattr__(self, "peak_nits", float(peak_nits))
        if not math.isfinite(float(self.black_nits)) or float(self.black_nits) < 0.0:
            raise ValueError("black_nits must be finite and non-negative.")
        if not math.isfinite(float(self.output_diffuse_white)) or float(self.output_diffuse_white) <= 0.0:
            raise ValueError("output_diffuse_white must be a finite positive value.")
        if not math.isfinite(float(self.content_headroom_percentile)) or not (0.0 < float(self.content_headroom_percentile) <= 100.0):
            raise ValueError("content_headroom_percentile must be in (0, 100].")


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
    # Dyes on a light table go transparent toward the illuminant, so the
    # light-table extension desaturates toward white like the paper mode
    # does (both are further Hunt-scaled by headroom at projection time).
    light_table_path_to_white_strength: float = 0.12
    paper_path_to_white_strength: float = 0.12
    gain_map_mode: Literal["luma", "rgb"] = "rgb"
    display_profile: HDRDisplayProfile | None = None
    highlight_detail_strength: float = 1.0
    highlight_detail_start: float = 1.0
    highlight_detail_end: float = 1.25

    def __post_init__(self) -> None:
        display_profile = self.display_profile
        if display_profile is not None:
            object.__setattr__(self, "max_headroom", float(display_profile.max_headroom))
            object.__setattr__(self, "headroom_percentile", float(display_profile.content_headroom_percentile))
            object.__setattr__(self, "output_diffuse_white", float(display_profile.output_diffuse_white))
            object.__setattr__(self, "display_reference_white_nits", float(display_profile.reference_white_nits))
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
        if self.max_detail < self.min_detail:
            raise ValueError("max_detail must be greater than or equal to min_detail.")
        if not math.isfinite(float(self.highlight_detail_strength)) or float(self.highlight_detail_strength) < 0.0:
            raise ValueError("highlight_detail_strength must be finite and non-negative.")
        if (
            not math.isfinite(float(self.highlight_detail_start))
            or not math.isfinite(float(self.highlight_detail_end))
            or float(self.highlight_detail_end) <= float(self.highlight_detail_start)
        ):
            raise ValueError("highlight_detail_end must be greater than highlight_detail_start.")
        object.__setattr__(self, "diffuse_white_scene_anchor", effective_scene_anchor)
        # Backward-compatible alias for older tests/callers. New code should use
        # diffuse_white_scene_anchor so the scene anchor is not mistaken for an
        # output diffuse-white target.
        object.__setattr__(self, "paper_white", effective_scene_anchor)
        if display_profile is None:
            display_profile = HDRDisplayProfile(
                reference_white_nits=float(self.display_reference_white_nits),
                max_headroom=float(self.max_headroom),
                output_diffuse_white=float(self.output_diffuse_white),
                content_headroom_percentile=float(self.headroom_percentile),
            )
            object.__setattr__(self, "display_profile", display_profile)


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


def _projection_profile_enabled() -> bool:
    return os.environ.get(_PROFILE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def _try_mx():
    try:
        return _mx()
    except Exception:
        return None


def _mlx_memory_bytes(getter_name: str) -> int | None:
    mx = _try_mx()
    if mx is None:
        return None
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, getter_name, None)
        if callable(getter):
            try:
                return int(getter())
            except (OSError, RuntimeError, TypeError, ValueError):
                return None
    return None


def _reset_mlx_peak_memory() -> None:
    mx = _try_mx()
    if mx is None:
        return
    for owner in (mx, getattr(mx, "metal", None)):
        reset = getattr(owner, "reset_peak_memory", None)
        if callable(reset):
            try:
                reset()
            except (OSError, RuntimeError, TypeError, ValueError):
                pass
            return


@contextmanager
def _backend_projection_profile():
    if not _projection_profile_enabled():
        yield None
        return
    profile = _BackendProjectionProfile()
    profile.begin()
    token = _ACTIVE_BACKEND_PROFILE.set(profile)
    try:
        yield profile
    finally:
        profile.refresh_memory()
        _ACTIVE_BACKEND_PROFILE.reset(token)


def _backend_projection_profile_diagnostics() -> dict[str, Any]:
    profile = _ACTIVE_BACKEND_PROFILE.get()
    if profile is None:
        return {}
    return {"projection_profile": profile.diagnostics()}


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


def _decode_backend_wrapper():
    """Cached MLX ArrayBackend for on-GPU CCTF decoding, or None."""
    global _DECODE_BACKEND_CACHE
    if _DECODE_BACKEND_CACHE is _DECODE_BACKEND_UNSET:
        try:
            from spektrafilm.gpu.backend import select_backend

            _DECODE_BACKEND_CACHE = select_backend("mlx", precision="float32")
        except Exception:
            _DECODE_BACKEND_CACHE = None
    return _DECODE_BACKEND_CACHE


_DECODE_BACKEND_UNSET = object()
_DECODE_BACKEND_CACHE: Any = _DECODE_BACKEND_UNSET


def _sdr_rgb_backend(master: RouteMaster):
    sdr = _as_rgb_backend(master.sdr_legacy_rgb, field="sdr_legacy_rgb")
    if sdr is None:
        return None
    sdr = _mx().clip(sdr, np.float32(0.0), np.float32(1.0))
    if not bool(master.diagnostics.get("output_cctf_encoding", True)):
        return sdr
    # Display-encoded SDR base: decode to linear on the backend instead of
    # bailing to the host colour.RGB_to_RGB path. cctf_decoding_backend
    # mirrors colour.RGB_to_RGB(cs, cs, decode) including the same-space
    # matrix, and is the decoding twin of the cctf_encoding_backend that
    # already produces the SDR output on this backend.
    backend = _decode_backend_wrapper()
    if backend is None:
        return None
    color_space = str(master.diagnostics.get("output_color_space", "Display P3"))
    try:
        from spektrafilm.gpu.kernels.color import cctf_decoding_backend

        return cctf_decoding_backend(sdr, color_space, backend)
    except NotImplementedError:
        return None


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
        # Scalar sentinel: a detail field of exactly ones collapses the
        # highlight-detail factor to a constant, so the full-frame ones
        # allocation is never needed (see _apply_highlight_detail_backend).
        return np.float32(1.0)
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


def _apply_highlight_detail_backend(base_y: Any, target_y: Any, detail: Any, ratio: Any, config: HDRProjectionConfig):
    mx = _mx()
    if float(config.highlight_detail_strength) <= 0.0:
        return target_y
    extension = mx.maximum(target_y - base_y, np.float32(0.0))
    if not _backend_scalar_bool(mx.any(extension > np.float32(0.0))):
        return target_y
    if np.isscalar(detail) and float(detail) == 1.0:
        # mask * (1 - 1) * strength + 1 == 1 exactly (mask is finite and
        # non-negative, so mask * +0.0 == +0.0), hence factor is the constant
        # clip(1, min_detail, max_detail). The extension * factor multiply is
        # kept even when the constant is 1.0: Metal flushes float32 subnormals,
        # so the multiply is semantic and dropping it would change bits.
        factor = np.float32(
            np.clip(np.float32(1.0), np.float32(config.min_detail), np.float32(config.max_detail))
        )
        return mx.minimum(base_y + extension * factor, base_y * np.float32(config.max_headroom))
    mask = _smoothstep_backend(float(config.highlight_detail_start), float(config.highlight_detail_end), ratio)
    factor = mask * (detail - np.float32(1.0)) * np.float32(config.highlight_detail_strength) + np.float32(1.0)
    factor = mx.clip(factor, np.float32(config.min_detail), np.float32(config.max_detail))
    return mx.minimum(base_y + extension * factor, base_y * np.float32(config.max_headroom))


def _percentile_backend(values: Any, percentile: float, *, label: str) -> float:
    mx = _mx()
    flat = mx.reshape(values, (-1,))
    size = int(flat.size)
    if size == 0:
        return float("nan")
    profile = _ACTIVE_BACKEND_PROFILE.get()
    start = perf_counter() if profile is not None else 0.0
    ordered = mx.sort(flat)
    position = (size - 1) * float(percentile) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        result = _backend_scalar_float(ordered[lower])
    else:
        weight = np.float32(position - lower)
        value = ordered[lower] * (np.float32(1.0) - weight) + ordered[upper] * weight
        result = _backend_scalar_float(value)
    if profile is not None:
        profile.record_percentile(
            label=label,
            percentile=percentile,
            size=size,
            elapsed_seconds=perf_counter() - start,
        )
    return result


def _authority_ratio_backend(scene_y: Any, *, white: float):
    anchor = np.float32(max(white, 1e-8))
    return _mx().maximum(scene_y, np.float32(0.0)) / anchor


def _extension_gain_backend(
    ratio: Any,
    *,
    max_headroom: float,
    strength: float,
):
    mx = _mx()
    ratio = mx.maximum(ratio, np.float32(0.0))
    if not _backend_scalar_bool(mx.any(ratio > np.float32(1.0))):
        return mx.ones_like(ratio)
    # The extension span is fixed by the configured headroom rather than a
    # content percentile so that crops/framing changes of the same scene keep
    # identical per-pixel rendering (content stats still bound the final
    # headroom metadata in _headroom_backend).
    span_end = max(1.25, float(max_headroom))
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
    # hdr_y[..., None] * blend broadcasts as (H, W, 1); every channel of the
    # former repeated white array carried this exact product, so the add is
    # bit-identical without materializing an H x W x 3 intermediate.
    return rgb * (blend * np.float32(-1.0) + np.float32(1.0)) + hdr_y[..., None] * blend


def _compress_highlight_gamut_backend(rgb: Any, limit: float):
    mx = _mx()
    limit32 = np.float32(max(1.0, limit))
    y = _luminance_y_backend(rgb)
    max_channel = mx.max(rgb, axis=2)
    min_channel = mx.min(rgb, axis=2)
    upper_den = mx.maximum(max_channel - y, _EPS32)
    lower_den = mx.maximum(y - min_channel, _EPS32)
    # limit32 broadcasts bit-identically to the former full-frame constant
    # arrays (x * 0.0 + limit32 == limit32 exactly for finite x), and the
    # (H, W, 1) neutral broadcasts like the former mx.repeat copy did. The
    # scalar must sit inside an mx op (mx.subtract/mx.divide): a leading
    # numpy scalar would dispatch through numpy and materialize the array.
    upper_scale = mx.where(max_channel > limit32, mx.subtract(limit32, y) / upper_den, np.float32(1.0))
    lower_scale = mx.where(min_channel < np.float32(0.0), y / lower_den, np.float32(1.0))
    scale = mx.clip(mx.minimum(upper_scale, lower_scale), np.float32(0.0), np.float32(1.0))
    neutral = y[..., None]
    compressed = neutral + (rgb - neutral) * scale[..., None]
    peak_scale = mx.divide(limit32, mx.maximum(max_channel, _EPS32))
    hue_preserved = rgb * mx.clip(peak_scale, np.float32(0.0), np.float32(1.0))[..., None]
    compressed = mx.where((y >= limit32)[..., None], hue_preserved, compressed)
    return mx.clip(compressed, np.float32(0.0), limit32)


def _apply_output_diffuse_white_backend(rgb: Any, sdr: Any, config: HDRProjectionConfig):
    target = np.float32(config.output_diffuse_white)
    if np.isclose(target, np.float32(1.0), rtol=0.0, atol=np.float32(1e-7)):
        return rgb
    delta = rgb - sdr
    return _mx().maximum(sdr + delta * target, np.float32(0.0))


def _headroom_backend(hdr_rgb: Any, config: HDRProjectionConfig) -> float:
    intensity = _mx().max(hdr_rgb, axis=2)
    content = _percentile_backend(intensity, config.headroom_percentile, label="headroom")
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
    if sdr_val.shape[0] * sdr_val.shape[1] >= _CHUNKED_PROJECTION_MIN_PIXELS:
        decoded = np.empty_like(sdr_val, dtype=np.float32)
        for y0 in range(0, sdr_val.shape[0], _CHUNKED_PROJECTION_ROWS):
            y1 = min(sdr_val.shape[0], y0 + _CHUNKED_PROJECTION_ROWS)
            decoded[y0:y1] = np.asarray(
                colour.RGB_to_RGB(
                    sdr_val[y0:y1],
                    color_space,
                    color_space,
                    apply_cctf_decoding=True,
                    apply_cctf_encoding=False,
                ),
                dtype=np.float32,
            )
        return decoded
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
    route_source = _as_rgb(master.route_linear_rgb, field="route_linear_rgb")
    if route_source.shape[:2] != shape:
        raise ValueError(f"route_linear_rgb must have shape {shape + (3,)}, got {route_source.shape}.")
    if shape[0] * shape[1] >= _CHUNKED_PROJECTION_MIN_PIXELS:
        chroma = np.empty_like(route_source, dtype=np.float32)
        for y0 in range(0, shape[0], _CHUNKED_PROJECTION_ROWS):
            y1 = min(shape[0], y0 + _CHUNKED_PROJECTION_ROWS)
            route_rgb = np.maximum(route_source[y0:y1], 0.0)
            route_y = np.maximum(luminance_y(route_rgb), _EPS32)
            np.divide(
                route_rgb,
                route_y[..., None],
                out=chroma[y0:y1],
                where=route_y[..., None] > _EPS32,
            )
        return chroma
    route_rgb = np.maximum(route_source, 0.0)
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


def _material_detail(master: RouteMaster, shape: tuple[int, int], config: HDRProjectionConfig):
    if master.material_detail_y is None:
        # Scalar sentinel: a detail field of exactly ones collapses the
        # highlight-detail factor to a constant (see _apply_highlight_detail),
        # so the full-frame ones allocation is never needed.
        return np.float32(1.0)
    detail = _as_y(master.material_detail_y, field="material_detail_y", shape=shape)
    return np.clip(detail, np.float32(config.min_detail), np.float32(config.max_detail))


def _smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return (x >= np.float32(edge1)).astype(np.float32)
    t = np.clip((x - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)


def _apply_highlight_detail(
    base_y: np.ndarray,
    target_y: np.ndarray,
    detail: np.ndarray,
    ratio: np.ndarray,
    config: HDRProjectionConfig,
) -> np.ndarray:
    if float(config.highlight_detail_strength) <= 0.0:
        return np.asarray(target_y, dtype=np.float32)
    extension = np.maximum(np.asarray(target_y, dtype=np.float32) - np.asarray(base_y, dtype=np.float32), 0.0)
    if not np.any(extension > 0.0):
        return np.asarray(target_y, dtype=np.float32)
    if np.isscalar(detail) and float(detail) == 1.0:
        # mask * (1 - 1) * strength + 1 == 1 exactly (mask is finite and
        # non-negative, so mask * +0.0 == +0.0), hence factor is the constant
        # clip(1, min_detail, max_detail) and the smoothstep mask never needs
        # to materialize.
        factor = np.float32(
            np.clip(np.float32(1.0), np.float32(config.min_detail), np.float32(config.max_detail))
        )
        hdr_y = np.asarray(base_y, dtype=np.float32) + extension * factor
        return np.minimum(hdr_y, np.asarray(base_y, dtype=np.float32) * np.float32(config.max_headroom)).astype(
            np.float32,
            copy=False,
        )
    mask = _smoothstep(float(config.highlight_detail_start), float(config.highlight_detail_end), ratio)
    factor = np.float32(1.0) + mask * (np.asarray(detail, dtype=np.float32) - np.float32(1.0)) * np.float32(
        config.highlight_detail_strength
    )
    factor = np.clip(factor, np.float32(config.min_detail), np.float32(config.max_detail))
    hdr_y = np.asarray(base_y, dtype=np.float32) + extension * factor
    return np.minimum(hdr_y, np.asarray(base_y, dtype=np.float32) * np.float32(config.max_headroom)).astype(
        np.float32,
        copy=False,
    )


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
    # The extension span is fixed by the configured headroom rather than a
    # content percentile so that crops/framing changes of the same scene keep
    # identical per-pixel rendering (content stats still bound the final
    # headroom metadata in _headroom).
    span_end = max(1.25, float(max_headroom))
    progress = _smoothstep(1.0, span_end, ratio)
    excess = np.clip((ratio - np.float32(1.0)) / np.float32(max(span_end - 1.0, 1e-8)), 0.0, 1.0)
    target_gain = np.float32(1.0) + progress * excess * np.float32(max(max_headroom - 1.0, 0.0)) * np.float32(strength)
    return np.clip(target_gain, 1.0, max_headroom).astype(np.float32, copy=False)


def _apply_path_to_white(rgb: np.ndarray, hdr_y: np.ndarray, strength: float, max_headroom: float) -> np.ndarray:
    if strength <= 0.0:
        return rgb
    progress = _smoothstep(1.0, max(1.01, max_headroom), hdr_y)
    blend = np.clip(progress * np.float32(strength), 0.0, 1.0)[..., None]
    # hdr_y[..., None] * blend broadcasts as (H, W, 1); every channel of the
    # former repeated white array carried this exact product, so the add is
    # bit-identical without materializing an H x W x 3 intermediate.
    return rgb * (np.float32(1.0) - blend) + hdr_y[..., None] * blend


def _compress_highlight_gamut(rgb: np.ndarray, limit: float) -> tuple[np.ndarray, dict[str, Any]]:
    arr = np.asarray(rgb, dtype=np.float32)
    limit32 = np.float32(max(1.0, limit))
    y = luminance_y(arr)
    max_channel = np.max(arr, axis=2)
    min_channel = np.min(arr, axis=2)
    needs_compression = (max_channel > limit32) | (min_channel < np.float32(0.0))
    if not np.any(needs_compression):
        return arr, {
            "highlight_gamut_strategy": "luminance_preserving_chroma_compression",
            "highlight_gamut_compressed_pixels": 0,
            "highlight_gamut_limit": float(limit32),
        }
    upper_den = np.maximum(max_channel - y, _EPS32)
    lower_den = np.maximum(y - min_channel, _EPS32)
    upper_scale = np.where(max_channel > limit32, (limit32 - y) / upper_den, 1.0)
    lower_scale = np.where(min_channel < 0.0, y / lower_den, 1.0)
    scale = np.clip(np.minimum(upper_scale, lower_scale), 0.0, 1.0).astype(np.float32, copy=False)
    neutral = y[..., None]
    compressed = neutral + (arr - neutral) * scale[..., None]
    peak_scale = limit32 / np.maximum(max_channel, _EPS32)
    hue_preserved = arr * np.clip(peak_scale, 0.0, 1.0)[..., None]
    compressed = np.where((y >= limit32)[..., None], hue_preserved, compressed)
    compressed = np.clip(compressed, 0.0, limit32).astype(np.float32, copy=False)
    return compressed, {
        "highlight_gamut_strategy": "luminance_preserving_chroma_compression",
        "highlight_gamut_compressed_pixels": int(np.count_nonzero(needs_compression)),
        "highlight_gamut_limit": float(limit32),
        "highlight_gamut_pre_max": float(np.max(max_channel)),
        "highlight_gamut_pre_min": float(np.min(min_channel)),
    }


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


def _display_profile_diagnostics(config: HDRProjectionConfig) -> dict[str, Any]:
    profile = config.display_profile
    if profile is None:
        return {}
    return {
        "display_profile": {
            "id": profile.profile_id,
            "color_primaries": profile.color_primaries,
            "output_color_volume": profile.output_color_volume,
            "transfer_function": profile.transfer_function,
            "reference_white_nits": float(profile.reference_white_nits),
            "peak_nits": float(profile.peak_nits),
            "max_headroom": float(profile.max_headroom),
            "black_nits": float(profile.black_nits),
            "output_diffuse_white": float(profile.output_diffuse_white),
            "content_headroom_percentile": float(profile.content_headroom_percentile),
            "gain_map_pair_encoding": "linear_sdr_base_plus_linear_hdr_alternate",
        }
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
    profile = config.display_profile
    reference_white_nits = float(profile.reference_white_nits if profile is not None else config.display_reference_white_nits)
    peak_nits = float(profile.peak_nits if profile is not None else reference_white_nits * float(headroom))
    black_nits = float(profile.black_nits if profile is not None else 0.005)
    return build_hdr_standards_metadata(
        color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        eotf="scene-linear",
        encoded_color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        reference_white_nits=reference_white_nits,
        hdr_headroom=float(headroom),
        min_mastering_luminance_nits=black_nits,
        mastering_scene_white=float(calibration.scene_diffuse_white_y),
        mastering_display_white_nits=reference_white_nits,
        mastering_target_peak_ev=float(math.log2(max(float(headroom), 1.0))),
        mastering_curve_budget_ev=float(math.log2(max(float(headroom), 1.0))),
        target_display_color_space=str(master.diagnostics.get("output_color_space", "Display P3")),
        target_display_min_luminance_nits=black_nits,
        target_display_max_luminance_nits=min(peak_nits, reference_white_nits * float(headroom)),
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
    sdr=None,
    scene_y=None,
) -> HDRProjectionResult | None:
    if _hdr_pair_debug_enabled() or not _is_mlx_array(hdr_y):
        return None
    if sdr is None or not _is_mlx_array(sdr):
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
    if scene_y is None or not _is_mlx_array(scene_y):
        if mode == "paper":
            scene_y = _scene_authority_backend(master, shape)
        else:
            scene_y = _as_y_backend(
                _spatial_authority_for_projection(master, shape),
                field="authority_y",
                shape=shape,
            )
    if scene_y is None:
        return None
    # Below the diffuse-white anchor both modes keep the authored SDR base
    # pixel-for-pixel; the projection only rebuilds chroma in the extension
    # zone. paper masks on scene energy, light_table on the same spatial
    # (post-halation) authority that drives its hdr_y.
    mask = (scene_y <= np.float32(calibration.scene_diffuse_white_y))[..., None]
    hdr_rgb = mx.where(mask, sdr, hdr_rgb)
    effective_path_to_white = _effective_path_to_white_strength(
        path_to_white_strength, config.max_headroom
    )
    hdr_rgb = _apply_path_to_white_backend(hdr_rgb, hdr_y, effective_path_to_white, config.max_headroom)
    hdr_rgb = _apply_output_diffuse_white_backend(hdr_rgb, sdr, config)
    hdr_rgb = _compress_highlight_gamut_backend(hdr_rgb, config.max_headroom)
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
        "content_headroom_percentile": float(config.headroom_percentile),
        "max_headroom": float(config.max_headroom),
        "measured_content_headroom": float(headroom),
        "extension_span_policy": "fixed_max_headroom",
        "path_to_white_strength_input": float(path_to_white_strength),
        "path_to_white_strength_effective": float(effective_path_to_white),
        "path_to_white_headroom_scaling": "hunt_log2_reference_4.0",
        "highlight_chroma_strategy": "route_luminance_ratio_chroma",
        "highlight_gamut_strategy": "luminance_preserving_chroma_compression",
        "highlight_detail_strategy": "highlight_extension_only",
        "highlight_detail_strength": float(config.highlight_detail_strength),
        "reference_white": dict(calibration.diagnostics),
        "preserve_sdr_base": True,
        "projection_backend": "mlx",
        "projection_metadata_statistics": "omitted_backend_fast_path",
        "projection_metadata_statistics_reason": (
            "backend fast path avoids full-frame scene/render statistics readback; "
            "HEIC pair export rebuilds file metadata after final materialization"
        ),
        **_display_profile_diagnostics(config),
        **_backend_projection_profile_diagnostics(),
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
    hdr_y = _build_hdr_y_from_route_backend(
        master,
        config,
        authority_y=scene_y,
        white=scene_white,
        strength=config.paper_extension_strength,
        sdr=sdr,
        authority_prevalidated=True,
        base_luma=sdr_y,
    )
    if hdr_y is None or not _is_mlx_array(hdr_y):
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
        sdr=sdr,
        scene_y=scene_y,
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
    sdr=None,
    scene_y=None,
) -> HDRProjectionResult:
    backend_result = _build_result_backend(
        master=master,
        mode=mode,
        hdr_y=hdr_y,
        config=config,
        calibration=calibration,
        path_to_white_strength=path_to_white_strength,
        diagnostics=diagnostics,
        sdr=sdr,
        scene_y=scene_y,
    )
    if backend_result is not None:
        return backend_result

    if sdr is None or _is_mlx_array(sdr):
        sdr = _sdr_rgb(master)
    if scene_y is not None and _is_mlx_array(scene_y):
        scene_y = None
    shape = sdr.shape[:2]
    chroma = _route_chroma(master, shape)
    hdr_rgb = np.maximum(chroma * np.maximum(hdr_y, 0.0)[..., None], 0.0)
    if scene_y is None:
        if mode == "paper":
            scene_y = _scene_authority(master, shape)
        else:
            scene_y = np.asarray(_spatial_authority_for_projection(master, shape), dtype=np.float32)
    # Both modes preserve the authored SDR base below the diffuse-white
    # anchor; only the extension zone is rebuilt from route chroma.
    mask = (scene_y <= np.float32(calibration.scene_diffuse_white_y))[..., None]
    hdr_rgb = np.where(mask, sdr, hdr_rgb)
    effective_path_to_white = _effective_path_to_white_strength(
        path_to_white_strength, config.max_headroom
    )
    hdr_rgb = _apply_path_to_white(hdr_rgb, hdr_y, effective_path_to_white, config.max_headroom)
    hdr_rgb = _apply_output_diffuse_white(hdr_rgb, sdr, config)
    hdr_rgb, gamut_diagnostics = _compress_highlight_gamut(hdr_rgb, config.max_headroom)
    headroom = _headroom(hdr_rgb, config)
    hdr_rgb = _clip_hdr(hdr_rgb, headroom)
    hdr_luma = luminance_y(hdr_rgb)
    if scene_y is None:
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
        "content_headroom_percentile": float(config.headroom_percentile),
        "max_headroom": float(config.max_headroom),
        "measured_content_headroom": float(headroom),
        "extension_span_policy": "fixed_max_headroom",
        "path_to_white_strength_input": float(path_to_white_strength),
        "path_to_white_strength_effective": float(effective_path_to_white),
        "path_to_white_headroom_scaling": "hunt_log2_reference_4.0",
        "highlight_chroma_strategy": "route_luminance_ratio_chroma",
        **gamut_diagnostics,
        "highlight_detail_strategy": "highlight_extension_only",
        "highlight_detail_strength": float(config.highlight_detail_strength),
        **_display_profile_diagnostics(config),
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

    hdr_y, _ = _build_hdr_y_from_route_numpy(
        master,
        config,
        authority_y=authority_y,
        white=white,
        strength=strength,
    )
    return hdr_y


def _build_hdr_y_from_route_numpy(
    master: RouteMaster,
    config: HDRProjectionConfig,
    *,
    authority_y: np.ndarray,
    white: float,
    strength: float,
    sdr: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Numpy tail of build_hdr_y_from_route.

    Returns ``(hdr_y, sdr)`` so callers can reuse the validated/decoded SDR
    base instead of recomputing it in ``_build_result``.
    """
    if sdr is None:
        sdr = _sdr_rgb(master)
    shape = sdr.shape[:2]
    base_y = np.maximum(luminance_y(sdr), _EPS32)
    ratio = _authority_ratio(authority_y, white=white)
    gain = _extension_gain(
        ratio,
        max_headroom=config.max_headroom,
        strength=strength,
    )
    detail = _material_detail(master, shape, config)
    target_y = np.maximum(base_y * gain, base_y)
    return _apply_highlight_detail(base_y, target_y, detail, ratio, config), sdr


def _build_hdr_y_from_route_backend(
    master: RouteMaster,
    config: HDRProjectionConfig,
    *,
    authority_y,
    white: float,
    strength: float,
    sdr=None,
    authority_prevalidated: bool = False,
    base_luma=None,
):
    if not _is_mlx_array(authority_y):
        return None
    if sdr is None:
        sdr = _sdr_rgb_backend(master)
    if sdr is None:
        return None
    shape = tuple(int(dim) for dim in sdr.shape[:2])
    if not authority_prevalidated:
        authority_y = _as_y_backend(authority_y, field="authority_y", shape=shape)
        if authority_y is None:
            return None
    mx = _mx()
    base_y = mx.maximum(
        base_luma if base_luma is not None else _luminance_y_backend(sdr),
        _EPS32,
    )
    ratio = _authority_ratio_backend(authority_y, white=white)
    gain = _extension_gain_backend(
        ratio,
        max_headroom=config.max_headroom,
        strength=strength,
    )
    detail = _material_detail_backend(master, shape, config)
    if detail is None:
        return None
    target_y = mx.maximum(base_y * gain, base_y)
    return _apply_highlight_detail_backend(base_y, target_y, detail, ratio, config)


__all__ = [
    "HDRProjectionConfig",
    "HDRDisplayProfile",
    "HDRProjectionResult",
    "HDRTransferFunction",
    "build_hdr_y_from_route",
    "_build_result",
    "_route_luminance",
    "_scene_authority",
    "_spatial_authority",
]
