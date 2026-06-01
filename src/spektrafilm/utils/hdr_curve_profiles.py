from __future__ import annotations

import copy
import json
import logging
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Final, Literal, TypeAlias

import numpy as np

from spektrafilm.utils.math_ops import smoothstep as _smoothstep

_log = logging.getLogger(__name__)

_LUMA_COEFFS: Final = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
_EPS: Final = 1e-8
_DEFAULT_FILM_SCAN_SAMPLE_PAPER: Final = "kodak_portra_endura"
DEFAULT_CURVE_PROFILE_DIR: Final = (
    Path(__file__).resolve().parents[1] / "data" / "hdr_curve_profiles"
)
HDRCurveRoute: TypeAlias = Literal["print_scan", "film_scan"]


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
class HDRCurveProfile:
    film: str
    paper: str | None
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
    route: HDRCurveRoute = "print_scan"
    scanner: str | None = None


FilmPrintHDRCurveProfile: TypeAlias = HDRCurveProfile


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
    paper: str | None,
    route: HDRCurveRoute = "print_scan",
    scanner: str | None = None,
    scene_y: np.ndarray,
    output_rgb: np.ndarray,
) -> dict[str, object]:
    if route not in ("print_scan", "film_scan"):
        raise ValueError("route must be 'print_scan' or 'film_scan'.")
    if route == "print_scan" and paper is None:
        raise ValueError("print_scan curve profiles require a paper identifier.")

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
        "route": route,
        "film": film,
        "paper": paper,
        "scanner": scanner,
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

    return HDRCurveProfile(
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
        route=fallback_profile.route,
        scanner=fallback_profile.scanner,
    )

def _slug(value: str) -> str:
    return re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9_.-]+", "_", value)).strip("_")


def _summary_entry(sample: dict[str, object], sample_path: str) -> dict[str, object]:
    metrics = sample.get("metrics", {})
    defaults = sample.get("hdr_defaults", {})
    if not isinstance(metrics, dict) or not isinstance(defaults, dict):
        raise ValueError("sample must contain metrics and hdr_defaults objects.")
    return {
        "route": str(sample.get("route", "print_scan")),
        "film": sample["film"],
        "paper": sample.get("paper"),
        "scanner": sample.get("scanner"),
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
        route = str(sample.get("route", "print_scan"))
        if route == "film_scan":
            filename = f"{_slug(str(sample['film']))}__film_scan.json"
        else:
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


def _prepare_profile_sampling_params(
    params,
    *,
    scan_film: bool,
    unclipped_scan_output: bool,
):
    from spektrafilm.runtime.params_builder import digest_params

    sampled = copy.deepcopy(params)
    sampled.io.scan_film = bool(scan_film)
    sampled.debug.deactivate_spatial_effects = True
    sampled.debug.deactivate_stochastic_effects = True
    sampled.settings.use_enlarger_lut = False
    sampled.settings.use_scanner_lut = False
    sampled.io.upscale_factor = 1.0
    sampled.io.crop = False
    sampled.io.input_cctf_decoding = False
    sampled.io.output_cctf_encoding = False
    if unclipped_scan_output:
        sampled.io.output_clip_min = False
        sampled.io.output_clip_max = False
    sampled.camera.auto_exposure = False
    sampled.camera.exposure_compensation_ev = 0.0
    return digest_params(sampled)


def sample_runtime_curve_profile(
    *,
    film: str,
    paper: str,
    ev_min: float = -10.0,
    ev_max: float = 6.0,
    ev_step: float = 0.5,
) -> dict[str, object]:
    from spektrafilm.runtime.params_builder import init_params
    from spektrafilm.runtime.process import Simulator

    params = init_params(film_profile=film, print_profile=paper)
    params = _prepare_profile_sampling_params(
        params,
        scan_film=False,
        unclipped_scan_output=False,
    )

    scene_y = neutral_scene_y_samples(ev_min=ev_min, ev_max=ev_max, ev_step=ev_step)
    ramp_rgb = np.repeat(scene_y.reshape(1, -1, 1), 3, axis=2).astype(np.float64)
    output_rgb = np.asarray(Simulator(params).process(ramp_rgb)[0], dtype=np.float32)
    return build_curve_profile_sample(
        film=film,
        paper=paper,
        route="print_scan",
        scene_y=scene_y,
        output_rgb=output_rgb,
    )


def sample_runtime_film_scan_curve_profile(
    *,
    params=None,
    film: str | None = None,
    paper: str | None = None,
    ev_min: float = -10.0,
    ev_max: float = 6.0,
    ev_step: float = 0.5,
) -> dict[str, object]:
    from spektrafilm.runtime.params_builder import init_params
    from spektrafilm.runtime.process import Simulator

    if params is None:
        if film is None:
            raise ValueError("film is required when params is not provided.")
        params = init_params(
            film_profile=film,
            print_profile=_DEFAULT_FILM_SCAN_SAMPLE_PAPER,
        )
    if film is None:
        film = getattr(getattr(getattr(params, "film", None), "info", None), "stock", None)
        film = None if film is None else str(film)
    if not film or film == "None":
        raise ValueError("film-scan curve sampling requires a film identifier.")

    sampled_params = _prepare_profile_sampling_params(
        params,
        scan_film=True,
        unclipped_scan_output=True,
    )

    scene_y = neutral_scene_y_samples(ev_min=ev_min, ev_max=ev_max, ev_step=ev_step)
    ramp_rgb = np.repeat(scene_y.reshape(1, -1, 1), 3, axis=2).astype(np.float64)
    output_rgb = np.asarray(Simulator(sampled_params).process(ramp_rgb)[0], dtype=np.float32)
    return build_curve_profile_sample(
        film=film,
        paper=None,
        route="film_scan",
        scanner="runtime_current",
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


def curve_profile_from_sample(sample: dict[str, object]) -> HDRCurveProfile:
    input_domain = sample.get("input_domain", {})
    output = sample.get("output", {})
    metrics = sample.get("metrics", {})
    if not isinstance(input_domain, dict) or not isinstance(output, dict) or not isinstance(metrics, dict):
        raise ValueError("curve profile sample must contain input_domain, output, and metrics objects.")

    route = str(sample.get("route", "print_scan"))
    if route not in ("print_scan", "film_scan"):
        raise ValueError("curve profile sample route must be 'print_scan' or 'film_scan'.")
    defaults = sample.get("hdr_defaults", {})
    if not isinstance(defaults, dict):
        defaults = {}

    return HDRCurveProfile(
        film=str(sample["film"]),
        paper=None if sample.get("paper") is None else str(sample["paper"]),
        polarity=str(metrics["polarity"]),
        safe_for_profile_aware_hdr=bool(metrics["safe_for_profile_aware_hdr"]),
        look_diffuse_white_y=_finite_float(metrics["look_diffuse_white_y"], 0.83),
        shoulder_limit_y=_finite_float(metrics["shoulder_limit_y"], 1.0),
        midtone_slope=_finite_float(metrics["midtone_slope"], 0.5),
        highlight_slope=_finite_float(metrics["highlight_slope"], 0.0),
        shoulder_severity=_finite_float(metrics["shoulder_severity"], 0.75),
        highlight_tint_spread=_finite_float(metrics["highlight_tint_spread"], 0.0),
        defaults=_defaults_from_mapping(defaults),
        scene_y=np.asarray(input_domain["scene_y"], dtype=np.float32),
        sdr_luminance_y=np.asarray(output["luminance_y"], dtype=np.float32),
        route=route,  # type: ignore[arg-type]
        scanner=None if sample.get("scanner") is None else str(sample["scanner"]),
    )


def _profile_from_entry(root: Path, entry: dict[str, object]) -> HDRCurveProfile:
    sample_path = root / str(entry["sample"])
    sample = json.loads(sample_path.read_text(encoding="utf-8"))
    scene_y = np.asarray(sample["input_domain"]["scene_y"], dtype=np.float32)
    sdr_y = np.asarray(sample["output"]["luminance_y"], dtype=np.float32)
    defaults_map = entry.get("defaults")
    if not isinstance(defaults_map, dict):
        defaults_map = sample.get("hdr_defaults", {})
    route = str(entry.get("route", sample.get("route", "print_scan")))
    if route not in ("print_scan", "film_scan"):
        route = "print_scan"
    return HDRCurveProfile(
        film=str(entry["film"]),
        paper=None if entry.get("paper") is None else str(entry["paper"]),
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
        route=route,  # type: ignore[arg-type]
        scanner=None if entry.get("scanner") is None else str(entry["scanner"]),
    )


@lru_cache(maxsize=8)
def load_hdr_curve_profiles(
    data_dir: str | Path = DEFAULT_CURVE_PROFILE_DIR,
) -> dict[tuple[str, str], HDRCurveProfile]:
    root = Path(data_dir)
    summary_path = root / "curve_profiles_v2.json"
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        entries = summary.get("profiles", [])
        if int(summary.get("version", 0)) != 2 or not isinstance(entries, list):
            return {}
        profiles: dict[tuple[str, str], HDRCurveProfile] = {}
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            profile = _profile_from_entry(root, entry)
            if profile.route == "print_scan" and profile.paper is not None:
                profiles[(profile.film, profile.paper)] = profile
        return profiles
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        _log.warning("Failed to load HDR curve profiles from %s: %s", summary_path, exc)
        return {}


def get_hdr_curve_profile(
    film: str,
    paper: str,
    data_dir: str | Path = DEFAULT_CURVE_PROFILE_DIR,
) -> HDRCurveProfile | None:
    return load_hdr_curve_profiles(data_dir).get((film, paper))


def evaluate_profile_sdr_curve(
    profile: HDRCurveProfile,
    scene_y: np.ndarray,
) -> np.ndarray:
    return _interp_log_domain(scene_y, profile.scene_y, profile.sdr_luminance_y)


def build_profile_hdr_curve(
    profile: HDRCurveProfile,
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


@dataclass(frozen=True, slots=True)
class ProfileHDRCurveResult:
    """Extended diagnostics for ``modern_recovery_peak_budget`` mode."""

    s_profile: np.ndarray
    h_profile: np.ndarray
    gain_ev: np.ndarray
    raw_gain_ev: np.ndarray
    slope: np.ndarray
    scene_ev: np.ndarray
    profile_ev: np.ndarray
    raw_h_ev: np.ndarray
    final_h_ev: np.ndarray
    compressed_ev: np.ndarray
    diffuse_white: float
    look_white: float
    target_peak_ev: float
    raw_peak_ev_before_budget: float
    actual_peak_ev_after_budget: float
    budget_scale: float


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


def budget_recovery_gain_ev(
    p_ev: np.ndarray,
    raw_gain_ev: np.ndarray,
    *,
    target_peak_ev: float = 2.03,
    active_mask: np.ndarray | None = None,
    normalize_percentile: float = 99.9,
    hard_cap: bool = True,
    return_info: bool = False,
) -> np.ndarray | tuple[np.ndarray, dict]:
    """Scale *raw_gain_ev* so the final ``p_ev + gain_ev`` fits within *target_peak_ev*.

    Budget only scales ``raw_gain_ev``; the profile baseline ``p_ev`` is never
    touched.  If ``p_ev`` itself already exceeds the target, the effective
    target is raised to accommodate.

    Parameters
    ----------
    p_ev:
        Profile-relative EV baseline (``log2(s / look_white)``).
    raw_gain_ev:
        Raw recovery gain in EV (pre-budget).
    target_peak_ev:
        Desired maximum of ``p_ev + gain_ev``.
    active_mask:
        Optional boolean mask selecting pixels/samples used to measure the
        percentile budget.  Scaling still applies to the full gain array.
    normalize_percentile:
        Percentile used to measure the raw peak.
    hard_cap:
        If *True*, clamp each element so that
        ``p_ev[i] + gain_ev[i] <= target_peak_ev`` strictly.
    return_info:
        If *True*, return ``(gain_ev, info_dict)``.
    """
    p_arr, raw_arr = np.broadcast_arrays(
        np.asarray(p_ev, dtype=np.float32),
        np.asarray(raw_gain_ev, dtype=np.float32),
    )
    p = np.nan_to_num(p_arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False)
    raw = np.maximum(
        np.nan_to_num(raw_arr, nan=0.0, posinf=0.0, neginf=0.0).astype(np.float32, copy=False),
        0.0,
    )
    target = float(target_peak_ev)
    if not math.isfinite(target) or target <= 0.0:
        raise ValueError("target_peak_ev must be a finite positive value.")
    percentile = float(normalize_percentile)
    if not math.isfinite(percentile) or not (0.0 < percentile <= 100.0):
        raise ValueError("normalize_percentile must be a finite value in (0, 100].")

    if active_mask is None:
        active = np.ones(p.shape, dtype=bool)
    else:
        active = np.broadcast_to(np.asarray(active_mask, dtype=bool), p.shape).copy()
    active &= np.isfinite(p) & np.isfinite(raw)
    if not np.any(active):
        active = np.ones(p.shape, dtype=bool)

    def _measured_percentile(values: np.ndarray) -> float:
        measured = np.asarray(values, dtype=np.float32)[active]
        if measured.size == 0:
            measured = np.asarray(values, dtype=np.float32).reshape(-1)
        if measured.size == 0:
            return 0.0
        try:
            value = np.percentile(measured, percentile, method="higher")
        except TypeError:  # NumPy < 1.22 compatibility.
            value = np.percentile(measured, percentile, interpolation="higher")
        result = float(value)
        return result if math.isfinite(result) else 0.0

    # If the baseline already exceeds the target, raise the effective target.
    baseline_peak = _measured_percentile(p)
    effective_target = max(target, baseline_peak)

    raw_h = p + raw
    raw_peak = _measured_percentile(raw_h)

    if raw_peak <= effective_target or raw_peak <= 0.0:
        # Budget not needed.
        gain = raw.copy()
        scale = 1.0
        applied = False
    else:
        # Find scale so that percentile(p + raw * scale) ≈ effective_target.
        # Since p + raw * scale is monotone in scale, binary search works.
        lo, hi = 0.0, 1.0
        for _ in range(64):
            mid = (lo + hi) * 0.5
            candidate_peak = _measured_percentile(p + raw * np.float32(mid))
            if candidate_peak > effective_target:
                hi = mid
            else:
                lo = mid
        scale = (lo + hi) * 0.5
        gain = raw * np.float32(scale)
        applied = True

    if hard_cap:
        headroom = np.maximum(np.float32(effective_target) - p, np.float32(0.0))
        gain = np.minimum(gain, headroom)
    gain = np.maximum(gain, np.float32(0.0))

    final_h = p + gain
    actual_peak = _measured_percentile(final_h)

    if return_info:
        info = {
            "budget_scale": scale,
            "budget_was_applied": applied,
            "target_peak_ev": target,
            "effective_target_peak_ev": effective_target,
            "raw_peak_ev_before_budget": raw_peak,
            "actual_peak_ev_after_budget": actual_peak,
            "normalize_percentile": percentile,
            "hard_cap": bool(hard_cap),
            "active_sample_count": int(np.count_nonzero(active)),
            "raw_h_ev": raw_h.astype(np.float32, copy=False),
            "final_h_ev": final_h.astype(np.float32, copy=False),
        }
        return gain.astype(np.float32), info
    return gain.astype(np.float32)


def profile_modern_recovery_budgeted_gain_ev(
    scene_y: np.ndarray,
    s_profile: np.ndarray,
    *,
    diffuse_white: float,
    look_white: float,
    recovery_ratio: float = 0.50,
    recovery_knee_ev: float = 0.10,
    recovery_full_ev: float = 1.10,
    slope_full: float = 0.90,
    slope_zero: float = 0.18,
    target_peak_ev: float = 2.03,
    normalize_percentile: float = 99.9,
    hard_cap: bool = True,
    return_diagnostics: bool = False,
) -> np.ndarray | dict:
    """Compute modern recovery gain EV with an EV budget constraint.

    The recovery gain restores a fraction (*recovery_ratio*) of the highlight
    luminance that the profile curve compressed away.  The total
    ``p_ev + gain_ev`` is budget-constrained to *target_peak_ev*.

    If *return_diagnostics* is *True*, return a dict with full diagnostics
    instead of just the gain_ev array.
    """
    eps = np.float32(_EPS)
    scene = np.maximum(_clean_array(scene_y), eps)
    s = np.maximum(_clean_array(s_profile), eps)
    dw = np.float32(max(float(diffuse_white), float(eps)))
    lw = np.float32(max(float(look_white), float(eps)))

    # Scene EV relative to diffuse white.
    x = np.log2(scene / dw)
    # Profile EV relative to look_white.
    p_ev = np.log2(s / lw)

    # Compressed EV: how much EV the profile "ate" relative to scene.
    compressed_ev = np.maximum(x - p_ev, np.float32(0.0))

    # Highlight onset: smoothstep ramp from knee to full.
    highlight_w = _smoothstep(float(recovery_knee_ev), float(recovery_full_ev), x)

    # Shoulder capacity from profile slope.
    slope = profile_slope_loglog(scene, s)
    shoulder_w = np.float32(1.0) - _smoothstep(float(slope_zero), float(slope_full), slope)
    shoulder_w = np.clip(shoulder_w, 0.0, 1.0)

    raw_gain_ev = np.float32(recovery_ratio) * highlight_w * shoulder_w * compressed_ev
    raw_gain_ev = np.maximum(raw_gain_ev, np.float32(0.0))

    # Apply budget.
    gain_ev, info = budget_recovery_gain_ev(
        p_ev,
        raw_gain_ev,
        target_peak_ev=target_peak_ev,
        normalize_percentile=normalize_percentile,
        hard_cap=hard_cap,
        return_info=True,
    )

    if return_diagnostics:
        return {
            "gain_ev": gain_ev,
            "raw_gain_ev": raw_gain_ev,
            "slope": slope,
            "scene_ev": x,
            "profile_ev": p_ev,
            "raw_h_ev": info["raw_h_ev"],
            "final_h_ev": info["final_h_ev"],
            "compressed_ev": compressed_ev,
            "highlight_w": highlight_w,
            "shoulder_w": shoulder_w,
            **info,
        }
    return gain_ev


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
) -> np.ndarray | ProfilePreservingHDRCurveResult | ProfileHDRCurveResult:
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
        If *True*, return a :class:`ProfilePreservingHDRCurveResult` or
        :class:`ProfileHDRCurveResult` instead of a plain array.

    Returns
    -------
    np.ndarray or ProfilePreservingHDRCurveResult or ProfileHDRCurveResult
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

    mode = getattr(mapping, "profile_hdr_mode", "strict_preserving")
    min_gain_val = _finite_float(getattr(mapping, "profile_hdr_min_gain", None), 1.0)
    do_monotonic = bool(getattr(mapping, "profile_hdr_enforce_monotonic", True))

    if mode not in ("strict_preserving", "modern_recovery_peak_budget"):
        raise ValueError("profile_hdr_mode must be 'strict_preserving' or 'modern_recovery_peak_budget'.")

    if mode == "modern_recovery_peak_budget":
        # --- Modern recovery peak budget path ---
        recovery_ratio = _finite_float(getattr(mapping, "profile_hdr_recovery_ratio", None), 0.50)
        recovery_knee_ev = _finite_float(getattr(mapping, "profile_hdr_recovery_knee_ev", None), 0.10)
        recovery_full_ev = _finite_float(getattr(mapping, "profile_hdr_recovery_full_ev", None), 1.10)
        slope_full = _finite_float(getattr(mapping, "profile_hdr_slope_full", None), 0.90)
        slope_zero = _finite_float(getattr(mapping, "profile_hdr_slope_zero", None), 0.18)
        target_peak_ev = _finite_float(getattr(mapping, "profile_hdr_target_peak_ev", None), 2.03)
        normalize_pct = _finite_float(getattr(mapping, "profile_hdr_normalize_percentile", None), 99.9)
        hard_cap = bool(getattr(mapping, "profile_hdr_budget_hard_cap", True))

        diag = profile_modern_recovery_budgeted_gain_ev(
            scene, s,
            diffuse_white=dw,
            look_white=look_white,
            recovery_ratio=recovery_ratio,
            recovery_knee_ev=recovery_knee_ev,
            recovery_full_ev=recovery_full_ev,
            slope_full=slope_full,
            slope_zero=slope_zero,
            target_peak_ev=target_peak_ev,
            normalize_percentile=normalize_pct,
            hard_cap=hard_cap,
            return_diagnostics=True,
        )

        gain_ev = diag["gain_ev"]
        h = s * np.exp2(gain_ev)

        if min_gain_val > 0.0:
            h = np.maximum(h, s * np.float32(min_gain_val))
        if do_monotonic:
            h = enforce_monotonic_profile_curve(scene, h)
        h = h.astype(np.float32)

        if return_diagnostics:
            lw = np.float32(max(look_white, _EPS))
            final_h_ev = np.log2(np.maximum(h, np.float32(_EPS)) / lw)
            return ProfileHDRCurveResult(
                s_profile=s,
                h_profile=h,
                gain_ev=gain_ev,
                raw_gain_ev=diag["raw_gain_ev"],
                slope=diag["slope"],
                scene_ev=diag["scene_ev"],
                profile_ev=diag["profile_ev"],
                raw_h_ev=diag["raw_h_ev"],
                final_h_ev=final_h_ev,
                compressed_ev=diag["compressed_ev"],
                diffuse_white=dw,
                look_white=look_white,
                target_peak_ev=target_peak_ev,
                raw_peak_ev_before_budget=diag["raw_peak_ev_before_budget"],
                actual_peak_ev_after_budget=diag["actual_peak_ev_after_budget"],
                budget_scale=diag["budget_scale"],
            )
        return h

    # --- Strict preserving path (default / original) ---
    peak_ev = _finite_float(getattr(mapping, "profile_hdr_peak_ev", None), 1.5)
    knee_ev = _finite_float(getattr(mapping, "profile_hdr_knee_ev", None), 0.35)
    softness_ev = _finite_float(getattr(mapping, "profile_hdr_softness_ev", None), 3.0)
    strength = _finite_float(getattr(mapping, "profile_hdr_strength", None), 0.65)
    slope_full = _finite_float(getattr(mapping, "profile_hdr_slope_full", None), 0.75)
    slope_zero = _finite_float(getattr(mapping, "profile_hdr_slope_zero", None), 0.12)
    clip_softness = _finite_float(getattr(mapping, "profile_hdr_soft_clip_softness", None), 0.45)

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
