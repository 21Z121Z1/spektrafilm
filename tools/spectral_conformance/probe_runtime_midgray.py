from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline


METHODS = (
    "hanatos2025",
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
    "mallett2019",
)
REFLECTANCE_METHODS = (
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
)
LEVELS = (0.018, 0.184, 0.5, 1.0)
MIDGRAY_TOLERANCE = 5e-4


def _raw_for(method: str, level: float) -> np.ndarray:
    params = init_params(
        film_profile="kodak_portra_400",
        print_profile="kodak_portra_endura",
    )
    params.settings.rgb_to_raw_method = method
    params.settings.compute_backend = "cpu"
    params.camera.auto_exposure = False
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params = digest_params(params)
    pipeline = SimulationPipeline(params)
    rgb = np.full((1, 1, 3), level, dtype=np.float64)
    raw = pipeline._filming_stage._rgb_to_film_raw(
        rgb,
        color_space="sRGB",
        apply_cctf_decoding=False,
        use_backend=False,
    )
    return np.asarray(raw, dtype=np.float64)[0, 0]


def build_report() -> dict:
    methods = {}
    for method in METHODS:
        levels = {}
        for level in LEVELS:
            raw = _raw_for(method, level)
            levels[f"{level:.3f}"] = raw.tolist()
        midgray = np.asarray(levels["0.184"], dtype=np.float64)
        methods[method] = {
            "levels": levels,
            "midgray_raw": midgray.tolist(),
            "midgray_log10": np.log10(np.maximum(midgray, 1e-30)).tolist(),
            "midgray_ev_vs_raw1": np.log2(np.maximum(midgray, 1e-30)).tolist(),
            "midgray_max_abs_error_from_raw1": float(np.max(np.abs(midgray - 1.0))),
        }

    hanatos_mid = np.asarray(methods["hanatos2025"]["midgray_raw"], dtype=np.float64)
    for method, data in methods.items():
        midgray = np.asarray(data["midgray_raw"], dtype=np.float64)
        data["midgray_ev_vs_hanatos"] = np.log2(
            np.maximum(midgray, 1e-30) / np.maximum(hanatos_mid, 1e-30)
        ).tolist()

    failures = [
        method
        for method in REFLECTANCE_METHODS
        if methods[method]["midgray_max_abs_error_from_raw1"] > MIDGRAY_TOLERANCE
    ]
    return {
        "schema": "spektrafilm.spectral_runtime_midgray.v2",
        "status": "failed" if failures else "ok",
        "film": "kodak_portra_400",
        "print": "kodak_portra_endura",
        "input": "linear sRGB neutral",
        "auto_exposure": False,
        "reflectance_midgray_tolerance": MIDGRAY_TOLERANCE,
        "failed_reflectance_methods": failures,
        "methods": methods,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = build_report()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["status"] != "ok":
        raise SystemExit(
            "reflectance midgray exposure contract failed for: "
            + ", ".join(report["failed_reflectance_methods"])
        )


if __name__ == "__main__":
    main()
