#!/usr/bin/env python3
"""Research-only DNG/RAW diffuse-white and Natural HDR eligibility probes.

This module intentionally does not change production rendering.  It gives the
DNG Natural HDR research pass a small, testable policy surface for separating
scene diffuse white from DNG WhiteLevel, sensor clipping, display reference
white, paper white, and authored HDR controls.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np


REC709_LUMA = (0.2126, 0.7152, 0.0722)
DISPLAY_P3_LUMA = (0.22897456, 0.69173852, 0.07868637)
_EPS = 1e-8
_DEFAULT_MAX_REPORTED_HEADROOM = 8.0

_NATURAL_MODE = "natural_scene_hdr"
_HEURISTIC_MODE = "scene_derived_heuristic_hdr"
_AUTHORED_MODE = "authored_hdr"
_SDR_MODE = "sdr_only"

_DISALLOWED_CREATIVE_CONTROLS = {
    "profile_hdr_peak_ev",
    "profile_hdr_target_peak_ev",
    "profile_hdr_strength",
    "profile_hdr_knee_ev",
    "profile_hdr_min_gain",
    "profile_hdr_recovery_ratio",
    "profile_hdr_recovery_knee_ev",
    "profile_hdr_recovery_full_ev",
    "modern_recovery_peak_budget",
    "budget_recovery_gain_ev",
    "profile_hdr_budget_hard_cap",
    "profile_hdr_max_chroma_gain",
    "source_chroma",
    "bounded_look_chroma",
    "hdr_highlight_saturation_boost",
    "path_to_white",
    "hdr_highlight_path_to_white",
    "profile_hdr_path_to_white_strength",
    "manual_headroom",
    "target_ev",
}


@dataclass(slots=True)
class RawCaptureDiagnostics:
    black_level: float | None
    white_level: float | None
    channel_white_levels: tuple[float, ...]
    clipping_fraction: float
    channel_clipping_fraction: tuple[float, ...]
    raw_p50: float
    raw_p95: float
    raw_p99: float
    raw_p999: float
    warnings: tuple[str, ...] = ()


@dataclass(slots=True)
class DiffuseWhiteEstimate:
    value: float
    method: str
    confidence: str
    provenance: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    clipping_fraction: float
    highlight_headroom_estimate: float
    is_user_override: bool
    is_measured: bool
    is_heuristic: bool
    can_claim_natural_hdr: bool
    recommended_mode: str
    natural_hdr_class: str
    raw_metadata_summary: dict[str, object]


@dataclass(slots=True)
class SceneLuminanceState:
    scene_rgb: np.ndarray
    scene_y: np.ndarray
    working_space: str
    luma_coefficients: tuple[float, float, float]
    diffuse_white: float | None = None
    normalized_scene_y: np.ndarray | None = None
    headroom_estimate: float | None = None
    headroom_confidence: str | None = None
    clipping_diagnostics: RawCaptureDiagnostics | None = None


@dataclass(slots=True)
class NaturalHDRProvenance:
    source_type: str
    raw_metadata_summary: dict[str, object]
    diffuse_white_method: str
    confidence: str
    natural_hdr_class: str
    disallowed_creative_controls: tuple[str, ...]
    downgrade_reason: str
    can_claim_natural_hdr: bool
    recommended_mode: str


def _luma_coefficients(working_space: str) -> tuple[float, float, float]:
    normalized = working_space.strip().lower()
    if normalized in {"display p3", "display-p3", "p3", "p3-d65"}:
        return DISPLAY_P3_LUMA
    return REC709_LUMA


def compute_scene_luminance_y(
    scene_rgb: np.ndarray,
    *,
    working_space: str = "Rec.709",
    luma_coefficients: tuple[float, float, float] | None = None,
) -> SceneLuminanceState:
    """Compute scene luminance from scene-linear RGB and record coefficients."""

    rgb = np.asarray(scene_rgb, dtype=np.float32)
    if rgb.ndim != 3 or rgb.shape[-1] < 3:
        raise ValueError("scene_rgb must have shape (height, width, 3).")
    coeffs = tuple(float(v) for v in (luma_coefficients or _luma_coefficients(working_space)))
    coeff_array = np.asarray(coeffs, dtype=np.float32)
    scene_y = np.tensordot(rgb[..., :3], coeff_array, axes=([-1], [0]))
    scene_y = np.nan_to_num(scene_y, nan=0.0, posinf=0.0, neginf=0.0)
    scene_y = np.maximum(scene_y, 0.0).astype(np.float32, copy=False)
    return SceneLuminanceState(
        scene_rgb=rgb[..., :3],
        scene_y=scene_y,
        working_space=working_space,
        luma_coefficients=coeffs,
    )


def _finite_scene_y(scene_y: np.ndarray) -> np.ndarray:
    values = np.asarray(scene_y, dtype=np.float32).reshape(-1)
    values = values[np.isfinite(values)]
    values = values[values >= 0.0]
    if values.size == 0:
        raise ValueError("scene luminance contains no finite non-negative samples.")
    return values


def _percentiles(values: np.ndarray) -> dict[str, float]:
    return {
        "p50": float(np.percentile(values, 50.0)),
        "p90": float(np.percentile(values, 90.0)),
        "p95": float(np.percentile(values, 95.0)),
        "p98": float(np.percentile(values, 98.0)),
        "p99": float(np.percentile(values, 99.0)),
        "p999": float(np.percentile(values, 99.9)),
    }


def _raw_metadata_summary(raw: RawCaptureDiagnostics | None) -> dict[str, object]:
    if raw is None:
        return {}
    return {
        "black_level": raw.black_level,
        "white_level": raw.white_level,
        "channel_white_levels": list(raw.channel_white_levels),
        "clipping_fraction": raw.clipping_fraction,
        "channel_clipping_fraction": list(raw.channel_clipping_fraction),
        "raw_p50": raw.raw_p50,
        "raw_p95": raw.raw_p95,
        "raw_p99": raw.raw_p99,
        "raw_p999": raw.raw_p999,
        "warnings": list(raw.warnings),
    }


def _headroom(
    scene_values: np.ndarray,
    diffuse_white: float,
    *,
    raw: RawCaptureDiagnostics | None,
    max_reported_headroom: float,
) -> float:
    high_scene = float(np.percentile(scene_values, 99.9))
    if raw is not None and math.isfinite(raw.raw_p999):
        high_scene = max(high_scene, float(raw.raw_p999))
    raw_headroom = high_scene / max(float(diffuse_white), _EPS)
    return float(min(max(raw_headroom, 1.0), max_reported_headroom))


def _saturation_map(scene_rgb: np.ndarray | None) -> np.ndarray | None:
    if scene_rgb is None:
        return None
    rgb = np.maximum(np.asarray(scene_rgb, dtype=np.float32)[..., :3], 0.0)
    max_rgb = np.max(rgb, axis=-1)
    min_rgb = np.min(rgb, axis=-1)
    return np.divide(max_rgb - min_rgb, np.maximum(max_rgb, _EPS), out=np.zeros_like(max_rgb), where=max_rgb > _EPS)


def _active_disallowed_controls(active_creative_controls: Iterable[str] | None) -> tuple[str, ...]:
    if active_creative_controls is None:
        return ()
    return tuple(sorted({str(control) for control in active_creative_controls if str(control) in _DISALLOWED_CREATIVE_CONTROLS}))


def _base_classification(
    *,
    confidence: str,
    measured: bool,
    headroom: float,
    clipping_fraction: float,
    source_type: str,
) -> tuple[bool, str, str]:
    if source_type in {"sdr", "sdr_only", "preview_sdr"}:
        return False, _SDR_MODE, "sdr_only_or_unrecoverable"
    if confidence == "invalid" or headroom < 1.05:
        return False, _SDR_MODE, "sdr_only_or_unrecoverable"
    if clipping_fraction >= 0.02:
        return False, _SDR_MODE, "sdr_only_or_unrecoverable"
    if measured and confidence == "high":
        return True, _NATURAL_MODE, "natural_scene_hdr_verified"
    if confidence == "medium" and clipping_fraction <= 0.005:
        return True, _NATURAL_MODE, "natural_scene_hdr_estimated"
    return False, _HEURISTIC_MODE, "scene_derived_heuristic_hdr"


def estimate_diffuse_white_from_scene(
    *,
    scene_rgb: np.ndarray | None = None,
    scene_y: np.ndarray | None = None,
    working_space: str = "Rec.709",
    raw_diagnostics: RawCaptureDiagnostics | None = None,
    measured_mask: np.ndarray | None = None,
    user_override: float | None = None,
    user_override_is_measured: bool = False,
    source_type: str = "raw_dng",
    active_creative_controls: Iterable[str] | None = None,
    max_reported_headroom: float = _DEFAULT_MAX_REPORTED_HEADROOM,
) -> DiffuseWhiteEstimate:
    """Estimate DNG diffuse white and classify Natural HDR eligibility."""

    if scene_y is None:
        if scene_rgb is None:
            raise ValueError("Either scene_rgb or scene_y is required.")
        luminance_state = compute_scene_luminance_y(scene_rgb, working_space=working_space)
        scene_y_array = luminance_state.scene_y
        rgb_array = luminance_state.scene_rgb
    else:
        scene_y_array = np.asarray(scene_y, dtype=np.float32)
        rgb_array = None if scene_rgb is None else np.asarray(scene_rgb, dtype=np.float32)[..., :3]

    flat_y = _finite_scene_y(scene_y_array)
    pct = _percentiles(flat_y)
    raw_summary = _raw_metadata_summary(raw_diagnostics)
    clipping_fraction = float(raw_diagnostics.clipping_fraction) if raw_diagnostics is not None else 0.0
    warnings: list[str] = []
    assumptions: list[str] = [
        "DNG WhiteLevel is treated as sensor saturation for normalization/clipping, not as scene diffuse white.",
        "Scene luminance Y is computed from linear RGB, not gamma-encoded display RGB.",
    ]
    method = "robust_image_statistics"
    confidence = "medium"
    measured = False
    user_assisted = False

    if raw_diagnostics is None:
        assumptions.append("No RAW black/white-level diagnostics were supplied; clipping confidence is limited.")
    elif raw_diagnostics.white_level is not None:
        assumptions.append(f"WhiteLevel={raw_diagnostics.white_level} remains sensor saturation metadata.")
    if raw_diagnostics is not None and raw_diagnostics.warnings:
        warnings.extend(raw_diagnostics.warnings)

    if measured_mask is not None:
        mask = np.asarray(measured_mask, dtype=bool)
        if mask.shape != scene_y_array.shape:
            raise ValueError(f"measured_mask must match scene luminance shape {scene_y_array.shape}, got {mask.shape}.")
        measured_values = scene_y_array[mask]
        measured_values = measured_values[np.isfinite(measured_values) & (measured_values > 0.0)]
        if measured_values.size == 0:
            value = float("nan")
            confidence = "invalid"
            warnings.append("measured white/gray mask had no finite positive samples")
        else:
            value = float(np.median(measured_values))
            confidence = "high"
            method = "measured_gray_or_white_card"
            measured = True
            assumptions.append("Diffuse white was anchored by a user/calibration region.")
    elif user_override is not None:
        value = float(user_override)
        user_assisted = True
        if not math.isfinite(value) or value <= 0.0:
            confidence = "invalid"
            warnings.append("user diffuse-white override was not finite and positive")
        elif user_override_is_measured:
            confidence = "high"
            method = "measured_gray_or_white_card"
            measured = True
            assumptions.append("User override was explicitly marked as a measured gray/white card.")
        else:
            confidence = "low"
            method = "user_assisted_white_anchor"
            warnings.append("user-assisted diffuse white is a heuristic unless the picked region is measured")
    else:
        value, confidence, method = _estimate_from_statistics(
            scene_y_array=scene_y_array,
            scene_rgb=rgb_array,
            pct=pct,
            raw_diagnostics=raw_diagnostics,
            warnings=warnings,
            assumptions=assumptions,
        )

    if not math.isfinite(value) or value <= 0.0:
        confidence = "invalid"
        value = 0.0
        warnings.append("diffuse white estimate is invalid")

    headroom = _headroom(flat_y, value, raw=raw_diagnostics, max_reported_headroom=max_reported_headroom)
    if clipping_fraction >= 0.02:
        confidence = "invalid" if clipping_fraction >= 0.08 else "low"
        warnings.append(f"clipped RAW highlights detected at fraction {clipping_fraction:.5f}; unrecoverable highlight regions cannot claim Natural HDR")
    elif clipping_fraction >= 0.001:
        confidence = "low"
        warnings.append(f"near-clipped RAW highlights detected at fraction {clipping_fraction:.5f}")

    can_claim, recommended, natural_class = _base_classification(
        confidence=confidence,
        measured=measured,
        headroom=headroom,
        clipping_fraction=clipping_fraction,
        source_type=source_type,
    )
    disallowed = _active_disallowed_controls(active_creative_controls)
    if disallowed:
        can_claim = False
        recommended = _AUTHORED_MODE
        natural_class = "authored_hdr_from_raw"
        warnings.append("active authored HDR controls disqualify Natural HDR labeling: " + ", ".join(disallowed))

    return DiffuseWhiteEstimate(
        value=float(value),
        method=method,
        confidence=confidence,
        provenance=source_type,
        assumptions=tuple(dict.fromkeys(assumptions)),
        warnings=tuple(dict.fromkeys(warnings)),
        clipping_fraction=clipping_fraction,
        highlight_headroom_estimate=headroom,
        is_user_override=user_assisted,
        is_measured=measured,
        is_heuristic=not measured,
        can_claim_natural_hdr=can_claim,
        recommended_mode=recommended,
        natural_hdr_class=natural_class,
        raw_metadata_summary=raw_summary,
    )


def _estimate_from_statistics(
    *,
    scene_y_array: np.ndarray,
    scene_rgb: np.ndarray | None,
    pct: dict[str, float],
    raw_diagnostics: RawCaptureDiagnostics | None,
    warnings: list[str],
    assumptions: list[str],
) -> tuple[float, str, str]:
    p50 = pct["p50"]
    p90 = pct["p90"]
    p95 = pct["p95"]
    p99 = pct["p99"]
    p999 = pct["p999"]
    raw_p99 = float(raw_diagnostics.raw_p99) if raw_diagnostics is not None and math.isfinite(raw_diagnostics.raw_p99) else p99
    raw_p999 = float(raw_diagnostics.raw_p999) if raw_diagnostics is not None and math.isfinite(raw_diagnostics.raw_p999) else p999
    high_reference = max(p99, raw_p99, p999)
    value = max(p95, _EPS)
    confidence = "medium"
    method = "robust_image_statistics"

    low_key = p50 < 0.06 and p95 < 0.20
    small_intense = high_reference / max(p95, _EPS) > 6.0
    if low_key:
        value = max(value, high_reference / 4.0, p50 * 4.0)
        confidence = "low"
        warnings.append("low-key scene: percentile-only diffuse white would fabricate excessive headroom")
        method = "low_key_conservative_statistics"
    elif small_intense:
        value = max(value, high_reference / 4.0)
        confidence = "low"
        warnings.append("small intense highlights: conservative diffuse-white floor used instead of a single high percentile")
        method = "highlight_guarded_statistics"

    saturation = _saturation_map(scene_rgb)
    if saturation is not None:
        y = np.asarray(scene_y_array, dtype=np.float32)
        finite_y = y[np.isfinite(y)]
        top_threshold = max(float(np.percentile(finite_y, 99.0)), p95 * 2.0)
        top_mask = y >= np.float32(top_threshold)
        if np.any(top_mask):
            saturated_top_fraction = float(np.mean(saturation[top_mask] > 0.55))
            if saturated_top_fraction >= 0.25:
                confidence = "low"
                value = max(value, high_reference / 4.0)
                warnings.append("emissive or saturated colored highlights detected; they are not treated as diffuse white")
                method = "semantic_highlight_guarded_statistics"

        neutral_high_mask = (y >= p90) & (saturation <= 0.18)
        neutral_high_fraction = float(np.mean(neutral_high_mask))
        if neutral_high_fraction >= 0.08 and p90 >= 0.70 and p99 / max(p90, _EPS) < 1.75:
            neutral_values = y[neutral_high_mask]
            if neutral_values.size:
                value = max(float(np.percentile(neutral_values, 70.0)), value)
            if confidence != "low":
                confidence = "medium"
            assumptions.append("large diffuse neutral high-key region used as a diffuse-white candidate")
            method = "neutral_high_key_statistics"

    if raw_p999 / max(value, _EPS) <= 1.05 and p999 / max(value, _EPS) <= 1.05:
        warnings.append("no reliable scene values above diffuse white were found")

    return float(value), confidence, method


def classify_dng_natural_hdr_eligibility(
    estimate: DiffuseWhiteEstimate,
    *,
    source_type: str = "raw_dng",
    active_creative_controls: Iterable[str] | None = None,
) -> NaturalHDRProvenance:
    disallowed = _active_disallowed_controls(active_creative_controls)
    if disallowed:
        return NaturalHDRProvenance(
            source_type=source_type,
            raw_metadata_summary=estimate.raw_metadata_summary,
            diffuse_white_method=estimate.method,
            confidence=estimate.confidence,
            natural_hdr_class="authored_hdr_from_raw",
            disallowed_creative_controls=disallowed,
            downgrade_reason="active authored HDR controls can create or reshape headroom",
            can_claim_natural_hdr=False,
            recommended_mode=_AUTHORED_MODE,
        )

    if source_type in {"sdr", "sdr_only", "preview_sdr"}:
        return NaturalHDRProvenance(
            source_type=source_type,
            raw_metadata_summary=estimate.raw_metadata_summary,
            diffuse_white_method=estimate.method,
            confidence=estimate.confidence,
            natural_hdr_class="sdr_only_or_unrecoverable",
            disallowed_creative_controls=(),
            downgrade_reason="SDR-only inputs do not prove scene-referred HDR headroom",
            can_claim_natural_hdr=False,
            recommended_mode=_SDR_MODE,
        )

    if estimate.can_claim_natural_hdr:
        reason = "verified measured diffuse white" if estimate.is_measured else "estimated diffuse white with medium confidence"
    elif estimate.recommended_mode == _HEURISTIC_MODE:
        reason = "diffuse-white anchor is heuristic or low confidence"
    elif estimate.recommended_mode == _SDR_MODE:
        reason = "no reliable recoverable headroom or invalid/clipped estimate"
    else:
        reason = "authored or creative HDR classification"

    return NaturalHDRProvenance(
        source_type=source_type,
        raw_metadata_summary=estimate.raw_metadata_summary,
        diffuse_white_method=estimate.method,
        confidence=estimate.confidence,
        natural_hdr_class=estimate.natural_hdr_class,
        disallowed_creative_controls=(),
        downgrade_reason=reason,
        can_claim_natural_hdr=estimate.can_claim_natural_hdr,
        recommended_mode=estimate.recommended_mode,
    )


def _neutral_scene(values: np.ndarray) -> np.ndarray:
    return np.repeat(np.asarray(values, dtype=np.float32)[..., None], 3, axis=-1)


def _synthetic_raw(
    *,
    clipping_fraction: float = 0.0,
    raw_p50: float = 0.18,
    raw_p95: float = 0.75,
    raw_p99: float = 0.95,
    raw_p999: float = 1.2,
) -> RawCaptureDiagnostics:
    return RawCaptureDiagnostics(
        black_level=64.0,
        white_level=4095.0,
        channel_white_levels=(4095.0, 4095.0, 4095.0, 4095.0),
        clipping_fraction=clipping_fraction,
        channel_clipping_fraction=(clipping_fraction, clipping_fraction, clipping_fraction, clipping_fraction),
        raw_p50=raw_p50,
        raw_p95=raw_p95,
        raw_p99=raw_p99,
        raw_p999=raw_p999,
        warnings=(),
    )


def synthetic_experiments() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    measured = _neutral_scene(np.full((16, 16), 0.35, dtype=np.float32))
    measured[2:8, 2:8, :] = 1.0
    measured[12:14, 12:14, :] = 3.0
    measured_mask = np.zeros((16, 16), dtype=bool)
    measured_mask[2:8, 2:8] = True
    rows.append(_case_result("measured_white_card", measured, raw=_synthetic_raw(raw_p999=3.0), measured_mask=measured_mask))

    normal = _neutral_scene(np.linspace(0.05, 2.0, 32 * 32, dtype=np.float32).reshape(32, 32))
    rows.append(_case_result("normal_unclipped_raw", normal, raw=_synthetic_raw(raw_p50=0.20, raw_p95=0.85, raw_p99=1.6, raw_p999=2.0)))

    low = np.full((32, 32), 0.025, dtype=np.float32)
    low[0:2, 0:2] = 5.0
    rows.append(_case_result("low_key_tiny_highlight", _neutral_scene(low), raw=_synthetic_raw(raw_p50=0.02, raw_p95=0.03, raw_p99=4.5, raw_p999=5.0)))

    snow = np.full((32, 32), 0.95, dtype=np.float32)
    snow[:, :8] = 0.75
    snow[0:2, 0:2] = 1.45
    rows.append(_case_result("snow_white_wall", _neutral_scene(snow), raw=_synthetic_raw(raw_p50=0.8, raw_p95=0.98, raw_p99=1.2, raw_p999=1.45)))

    neon = _neutral_scene(np.full((32, 32), 0.18, dtype=np.float32))
    neon[0:2, 0:2, :] = np.array([9.0, 0.05, 0.02], dtype=np.float32)
    neon[30:32, 30:32, :] = np.array([0.02, 0.05, 7.0], dtype=np.float32)
    rows.append(_case_result("neon_emissive_highlights", neon, raw=_synthetic_raw(raw_p50=0.18, raw_p95=0.2, raw_p99=3.0, raw_p999=7.5)))

    clipped = _neutral_scene(np.linspace(0.1, 4.0, 64, dtype=np.float32).reshape(8, 8))
    rows.append(_case_result("clipped_highlights", clipped, raw=_synthetic_raw(clipping_fraction=0.04, raw_p99=1.0, raw_p999=1.0)))

    authored = _case_result(
        "authored_controls_active",
        measured,
        raw=_synthetic_raw(raw_p999=3.0),
        measured_mask=measured_mask,
        active_creative_controls=("profile_hdr_target_peak_ev", "modern_recovery_peak_budget", "path_to_white"),
    )
    rows.append(authored)
    return rows


def _case_result(
    name: str,
    scene_rgb: np.ndarray,
    *,
    raw: RawCaptureDiagnostics,
    measured_mask: np.ndarray | None = None,
    active_creative_controls: Iterable[str] | None = None,
) -> dict[str, Any]:
    estimate = estimate_diffuse_white_from_scene(
        scene_rgb=scene_rgb,
        measured_mask=measured_mask,
        raw_diagnostics=raw,
        active_creative_controls=active_creative_controls,
    )
    provenance = classify_dng_natural_hdr_eligibility(
        estimate,
        source_type="raw_dng",
        active_creative_controls=active_creative_controls,
    )
    return {
        "case": name,
        "estimate": _jsonable(asdict(estimate)),
        "provenance": _jsonable(asdict(provenance)),
    }


def _raw_sensor_diagnostics_from_dng(path: Path) -> tuple[RawCaptureDiagnostics, np.ndarray]:
    import rawpy

    with rawpy.imread(str(path)) as raw:
        raw_image = np.asarray(raw.raw_image_visible, dtype=np.float64)
        white_level = getattr(raw, "white_level", None)
        white = float(white_level) if white_level is not None else None
        black_levels = np.asarray(getattr(raw, "black_level_per_channel", []), dtype=np.float64)
        black = float(np.nanmin(black_levels)) if black_levels.size else 0.0
        if white is None or white <= black:
            normalized = raw_image.astype(np.float64)
            warnings = ("missing usable DNG WhiteLevel; raw normalization is approximate",)
        else:
            normalized = (raw_image - black) / max(white - black, _EPS)
            warnings = ()
        finite = normalized[np.isfinite(normalized)]
        if finite.size == 0:
            finite = np.array([0.0], dtype=np.float64)

        raw_colors = getattr(raw, "raw_colors_visible", None)
        channel_clip: list[float] = []
        if raw_colors is not None:
            colors = np.asarray(raw_colors)
            for index in sorted(int(v) for v in np.unique(colors)):
                mask = colors == index
                if np.any(mask):
                    channel_clip.append(float(np.mean(normalized[mask] >= 0.999)))

        try:
            rgb = raw.postprocess(
                output_color=rawpy.ColorSpace.ACES,
                output_bps=16,
                no_auto_bright=True,
                gamma=(1, 1),
                use_camera_wb=True,
                half_size=True,
            ).astype(np.float32) / np.float32(65535.0)
        except TypeError:
            rgb = raw.postprocess(
                output_bps=16,
                no_auto_bright=True,
                gamma=(1, 1),
                use_camera_wb=True,
                half_size=True,
            ).astype(np.float32) / np.float32(65535.0)

    diagnostics = RawCaptureDiagnostics(
        black_level=black,
        white_level=white,
        channel_white_levels=tuple(float(v) for v in ([white] * 4 if white is not None else [])),
        clipping_fraction=float(np.mean(finite >= 0.999)),
        channel_clipping_fraction=tuple(channel_clip),
        raw_p50=float(np.percentile(finite, 50.0)),
        raw_p95=float(np.percentile(finite, 95.0)),
        raw_p99=float(np.percentile(finite, 99.0)),
        raw_p999=float(np.percentile(finite, 99.9)),
        warnings=warnings,
    )
    return diagnostics, rgb


def scan_dng_directory(sample_dir: Path, *, max_samples: int) -> list[dict[str, Any]]:
    paths = [path for path in sorted(sample_dir.rglob("*")) if path.is_file() and path.suffix.lower() == ".dng"]
    rows: list[dict[str, Any]] = []
    successes = 0
    max_attempts = max(1, int(max_samples)) * 8
    for attempt, path in enumerate(paths, start=1):
        if attempt > max_attempts and successes > 0:
            break
        if successes >= max_samples:
            break
        try:
            raw, rgb = _raw_sensor_diagnostics_from_dng(path)
            estimate = estimate_diffuse_white_from_scene(scene_rgb=rgb, working_space="ACES2065-1", raw_diagnostics=raw)
            provenance = classify_dng_natural_hdr_eligibility(estimate, source_type="raw_dng")
            rows.append(
                {
                    "file": str(path),
                    "estimate": _jsonable(asdict(estimate)),
                    "provenance": _jsonable(asdict(provenance)),
                }
            )
            successes += 1
        except Exception as exc:  # pragma: no cover - exercised by real-file CLI smoke.
            rows.append({"file": str(path), "error": str(exc)})
    return rows


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        return str(value)
    return value


def _write_json(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case",
                "file",
                "method",
                "confidence",
                "value",
                "headroom",
                "recommended_mode",
                "natural_hdr_class",
                "can_claim_natural_hdr",
                "warnings",
            ],
        )
        writer.writeheader()
        for row in rows:
            estimate = row.get("estimate", {})
            writer.writerow(
                {
                    "case": row.get("case", ""),
                    "file": row.get("file", ""),
                    "method": estimate.get("method", ""),
                    "confidence": estimate.get("confidence", ""),
                    "value": estimate.get("value", ""),
                    "headroom": estimate.get("highlight_headroom_estimate", ""),
                    "recommended_mode": estimate.get("recommended_mode", ""),
                    "natural_hdr_class": estimate.get("natural_hdr_class", ""),
                    "can_claim_natural_hdr": estimate.get("can_claim_natural_hdr", ""),
                    "warnings": "; ".join(str(v) for v in estimate.get("warnings", [])),
                }
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthetic", action="store_true", help="Run built-in synthetic fixtures.")
    parser.add_argument("--sample-dir", type=Path, help="Directory containing DNG files to scan.")
    parser.add_argument("--max-samples", type=int, default=4, help="Maximum real DNG files to inspect.")
    parser.add_argument("--json-output", type=Path, help="Write JSON diagnostics to this path.")
    parser.add_argument("--csv-output", type=Path, help="Write CSV summary to this path.")
    args = parser.parse_args(argv)

    rows: list[dict[str, Any]] = []
    if args.synthetic or args.sample_dir is None:
        rows.extend(synthetic_experiments())
    if args.sample_dir is not None:
        rows.extend(scan_dng_directory(args.sample_dir, max_samples=max(1, int(args.max_samples))))

    if args.json_output is not None:
        _write_json(args.json_output, rows)
    if args.csv_output is not None:
        _write_csv(args.csv_output, rows)
    if args.json_output is None and args.csv_output is None:
        print(json.dumps(rows, indent=2, ensure_ascii=False))
    return 0


__all__ = [
    "DiffuseWhiteEstimate",
    "NaturalHDRProvenance",
    "RawCaptureDiagnostics",
    "SceneLuminanceState",
    "classify_dng_natural_hdr_eligibility",
    "compute_scene_luminance_y",
    "estimate_diffuse_white_from_scene",
    "scan_dng_directory",
    "synthetic_experiments",
]


if __name__ == "__main__":
    raise SystemExit(main())
