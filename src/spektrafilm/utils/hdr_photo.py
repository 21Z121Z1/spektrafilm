from __future__ import annotations

import importlib.resources as pkg_resources
import math
import platform
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

import numpy as np

from spektrafilm.utils.hdr_curve_profiles import (
    FilmPrintHDRCurveProfile,
    ProfilePreservingHDRCurveResult,
    ProfileHDRCurveResult,
    build_profile_hdr_curve,
    build_profile_preserving_hdr_curve,
    evaluate_profile_sdr_curve,
    get_hdr_curve_profile,
    build_dynamic_curve_profile,
    luminance_y,
    profile_slope_loglog,
)

SUPPORTED_HDR_PHOTO_EXTENSIONS: Final = {".heic", ".heif"}
SUPPORTED_HDR_PHOTO_COLOR_SPACES: Final = {
    "sRGB",
    "Display P3",
    "ITU-R BT.2020",
}
DEFAULT_HDR_PHOTO_COLOR_SPACE: Final = "Display P3"
MIN_HDR_PHOTO_HEADROOM: Final = 1.01
HDR_REFERENCE_WHITE_LUMINANCE_NITS: Final = 203.0

_ROLLOFF_MODES: Final = {"logistic", "logarithmic"}
_HDR_MAPPING_MODES: Final = {"generic", "profile_aware"}


class HDRPhotoExportError(RuntimeError):
    """Raised when the platform HDR photo encoder cannot create a valid file."""


@dataclass(frozen=True, slots=True)
class HDRPhotoMapping:
    hdr_mapping_mode: Literal["generic", "profile_aware"] = "generic"
    preserve_sdr_base: bool = True
    film: str | None = None
    paper: str | None = None
    curve_profile: FilmPrintHDRCurveProfile | None = None
    diffuse_white: float = 1.0
    sdr_paper_white: float = 0.9
    max_headroom: float = 8.0
    shoulder_strength: float = 4.0
    # Paper rolloff parameters.
    # Default Logistic k/x0 from RA-4 color paper green-channel density fits:
    #   Fujifilm Crystal Archive Type II: k=5.556, x0=0.177
    #   Kodak Ektacolor Edge:             k=5.263, x0=0.211
    #   Kodak Endura Premier:             k=7.111, x0=0.156
    #   Kodak Portra Endura:              k=4.657, x0=0.236
    #   Kodak Supra Endura:               k=5.495, x0=0.190
    #   Kodak Ultra Endura:               k=6.974, x0=0.214
    paper_rolloff_mode: Literal["logistic", "logarithmic"] = "logistic"
    paper_rolloff_enabled: bool = True
    paper_rolloff_start: float = 1.0
    paper_rolloff_k: float = 5.5
    paper_rolloff_x0: float = 0.19
    paper_rolloff_contrast: float = 1.0
    paper_rolloff_exposure_scale: float = 2.5
    paper_rolloff_strength: float = 4.0
    hdr_render_ev: float = 0.0
    graft_start: float = 1.0
    graft_end: float = 4.0
    graft_strength: float = 0.5
    headroom_percentile: float = 99.9

    # HDR Diffuse Lift parameters
    hdr_diffuse_lift_enabled: bool = True
    hdr_diffuse_white_target: float = 1.0
    hdr_diffuse_lift_start: float = 0.35
    hdr_diffuse_lift_end: float = 1.0
    hdr_diffuse_lift_strength: float = 1.0
    look_diffuse_white_reference: float | None = None
    look_paper_white_percentile: float = 99.0
    profile_diffuse_white_reference: float = 0.8387
    gain_map_mode: Literal["luma", "rgb"] = "rgb"
    profile_scene_y_samples: np.ndarray | None = None
    profile_look_y_samples: np.ndarray | None = None

    hdr_highlight_color_mode: Literal["off", "source_chroma", "bounded_look_chroma"] = "off"
    hdr_highlight_saturation_boost: float = 0.0
    hdr_highlight_chroma_limit: float = 2.0
    hdr_highlight_path_to_white: float = 1.0
    hdr_highlight_gamut: Literal["display-p3", "rec2020", "working"] = "display-p3"

    # --- Profile-preserving HDR curve parameters ---
    profile_curve_mode: Literal["profile_preserving", "legacy_graft"] = "profile_preserving"
    profile_hdr_peak_ev: float = 1.5
    profile_hdr_strength: float = 0.65
    profile_hdr_knee_ev: float = 0.35
    profile_hdr_softness_ev: float = 3.0
    profile_hdr_slope_full: float = 0.75
    profile_hdr_slope_zero: float = 0.12
    profile_hdr_soft_clip_softness: float = 0.45
    profile_hdr_min_gain: float = 1.0
    profile_hdr_enforce_monotonic: bool = True
    profile_hdr_max_chroma_gain: float = 1.25
    profile_hdr_path_to_white_start_ev: float = 1.25
    profile_hdr_path_to_white_end_ev: float = 2.25
    profile_hdr_path_to_white_strength: float = 0.30
    diffuse_white_override: float | None = None

    # --- Modern recovery peak budget parameters ---
    profile_hdr_mode: Literal["strict_preserving", "modern_recovery_peak_budget"] = "strict_preserving"
    profile_hdr_target_peak_ev: float = 2.03
    profile_hdr_normalize_percentile: float = 99.9
    profile_hdr_budget_hard_cap: bool = True
    profile_hdr_recovery_ratio: float = 0.50
    profile_hdr_recovery_knee_ev: float = 0.10
    profile_hdr_recovery_full_ev: float = 1.10

    def __post_init__(self) -> None:
        if self.hdr_mapping_mode not in _HDR_MAPPING_MODES:
            raise ValueError(f"hdr_mapping_mode must be one of {_HDR_MAPPING_MODES!r}.")
        if not math.isfinite(self.diffuse_white) or self.diffuse_white <= 0.0:
            raise ValueError("diffuse_white must be a finite positive value.")
        if not math.isfinite(self.sdr_paper_white) or not (0.0 < self.sdr_paper_white < 1.0):
            raise ValueError("sdr_paper_white must be a finite value in the open interval (0, 1).")
        if not math.isfinite(self.max_headroom) or self.max_headroom < MIN_HDR_PHOTO_HEADROOM:
            raise ValueError("max_headroom must be a finite value greater than SDR white.")
        if not math.isfinite(self.shoulder_strength) or self.shoulder_strength <= 0.0:
            raise ValueError("shoulder_strength must be a finite positive value.")
        if self.paper_rolloff_mode not in _ROLLOFF_MODES:
            raise ValueError(f"paper_rolloff_mode must be one of {_ROLLOFF_MODES!r}.")
        if not math.isfinite(self.paper_rolloff_start) or self.paper_rolloff_start <= 0.0:
            raise ValueError("paper_rolloff_start must be a finite positive value.")
        if not math.isfinite(self.paper_rolloff_k) or self.paper_rolloff_k <= 0.0:
            raise ValueError("paper_rolloff_k must be a finite positive value.")
        if not math.isfinite(self.paper_rolloff_exposure_scale) or self.paper_rolloff_exposure_scale <= 0.0:
            raise ValueError("paper_rolloff_exposure_scale must be a finite positive value.")
        if not math.isfinite(self.paper_rolloff_strength) or self.paper_rolloff_strength <= 0.0:
            raise ValueError("paper_rolloff_strength must be a finite positive value.")
        if not math.isfinite(self.graft_start) or not math.isfinite(self.graft_end) or self.graft_start >= self.graft_end:
            raise ValueError("graft_start must be finite and strictly less than graft_end.")
        if not math.isfinite(self.graft_strength) or not (0.0 <= self.graft_strength <= 1.0):
            raise ValueError("graft_strength must be a finite value in [0, 1].")
        if not math.isfinite(self.headroom_percentile) or not (0.0 < self.headroom_percentile <= 100.0):
            raise ValueError("headroom_percentile must be a finite value in (0, 100].")
        if not math.isfinite(self.hdr_diffuse_white_target) or self.hdr_diffuse_white_target <= 0.0:
            raise ValueError("hdr_diffuse_white_target must be a finite positive value.")
        if not math.isfinite(self.hdr_diffuse_lift_start) or not math.isfinite(self.hdr_diffuse_lift_end) or self.hdr_diffuse_lift_start >= self.hdr_diffuse_lift_end:
            raise ValueError("hdr_diffuse_lift_start must be strictly less than hdr_diffuse_lift_end.")
        if not math.isfinite(self.hdr_diffuse_lift_strength) or not (0.0 <= self.hdr_diffuse_lift_strength <= 1.0):
            raise ValueError("hdr_diffuse_lift_strength must be a finite value in [0, 1].")
        if self.look_diffuse_white_reference is not None and (not math.isfinite(self.look_diffuse_white_reference) or self.look_diffuse_white_reference <= 0.0):
            raise ValueError("look_diffuse_white_reference must be a finite positive value if provided.")
        if self.gain_map_mode not in ("luma", "rgb"):
            raise ValueError("gain_map_mode must be either 'luma' or 'rgb'.")
        if self.hdr_highlight_color_mode not in ("off", "source_chroma", "bounded_look_chroma"):
            raise ValueError("hdr_highlight_color_mode must be 'off', 'source_chroma', or 'bounded_look_chroma'.")
        if self.hdr_highlight_gamut not in ("display-p3", "rec2020", "working"):
            raise ValueError("hdr_highlight_gamut must be 'display-p3', 'rec2020', or 'working'.")
        if not math.isfinite(self.hdr_highlight_saturation_boost) or self.hdr_highlight_saturation_boost < 0.0:
            raise ValueError("hdr_highlight_saturation_boost must be a finite non-negative value.")
        if not math.isfinite(self.hdr_highlight_chroma_limit) or self.hdr_highlight_chroma_limit < 0.0:
            raise ValueError("hdr_highlight_chroma_limit must be a finite non-negative value.")
        if not math.isfinite(self.hdr_highlight_path_to_white) or self.hdr_highlight_path_to_white < 0.0:
            raise ValueError("hdr_highlight_path_to_white must be a finite non-negative value.")
        if self.profile_curve_mode not in ("profile_preserving", "legacy_graft"):
            raise ValueError("profile_curve_mode must be 'profile_preserving' or 'legacy_graft'.")
        if not math.isfinite(self.profile_hdr_peak_ev) or self.profile_hdr_peak_ev <= 0.0:
            raise ValueError("profile_hdr_peak_ev must be a finite positive value.")
        if not math.isfinite(self.profile_hdr_strength) or not (0.0 <= self.profile_hdr_strength <= 1.0):
            raise ValueError("profile_hdr_strength must be a finite value in [0, 1].")
        if not math.isfinite(self.profile_hdr_softness_ev) or self.profile_hdr_softness_ev <= 0.0:
            raise ValueError("profile_hdr_softness_ev must be a finite positive value.")
        if self.diffuse_white_override is not None and (not math.isfinite(self.diffuse_white_override) or self.diffuse_white_override <= 0.0):
            raise ValueError("diffuse_white_override must be a finite positive value if provided.")
        if self.profile_hdr_mode not in ("strict_preserving", "modern_recovery_peak_budget"):
            raise ValueError("profile_hdr_mode must be 'strict_preserving' or 'modern_recovery_peak_budget'.")
        if not math.isfinite(self.profile_hdr_target_peak_ev) or self.profile_hdr_target_peak_ev <= 0.0:
            raise ValueError("profile_hdr_target_peak_ev must be a finite positive value.")
        if not math.isfinite(self.profile_hdr_recovery_ratio) or not (0.0 <= self.profile_hdr_recovery_ratio <= 1.0):
            raise ValueError("profile_hdr_recovery_ratio must be a finite value in [0, 1].")


@dataclass(frozen=True, slots=True)
class HDRPhotoRenditions:
    hdr_rgb: np.ndarray
    sdr_rgb: np.ndarray
    headroom: float
    mapping_mode_used: Literal["generic", "profile_aware"] = "generic"
    diagnostics: tuple[str, ...] = ()


def is_hdr_photo_extension(filename: str | Path) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_HDR_PHOTO_EXTENSIONS


def hdr_photo_color_space(color_space: str | None) -> str:
    """Return an Apple HEIC-friendly RGB color space for HDR photo export."""

    if color_space in SUPPORTED_HDR_PHOTO_COLOR_SPACES:
        return str(color_space)
    return DEFAULT_HDR_PHOTO_COLOR_SPACE


def save_hdr_photo_heic(
    filename: str | Path,
    image_data: np.ndarray,
    *,
    mapping: HDRPhotoMapping | None = None,
    color_space: str,
    quality: float = 0.95,
    scene_luminance: np.ndarray | None = None,
    scene_rgb: np.ndarray | None = None,
    gain_map_mode: Literal["luma", "rgb"] = "rgb",
) -> tuple[str, ...]:
    """Save a linear RGB HDR image as a macOS/CoreImage gain-map HEIC/HEIF."""

    if platform.system() != "Darwin":
        raise HDRPhotoExportError("HEIC HDR photo export currently requires macOS CoreImage.")

    output_path = Path(filename)
    if output_path.suffix.lower() not in SUPPORTED_HDR_PHOTO_EXTENSIONS:
        raise ValueError(f"HDR photo export requires a HEIC/HEIF extension, got {output_path.suffix!r}.")

    mapping = HDRPhotoMapping() if mapping is None else mapping
    if gain_map_mode not in ("luma", "rgb"):
        raise ValueError("gain_map_mode must be either 'luma' or 'rgb'.")

    renditions = prepare_hdr_photo_renditions(image_data, mapping=mapping, scene_luminance=scene_luminance, scene_rgb=scene_rgb)
    color_space = hdr_photo_color_space(color_space)
    sdr_payload = _rgba_float_payload(renditions.sdr_rgb, headroom=1.0)
    hdr_payload = _rgba_float_payload(renditions.hdr_rgb, headroom=renditions.headroom)

    try:
        with tempfile.TemporaryDirectory(prefix="spektrafilm-hdr-heif-") as tmp_dir:
            tmp_path = Path(tmp_dir)
            sdr_raw_path = tmp_path / "sdr-rgba-f32.raw"
            hdr_raw_path = tmp_path / "hdr-rgba-f32.raw"
            sdr_payload.tofile(sdr_raw_path)
            hdr_payload.tofile(hdr_raw_path)
            del sdr_payload, hdr_payload

            command = [
                *_swift_command(),
                str(_encoder_script_path()),
                str(sdr_raw_path),
                str(hdr_raw_path),
                str(output_path),
                str(renditions.hdr_rgb.shape[1]),
                str(renditions.hdr_rgb.shape[0]),
                color_space,
                f"{renditions.headroom:.8g}",
                f"{float(quality):.6g}",
                gain_map_mode,
            ]
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=300,
            )
    except FileNotFoundError as exc:
        raise HDRPhotoExportError("Swift toolchain not found; install Xcode Command Line Tools to export HDR HEIC.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HDRPhotoExportError("CoreImage HDR HEIC export timed out.") from exc

    if result.returncode != 0:
        details = (result.stderr or result.stdout or "").strip()
        message = "CoreImage HDR HEIC export failed"
        if details:
            message = f"{message}: {details}"
        raise HDRPhotoExportError(message)
    
    return renditions.diagnostics


def _prepare_hdr_rgb(image_data: np.ndarray) -> np.ndarray:
    image = np.asarray(image_data)
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("HDR photo export requires an RGB image with shape (height, width, 3).")
    if image.shape[0] <= 0 or image.shape[1] <= 0:
        raise ValueError("Cannot save an empty HDR photo.")
    if not np.issubdtype(image.dtype, np.floating):
        raise ValueError("HDR photo export requires floating-point linear RGB data.")

    image = np.asarray(image[..., :3], dtype=np.float32)
    if not np.all(np.isfinite(image)):
        raise ValueError("HDR photo export requires finite floating-point RGB values.")
    return image


# ---------------------------------------------------------------------------
# Paper rolloff helpers
# ---------------------------------------------------------------------------


def _paper_logistic_progress(
    scene_y: np.ndarray,
    *,
    start: float,
    k: float,
    x0: float,
    contrast: float = 1.0,
    exposure_scale: float = 2.5,
) -> np.ndarray:
    """Compute Logistic paper-curve progress (0.0 to 1.0) for scene luminance."""

    eps = np.float32(1e-8)
    y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)
    s = np.float32(max(start, eps))
    out = np.zeros_like(y)

    above = y > s
    if not np.any(above):
        return out

    # Log-exposure domain with scaling.
    x = np.log2(np.maximum(y[above], eps) / s) / np.float32(max(exposure_scale, eps))

    # Normalized Logistic progress: 0 at x=0, approaching 1 for large x.
    k_f = np.float32(k)
    x0_f = np.float32(x0)
    raw = np.float32(1.0) / (np.float32(1.0) + np.exp(-k_f * (x - x0_f)))
    raw0 = float(1.0 / (1.0 + math.exp(-k * (0.0 - x0))))
    progress = np.clip((raw - np.float32(raw0)) / np.float32(max(1.0 - raw0, 1e-8)), 0.0, 1.0)

    if contrast != 1.0:
        progress = np.power(progress, np.float32(contrast))

    out[above] = progress
    return out


def _paper_logarithmic_progress(
    scene_y: np.ndarray,
    *,
    max_headroom: float,
    start: float,
    strength: float,
    contrast: float = 1.0,
) -> np.ndarray:
    """Compute Logarithmic shoulder progress (0.0 to 1.0) fallback."""

    eps = np.float32(1e-8)
    y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)
    h = np.float32(max(max_headroom, 1.0))
    s = np.float32(max(start, eps))
    out = np.zeros_like(y)

    above = y > s
    if not np.any(above):
        return out

    t = np.clip((y[above] - s) / np.float32(max(float(h - s), 1e-8)), 0.0, 1.0)
    progress = np.log1p(np.float32(strength) * t) / np.float32(max(math.log1p(strength), 1e-8))

    if contrast != 1.0:
        progress = np.power(progress, np.float32(contrast))

    out[above] = progress
    return out


def _apply_rolloff(
    scene_y: np.ndarray,
    *,
    mapping: HDRPhotoMapping,
) -> np.ndarray:
    """Dispatch to the configured rolloff helper and apply compression core."""

    if mapping.paper_rolloff_mode == "logistic":
        progress = _paper_logistic_progress(
            scene_y,
            start=mapping.paper_rolloff_start,
            k=mapping.paper_rolloff_k,
            x0=mapping.paper_rolloff_x0,
            contrast=mapping.paper_rolloff_contrast,
            exposure_scale=mapping.paper_rolloff_exposure_scale,
        )
    else:
        progress = _paper_logarithmic_progress(
            scene_y,
            max_headroom=mapping.max_headroom,
            start=mapping.paper_rolloff_start,
            strength=mapping.paper_rolloff_strength,
            contrast=mapping.paper_rolloff_contrast,
        )

    # Unified compression core
    eps = np.float32(1e-8)
    y = np.maximum(np.asarray(scene_y, dtype=np.float32), 0.0)
    s = np.float32(max(mapping.paper_rolloff_start, eps))
    h = np.float32(max(mapping.max_headroom, 1.0))
    out = y.copy()

    above = y > s
    if not np.any(above):
        return np.minimum(out, h)

    excess = y[above] - s
    range_ = np.maximum(h - s, eps)
    compression = np.float32(1.0) + progress[above] * (excess / range_)
    
    out[above] = s + excess / compression
    return np.minimum(out, h)


# ---------------------------------------------------------------------------
# Scene luminance graft and fallback rolloff
# ---------------------------------------------------------------------------


def prepare_hdr_photo_renditions(
    image_data: np.ndarray,
    *,
    mapping: HDRPhotoMapping | None = None,
    scene_luminance: np.ndarray | None = None,
    scene_rgb: np.ndarray | None = None,
) -> HDRPhotoRenditions:
    mapping = HDRPhotoMapping() if mapping is None else mapping
    image = _prepare_hdr_rgb(image_data)
    if mapping.hdr_mapping_mode == "profile_aware":
        return _prepare_profile_aware_renditions(image, mapping=mapping, scene_luminance=scene_luminance, scene_rgb=scene_rgb)
    return _prepare_generic_renditions(image, mapping=mapping, scene_luminance=scene_luminance)


def _prepare_generic_renditions(
    image: np.ndarray,
    *,
    mapping: HDRPhotoMapping,
    scene_luminance: np.ndarray | None,
    diagnostics: tuple[str, ...] = (),
) -> HDRPhotoRenditions:
    if scene_luminance is None:
        hdr_rgb = image / np.float32(mapping.diffuse_white)
        hdr_rgb = np.maximum(hdr_rgb, 0.0, dtype=np.float32)
        if mapping.paper_rolloff_enabled:
            hdr_rgb = _apply_fallback_rolloff(hdr_rgb, mapping=mapping)
        unlifted_hdr_rgb = hdr_rgb
    else:
        hdr_rgb, unlifted_hdr_rgb = _graft_scene_luminance(image, scene_luminance, mapping=mapping)
    headroom = min(_content_headroom(hdr_rgb, percentile=mapping.headroom_percentile), float(mapping.max_headroom))
    if headroom < MIN_HDR_PHOTO_HEADROOM:
        raise ValueError("HEIC HDR photo export requires linear image values above SDR white (1.0).")
    hdr_rgb = np.clip(hdr_rgb, 0.0, headroom).astype(np.float32, copy=False)
    unlifted_hdr_rgb = np.clip(unlifted_hdr_rgb, 0.0, headroom).astype(np.float32, copy=False)
    
    if getattr(mapping, 'preserve_sdr_base', True):
        # Image is the unmapped original scene look RGB
        sdr_rgb = np.clip(image, 0.0, 1.0).astype(np.float32, copy=False)
    else:
        sdr_rgb = _tone_map_sdr_base(unlifted_hdr_rgb, mapping=mapping, headroom=headroom)
        
    return HDRPhotoRenditions(
        hdr_rgb=np.ascontiguousarray(hdr_rgb),
        sdr_rgb=np.ascontiguousarray(sdr_rgb),
        headroom=float(headroom),
        mapping_mode_used="generic",
        diagnostics=diagnostics,
    )


def _resolve_curve_profile(mapping: HDRPhotoMapping) -> FilmPrintHDRCurveProfile | None:
    if mapping.curve_profile is not None:
        return mapping.curve_profile
    if mapping.film is None or mapping.paper is None:
        return None
    return get_hdr_curve_profile(mapping.film, mapping.paper)


def _prepare_profile_aware_renditions(
    image: np.ndarray,
    *,
    mapping: HDRPhotoMapping,
    scene_luminance: np.ndarray | None,
    scene_rgb: np.ndarray | None = None,
) -> HDRPhotoRenditions:
    if scene_luminance is None:
        raise ValueError("profile-aware HDR mapping requires a scene luminance sidecar.")

    static_profile = _resolve_curve_profile(mapping)
    if static_profile is None:
        raise ValueError("profile-aware HDR mapping requires a valid curve profile.")
        
    if mapping.profile_scene_y_samples is not None and mapping.profile_look_y_samples is not None:
        profile = build_dynamic_curve_profile(
            mapping.profile_scene_y_samples,
            mapping.profile_look_y_samples,
            fallback_profile=static_profile,
        )
    else:
        profile = static_profile

    if profile.polarity != "increasing" or not profile.safe_for_profile_aware_hdr:
        raise ValueError(f"profile-aware HDR mapping requires a safe increasing curve profile, but got unsafe {profile.polarity}.")

    look = np.maximum(np.asarray(image, dtype=np.float32), 0.0)
    scene_y = _prepare_scene_luminance(scene_luminance, shape=look.shape[:2])
    scene_y = scene_y / np.float32(mapping.diffuse_white)
    if mapping.hdr_render_ev != 0.0:
        scene_y = scene_y * np.float32(2.0 ** mapping.hdr_render_ev)
    scene_y = np.maximum(scene_y, np.float32(1e-8))

    # Resolve diffuse_white: override > default 1.0 (scene_y already normalised).
    diffuse_white = (
        mapping.diffuse_white_override
        if mapping.diffuse_white_override is not None
        else 1.0
    )

    look_y = luminance_y(look)

    # Curve selection: profile-preserving (default) vs legacy graft.
    if mapping.profile_curve_mode == "legacy_graft":
        s_profile = evaluate_profile_sdr_curve(profile, scene_y)
        h_profile = build_profile_hdr_curve(profile, scene_y, mapping=mapping)
        look_white = float(evaluate_profile_sdr_curve(
            profile,
            np.array([max(diffuse_white, 1e-8)], dtype=np.float32),
        )[0])
        look_white = max(look_white, 1e-8)
    else:
        curve = build_profile_preserving_hdr_curve(
            profile,
            scene_y,
            diffuse_white=diffuse_white,
            mapping=mapping,
            return_diagnostics=True,
        )
        s_profile = curve.s_profile
        h_profile = curve.h_profile
        look_white = curve.look_white

    hdr_gain = np.divide(
        h_profile,
        np.maximum(s_profile, np.float32(1e-8)),
        out=np.ones_like(h_profile, dtype=np.float32),
        where=s_profile > np.float32(1e-6),
    )
    
    diagnostics_list: list[str] = []
    safe_max_headroom = float(profile.defaults.safe_max_headroom)
    hdr_rgb = _apply_hdr_color_recovery(
        look=look,
        h_profile=h_profile,
        s_profile=s_profile,
        hdr_gain=hdr_gain,
        scene_y=scene_y,
        scene_rgb=scene_rgb,
        mapping=mapping,
        diagnostics=diagnostics_list,
        max_headroom=safe_max_headroom,
        look_white=look_white,
    )
    
    hdr_rgb = np.clip(hdr_rgb, 0.0, safe_max_headroom).astype(np.float32, copy=False)
    headroom = min(_content_headroom(hdr_rgb, percentile=mapping.headroom_percentile), safe_max_headroom)
    if headroom < MIN_HDR_PHOTO_HEADROOM:
        raise ValueError("HEIC HDR photo export requires linear image values above SDR white (1.0).")

    hdr_rgb = np.clip(hdr_rgb, 0.0, headroom).astype(np.float32, copy=False)
    # The authored SDR base preserves the exact look the user authored.
    sdr_rgb = np.clip(look, 0.0, 1.0).astype(np.float32, copy=False)
    return HDRPhotoRenditions(
        hdr_rgb=np.ascontiguousarray(hdr_rgb),
        sdr_rgb=np.ascontiguousarray(sdr_rgb),
        headroom=float(headroom),
        mapping_mode_used="profile_aware",
        diagnostics=tuple(diagnostics_list),
    )


def _apply_hdr_color_recovery(
    look: np.ndarray,
    h_profile: np.ndarray,
    s_profile: np.ndarray,
    hdr_gain: np.ndarray,
    scene_y: np.ndarray,
    scene_rgb: np.ndarray | None,
    mapping: HDRPhotoMapping,
    diagnostics: list[str],
    max_headroom: float,
    look_white: float = 1.0,
) -> np.ndarray:
    eps = np.float32(1e-8)
    
    if mapping.hdr_highlight_color_mode == "off":
        hdr_rgb = look * hdr_gain[..., None]
    elif mapping.hdr_highlight_color_mode == "source_chroma":
        if scene_rgb is None:
            diagnostics.append("source_chroma fallback: scene_rgb is missing, degrading to off")
            hdr_rgb = look * hdr_gain[..., None]
        else:
            source_y = luminance_y(scene_rgb)
            divergence = np.abs(source_y - scene_y) / np.maximum(scene_y, eps)
            # Per-pixel validity: only use source_chroma where scene_rgb is consistent with scene_luminance
            valid_source = divergence <= np.float32(0.05)
            if not np.any(valid_source):
                diagnostics.append("source_chroma fallback: scene_rgb luminance diverged from scene_luminance by > 5% everywhere, degrading to off")
                hdr_rgb = look * hdr_gain[..., None]
            else:
                if not np.all(valid_source):
                    n_bad = int(np.sum(~valid_source))
                    diagnostics.append(f"source_chroma: {n_bad} pixels diverged > 5%, using gain-only fallback for those pixels")
                    
                source_chroma = scene_rgb / np.maximum(source_y[..., None], eps)
                hdr_rgb_source = source_chroma * h_profile[..., None]
                
                # Blend factor: transition from look*gain to source_chroma*h_profile as hdr_gain increases
                blend = _smoothstep(1.0, 1.5, hdr_gain)
                # Zero out blend for pixels where source diverged
                blend = blend * valid_source.astype(np.float32)
                base_hdr_rgb = look * hdr_gain[..., None]
                hdr_rgb = base_hdr_rgb * (np.float32(1.0) - blend[..., None]) + hdr_rgb_source * blend[..., None]
        
    elif mapping.hdr_highlight_color_mode == "bounded_look_chroma":
        boost = mapping.hdr_highlight_saturation_boost
        if boost <= 0.0:
            hdr_rgb = look * hdr_gain[..., None]
        else:
            luma = luminance_y(look)
            min_rgb = np.min(look, axis=-1)
            max_rgb = np.max(look, axis=-1)
            sat = (max_rgb - min_rgb) / np.maximum(max_rgb, eps)
            
            neutral_guard = _smoothstep(0.05, 0.2, sat)
            highlight_guard = _smoothstep(0.5, 0.9, luma)
            mask = _smoothstep(1.0, 2.0, hdr_gain)
            
            effect = mask * neutral_guard * highlight_guard
            sat_multiplier = np.float32(1.0) + effect * np.float32(boost)
            sat_multiplier = np.minimum(sat_multiplier, np.float32(mapping.hdr_highlight_chroma_limit))
            
            boosted_look = luma[..., None] + (look - luma[..., None]) * sat_multiplier[..., None]
            hdr_rgb = boosted_look * hdr_gain[..., None]
    else:
        hdr_rgb = look * hdr_gain[..., None]

    # Bounded chroma gain: limit chroma expansion while preserving target luminance.
    max_chroma_gain = float(getattr(mapping, "profile_hdr_max_chroma_gain", 1.25))
    if max_chroma_gain < 50.0:  # Only apply when a finite limit is set.
        hdr_luma = luminance_y(hdr_rgb)
        chroma_vec = hdr_rgb - hdr_luma[..., None]
        # Reference: gain-only chroma (look * gain minus its luma).
        base_hdr = look * hdr_gain[..., None]
        base_luma = luminance_y(base_hdr)
        base_chroma = base_hdr - base_luma[..., None]
        base_norm = np.sqrt(np.sum(base_chroma ** 2, axis=-1, keepdims=True))
        hdr_norm = np.sqrt(np.sum(chroma_vec ** 2, axis=-1, keepdims=True))
        raw_cg = hdr_norm / np.maximum(base_norm, eps)
        limited_cg = np.minimum(raw_cg, np.float32(max_chroma_gain))
        scale = limited_cg / np.maximum(raw_cg, eps)
        # Reconstruct: preserved luma + scaled chroma.
        hdr_rgb = hdr_luma[..., None] + chroma_vec * scale

    # Path to white — EV-relative to look_white.
    lw = np.float32(max(look_white, float(eps)))
    pw_start_ev = float(getattr(mapping, "profile_hdr_path_to_white_start_ev", 1.25))
    pw_end_ev = float(getattr(mapping, "profile_hdr_path_to_white_end_ev", 2.25))
    pw_strength = np.float32(getattr(mapping, "profile_hdr_path_to_white_strength", 0.30))
    # Also support the legacy path_to_white for non-profile-preserving callers.
    if float(getattr(mapping, "hdr_highlight_path_to_white", 0.0)) > 0.0 and pw_strength <= 0.0:
        pw_strength = np.float32(mapping.hdr_highlight_path_to_white)
    if pw_strength > 0.0:
        h_ev = np.log2(np.maximum(h_profile, eps) / lw)
        pw_mask = _smoothstep(pw_start_ev, pw_end_ev, h_ev)
        hdr_luma = luminance_y(hdr_rgb)
        hdr_rgb = hdr_rgb * (np.float32(1.0) - pw_mask[..., None] * pw_strength) + \
                  hdr_luma[..., None] * (pw_mask[..., None] * pw_strength)
              
    # Gamut Compression (Luma preserving chroma reduction)
    max_rgb = np.max(hdr_rgb, axis=-1)
    overshoot = max_rgb > max_headroom
    if np.any(overshoot):
        hdr_luma = luminance_y(hdr_rgb)
        scale = (np.float32(max_headroom) - hdr_luma[overshoot]) / np.maximum(max_rgb[overshoot] - hdr_luma[overshoot], eps)
        scale = np.clip(scale, 0.0, 1.0)
        hdr_rgb[overshoot] = hdr_luma[overshoot, None] + (hdr_rgb[overshoot] - hdr_luma[overshoot, None]) * scale[..., None]
        
    return np.maximum(hdr_rgb, 0.0).astype(np.float32, copy=False)


def build_hdr_debug_sidecar(
    curve_result: ProfilePreservingHDRCurveResult | ProfileHDRCurveResult,
    *,
    mapping: HDRPhotoMapping | None = None,
    extra: dict | None = None,
) -> dict:
    """Build a JSON-serializable debug sidecar from a curve diagnostics result.

    Accepts :class:`ProfilePreservingHDRCurveResult` or
    :class:`ProfileHDRCurveResult` returned by
    ``build_profile_preserving_hdr_curve(..., return_diagnostics=True)`` so
    that no values are re-computed.
    """
    def _pcts(arr: np.ndarray) -> dict:
        flat = arr.reshape(-1)
        if flat.size == 0:
            return {}
        return {
            "p50": float(np.percentile(flat, 50.0)),
            "p90": float(np.percentile(flat, 90.0)),
            "p99": float(np.percentile(flat, 99.0)),
            "p999": float(np.percentile(flat, 99.9)),
        }

    is_modern = isinstance(curve_result, ProfileHDRCurveResult)

    sidecar: dict = {
        "mode": "modern_recovery_peak_budget" if is_modern else "profile_preserving",
        "diffuse_white": curve_result.diffuse_white,
        "look_white": curve_result.look_white,
        "percentiles": {
            "s_profile": _pcts(curve_result.s_profile),
            "h_profile": _pcts(curve_result.h_profile),
            "gain_ev": _pcts(curve_result.gain_ev),
            "slope": _pcts(curve_result.slope),
        },
    }

    if is_modern:
        sidecar["target_peak_ev"] = curve_result.target_peak_ev
        sidecar["raw_peak_ev_before_budget"] = curve_result.raw_peak_ev_before_budget
        sidecar["actual_peak_ev_after_budget"] = curve_result.actual_peak_ev_after_budget
        sidecar["budget_scale"] = curve_result.budget_scale
        sidecar["percentiles"]["raw_gain_ev"] = _pcts(curve_result.raw_gain_ev)
        sidecar["percentiles"]["compressed_ev"] = _pcts(curve_result.compressed_ev)
        sidecar["percentiles"]["final_h_ev"] = _pcts(curve_result.final_h_ev)
    else:
        sidecar["visual_peak"] = curve_result.visual_peak

    if mapping is not None:
        mapping_info: dict = {
            "profile_hdr_mode": getattr(mapping, "profile_hdr_mode", "strict_preserving"),
        }
        if is_modern:
            mapping_info.update({
                "profile_hdr_target_peak_ev": mapping.profile_hdr_target_peak_ev,
                "profile_hdr_recovery_ratio": mapping.profile_hdr_recovery_ratio,
                "profile_hdr_recovery_knee_ev": mapping.profile_hdr_recovery_knee_ev,
                "profile_hdr_recovery_full_ev": mapping.profile_hdr_recovery_full_ev,
            })
        else:
            mapping_info.update({
                "profile_hdr_peak_ev": mapping.profile_hdr_peak_ev,
                "profile_hdr_strength": mapping.profile_hdr_strength,
                "profile_hdr_knee_ev": mapping.profile_hdr_knee_ev,
                "profile_hdr_softness_ev": mapping.profile_hdr_softness_ev,
                "profile_hdr_slope_full": mapping.profile_hdr_slope_full,
                "profile_hdr_slope_zero": mapping.profile_hdr_slope_zero,
                "profile_hdr_soft_clip_softness": mapping.profile_hdr_soft_clip_softness,
            })
        sidecar["mapping"] = mapping_info
    if extra:
        sidecar.update(extra)
    return sidecar


def _prepare_scene_luminance(scene_luminance: np.ndarray, *, shape: tuple[int, int]) -> np.ndarray:
    luminance = np.asarray(scene_luminance, dtype=np.float32)
    if luminance.ndim == 3 and luminance.shape[2] == 1:
        luminance = luminance[..., 0]
    if luminance.shape != shape:
        raise ValueError(
            "HDR scene luminance sidecar must match image height and width; "
            f"expected {shape}, got {luminance.shape}."
        )
    if not np.all(np.isfinite(luminance)):
        raise ValueError("HDR scene luminance sidecar requires finite values.")
    return np.maximum(luminance, 0.0, dtype=np.float32)


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    t = np.clip((value - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return t * t * (np.float32(3.0) - np.float32(2.0) * t)


def _estimate_look_diffuse_white_reference(
    look_y: np.ndarray,
    scene_y: np.ndarray | None,
    *,
    explicit: float | None,
    fallback_percentile: float = 99.0,
    profile_fallback: float = 0.8387,
    min_samples: int = 100,
) -> float:
    if explicit is not None:
        return float(explicit)
    
    if scene_y is not None:
        mask = (scene_y >= 0.9) & (scene_y <= 1.1) & np.isfinite(scene_y) & np.isfinite(look_y)
        if np.count_nonzero(mask) >= min_samples:
            return float(np.median(look_y[mask]))
        return float(profile_fallback)
    
    # Fallback to look_y percentile only if scene_y is not available
    valid_look = look_y[np.isfinite(look_y)]
    if valid_look.size > 0:
        return float(np.percentile(valid_look, fallback_percentile))
    return float(profile_fallback)


def _graft_scene_luminance(
    look_rgb: np.ndarray,
    scene_luminance: np.ndarray,
    *,
    mapping: HDRPhotoMapping,
) -> tuple[np.ndarray, np.ndarray]:
    """Graft scene-energy luminance onto the paper-limited look, with diffue lift and rolloff."""

    eps = np.float32(1e-8)
    look = np.maximum(np.asarray(look_rgb, dtype=np.float32), 0.0)
    look_y = np.max(look, axis=2)
    
    scene_y_raw = _prepare_scene_luminance(scene_luminance, shape=look.shape[:2])
    scene_y = scene_y_raw / np.float32(mapping.diffuse_white)
    if mapping.hdr_render_ev != 0.0:
        scene_y = scene_y * np.float32(2.0 ** mapping.hdr_render_ev)
    
    scene_y = np.maximum(scene_y, eps)
    log2_y = np.log2(scene_y)

    look_white = mapping.look_diffuse_white_reference
    if look_white is None and mapping.profile_scene_y_samples is not None and mapping.profile_look_y_samples is not None:
        idx_1 = np.argmin(np.abs(mapping.profile_scene_y_samples - 1.0))
        look_white = float(mapping.profile_look_y_samples[idx_1])
    
    if look_white is None:
        look_white = _estimate_look_diffuse_white_reference(
            look_y,
            scene_y,
            explicit=mapping.look_diffuse_white_reference,
            fallback_percentile=mapping.look_paper_white_percentile,
            profile_fallback=mapping.profile_diffuse_white_reference,
        )

    # 1. Diffuse lift layer
    if mapping.hdr_diffuse_lift_enabled:
        log2_d_start = np.log2(np.float32(mapping.hdr_diffuse_lift_start))
        log2_d_end = np.log2(np.float32(mapping.hdr_diffuse_lift_end))
        diffuse_w = _smoothstep(log2_d_start, log2_d_end, log2_y) * np.float32(mapping.hdr_diffuse_lift_strength)
        
        diffuse_gain = np.float32(mapping.hdr_diffuse_white_target) / np.float32(max(look_white, 1e-8))
        diffuse_target_y = look_y * (np.float32(1.0) + diffuse_w * (diffuse_gain - np.float32(1.0)))
    else:
        diffuse_target_y = look_y

    # 2. Specular rolloff layer
    if mapping.paper_rolloff_enabled:
        rolled_y = _apply_rolloff(scene_y, mapping=mapping)
    else:
        rolled_y = scene_y

    log2_graft_start = np.log2(np.float32(mapping.graft_start))
    log2_graft_end = np.log2(np.float32(mapping.graft_end))
    w_spec = _smoothstep(log2_graft_start, log2_graft_end, log2_y) * np.float32(mapping.graft_strength)
    
    # Merge: specular extends above diffuse baseline only
    specular_delta = np.maximum(rolled_y - diffuse_target_y, np.float32(0.0))
    target_y = diffuse_target_y + w_spec * specular_delta
    
    unlifted_target_y = look_y + w_spec * np.maximum(rolled_y - look_y, np.float32(0.0))

    scale = target_y / np.maximum(look_y, eps)
    unlifted_scale = unlifted_target_y / np.maximum(look_y, eps)
    
    hdr_rgb = look * scale[..., None]
    hdr_rgb = np.clip(hdr_rgb, 0.0, float(mapping.max_headroom))
    
    unlifted_hdr_rgb = look * unlifted_scale[..., None]
    unlifted_hdr_rgb = np.clip(unlifted_hdr_rgb, 0.0, float(mapping.max_headroom))
    
    return hdr_rgb.astype(np.float32, copy=False), unlifted_hdr_rgb.astype(np.float32, copy=False)


def _apply_fallback_rolloff(
    hdr_rgb: np.ndarray,
    *,
    mapping: HDRPhotoMapping,
) -> np.ndarray:
    """Apply paper rolloff to the fallback path (no scene_luminance sidecar).

    This is a standalone helper — it does NOT reuse the graft logic.  It
    compresses per-pixel max-channel intensity through the configured rolloff
    curve while preserving channel ratios (hue).
    """

    eps = np.float32(1e-8)
    image = np.maximum(np.asarray(hdr_rgb, dtype=np.float32), 0.0)
    intensity = np.max(image, axis=2)
    rolled_intensity = _apply_rolloff(intensity, mapping=mapping)
    scale = rolled_intensity / np.maximum(intensity, eps)
    return np.maximum(image * scale[..., None], 0.0).astype(np.float32, copy=False)


def _tone_map_sdr_base(image: np.ndarray, *, mapping: HDRPhotoMapping, headroom: float) -> np.ndarray:
    image = np.maximum(np.asarray(image, dtype=np.float32), 0.0)
    intensity = np.max(image, axis=2)
    clipped_intensity = np.minimum(intensity, np.float32(headroom))
    mapped = np.empty_like(intensity, dtype=np.float32)
    below = intensity <= 1.0
    mapped[below] = clipped_intensity[below] * np.float32(mapping.sdr_paper_white)

    if np.any(~below):
        shoulder_strength = np.float32(mapping.shoulder_strength)
        denominator = np.log1p(shoulder_strength * np.float32(headroom - 1.0))
        mapped[~below] = np.float32(mapping.sdr_paper_white) + np.float32(1.0 - mapping.sdr_paper_white) * (
            np.log1p(shoulder_strength * (clipped_intensity[~below] - np.float32(1.0))) / denominator
        )

    scale = mapped / np.maximum(intensity, np.float32(1e-8))
    return np.clip(
        image * scale[..., None],
        0.0,
        1.0,
    ).astype(np.float32, copy=False)


def _content_headroom(image: np.ndarray, *, percentile: float = 99.9) -> float:
    """Compute robust content headroom using a per-pixel max-channel percentile.

    Unlike ``np.max(image)`` which lets a single hot pixel determine the
    entire image headroom, this computes per-pixel max-channel intensity
    and then takes a robust percentile.
    """

    intensity = np.max(image, axis=2)
    value = float(np.percentile(intensity, percentile))
    if not math.isfinite(value):
        return 1.0
    return max(value, 1.0)


def _rgba_float_payload(image: np.ndarray, *, headroom: float) -> np.ndarray:
    height, width = image.shape[:2]
    rgba = np.empty((height, width, 4), dtype=np.float32)
    np.clip(image, 0.0, headroom, out=rgba[..., :3])
    rgba[..., 3] = 1.0
    return np.ascontiguousarray(rgba)


def _swift_command() -> list[str]:
    xcrun = shutil.which("xcrun")
    if xcrun is not None:
        return [xcrun, "swift"]
    swift = shutil.which("swift")
    if swift is not None:
        return [swift]
    raise HDRPhotoExportError("Swift toolchain not found; install Xcode Command Line Tools to export HDR HEIC.")


def _encoder_script_path() -> Path:
    return Path(pkg_resources.files("spektrafilm.data.macos").joinpath("hdr_heif_encoder.swift"))
