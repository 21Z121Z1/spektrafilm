from __future__ import annotations

import numpy as np

from spektrafilm.hdr.projection import (
    HDRProjectionConfig,
    HDRProjectionResult,
    _apply_highlight_detail,
    _backend_projection_profile,
    _build_hdr_y_from_route_numpy,
    _build_paper_generic_result_backend,
    _build_result,
    _is_mlx_array,
    _material_detail,
    _scene_authority,
    _smoothstep,
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


def _smooth_max(a: np.ndarray, b: np.ndarray, softness: float) -> np.ndarray:
    """C1-continuous max approximation.

    Exact where a == b (so the diffuse-white seam stays untouched), never
    below min(a, b) (so 'HDR never darker than SDR' is preserved), and within
    softness/2 of the true max away from the crossing.
    """

    k = np.float32(max(float(softness), 1e-6))
    diff = a - b
    return (
        np.float32(0.5) * (a + b + np.sqrt(diff * diff + k * k) - k)
    ).astype(np.float32, copy=False)


def _soft_clip_gain(gain: np.ndarray, max_headroom: float) -> np.ndarray:
    """Quadratic-knee saturation toward the gain cap.

    Identity below cap - width, exactly cap above cap + width, C1 everywhere
    in between; the cap is reached at finite input (non-asymptotic), unlike a
    hard np.clip which introduces a slope discontinuity at the cap.
    """

    cap = float(max_headroom)
    width = max(0.1 * (cap - 1.0), 1e-6)
    lower = np.float32(cap - width)
    upper = np.float32(cap + width)
    knee = np.float32(cap) - (gain - upper) * (gain - upper) / np.float32(4.0 * width)
    return np.where(
        gain <= lower,
        gain,
        np.where(gain >= upper, np.float32(cap), knee),
    ).astype(np.float32, copy=False)


def _backend_scene_has_headroom(scene_y_raw, scene_white: float) -> bool:
    """Single-scalar readback of ``any(scene > white)`` for backend masters.

    Comparison semantics match the numpy decision on the validated authority:
    ``maximum(x, 0) > white`` equals ``x > white`` for positive ``white``, and
    non-finite scenes fall through to the generic path whose validation raises
    the same error the numpy path would have raised.
    """
    import mlx.core as mx

    return bool(np.asarray(mx.any(scene_y_raw > np.float32(scene_white))))


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

    # The extension span is fixed by the configured headroom rather than a
    # content percentile so that crops/framing changes of the same scene keep
    # identical per-pixel rendering (content stats still bound the final
    # headroom metadata in projection._headroom).
    span_end = max(1.25, float(config.max_headroom))
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
    gain = np.maximum(_soft_clip_gain(gain, config.max_headroom), np.float32(1.0))

    detail = _material_detail(master, sdr_y.shape, config)
    existing_chemical_y = _apply_highlight_detail(
        sdr_y,
        np.maximum(sdr_y * gain, sdr_y),
        detail,
        ratio,
        config,
    )
    display_budget_y = np.maximum(np.float32(config.max_headroom) - sdr_y, 0.0)
    display_extension_y = (
        sdr_y
        + progress
        * compressed_excess
        * display_budget_y
        * np.float32(effective_strength)
    )
    display_extension_y = _apply_highlight_detail(sdr_y, display_extension_y, detail, ratio, config)
    # A hard max between the multiplicative chemical arm and the additive
    # display-budget arm leaves a C1 kink where the curves cross; the smooth
    # blend stays exact at the seam (both arms equal sdr_y there).
    blend_softness = 0.02 * max(float(config.max_headroom) - 1.0, 0.0)
    return _smooth_max(existing_chemical_y, display_extension_y, blend_softness)


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
    *,
    chemical_profile: HDRCurveProfile | None = None,
    chemical_profile_origin: str | None = None,
) -> HDRProjectionResult:
    """Project a print-scan RouteMaster to Idealized HDR Paper output.

    This is a counterfactual digital medium. Below paper white it preserves
    the legacy photographic print projection; above paper white it extends
    highlights from scene/material energy into display headroom.

    ``chemical_profile`` overrides the static bundled (film, paper) profile
    with one resampled from the caller's current tone parameters (see
    ``spektrafilm.hdr.profile_cache.get_dynamic_print_curve_profile``); the
    same safety classification applies, so an unsafe dynamic profile falls
    back to the generic scene extension.
    """

    config = HDRProjectionConfig() if config is None else config
    if master.route_kind != "print_scan":
        raise ValueError("Idealized HDR Paper requires a print_scan RouteMaster.")
    calibration = resolve_reference_white(master, config)

    with _backend_projection_profile():
        scene_white = float(calibration.scene_diffuse_white_y)
        if chemical_profile is not None:
            profile, fallback_reason = chemical_profile, None
            profile_origin = chemical_profile_origin or "dynamic_resample"
        else:
            profile, fallback_reason = _chemical_profile_from_master(master)
            profile_origin = "static_bundled"
        path_to_white_strength = config.paper_path_to_white_strength
        profile_diagnostics: dict[str, object] = {}
        profile_safe = False
        unsafe_reason: str | None = None
        if profile is not None:
            profile_diagnostics = _profile_diagnostics(profile)
            profile_safe, unsafe_reason = _chemical_profile_is_safe(profile)
            if not profile_safe:
                fallback_reason = unsafe_reason

        # Generic-extension candidates can ride the backend projection without
        # materializing the frame to the host first. Chemical eligibility for
        # backend-resident masters is decided by a single mx.any readback; host
        # masters keep the original numpy decision flow below.
        scene_is_backend = _is_mlx_array(master.scene_y_raw)
        use_chemical_rolloff = False
        if profile is not None and profile_safe and scene_is_backend:
            use_chemical_rolloff = _backend_scene_has_headroom(master.scene_y_raw, scene_white)
            if not use_chemical_rolloff:
                fallback_reason = "no_scene_headroom"
        if not use_chemical_rolloff and (profile is None or not profile_safe or scene_is_backend):
            chemical_diagnostics = {
                "paper_rolloff_strategy": "generic_scene_extension",
                **profile_diagnostics,
                "chemical_profile_safe": profile_safe,
                "chemical_profile_origin": profile_origin,
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
        if profile is not None:
            if profile_safe:
                if not scene_is_backend:
                    use_chemical_rolloff = bool(
                        np.any(scene_y > np.float32(scene_white))
                    )
                    if not use_chemical_rolloff:
                        fallback_reason = "no_scene_headroom"
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
                        "chemical_profile_origin": profile_origin,
                    }
                else:
                    fallback_reason = "no_scene_headroom"
            else:
                fallback_reason = unsafe_reason
        if not use_chemical_rolloff:
            # scene_y is host-resident here, so the backend HDR-Y builder can
            # never engage; go straight to the numpy tail and reuse the SDR
            # base decoded above instead of recomputing it.
            hdr_y, _ = _build_hdr_y_from_route_numpy(
                master,
                config,
                authority_y=scene_y,
                white=scene_white,
                strength=config.paper_extension_strength,
                sdr=sdr_rgb,
            )
            chemical_diagnostics = {
                "paper_rolloff_strategy": "generic_scene_extension",
                **profile_diagnostics,
                "chemical_profile_safe": profile_safe,
                "chemical_profile_origin": profile_origin,
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
            sdr=sdr_rgb,
            scene_y=scene_y,
        )


__all__ = ["project_hdr_ideal_paper"]
