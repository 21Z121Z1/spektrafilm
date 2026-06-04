#!/usr/bin/env python3
"""Research-only probes for natural scene HDR film simulation.

This script intentionally does not change production rendering.  It builds tiny
synthetic scene-linear arrays and compares a minimal content-derived HDR model
with a small profile-shaped proxy based on Spektrafilm's current
``profile_aware`` / ``modern_recovery_peak_budget`` equations.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np


EPS = np.float32(1e-8)


@dataclass(slots=True)
class ExperimentResult:
    name: str
    natural_headroom: float
    current_headroom: float | None
    scene_highlight_alignment: float
    verdict: str
    notes: list[str]


@dataclass(slots=True)
class SyntheticCurveProfile:
    name: str
    scene_y: np.ndarray
    sdr_luminance_y: np.ndarray
    look_diffuse_white_y: float
    safe_max_headroom: float = 8.0


def luminance_y(rgb: np.ndarray) -> np.ndarray:
    coeffs = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    return np.tensordot(np.asarray(rgb, dtype=np.float32)[..., :3], coeffs, axes=([-1], [0]))


def synthetic_scene(values: np.ndarray, *, color: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    scene_y = np.asarray(values, dtype=np.float32)
    chroma = np.asarray(color, dtype=np.float32)
    chroma = chroma / max(float(np.dot(chroma, np.array([0.2126, 0.7152, 0.0722], dtype=np.float32))), 1e-8)
    return scene_y[..., None] * chroma


def simple_film_exposure_response(scene_rgb: np.ndarray, *, exposure_ev: float = 0.0) -> np.ndarray:
    """Small film-like response in exposure/log domain.

    It is not a production film model.  It is only a monotonic shoulder/toe
    probe that lets the experiments test where HDR energy originates.
    """

    scene = np.maximum(np.asarray(scene_rgb, dtype=np.float32) * np.float32(2.0**exposure_ev), 0.0)
    log_e = np.log2(scene + EPS)
    toe = 1.0 / (1.0 + np.exp(-(log_e + 3.0) * 1.1))
    shoulder = 1.0 / (1.0 + np.exp((log_e - 3.5) * 0.45))
    density_like = toe * shoulder
    return np.clip(density_like, 0.0, None).astype(np.float32)


def natural_scene_hdr_pair(
    scene_rgb: np.ndarray,
    *,
    diffuse_white: float = 1.0,
    output_peak: float = 8.0,
    exposure_ev: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, float]:
    """Return SDR/HDR renditions where HDR only comes from scene values above diffuse white."""

    if diffuse_white <= 0.0 or not math.isfinite(diffuse_white):
        raise ValueError("diffuse_white must be finite and positive")
    scene = np.maximum(np.asarray(scene_rgb, dtype=np.float32) / np.float32(diffuse_white), 0.0)
    film_rgb = simple_film_exposure_response(scene, exposure_ev=exposure_ev)
    scene_y = luminance_y(scene)

    base_y = np.maximum(luminance_y(film_rgb), EPS)
    sdr_y = np.minimum(base_y / np.float32(max(float(np.percentile(base_y, 99.0)), 1e-6)), 1.0)
    sdr_rgb = np.clip(film_rgb * (sdr_y / base_y)[..., None], 0.0, 1.0)

    highlight_ratio = np.maximum(scene_y - 1.0, 0.0) / np.maximum(scene_y, EPS)
    hdr_y = sdr_y + highlight_ratio * np.minimum(scene_y, output_peak)
    hdr_rgb = film_rgb * (hdr_y / base_y)[..., None]
    hdr_rgb = np.clip(hdr_rgb, 0.0, output_peak).astype(np.float32)
    headroom = float(max(np.percentile(np.max(hdr_rgb, axis=-1), 99.9), 1.0))
    return sdr_rgb.astype(np.float32), hdr_rgb, headroom


def smoothstep(edge0: float, edge1: float, x: np.ndarray) -> np.ndarray:
    if edge0 == edge1:
        return (x >= edge1).astype(np.float32)
    t = np.clip((x - np.float32(edge0)) / np.float32(edge1 - edge0), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def profile_slope_loglog(scene_y: np.ndarray, s_profile: np.ndarray) -> np.ndarray:
    scene = np.maximum(np.asarray(scene_y, dtype=np.float32), EPS)
    sdr = np.maximum(np.asarray(s_profile, dtype=np.float32), EPS)
    flat_scene = scene.reshape(-1)
    flat_sdr = sdr.reshape(-1)
    order = np.argsort(flat_scene)
    sorted_scene = np.log2(flat_scene[order])
    sorted_sdr = np.log2(flat_sdr[order])
    slope = np.gradient(sorted_sdr, sorted_scene, edge_order=1).astype(np.float32)
    inv = np.empty_like(order)
    inv[order] = np.arange(order.size)
    return np.clip(slope[inv].reshape(scene.shape), 0.0, 4.0).astype(np.float32)


def synthetic_profile(name: str, shoulder: float) -> SyntheticCurveProfile:
    scene_y = np.array([0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    sdr_y = np.array([0.045, 0.090, 0.46, 0.83, 0.92, 0.97, 1.02, 1.06], dtype=np.float32)
    sdr_y = np.where(scene_y > 1.0, 0.83 + (sdr_y - 0.83) * np.float32(shoulder), sdr_y)
    return SyntheticCurveProfile(
        name=name,
        scene_y=scene_y,
        sdr_luminance_y=sdr_y,
        look_diffuse_white_y=0.83,
    )


def profile_aware_headroom(scene_y: np.ndarray, *, shoulder: float, mode: str = "strict_preserving") -> float | None:
    profile = synthetic_profile(f"research_shoulder_{shoulder:.2f}", shoulder)
    scene = np.maximum(np.asarray(scene_y, dtype=np.float32), EPS)
    s_profile = np.interp(scene.reshape(-1), profile.scene_y, profile.sdr_luminance_y).reshape(scene.shape).astype(np.float32)
    if float(np.max(scene)) <= 1.0:
        return None

    scene_ev = np.log2(scene)
    slope = profile_slope_loglog(scene, s_profile)
    if mode == "modern_recovery_peak_budget":
        profile_ev = np.log2(np.maximum(s_profile, EPS) / np.float32(profile.look_diffuse_white_y))
        compressed_ev = np.maximum(scene_ev - profile_ev, 0.0)
        highlight_w = smoothstep(0.10, 1.10, scene_ev)
        shoulder_w = 1.0 - smoothstep(0.18, 0.90, slope)
        gain_ev = 0.50 * highlight_w * shoulder_w * compressed_ev
        h_ev = profile_ev + gain_ev
        peak = float(np.percentile(h_ev, 100.0))
        if peak > 2.03:
            gain_ev = np.maximum(gain_ev - np.float32(peak - 2.03), 0.0)
    else:
        scene_excess = np.maximum(scene_ev - 0.35, 0.0)
        scene_excess = scene_excess / (scene_excess + np.float32(3.0))
        shoulder_capacity = 1.0 - smoothstep(0.12, 0.75, slope)
        gain_ev = 1.5 * scene_excess * shoulder_capacity * 0.65

    h_profile = s_profile * np.exp2(gain_ev)
    hdr_gain = h_profile / np.maximum(s_profile, EPS)
    headroom = min(
        max(float(np.percentile(h_profile, 100.0)), float(np.percentile(hdr_gain, 100.0))),
        profile.safe_max_headroom,
    )
    return headroom if headroom >= 1.01 else None


def alignment_score(scene_y: np.ndarray, hdr_rgb: np.ndarray) -> float:
    scene_hot = scene_y > 1.0
    hdr_gain = np.maximum(np.max(hdr_rgb, axis=-1) - 1.0, 0.0)
    if not np.any(hdr_gain > 1e-6):
        return 1.0 if not np.any(scene_hot) else 0.0
    return float(np.sum(hdr_gain[scene_hot]) / max(float(np.sum(hdr_gain)), 1e-8))


def run_experiments() -> dict[str, Any]:
    results: list[ExperimentResult] = []

    low_scene_y = np.array([[0.18, 0.35, 0.60, 0.90]], dtype=np.float32)
    low_scene = synthetic_scene(low_scene_y)
    _sdr, hdr, natural_headroom = natural_scene_hdr_pair(low_scene)
    current = profile_aware_headroom(low_scene_y, shoulder=0.25)
    results.append(
        ExperimentResult(
            name="A_no_true_hdr_content",
            natural_headroom=natural_headroom,
            current_headroom=current,
            scene_highlight_alignment=alignment_score(low_scene_y, hdr),
            verdict="pass",
            notes=[
                "Natural path keeps headroom at 1.0 when scene_luminance <= diffuse white.",
                "Any mode that emits >1.0 here should be labeled authored/synthetic.",
            ],
        )
    )

    high_scene_y = np.array([[0.18, 0.75, 1.0, 2.0, 4.0, 8.0]], dtype=np.float32)
    high_scene = synthetic_scene(high_scene_y)
    _sdr, hdr, natural_headroom = natural_scene_hdr_pair(high_scene)
    current = profile_aware_headroom(high_scene_y, shoulder=0.25)
    results.append(
        ExperimentResult(
            name="B_real_highlight_content",
            natural_headroom=natural_headroom,
            current_headroom=current,
            scene_highlight_alignment=alignment_score(high_scene_y, hdr),
            verdict="pass" if alignment_score(high_scene_y, hdr) > 0.95 else "inspect",
            notes=["Natural HDR energy is spatially aligned with scene values above diffuse white."],
        )
    )

    profile_low = profile_aware_headroom(high_scene_y, shoulder=0.15)
    profile_high = profile_aware_headroom(high_scene_y, shoulder=0.85)
    results.append(
        ExperimentResult(
            name="C_same_content_different_profiles",
            natural_headroom=natural_headroom,
            current_headroom=None if profile_low is None or profile_high is None else abs(profile_low - profile_high),
            scene_highlight_alignment=alignment_score(high_scene_y, hdr),
            verdict="authored_if_large_delta",
            notes=[
                f"profile-shaped headroom delta={None if profile_low is None or profile_high is None else round(abs(profile_low - profile_high), 4)}",
                "Natural HDR distribution should be primarily content driven; profile changes may alter film rendering, not invent highlight locations.",
            ],
        )
    )

    modern_low = profile_aware_headroom(low_scene_y, shoulder=0.25, mode="modern_recovery_peak_budget")
    modern_high = profile_aware_headroom(high_scene_y, shoulder=0.25, mode="modern_recovery_peak_budget")
    results.append(
        ExperimentResult(
            name="D_same_profile_different_content",
            natural_headroom=natural_headroom,
            current_headroom=modern_high,
            scene_highlight_alignment=alignment_score(high_scene_y, hdr),
            verdict="inspect_budget_cap",
            notes=[
                f"modern low-dynamic headroom={modern_low}",
                f"modern high-dynamic headroom={modern_high}",
                "If different scenes collapse toward the same target EV, the mode is budgeted creative recovery.",
            ],
        )
    )

    _sdr_normal, _hdr_normal, headroom_normal = natural_scene_hdr_pair(high_scene, exposure_ev=0.0)
    _sdr_print, _hdr_print, headroom_print = natural_scene_hdr_pair(high_scene, exposure_ev=-1.0)
    results.append(
        ExperimentResult(
            name="E_exposure_print_exposure_adjustment",
            natural_headroom=headroom_print,
            current_headroom=headroom_normal,
            scene_highlight_alignment=1.0,
            verdict="diffuse_anchor_unchanged",
            notes=[
                "Changing exposure/render intent changes the rendition but does not redefine physical diffuse white.",
                "Current hdr_render_ev should be treated as creative rendering, not as scene energy.",
            ],
        )
    )

    color_scene_y = np.array([[1.0, 4.0, 4.0]], dtype=np.float32)
    red_scene = synthetic_scene(color_scene_y, color=(4.0, 0.4, 0.2))
    _sdr_color, hdr_color, color_headroom = natural_scene_hdr_pair(red_scene)
    results.append(
        ExperimentResult(
            name="F_colored_highlights",
            natural_headroom=color_headroom,
            current_headroom=None,
            scene_highlight_alignment=alignment_score(color_scene_y, hdr_color),
            verdict="separate_content_from_output_rendering",
            notes=[
                "Scene chromaticity, film dye response, path-to-white, and gamut compression are separate decisions.",
                "source_chroma and bounded_look_chroma should be documented as output/rendering controls unless scene_rgb is validated.",
            ],
        )
    )

    _sdr_dw1, _hdr_dw1, headroom_dw1 = natural_scene_hdr_pair(high_scene, diffuse_white=1.0)
    _sdr_dw2, _hdr_dw2, headroom_dw2 = natural_scene_hdr_pair(high_scene, diffuse_white=2.0)
    results.append(
        ExperimentResult(
            name="G_diffuse_white_anchor",
            natural_headroom=headroom_dw2,
            current_headroom=headroom_dw1,
            scene_highlight_alignment=alignment_score(high_scene_y / 2.0, _hdr_dw2),
            verdict="anchor_changes_headroom",
            notes=[
                f"headroom diffuse_white=1.0: {headroom_dw1:.4f}",
                f"headroom diffuse_white=2.0: {headroom_dw2:.4f}",
                "The anchor must be explicit or tagged heuristic; DNG WhiteLevel is not this anchor.",
            ],
        )
    )

    return {
        "summary": {
            "model": "research_only_minimal_scene_hdr_film_probe",
            "natural_hdr_rule": "HDR headroom is emitted only from scene luminance above diffuse white.",
            "production_code_changed": False,
        },
        "experiments": [asdict(result) for result in results],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()

    payload = run_experiments()
    if args.format == "json":
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print("# Natural HDR Film Simulation Research Probe")
    print()
    print(f"- Model: `{payload['summary']['model']}`")
    print(f"- Rule: {payload['summary']['natural_hdr_rule']}")
    print(f"- Production code changed: {payload['summary']['production_code_changed']}")
    print()
    print("| Experiment | Natural headroom | Current/probe headroom | Alignment | Verdict | Notes |")
    print("| --- | ---: | ---: | ---: | --- | --- |")
    for result in payload["experiments"]:
        current = "n/a" if result["current_headroom"] is None else f"{result['current_headroom']:.4f}"
        notes = " ".join(result["notes"])
        print(
            f"| {result['name']} | {result['natural_headroom']:.4f} | {current} | "
            f"{result['scene_highlight_alignment']:.4f} | {result['verdict']} | {notes} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
