from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final

import numpy as np

_LUMA_COEFFS: Final = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
_EPS: Final = 1e-8
DEFAULT_CURVE_PROFILE_DIR: Final = (
    Path(__file__).resolve().parents[1] / "data" / "hdr_curve_profiles"
)


@dataclass(frozen=True, slots=True)
class HDRCurveDefaults:
    look_diffuse_white_reference: float
    hdr_diffuse_lift_strength: float
    hdr_diffuse_lift_start: float
    hdr_diffuse_lift_end: float
    paper_rolloff_k: float
    paper_rolloff_exposure_scale: float
    graft_strength: float
    safe_max_headroom: float


@dataclass(frozen=True, slots=True)
class FilmPrintHDRCurveProfile:
    film: str
    paper: str
    polarity: str
    safe_for_profile_aware_hdr: bool
    look_diffuse_white_y: float
    shoulder_limit_y: float
    midtone_slope: float
    highlight_slope: float
    shoulder_severity: float
    highlight_tint_spread: float
    defaults: HDRCurveDefaults
    scene_y: np.ndarray
    sdr_luminance_y: np.ndarray


def luminance_y(rgb: np.ndarray) -> np.ndarray:
    values = np.asarray(rgb, dtype=np.float32)
    return np.tensordot(values[..., :3], _LUMA_COEFFS, axes=([-1], [0])).astype(np.float32, copy=False)


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float(default)
    if not math.isfinite(result):
        return float(default)
    return result


def _clean_array(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float32)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)


def _interp_log_domain(scene_y: np.ndarray, source_scene_y: np.ndarray, values: np.ndarray) -> np.ndarray:
    query = np.maximum(_clean_array(scene_y), np.float32(_EPS))
    source_x = np.log2(np.maximum(_clean_array(source_scene_y), np.float32(_EPS)))
    value_y = _clean_array(values)
    order = np.argsort(source_x)
    return np.interp(
        np.log2(query).reshape(-1),
        source_x[order],
        value_y[order],
        left=float(value_y[order][0]),
        right=float(value_y[order][-1]),
    ).reshape(query.shape).astype(np.float32)


def _smoothstep(edge0: float, edge1: float, value: np.ndarray) -> np.ndarray:
    if edge1 <= edge0:
        return np.where(value >= np.float32(edge1), np.float32(1.0), np.float32(0.0))
    t = np.clip((value - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return (t * t * (np.float32(3.0) - np.float32(2.0) * t)).astype(np.float32, copy=False)


def _classify_polarity(y: np.ndarray) -> tuple[str, int]:
    diffs = np.diff(np.asarray(y, dtype=np.float32))
    tol = np.float32(1e-5)
    increasing_violations = int(np.count_nonzero(diffs < -tol))
    decreasing_violations = int(np.count_nonzero(diffs > tol))
    allowed = max(1, int(math.ceil(0.02 * max(len(diffs), 1))))
    if y[-1] >= y[0] and increasing_violations <= allowed:
        return "increasing", increasing_violations
    if y[-1] <= y[0] and decreasing_violations <= allowed:
        return "decreasing", decreasing_violations
    return "nonmonotonic", min(increasing_violations, decreasing_violations)


def _slope_between(scene_y: np.ndarray, y: np.ndarray, low: float, high: float) -> float:
    y_low = float(_interp_log_domain(np.array([low], dtype=np.float32), scene_y, y)[0])
    y_high = float(_interp_log_domain(np.array([high], dtype=np.float32), scene_y, y)[0])
    return (y_high - y_low) / max(high - low, _EPS)


def _fit_summary(y: np.ndarray) -> dict[str, object]:
    return {
        "model": "linear_log_scene_interpolation",
        "params": {},
        "rmse": 0.0,
        "r2": 1.0 if y.size > 1 else 0.0,
    }


def _anchor_float(value: float) -> float:
    for anchor in (0.184, 1.0, 2.0, 4.0, 8.0):
        if math.isclose(float(value), anchor, rel_tol=0.0, abs_tol=1e-6):
            return anchor
    return float(value)


def _default_hdr_defaults(metrics: dict[str, float | str | bool]) -> HDRCurveDefaults:
    look_white = _finite_float(metrics.get("look_diffuse_white_y"), 0.83)
    shoulder_severity = float(np.clip(_finite_float(metrics.get("shoulder_severity"), 0.75), 0.0, 1.0))
    tint_spread = float(np.clip(_finite_float(metrics.get("highlight_tint_spread"), 0.0), 0.0, 1.0))
    return HDRCurveDefaults(
        look_diffuse_white_reference=max(look_white, _EPS),
        hdr_diffuse_lift_strength=float(np.clip(0.65 + 0.35 * shoulder_severity, 0.0, 1.0)),
        hdr_diffuse_lift_start=0.35,
        hdr_diffuse_lift_end=1.0,
        paper_rolloff_k=float(np.clip(4.0 + 4.0 * shoulder_severity, 2.0, 10.0)),
        paper_rolloff_exposure_scale=float(np.clip(3.0 - shoulder_severity, 1.0, 4.0)),
        graft_strength=float(np.clip(1.0 - 0.25 * tint_spread, 0.5, 1.0)),
        safe_max_headroom=8.0,
    )


def build_curve_profile_sample(
    *,
    film: str,
    paper: str,
    scene_y: np.ndarray,
    output_rgb: np.ndarray,
) -> dict[str, object]:
    scene = _clean_array(scene_y).reshape(-1)
    rgb = _clean_array(output_rgb)
    if rgb.ndim != 2 or rgb.shape[1] < 3:
        raise ValueError("output_rgb must have shape (sample_count, 3).")
    if scene.shape[0] != rgb.shape[0]:
        raise ValueError("scene_y and output_rgb must have the same sample count.")
    if np.any(scene <= 0.0):
        raise ValueError("scene_y samples must be positive.")

    order = np.argsort(scene)
    scene = scene[order]
    rgb = rgb[order, :3]
    y = luminance_y(rgb)
    max_channel = np.max(rgb, axis=1).astype(np.float32)
    min_channel = np.min(rgb, axis=1).astype(np.float32)
    spread = (max_channel - min_channel).astype(np.float32)

    polarity, violations = _classify_polarity(y)
    look_white_y = float(_interp_log_domain(np.array([1.0], dtype=np.float32), scene, y)[0])
    look_white_max = float(_interp_log_domain(np.array([1.0], dtype=np.float32), scene, max_channel)[0])
    midgray_y = float(_interp_log_domain(np.array([0.184], dtype=np.float32), scene, y)[0])
    midtone_slope = _slope_between(scene, y, 0.184, 1.0)
    highlight_slope = _slope_between(scene, y, 1.0, 8.0)
    shoulder_limit_y = float(np.max(y[scene >= 1.0])) if np.any(scene >= 1.0) else float(np.max(y))
    shoulder_severity = float(np.clip(1.0 - highlight_slope / max(midtone_slope, _EPS), 0.0, 1.0))
    highlight_tint_spread = float(np.percentile(spread[scene >= 1.0], 95.0)) if np.any(scene >= 1.0) else float(np.max(spread))
    safe = bool(
        polarity == "increasing"
        and math.isfinite(look_white_y)
        and look_white_y > 0.0
        and midtone_slope > 0.0
        and highlight_slope >= -1e-5
    )

    metrics: dict[str, float | str | bool] = {
        "polarity": polarity,
        "monotonicity_violations": float(violations),
        "look_diffuse_white_y": look_white_y,
        "look_diffuse_white_max_channel": look_white_max,
        "midgray_y": midgray_y,
        "shoulder_start_scene_y": 1.0,
        "shoulder_limit_y": shoulder_limit_y,
        "midtone_slope": float(midtone_slope),
        "highlight_slope": float(highlight_slope),
        "shoulder_severity": shoulder_severity,
        "highlight_tint_spread": highlight_tint_spread,
        "safe_for_profile_aware_hdr": safe,
    }
    defaults = _default_hdr_defaults(metrics)

    ev = np.log2(scene)
    return {
        "version": 2,
        "film": film,
        "paper": paper,
        "input_domain": {
            "scene_y_anchor": "diffuse_white_is_1.0",
            "ev_relative_to_diffuse_white": [float(v) for v in ev],
            "scene_y": [_anchor_float(float(v)) for v in scene],
            "rgb_ramp": "neutral_rgb_scene_y",
        },
        "output": {
            "rgb": [[float(channel) for channel in row] for row in rgb],
            "luminance_y": [float(v) for v in y],
            "max_channel": [float(v) for v in max_channel],
            "min_channel": [float(v) for v in min_channel],
            "channel_spread": [float(v) for v in spread],
        },
        "metrics": metrics,
        "fits": {
            "luminance_y": _fit_summary(y),
            "r": _fit_summary(rgb[:, 0]),
            "g": _fit_summary(rgb[:, 1]),
            "b": _fit_summary(rgb[:, 2]),
        },
        "hdr_defaults": {
            "look_diffuse_white_reference": defaults.look_diffuse_white_reference,
            "hdr_diffuse_lift_strength": defaults.hdr_diffuse_lift_strength,
            "hdr_diffuse_lift_start": defaults.hdr_diffuse_lift_start,
            "hdr_diffuse_lift_end": defaults.hdr_diffuse_lift_end,
            "paper_rolloff_k": defaults.paper_rolloff_k,
            "paper_rolloff_exposure_scale": defaults.paper_rolloff_exposure_scale,
            "graft_strength": defaults.graft_strength,
            "safe_max_headroom": defaults.safe_max_headroom,
        },
    }


def build_dynamic_curve_profile(
    scene_y: np.ndarray,
    look_y: np.ndarray,
    fallback_profile: FilmPrintHDRCurveProfile,
) -> FilmPrintHDRCurveProfile:
    """Build a curve profile from dynamic pipeline output, inheriting defaults from a static profile."""
    scene = _clean_array(scene_y).reshape(-1)
    y = _clean_array(look_y).reshape(-1)
    if scene.shape[0] != y.shape[0]:
        raise ValueError("scene_y and look_y must have the same sample count.")

    order = np.argsort(scene)
    scene = scene[order]
    y = y[order]

    polarity, _ = _classify_polarity(y)
    look_white_y = float(_interp_log_domain(np.array([1.0], dtype=np.float32), scene, y)[0])
    midtone_slope = _slope_between(scene, y, 0.184, 1.0)
    highlight_slope = _slope_between(scene, y, 1.0, 8.0)
    shoulder_limit_y = float(np.max(y[scene >= 1.0])) if np.any(scene >= 1.0) else float(np.max(y))
    shoulder_severity = float(np.clip(1.0 - highlight_slope / max(midtone_slope, _EPS), 0.0, 1.0))
    
    safe = bool(
        polarity == "increasing"
        and math.isfinite(look_white_y)
        and look_white_y > 0.0
        and midtone_slope > 0.0
        and highlight_slope >= -1e-5
    )

    metrics: dict[str, float | str | bool] = {
        "look_diffuse_white_y": look_white_y,
        "shoulder_severity": shoulder_severity,
        "highlight_tint_spread": fallback_profile.highlight_tint_spread,
    }
    defaults = _default_hdr_defaults(metrics)

    return FilmPrintHDRCurveProfile(
        film=fallback_profile.film,
        paper=fallback_profile.paper,
        polarity=polarity,
        safe_for_profile_aware_hdr=safe,
        look_diffuse_white_y=look_white_y,
        shoulder_limit_y=shoulder_limit_y,
        midtone_slope=float(midtone_slope),
        highlight_slope=float(highlight_slope),
        shoulder_severity=shoulder_severity,
        highlight_tint_spread=fallback_profile.highlight_tint_spread,
        defaults=defaults,
        scene_y=scene,
        sdr_luminance_y=y,
    )

def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def _summary_entry(sample: dict[str, object], sample_path: str) -> dict[str, object]:
    metrics = sample.get("metrics", {})
    defaults = sample.get("hdr_defaults", {})
    if not isinstance(metrics, dict) or not isinstance(defaults, dict):
        raise ValueError("sample must contain metrics and hdr_defaults objects.")
    return {
        "film": sample["film"],
        "paper": sample["paper"],
        "sample": sample_path,
        "polarity": metrics["polarity"],
        "safe_for_profile_aware_hdr": bool(metrics["safe_for_profile_aware_hdr"]),
        "look_diffuse_white_y": float(metrics["look_diffuse_white_y"]),
        "shoulder_limit_y": float(metrics["shoulder_limit_y"]),
        "midtone_slope": float(metrics["midtone_slope"]),
        "highlight_slope": float(metrics["highlight_slope"]),
        "shoulder_severity": float(metrics["shoulder_severity"]),
        "highlight_tint_spread": float(metrics["highlight_tint_spread"]),
        "defaults": {key: float(value) for key, value in defaults.items()},
    }


def write_curve_profile_database(samples: list[dict[str, object]], output_dir: str | Path) -> Path:
    root = Path(output_dir)
    samples_dir = root / "samples"
    samples_dir.mkdir(parents=True, exist_ok=True)
    profiles: list[dict[str, object]] = []
    for sample in samples:
        filename = f"{_slug(str(sample['film']))}__{_slug(str(sample['paper']))}.json"
        relative_path = f"samples/{filename}"
        path = root / relative_path
        path.write_text(json.dumps(sample, indent=2, sort_keys=True), encoding="utf-8")
        profiles.append(_summary_entry(sample, relative_path))

    summary_path = root / "curve_profiles_v2.json"
    summary = {
        "version": 2,
        "description": "Spektrafilm sampled SDR film/paper curves and derived HDR defaults.",
        "profiles": profiles,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def neutral_scene_y_samples(
    *,
    ev_min: float = -10.0,
    ev_max: float = 6.0,
    ev_step: float = 0.5,
) -> np.ndarray:
    if ev_step <= 0.0:
        raise ValueError("ev_step must be positive.")
    ev = np.arange(float(ev_min), float(ev_max) + 0.5 * float(ev_step), float(ev_step), dtype=np.float64)
    scene = np.power(2.0, ev)
    anchors = np.array([0.184, 1.0, 2.0, 4.0, 8.0], dtype=np.float64)
    scene = np.concatenate([scene, anchors])
    scene = scene[(scene > 0.0) & np.isfinite(scene)]
    scene = np.unique(np.round(scene, decimals=8))
    return np.asarray(np.sort(scene), dtype=np.float32)


def sample_runtime_curve_profile(
    *,
    film: str,
    paper: str,
    ev_min: float = -10.0,
    ev_max: float = 6.0,
    ev_step: float = 0.5,
) -> dict[str, object]:
    from spektrafilm.runtime.params_builder import digest_params, init_params
    from spektrafilm.runtime.process import Simulator

    params = init_params(film_profile=film, print_profile=paper)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.io.full_image = True
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    params = digest_params(params)

    scene_y = neutral_scene_y_samples(ev_min=ev_min, ev_max=ev_max, ev_step=ev_step)
    ramp_rgb = np.repeat(scene_y.reshape(1, -1, 1), 3, axis=2).astype(np.float64)
    output_rgb = np.asarray(Simulator(params).process(ramp_rgb)[0], dtype=np.float32)
    return build_curve_profile_sample(
        film=film,
        paper=paper,
        scene_y=scene_y,
        output_rgb=output_rgb,
    )


def _defaults_from_mapping(values: dict[str, object]) -> HDRCurveDefaults:
    return HDRCurveDefaults(
        look_diffuse_white_reference=_finite_float(values.get("look_diffuse_white_reference"), 0.83),
        hdr_diffuse_lift_strength=_finite_float(values.get("hdr_diffuse_lift_strength"), 1.0),
        hdr_diffuse_lift_start=_finite_float(values.get("hdr_diffuse_lift_start"), 0.35),
        hdr_diffuse_lift_end=_finite_float(values.get("hdr_diffuse_lift_end"), 1.0),
        paper_rolloff_k=_finite_float(values.get("paper_rolloff_k"), 5.5),
        paper_rolloff_exposure_scale=_finite_float(values.get("paper_rolloff_exposure_scale"), 2.5),
        graft_strength=_finite_float(values.get("graft_strength"), 1.0),
        safe_max_headroom=max(_finite_float(values.get("safe_max_headroom"), 8.0), 1.01),
    )


def _profile_from_entry(root: Path, entry: dict[str, object]) -> FilmPrintHDRCurveProfile:
    sample_path = root / str(entry["sample"])
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    scene_y = np.asarray(sample["input_domain"]["scene_y"], dtype=np.float32)
    sdr_y = np.asarray(sample["output"]["luminance_y"], dtype=np.float32)
    defaults_map = entry.get("defaults")
    if not isinstance(defaults_map, dict):
        defaults_map = sample.get("hdr_defaults", {})
    return FilmPrintHDRCurveProfile(
        film=str(entry["film"]),
        paper=str(entry["paper"]),
        polarity=str(entry["polarity"]),
        safe_for_profile_aware_hdr=bool(entry["safe_for_profile_aware_hdr"]),
        look_diffuse_white_y=_finite_float(entry["look_diffuse_white_y"], 0.83),
        shoulder_limit_y=_finite_float(entry["shoulder_limit_y"], 1.0),
        midtone_slope=_finite_float(entry["midtone_slope"], 0.5),
        highlight_slope=_finite_float(entry["highlight_slope"], 0.0),
        shoulder_severity=_finite_float(entry["shoulder_severity"], 0.75),
        highlight_tint_spread=_finite_float(entry["highlight_tint_spread"], 0.0),
        defaults=_defaults_from_mapping(defaults_map),
        scene_y=scene_y,
        sdr_luminance_y=sdr_y,
    )


@lru_cache(maxsize=8)
def load_hdr_curve_profiles(
    data_dir: str | Path = DEFAULT_CURVE_PROFILE_DIR,
) -> dict[tuple[str, str], FilmPrintHDRCurveProfile]:
    root = Path(data_dir)
    summary_path = root / "curve_profiles_v2.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        entries = summary.get("profiles", [])
        if int(summary.get("version", 0)) != 2 or not isinstance(entries, list):
            return {}
        profiles: dict[tuple[str, str], FilmPrintHDRCurveProfile] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            profile = _profile_from_entry(root, entry)
            profiles[(profile.film, profile.paper)] = profile
        return profiles
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return {}


def get_hdr_curve_profile(
    film: str,
    paper: str,
    data_dir: str | Path = DEFAULT_CURVE_PROFILE_DIR,
) -> FilmPrintHDRCurveProfile | None:
    return load_hdr_curve_profiles(data_dir).get((film, paper))


def evaluate_profile_sdr_curve(
    profile: FilmPrintHDRCurveProfile,
    scene_y: np.ndarray,
) -> np.ndarray:
    return _interp_log_domain(scene_y, profile.scene_y, profile.sdr_luminance_y)


def build_profile_hdr_curve(
    profile: FilmPrintHDRCurveProfile,
    scene_y: np.ndarray,
    *,
    mapping: object | None = None,
) -> np.ndarray:
    """Legacy HDR curve via diffuse lift + specular graft.

    .. deprecated::
        Use :func:`build_profile_preserving_hdr_curve` instead. This function
        is retained for regression comparison and emergency fallback only.
    """
    scene = np.maximum(_clean_array(scene_y), np.float32(_EPS))
    sdr = evaluate_profile_sdr_curve(profile, scene)
    defaults = profile.defaults

    max_headroom = max(defaults.safe_max_headroom, 1.01)
    look_white = max(
        _finite_float(getattr(mapping, "look_diffuse_white_reference", None), defaults.look_diffuse_white_reference),
        _EPS,
    )
    target_white = _finite_float(getattr(mapping, "hdr_diffuse_white_target", 1.0), 1.0)
    lift_strength = defaults.hdr_diffuse_lift_strength
    lift_start = defaults.hdr_diffuse_lift_start
    lift_end = defaults.hdr_diffuse_lift_end
    graft_strength = defaults.graft_strength
    rolloff_k = defaults.paper_rolloff_k
    exposure_scale = defaults.paper_rolloff_exposure_scale

    log_scene = np.log2(scene)
    diffuse_w = _smoothstep(np.log2(max(lift_start, _EPS)), np.log2(max(lift_end, _EPS)), log_scene)
    diffuse_w = np.clip(diffuse_w * np.float32(lift_strength), 0.0, 1.0)
    diffuse_branch = sdr * np.float32(target_white / look_white)
    diffuse_target = sdr + diffuse_w * (diffuse_branch - sdr)

    shoulder_input = np.maximum(scene - np.float32(1.0), np.float32(0.0))
    denom = np.float32(max(max_headroom * max(exposure_scale, _EPS) / max(rolloff_k / 5.5, 0.25), _EPS))
    highlight = np.float32(1.0) + np.float32(max_headroom - 1.0) * (
        np.float32(1.0) - np.exp(-shoulder_input / denom)
    )
    highlight = np.clip(highlight, 0.0, np.float32(max_headroom))

    graft_start = _finite_float(getattr(mapping, "graft_start", 1.0), 1.0)
    graft_end = _finite_float(getattr(mapping, "graft_end", 4.0), 4.0)
    spec_w = _smoothstep(np.log2(max(graft_start, _EPS)), np.log2(max(graft_end, _EPS)), log_scene)
    spec_w = np.clip(spec_w * np.float32(graft_strength), 0.0, 1.0)
    hdr = diffuse_target + spec_w * np.maximum(highlight - diffuse_target, np.float32(0.0))

    flat_scene = scene.reshape(-1)
    flat_hdr = hdr.reshape(-1)
    order = np.argsort(flat_scene)
    flat_sorted = flat_hdr[order]
    flat_sorted = np.maximum.accumulate(flat_sorted)
    restored = np.empty_like(flat_hdr)
    restored[order] = flat_sorted
    return np.clip(restored.reshape(scene.shape), 0.0, np.float32(max_headroom)).astype(np.float32, copy=False)


# ---------------------------------------------------------------------------
# Profile-preserving HDR curve  (replaces legacy diffuse_lift + specular_graft)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProfilePreservingHDRCurveResult:
    """Diagnostics bundle returned by :func:`build_profile_preserving_hdr_curve`."""

    s_profile: np.ndarray
    h_profile: np.ndarray
    gain_ev: np.ndarray
    slope: np.ndarray
    diffuse_white: float
    look_white: float
    visual_peak: float


def profile_slope_loglog(
    scene_y: np.ndarray,
    s_profile: np.ndarray,
) -> np.ndarray:
    """Compute local log-log slope ``d log2(s) / d log2(scene_y)``.

    The input arrays need not be sorted; they are sorted internally.
    Duplicate scene_y values are collapsed.  Non-finite / non-positive values
    are clamped.  The returned slope is clipped to [-0.5, 2.0].
    """
    scene = np.maximum(_clean_array(scene_y).reshape(-1), np.float32(_EPS))
    s = np.maximum(_clean_array(s_profile).reshape(-1), np.float32(_EPS))

    unique_scene, unique_idx = np.unique(scene, return_index=True)
    if unique_scene.size < 2:
        return np.zeros_like(scene_y, dtype=np.float32)

    unique_s = s[unique_idx]

    log_scene = np.log2(unique_scene).astype(np.float64)
    log_s = np.log2(unique_s).astype(np.float64)

    # Use a small offset to prevent any extremely close values causing division by zero in gradient
    # Since unique_scene is strictly increasing, adding a cumulative epsilon ensures log_scene is strictly increasing even under precision loss.
    log_scene += np.arange(log_scene.size) * 1e-12

    slope = np.gradient(log_s, log_scene).astype(np.float32)
    slope = np.nan_to_num(slope, nan=0.0, posinf=0.0, neginf=0.0)
    slope = np.clip(slope, -0.5, 2.0)

    # Map back to the original (possibly unsorted / duplicated) input order.
    result = np.interp(
        np.log2(scene).astype(np.float64),
        log_scene,
        slope.astype(np.float64),
    ).astype(np.float32)
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0).reshape(scene_y.shape)


def profile_relative_hdr_gain_ev(
    scene_y: np.ndarray,
    s_profile: np.ndarray,
    diffuse_white: float,
    *,
    peak_ev: float = 1.5,
    knee_ev: float = 0.35,
    softness_ev: float = 3.0,
    strength: float = 0.65,
    slope_full: float = 0.75,
    slope_zero: float = 0.12,
) -> np.ndarray:
    """Compute profile-relative HDR gain in exposure stops.

    ``gain_ev = peak_ev × scene_excess × shoulder_capacity × strength``

    *   ``scene_excess``  rises from 0 above ``diffuse_white + knee_ev`` stops.
    *   ``shoulder_capacity``  rises where the profile log-log slope is low
        (i.e. the profile has entered shoulder compression).
    *   ``gain_ev`` is zero or near-zero below diffuse white.
    """
    eps = np.float32(_EPS)
    scene = np.maximum(_clean_array(scene_y), eps)
    dw = np.float32(max(float(diffuse_white), float(eps)))

    # Scene-relative EV above diffuse white.
    x = np.log2(scene / dw)

    # Scene excess: soft ramp starting at knee_ev.
    t = np.maximum(x - np.float32(knee_ev), np.float32(0.0))
    scene_excess = t / (t + np.float32(max(softness_ev, 1e-6)))

    # Shoulder capacity from profile slope.
    slope = profile_slope_loglog(scene_y, s_profile)
    shoulder_capacity = np.float32(1.0) - _smoothstep(float(slope_zero), float(slope_full), slope)
    shoulder_capacity = np.clip(shoulder_capacity, 0.0, 1.0)

    gain = (
        np.float32(peak_ev)
        * scene_excess
        * shoulder_capacity
        * np.float32(strength)
    )
    return np.maximum(gain, np.float32(0.0)).astype(np.float32)


def soft_clip_relative_to_white(
    y: np.ndarray,
    *,
    white: float,
    peak: float,
    softness: float = 0.45,
) -> np.ndarray:
    """Soft-clip *y* relative to *white* so it asymptotes toward *peak*.

    Below the knee ``white + (peak − white) × (1 − softness)`` the output
    equals the input.  Above the knee the excess is compressed via
    ``knee + room × (1 − exp(−t / room))`` and the result is capped at *peak*.
    """
    eps = np.float32(_EPS)
    y = np.asarray(y, dtype=np.float32).copy()
    white_f = np.float32(max(float(white), float(eps)))
    peak_f = np.float32(max(float(peak), float(white_f) + float(eps)))
    softness_f = np.float32(np.clip(float(softness), 0.0, 0.95))

    knee = white_f + (peak_f - white_f) * (np.float32(1.0) - softness_f)
    room = np.float32(max(float(peak_f - knee), float(eps)))

    above = y > knee
    if np.any(above):
        t = np.maximum(y[above] - knee, np.float32(0.0))
        y[above] = knee + room * (np.float32(1.0) - np.exp(-t / room))

    return np.minimum(y, peak_f).astype(np.float32)


def enforce_monotonic_profile_curve(
    scene_y: np.ndarray,
    h: np.ndarray,
) -> np.ndarray:
    """Ensure *h* is monotonically non-decreasing w.r.t. sorted *scene_y*."""
    scene = _clean_array(scene_y).reshape(-1)
    h_flat = _clean_array(h).reshape(-1)
    order = np.argsort(scene)
    inv = np.empty_like(order)
    inv[order] = np.arange(order.size)
    sorted_h = np.maximum.accumulate(h_flat[order])
    return sorted_h[inv].reshape(h.shape).astype(np.float32)


def build_profile_preserving_hdr_curve(
    profile: FilmPrintHDRCurveProfile,
    scene_y: np.ndarray,
    *,
    diffuse_white: float,
    mapping: object | None = None,
    return_diagnostics: bool = False,
) -> np.ndarray | ProfilePreservingHDRCurveResult:
    """Build an HDR target curve as ``S_profile × 2^gain_ev``.

    Parameters
    ----------
    profile:
        The measured SDR pipeline profile.
    scene_y:
        Scene-linear energy samples (relative, diffuse-white ≈ 1.0).
    diffuse_white:
        Estimated scene-linear diffuse-white value.
    mapping:
        An ``HDRPhotoMapping`` (or compatible object) carrying
        ``profile_hdr_*`` parameters.  Falls back to conservative defaults
        when *None* or when attributes are missing.
    return_diagnostics:
        If *True*, return a :class:`ProfilePreservingHDRCurveResult`
        instead of a plain array.

    Returns
    -------
    np.ndarray or ProfilePreservingHDRCurveResult
        The authored HDR target luminance ``h_profile``.
    """
    scene = np.maximum(_clean_array(scene_y), np.float32(_EPS))
    s = evaluate_profile_sdr_curve(profile, scene).astype(np.float32)
    dw = max(float(diffuse_white), _EPS)

    look_white = float(evaluate_profile_sdr_curve(
        profile,
        np.array([dw], dtype=np.float32),
    )[0])
    look_white = max(look_white, _EPS)

    # Read mapping parameters with safe fallbacks.
    peak_ev = _finite_float(getattr(mapping, "profile_hdr_peak_ev", None), 1.5)
    knee_ev = _finite_float(getattr(mapping, "profile_hdr_knee_ev", None), 0.35)
    softness_ev = _finite_float(getattr(mapping, "profile_hdr_softness_ev", None), 3.0)
    strength = _finite_float(getattr(mapping, "profile_hdr_strength", None), 0.65)
    slope_full = _finite_float(getattr(mapping, "profile_hdr_slope_full", None), 0.75)
    slope_zero = _finite_float(getattr(mapping, "profile_hdr_slope_zero", None), 0.12)
    clip_softness = _finite_float(getattr(mapping, "profile_hdr_soft_clip_softness", None), 0.45)
    min_gain_val = _finite_float(getattr(mapping, "profile_hdr_min_gain", None), 1.0)
    do_monotonic = bool(getattr(mapping, "profile_hdr_enforce_monotonic", True))

    gain_ev = profile_relative_hdr_gain_ev(
        scene,
        s,
        dw,
        peak_ev=peak_ev,
        knee_ev=knee_ev,
        softness_ev=softness_ev,
        strength=strength,
        slope_full=slope_full,
        slope_zero=slope_zero,
    )

    h = s * np.exp2(gain_ev)

    # Floor: h >= s * min_gain.
    if min_gain_val > 0.0:
        h = np.maximum(h, s * np.float32(min_gain_val))

    # Soft-clip relative to look_white.
    visual_peak = look_white * float(np.exp2(peak_ev))
    h = soft_clip_relative_to_white(
        h,
        white=look_white,
        peak=visual_peak,
        softness=clip_softness,
    )

    if do_monotonic:
        h = enforce_monotonic_profile_curve(scene, h)

    h = h.astype(np.float32)

    if return_diagnostics:
        slope = profile_slope_loglog(scene, s)
        return ProfilePreservingHDRCurveResult(
            s_profile=s,
            h_profile=h,
            gain_ev=gain_ev,
            slope=slope,
            diffuse_white=dw,
            look_white=look_white,
            visual_peak=visual_peak,
        )
    return h
