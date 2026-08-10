from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

try:
    from spektrafilm.utils.spectral_reflectance import (
        compute_reflectance_tc_lut,
        rgb_to_raw_reflectance,
    )
except ModuleNotFoundError:
    from spektrafilm.utils.spectral_upsampling import (  # type: ignore[attr-defined]
        compute_reflectance_tc_lut,
        rgb_to_raw_reflectance,
    )

from spektrafilm.utils.spectral_upsampling import rgb_to_raw_mallett2019


REFLECTANCE_METHODS = (
    "arctic2026beta04",
    "jakob2019",
    "otsu2018",
    "gauss-lasers",
)
REFERENCE_ILLUMINANTS = ("D55", "D65", "A")
COLOR_CASES = (
    ("srgb_linear", "sRGB", False),
    ("srgb_encoded", "sRGB", True),
    ("bt2020_linear", "ITU-R BT.2020", False),
    ("prophoto_linear", "ProPhoto RGB", False),
)


def _sensitivity() -> np.ndarray:
    w = np.linspace(0.0, 1.0, 81, dtype=np.float64)
    return np.stack(
        (
            0.35 + 0.9 * w + 0.08 * np.sin(3.0 * np.pi * w),
            0.72 + 0.18 * np.cos(2.0 * np.pi * w),
            1.18 - 0.52 * w + 0.06 * np.sin(5.0 * np.pi * w),
        ),
        axis=-1,
    )


def _rgb_fixture() -> np.ndarray:
    # Mix ordinary colors, memory-color-like samples, high saturation, OOG,
    # negative values, and >1 values. Shape is image-like so the production
    # RGB->raw functions exercise their normal broadcasting path.
    rows = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.018, 0.018, 0.018],
            [0.184, 0.184, 0.184],
            [0.5, 0.5, 0.5],
            [1.0, 1.0, 1.0],
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
            [1.0, 1.0, 0.0],
            [0.0, 1.0, 1.0],
            [1.0, 0.0, 1.0],
            [0.72, 0.42, 0.31],  # warm skin-like
            [0.18, 0.48, 0.13],  # foliage-like
            [0.10, 0.26, 0.70],
            [1.25, 0.18, 0.03],
            [0.05, 1.35, 0.08],
            [-0.08, 0.22, 0.95],
            [1.60, -0.12, 0.35],
            [2.00, 2.00, 2.00],
            [3.00, 0.02, 1.40],
        ],
        dtype=np.float64,
    )
    return rows.reshape(4, 5, 3)


def _maybe_compute_mallett_lut(
    outputs: dict[str, np.ndarray],
    sensitivity: np.ndarray,
    rgb: np.ndarray,
) -> None:
    # Current upstream experimental ships Mallett as a reflectance tc LUT.
    # Our branch intentionally retains the older direct/GPU Mallett path, so
    # this probe records the LUT form only where the descriptor is available.
    for ref in REFERENCE_ILLUMINANTS:
        try:
            tc_lut = compute_reflectance_tc_lut("mallett2019", sensitivity, ref)
        except (KeyError, ValueError, FileNotFoundError):
            return
        outputs[f"mallett_lut__{ref}__tc_lut"] = tc_lut
        for case_name, color_space, decode in COLOR_CASES:
            outputs[f"mallett_lut__{ref}__{case_name}"] = rgb_to_raw_reflectance(
                "mallett2019",
                rgb,
                sensitivity,
                color_space=color_space,
                apply_cctf_decoding=decode,
                reference_illuminant=ref,
                tc_lut=tc_lut,
            )


def run_probe(output: Path) -> None:
    sensitivity = _sensitivity()
    rgb = _rgb_fixture()
    outputs: dict[str, np.ndarray] = {
        "fixture__sensitivity": sensitivity,
        "fixture__rgb": rgb,
    }

    for method in REFLECTANCE_METHODS:
        for ref in REFERENCE_ILLUMINANTS:
            tc_lut = compute_reflectance_tc_lut(method, sensitivity, ref)
            outputs[f"{method}__{ref}__tc_lut"] = tc_lut
            for case_name, color_space, decode in COLOR_CASES:
                outputs[f"{method}__{ref}__{case_name}"] = rgb_to_raw_reflectance(
                    method,
                    rgb,
                    sensitivity,
                    color_space=color_space,
                    apply_cctf_decoding=decode,
                    reference_illuminant=ref,
                    tc_lut=tc_lut,
                )

    for ref in REFERENCE_ILLUMINANTS:
        for case_name, color_space, decode in COLOR_CASES:
            outputs[f"mallett_direct__{ref}__{case_name}"] = rgb_to_raw_mallett2019(
                rgb,
                sensitivity,
                color_space=color_space,
                apply_cctf_decoding=decode,
                reference_illuminant=ref,
            )

    _maybe_compute_mallett_lut(outputs, sensitivity, rgb)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output, **outputs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run_probe(args.output)


if __name__ == "__main__":
    main()
