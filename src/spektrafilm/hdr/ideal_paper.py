from __future__ import annotations

import numpy as np

from spektrafilm.hdr.projection import (
    HDRProjectionConfig,
    HDRProjectionResult,
    _backend_projection_profile,
    _build_paper_generic_result_backend,
    _build_result,
    _material_detail,
    _scene_authority,
    _smoothstep,
    build_hdr_y_from_route,
    _sdr_rgb,
)
from spektrafilm.hdr.reference_white import resolve_reference_white
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils.hdr_curve_profiles import (
    HDRCurveProfile,
    evaluate_profile_rgb_curve,
    evaluate_profile_sdr_curve,
    get_hdr_curve_profile,
    luminance_y,
)

_EPS32 = np.float32(1e-8)
_TINT_GUARD_THRESHOLD = 0.12


def _diagnostic_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text or text == "None":
        return None
    return text


def _chemical_profile_from_master(master: RouteMaster) -> tuple[HDRCurveProfile | None, str | None]:
    film = _diagnostic_string(master.diagnostics.get("film"))
    paper = _diagnostic_string(master.diagnostics.get("paper"))
    if film is None or paper is None:
        return None, "missing_film_or_paper_identifier"
    profile = get_hdr_curve_profile(film, paper)
    if profile is None:
        return None, "missing_curve_profile"
    return profile, None


def _chemical_profile_is_safe(profile: HDRCurveProfile) -> tuple[bool, str | None]:
    if profile.route != "print_scan" or profile.paper is None:
        return False, "not_print_scan_profile"
    if not profile.safe_for_profile_aware_hdr:
        return False, "profile_marked_unsafe"
    if profile.polarity != "increasing":
        return False, "profile_not_increasing"
    if profile.midtone_slope <= 0.0:
        return False, "nonpositive_midtone_slope"
    if profile.highlight_slope < 0.0:
        return False, "negative_highlight_slope"
    if profile.output_rgb is None:
        return False, "missing_rgb_samples"
    try:
        evaluate_profile_rgb_curve(profile, np.array([1.0], dtype=np.float32))
    except ValueError:
        return False, "invalid_rgb_samples"
    return True, None


def _tint_guard(profile: HDRCurveProfile) -> float:
    return 1.0 - float(
        np.clip(profile.highlight_tint_spread / _TINT_GUARD_THRESHOLD, 0.0, 0.5)
    )


def _profile_value_at(profile: HDRCurveProfile, scene_y: np.ndarray | float) -> np.ndarray:
    return evaluate_profile_sdr_curve(profile, np.asarray(scene_y, dtype=np.float32))


def _paper_display_extension_strength(config: HDRProjectionConfig, profile: HDRCurveProfile) -> float:
    severity = float(np.clip(profile.shoulder_severity, 0.0, 1.0))
    return (
        float(config.paper_extension_strength)
        * (1.0 - 0.35 * severity)
        * _tint_guard(profile)
    )


def _chemical_print_hdr_y(
    *,
    master: RouteMaster,
    config: HDRProjectionConfig,
    sdr_y: np.ndarray,
    scene_y: np.ndarray,
    profile: HDRCurveProfile,
) -> np.ndarray:
    white = np.float32(max(float(config.diffuse_white_scene_anchor), float(_EPS32)))
    ratio = np.maximum(scene_y, 0.0) / white
    if not np.any(ratio > np.float32(1.0)):
        return sdr_y.astype(np.float32, copy=False)

    profile_y = _profile_value_at(profile, np.maximum(ratio, _EPS32))
    profile_white_y = float(_profile_value_at(profile, np.array([1.0], dtype=np.float32))[0])
    capacity = max(float(profile.shoulder_limit_y) - profile_white_y, float(_EPS32))
    used_capacity = np.maximum(profile_y - np.float32(profile_white_y), 0.0)
    chemical_progress = np.clip(used_capacity / np.float32(capacity), 0.0, 1.0)

    peak = float(np.nanpercentile(ratio, config.headroom_percentile))
    span_end = max(1.25, min(float(config.max_headroom), peak))
    scene_excess = np.clip(
        (ratio - np.float32(1.0)) / np.float32(max(span_end - 1.0, float(_EPS32))),
        0.0,
        1.0,
    )
    progress = _smoothstep(1.0, span_end, ratio)

    slope_ratio = float(np.clip(profile.highlight_slope / max(profile.midtone_slope, float(_EPS32)), 0.0, 1.0))
    severity = float(np.clip(profile.shoulder_severity, 0.0, 1.0))
    softness = 1.8 + (0.7 - 1.8) * slope_ratio
    effective_strength = _paper_display_extension_strength(config, profile)
    compressed_excess = scene_excess / (
        np.float32(1.0) + chemical_progress * np.float32(severity * softness * 2.0) * scene_excess
    )
    gain = (
        np.float32(1.0)
        + progress
        * compressed_excess
        * np.float32(max(config.max_headroom - 1.0, 0.0))
        * np.float32(effective_strength)
    )
    gain = np.clip(gain, 1.0, config.max_headroom).astype(np.float32, copy=False)

    detail = _material_detail(master, sdr_y.shape, config)
    low_frequency_gain = gain / np.maximum(detail, _EPS32)
    existing_chemical_y = np.maximum(sdr_y * low_frequency_gain * detail, sdr_y)
    display_budget_y = np.maximum(np.float32(config.max_headroom) - sdr_y, 0.0)
    display_extension_y = (
        sdr_y
        + progress
        * compressed_excess
        * display_budget_y
        * np.float32(effective_strength)
    )
    return np.maximum(existing_chemical_y, display_extension_y).astype(np.float32, copy=False)


def _profile_diagnostics(profile: HDRCurveProfile) -> dict[str, object]:
    return {
        "chemical_profile_source": f"{profile.film}__{profile.paper}",
        "chemical_profile_safe": True,
        "chemical_shoulder_severity": float(profile.shoulder_severity),
        "chemical_highlight_tint_spread": float(profile.highlight_tint_spread),
        "chemical_highlight_slope": float(profile.highlight_slope),
        "chemical_midtone_slope": float(profile.midtone_slope),
    }


def project_hdr_ideal_paper(
    master: RouteMaster,
    config: HDRProjectionConfig | None = None,
) -> HDRProjectionResult:
    """Project a print-scan RouteMaster to Idealized HDR Paper output.

    This is a counterfactual digital medium. Below paper white it preserves
    the legacy photographic print projection; above paper white it extends
    highlights from scene/material energy into display headroom.
    """

    config = HDRProjectionConfig() if config is None else config
    if master.route_kind != "print_scan":
        raise ValueError("Idealized HDR Paper requires a print_scan RouteMaster.")
    calibration = resolve_reference_white(master, config)

    with _backend_projection_profile():
        scene_white = float(calibration.scene_diffuse_white_y)
        profile, fallback_reason = _chemical_profile_from_master(master)
        path_to_white_strength = config.paper_path_to_white_strength
        if profile is None:
            chemical_diagnostics = {
                "paper_rolloff_strategy": "generic_scene_extension",
                "chemical_profile_safe": False,
                "chemical_fallback_reason": fallback_reason or "unavailable",
                "paper_path_to_white_strength_used": float(path_to_white_strength),
            }
            backend_result = _build_paper_generic_result_backend(
                master=master,
                config=config,
                calibration=calibration,
                path_to_white_strength=path_to_white_strength,
                diagnostics={
                    "hdr_mode": "paper",
                    "authority_y": "scene_y_raw",
                    "paper_below_white": "legacy_sdr_print_look",
                    "paper_medium": "counterfactual_digital",
                    **chemical_diagnostics,
                },
            )
            if backend_result is not None:
                return backend_result

        sdr_rgb = _sdr_rgb(master)
        sdr_y = luminance_y(sdr_rgb)
        scene_y = _scene_authority(master, sdr_y.shape)
        chemical_diagnostics: dict[str, object]
        profile_diagnostics: dict[str, object] = {}
        profile_safe = False
        use_chemical_rolloff = False
        if profile is not None:
            profile_diagnostics = _profile_diagnostics(profile)
            safe, unsafe_reason = _chemical_profile_is_safe(profile)
            profile_safe = safe
            if safe:
                use_chemical_rolloff = bool(
                    np.any(scene_y > np.float32(scene_white))
                )
                if use_chemical_rolloff:
                    hdr_y = _chemical_print_hdr_y(
                        master=master,
                        config=config,
                        sdr_y=sdr_y,
                        scene_y=scene_y,
                        profile=profile,
                    )
                    path_to_white_strength *= _tint_guard(profile)
                    chemical_diagnostics = {
                        "paper_rolloff_strategy": "chemical_print",
                        "paper_headroom_strategy": "chemical_display_budget",
                        "paper_display_extension_strength_used": _paper_display_extension_strength(config, profile),
                        **profile_diagnostics,
                        "chemical_profile_safe": True,
                    }
                else:
                    fallback_reason = "no_scene_headroom"
            else:
                fallback_reason = unsafe_reason
        if not use_chemical_rolloff:
            hdr_y = build_hdr_y_from_route(
                master,
                config,
                authority_y=scene_y,
                white=scene_white,
                strength=config.paper_extension_strength,
            )
            chemical_diagnostics = {
                "paper_rolloff_strategy": "generic_scene_extension",
                **profile_diagnostics,
                "chemical_profile_safe": profile_safe,
                "chemical_fallback_reason": fallback_reason or "unavailable",
            }
        chemical_diagnostics["paper_path_to_white_strength_used"] = float(path_to_white_strength)
        hdr_y = np.where(scene_y <= np.float32(scene_white), sdr_y, hdr_y)
        hdr_y = hdr_y.astype(np.float32, copy=False)
        return _build_result(
            master=master,
            mode="paper",
            hdr_y=hdr_y,
            config=config,
            calibration=calibration,
            path_to_white_strength=path_to_white_strength,
            diagnostics={
                "hdr_mode": "paper",
                "authority_y": "scene_y_raw",
                "paper_below_white": "legacy_sdr_print_look",
                "paper_medium": "counterfactual_digital",
                **chemical_diagnostics,
            },
        )


__all__ = ["project_hdr_ideal_paper"]
