#!/usr/bin/env python3
"""Independent graph-based validation for Velvia 100 profile candidates.

Avian Rochester publicly identifies the MicroCalT24 transmissive microscope
target as Fujifilm Velvia 100 and publishes nominal 400--700 nm transmittance
graphs for 18 chromatic and 6 neutral patches.  No machine-readable matrix,
instrument record, processing record, patch-to-curve legend, or derivative
licence is published.  This script therefore uses the graphs only as an
independent, validation-only stress test.  It never emits a profile and never
modifies bundled arrays.

The chromatic PNG contains 18 exact solid line colours.  At each 5 nm graph
coordinate the script samples only visible pixels of that exact colour; hidden
or overwritten line segments remain missing and are never filled.  The highest
neutral dotted curve is sampled as one same-target effective-white reference,
then three deliberately non-physical common-reference sensitivities test
whether the ranking depends on that interpretation.  None is labelled GS0,
base-plus-fog, or an analytical Dmin measurement.
"""

from __future__ import annotations

import argparse
import hashlib
from http.client import IncompleteRead
import itertools
import json
from pathlib import Path
import platform
import sys
from typing import Any
from urllib.request import Request, urlopen

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
import scipy
from scipy.optimize import nnls
from scipy.stats import binomtest


ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = (
    ROOT / "src/spektrafilm/data/profiles/fujifilm_velvia_100.json"
)
PUBLIC_MANIFEST = (
    ROOT / "tmp/profile-public-batch-candidates/CURRENT_CANDIDATES.json"
)
FUJI_REPORT = (
    ROOT / "tmp/profile-source-curves/fuji/fuji_source_curve_digitization.json"
)
DEFAULT_SOURCE_DIR = ROOT / "tmp/profile-velvia-microcal/sources"
DEFAULT_OUTPUT_DIR = ROOT / "tmp/profile-velvia-microcal/results"

SOURCE_PAGE_URL = "https://www.avianrochester.com/microcal24t/"
SOURCE_SPECS = {
    "brochure": {
        "filename": "MicroCalT24.pdf",
        "url": (
            "https://www.avianrochester.com/images/MicroCalT24/"
            "MicroCalT24.pdf"
        ),
        "sha256": (
            "0df3908acafe06535b229f17aae0455ad4259ded9d2d135b272d3f31575e70f2"
        ),
    },
    "chromatic_graph": {
        "filename": "chromaticT.png",
        "url": (
            "https://www.avianrochester.com/images/MicroCalT24/"
            "chromaticT.png"
        ),
        "sha256": (
            "74fde88bebb1afdf6eb814e1e9df4f427b5ff48a686e769a7c32ba2b62a093c7"
        ),
    },
    "neutral_graph": {
        "filename": "neutralT.png",
        "url": (
            "https://www.avianrochester.com/images/MicroCalT24/"
            "neutralT.png"
        ),
        "sha256": (
            "17e55ce30d87460cbee84fea829c54d18d478691a119b89f9e08b87a2a6767f4"
        ),
    },
}

WAVELENGTHS_NM = np.arange(400.0, 701.0, 5.0)
PRIMARY_AXIS = {
    "x_left_px": 180.0,
    "x_right_px": 963.0,
    "y_top_px": 33.5,
    "y_bottom_px": 467.0,
    "x_window_px": 3,
}
AXIS_VARIANTS = tuple(
    {
        "x_left_px": x_left,
        "x_right_px": x_right,
        "y_top_px": y_top,
        "y_bottom_px": y_bottom,
        "x_window_px": x_window,
    }
    for x_left, x_right, y_top, y_bottom, x_window in itertools.product(
        (179.5, 180.0, 180.5),
        (962.5, 963.0, 963.5),
        (33.0, 33.5, 34.0),
        (466.5, 467.0, 467.5),
        (2, 3, 4),
    )
)
TRANSMITTANCE_FLOOR = 0.02
REFERENCE_POLICY_ORDER = (
    "highest_neutral_all_joint_valid",
    "highest_neutral_nonnegative_relative_density_only",
    "maximum_transmittance_envelope",
    "common_zero_density",
)
RELATIVE_DENSITY_TOLERANCE_D = 1e-12


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ensure_source(
    spec: dict[str, str],
    source_dir: Path,
    download_missing: bool,
) -> Path:
    path = source_dir / spec["filename"]
    if not path.exists():
        if not download_missing:
            raise FileNotFoundError(
                f"Missing {path}; rerun with --download-missing"
            )
        source_dir.mkdir(parents=True, exist_ok=True)
        payload = None
        last_error: Exception | None = None
        for _ in range(3):
            request = Request(
                spec["url"],
                headers={
                    "User-Agent": "Spektrafilm closed-evidence audit",
                    "Accept-Encoding": "identity",
                    "Connection": "close",
                },
            )
            try:
                with urlopen(request, timeout=60) as response:  # noqa: S310
                    payload = response.read()
                break
            except (IncompleteRead, OSError) as error:
                last_error = error
        if payload is None:
            raise RuntimeError(
                f"Could not download {spec['url']} after three attempts"
            ) from last_error
        path.write_bytes(payload)
    observed = _sha256(path)
    if observed != spec["sha256"]:
        raise ValueError(
            f"Source hash mismatch for {path}: {observed} != {spec['sha256']}"
        )
    return path


def _load_rgb(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.uint8)


def _discover_chromatic_colours(image: np.ndarray) -> list[tuple[int, int, int]]:
    crop = image[20:480, 160:980]
    saturation = crop.max(axis=2) - crop.min(axis=2)
    selected = crop[saturation > 40]
    colours, counts = np.unique(
        selected.reshape(-1, 3), axis=0, return_counts=True
    )
    records = [
        (int(count), tuple(int(value) for value in colour))
        for colour, count in zip(colours, counts, strict=True)
        if count > 200
    ]
    records.sort(reverse=True)
    if len(records) != 18:
        raise ValueError(
            f"Expected 18 exact chromatic line colours, found {len(records)}"
        )
    return [colour for _, colour in records]


def _sample_visible_curve(
    mask: np.ndarray,
    axis: dict[str, float | int],
    *,
    y_min_px: int,
    y_max_px: int,
    excluded_rows: tuple[tuple[int, int], ...] = (),
) -> tuple[np.ndarray, np.ndarray]:
    y_pixels: list[float] = []
    x_window = int(axis["x_window_px"])
    for wavelength in WAVELENGTHS_NM:
        x = float(axis["x_left_px"]) + (wavelength - 400.0) * (
            float(axis["x_right_px"]) - float(axis["x_left_px"])
        ) / 300.0
        x_index = int(round(x))
        x_start = max(0, x_index - x_window)
        x_stop = min(mask.shape[1], x_index + x_window + 1)
        rows, _ = np.where(mask[:, x_start:x_stop])
        rows = rows[(rows >= y_min_px) & (rows <= y_max_px)]
        for excluded_row, tolerance in excluded_rows:
            rows = rows[np.abs(rows - excluded_row) > tolerance]
        y_pixels.append(float(np.median(rows)) if rows.size else np.nan)

    y_pixels_array = np.asarray(y_pixels, dtype=float)
    transmittance = (
        float(axis["y_bottom_px"]) - y_pixels_array
    ) / (float(axis["y_bottom_px"]) - float(axis["y_top_px"]))
    return transmittance, y_pixels_array


def _extract_graphs(
    chromatic_image: np.ndarray,
    neutral_image: np.ndarray,
    axis: dict[str, float | int],
    colours: list[tuple[int, int, int]],
) -> dict[str, Any]:
    chromatic_curves = []
    chromatic_y_pixels = []
    for colour in colours:
        mask = np.all(chromatic_image == colour, axis=2)
        curve, y_pixels = _sample_visible_curve(
            mask,
            axis,
            y_min_px=30,
            y_max_px=470,
        )
        chromatic_curves.append(curve)
        chromatic_y_pixels.append(y_pixels)

    black_mask = np.all(neutral_image == 0, axis=2)
    neutral_white, neutral_y_pixels = _sample_visible_curve(
        black_mask,
        axis,
        y_min_px=70,
        y_max_px=230,
        excluded_rows=((120, 4), (207, 4)),
    )
    # The 400 nm dotted marker is hidden by the black y-axis, so the vertical
    # axis would otherwise be mistaken for source data.
    neutral_white[0] = np.nan
    neutral_y_pixels[0] = np.nan

    chromatic = np.asarray(chromatic_curves, dtype=float)
    y_pixels = np.asarray(chromatic_y_pixels, dtype=float)
    finite = np.isfinite(chromatic)
    if finite.sum() < 900:
        raise ValueError("Insufficient visible chromatic graph support")
    if np.nanmin(chromatic) < 0.0 or np.nanmax(chromatic) > 1.02:
        raise ValueError("Extracted chromatic transmittance is out of range")
    if np.nanmin(neutral_white) < 0.0 or np.nanmax(neutral_white) > 1.02:
        raise ValueError("Extracted neutral transmittance is out of range")
    return {
        "chromatic_transmittance": chromatic,
        "chromatic_y_pixels": y_pixels,
        "neutral_white_transmittance": neutral_white,
        "neutral_white_y_pixels": neutral_y_pixels,
    }


def _profile_grid_indices(payload: dict[str, Any]) -> np.ndarray:
    wavelengths = np.asarray(payload["data"]["wavelengths"], dtype=float)
    indices = []
    for wavelength in WAVELENGTHS_NM:
        matches = np.flatnonzero(np.isclose(wavelengths, wavelength))
        if matches.size != 1:
            raise ValueError(f"Profile grid does not contain {wavelength} nm")
        indices.append(int(matches[0]))
    return np.asarray(indices, dtype=int)


def _load_profile(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_from_manifest(kind: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = json.loads(PUBLIC_MANIFEST.read_text(encoding="utf-8"))
    matches = [
        entry
        for entry in manifest["authoritative_for_this_run"]
        if entry["profile"] == "fujifilm_velvia_100"
        and entry["candidate_kind"] == kind
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one Velvia {kind} candidate")
    entry = matches[0]
    path = Path(entry["output"]["path"])
    if _sha256(path) != entry["output"]["sha256"]:
        raise ValueError(f"Candidate hash mismatch: {path}")
    return _load_profile(path), entry


def _load_models() -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    bundled = _load_profile(PROFILE_PATH)
    base_candidate, base_entry = _candidate_from_manifest("base_density")
    effective_candidate, effective_entry = _candidate_from_manifest(
        "effective_basis"
    )
    fuji_report = json.loads(FUJI_REPORT.read_text(encoding="utf-8"))
    primary = fuji_report["stocks"]["velvia_100"]["primary_normalized"]

    bundled_indices = _profile_grid_indices(bundled)
    base_indices = _profile_grid_indices(base_candidate)
    effective_indices = _profile_grid_indices(effective_candidate)
    bundled_basis = np.asarray(
        bundled["data"]["channel_density"], dtype=object
    )[bundled_indices].astype(float)
    manufacturer_basis = np.column_stack(
        [np.asarray(primary[channel], dtype=float) for channel in ("C", "M", "Y")]
    ) * np.max(bundled_basis, axis=0)

    models = {
        "bundled": {
            "base": np.asarray(bundled["data"]["base_density"], dtype=object)[
                bundled_indices
            ].astype(float),
            "basis": bundled_basis,
            "semantics": "bundled processed profile",
        },
        "public_grouped_base": {
            "base": np.asarray(
                base_candidate["data"]["base_density"], dtype=object
            )[base_indices].astype(float),
            "basis": bundled_basis,
            "semantics": "ColorReference grouped GS0 effective base; bundled basis",
        },
        "public_effective_basis": {
            "base": np.asarray(
                effective_candidate["data"]["base_density"], dtype=object
            )[effective_indices].astype(float),
            "basis": np.asarray(
                effective_candidate["data"]["channel_density"], dtype=object
            )[effective_indices].astype(float),
            "semantics": "ColorReference grouped base plus effective rank-3 basis",
        },
        "manufacturer_primary_basis": {
            "base": np.asarray(
                base_candidate["data"]["base_density"], dtype=object
            )[base_indices].astype(float),
            "basis": manufacturer_basis,
            "semantics": "ColorReference grouped base plus AF3-202E normalized basis",
        },
    }
    context = {
        "bundled_profile_sha256": _sha256(PROFILE_PATH),
        "public_manifest_sha256": _sha256(PUBLIC_MANIFEST),
        "fuji_report_sha256": _sha256(FUJI_REPORT),
        "public_grouped_base_candidate": base_entry,
        "public_effective_basis_candidate": effective_entry,
    }
    return models, context


def _fit_curve(
    patch_transmittance: np.ndarray,
    base_density: np.ndarray,
    basis: np.ndarray,
    *,
    neutral_transmittance: np.ndarray | None = None,
    exclude_negative_relative_density: bool = False,
) -> dict[str, Any]:
    valid = (
        np.isfinite(patch_transmittance)
        & (patch_transmittance >= TRANSMITTANCE_FLOOR)
        & (patch_transmittance <= 1.0)
    )
    joint_visible_point_count = int(valid.sum())
    negative_relative_density = np.zeros_like(valid, dtype=bool)
    if neutral_transmittance is not None:
        valid &= (
            np.isfinite(neutral_transmittance)
            & (neutral_transmittance >= TRANSMITTANCE_FLOOR)
            & (neutral_transmittance <= 1.0)
        )
        joint_visible_point_count = int(valid.sum())
        relative_density = np.full_like(patch_transmittance, np.nan, dtype=float)
        relative_density[valid] = np.log10(
            neutral_transmittance[valid] / patch_transmittance[valid]
        )
        negative_relative_density = valid & (
            relative_density < -RELATIVE_DENSITY_TOLERANCE_D
        )
        if exclude_negative_relative_density:
            valid &= ~negative_relative_density
        base = -np.log10(neutral_transmittance[valid])
    else:
        if exclude_negative_relative_density:
            raise ValueError(
                "Negative-relative-density exclusion requires a common "
                "reference transmittance"
            )
        base = base_density[valid]
    if int(valid.sum()) < 25:
        raise ValueError("Insufficient visible points for NNLS reconstruction")
    observed_density = -np.log10(patch_transmittance[valid])
    coefficients = nnls(basis[valid], observed_density - base)[0]
    predicted_density = base + basis[valid] @ coefficients
    predicted_transmittance = np.power(10.0, -predicted_density)
    density_error = predicted_density - observed_density
    transmittance_error = predicted_transmittance - patch_transmittance[valid]
    return {
        "density_error": density_error,
        "transmittance_error": transmittance_error,
        "density_rmse_D": float(np.sqrt(np.mean(np.square(density_error)))),
        "transmittance_rmse_percentage_points": float(
            np.sqrt(np.mean(np.square(transmittance_error))) * 100.0
        ),
        "visible_point_count": int(valid.sum()),
        "joint_visible_point_count_before_policy_exclusion": (
            joint_visible_point_count
        ),
        "negative_relative_density_point_count": int(
            negative_relative_density.sum()
        ),
        "excluded_negative_relative_density_point_count": int(
            negative_relative_density.sum()
            if exclude_negative_relative_density
            else 0
        ),
    }


def _evaluate_model(
    chromatic: np.ndarray,
    model: dict[str, Any],
    *,
    neutral_transmittance: np.ndarray | None = None,
    exclude_negative_relative_density: bool = False,
) -> dict[str, Any]:
    curve_results = [
        _fit_curve(
            curve,
            model["base"],
            model["basis"],
            neutral_transmittance=neutral_transmittance,
            exclude_negative_relative_density=(
                exclude_negative_relative_density
            ),
        )
        for curve in chromatic
    ]
    density_errors = np.concatenate(
        [result["density_error"] for result in curve_results]
    )
    transmittance_errors = np.concatenate(
        [result["transmittance_error"] for result in curve_results]
    )
    return {
        "micro": {
            "density_rmse_D": float(
                np.sqrt(np.mean(np.square(density_errors)))
            ),
            "transmittance_rmse_percentage_points": float(
                np.sqrt(np.mean(np.square(transmittance_errors))) * 100.0
            ),
        },
        "curve_macro_median": {
            metric: float(np.median([result[metric] for result in curve_results]))
            for metric in (
                "density_rmse_D",
                "transmittance_rmse_percentage_points",
            )
        },
        "curve_macro_mean": {
            metric: float(np.mean([result[metric] for result in curve_results]))
            for metric in (
                "density_rmse_D",
                "transmittance_rmse_percentage_points",
            )
        },
        "support_qa": {
            key: int(sum(result[key] for result in curve_results))
            for key in (
                "joint_visible_point_count_before_policy_exclusion",
                "visible_point_count",
                "negative_relative_density_point_count",
                "excluded_negative_relative_density_point_count",
            )
        }
        | {
            "curve_count_with_negative_relative_density": int(
                sum(
                    result["negative_relative_density_point_count"] > 0
                    for result in curve_results
                )
            )
        },
        "per_curve": [
            {
                key: value
                for key, value in result.items()
                if key not in {"density_error", "transmittance_error"}
            }
            for result in curve_results
        ],
    }


def _reference_policies(extracted: dict[str, Any]) -> dict[str, dict[str, Any]]:
    chromatic = extracted["chromatic_transmittance"]
    highest_neutral = extracted["neutral_white_transmittance"]
    stacked = np.vstack((highest_neutral[np.newaxis, :], chromatic))
    envelope_source_valid = (
        np.isfinite(stacked)
        & (stacked >= TRANSMITTANCE_FLOOR)
        & (stacked <= 1.0)
    )
    envelope_support_count = envelope_source_valid.sum(axis=0).astype(int)
    envelope = np.full(stacked.shape[1], np.nan, dtype=float)
    for index in np.flatnonzero(envelope_support_count):
        envelope[index] = float(
            np.max(stacked[envelope_source_valid[:, index], index])
        )

    policies = {
        "highest_neutral_all_joint_valid": {
            "reference_transmittance": highest_neutral,
            "exclude_negative_relative_density": False,
            "semantics": (
                "Highest plotted neutral curve as an effective-white common "
                "reference; all joint-valid points retained"
            ),
            "physical_base_claimed": False,
            "selection_dependence": "none beyond source graph visibility",
        },
        "highest_neutral_nonnegative_relative_density_only": {
            "reference_transmittance": highest_neutral,
            "exclude_negative_relative_density": True,
            "semantics": (
                "Same highest-neutral reference after excluding points whose "
                "observed density is below that reference"
            ),
            "physical_base_claimed": False,
            "selection_dependence": (
                "outcome-dependent point exclusion; sensitivity-only"
            ),
        },
        "maximum_transmittance_envelope": {
            "reference_transmittance": envelope,
            "exclude_negative_relative_density": False,
            "semantics": (
                "Generated wavelength-wise maximum across the visible "
                "highest-neutral and 18 chromatic curves"
            ),
            "physical_base_claimed": False,
            "selection_dependence": (
                "constructed from the evaluated target curves and may switch "
                "source patch by wavelength; sensitivity-only"
            ),
            "envelope_support_count_by_wavelength": (
                envelope_support_count.tolist()
            ),
        },
        "common_zero_density": {
            "reference_transmittance": np.ones_like(highest_neutral),
            "exclude_negative_relative_density": False,
            "semantics": (
                "Generated zero-density common reference (unit "
                "transmittance) to remove candidate-base differences"
            ),
            "physical_base_claimed": False,
            "selection_dependence": (
                "not estimated from a physical clear patch; sensitivity-only"
            ),
        },
    }
    if tuple(policies) != REFERENCE_POLICY_ORDER:
        raise AssertionError("Reference policy ordering changed")
    return policies


def _evaluate_reference_policy(
    extracted: dict[str, Any],
    models: dict[str, dict[str, Any]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    basis_only = {
        name: _evaluate_model(
            extracted["chromatic_transmittance"],
            model,
            neutral_transmittance=policy["reference_transmittance"],
            exclude_negative_relative_density=policy[
                "exclude_negative_relative_density"
            ],
        )
        for name, model in models.items()
        if name
        in {
            "bundled",
            "public_effective_basis",
            "manufacturer_primary_basis",
        }
    }
    return {
        "basis_only": basis_only,
        "comparisons_vs_bundled_basis": {
            name: _comparison(basis_only["bundled"], result)
            for name, result in basis_only.items()
            if name != "bundled"
        },
    }


def _comparison(
    baseline: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    metrics = (
        "density_rmse_D",
        "transmittance_rmse_percentage_points",
    )
    improvement = {
        metric: float(
            100.0
            * (baseline["micro"][metric] - candidate["micro"][metric])
            / baseline["micro"][metric]
        )
        for metric in metrics
    }
    wins = {}
    p_values = {}
    for metric in metrics:
        count = sum(
            candidate_result[metric] < baseline_result[metric]
            for baseline_result, candidate_result in zip(
                baseline["per_curve"], candidate["per_curve"], strict=True
            )
        )
        wins[metric] = int(count)
        p_values[metric] = float(
            binomtest(count, n=len(baseline["per_curve"]), p=0.5, alternative="greater").pvalue
        )
    return {
        "micro_improvement_percent": improvement,
        "curve_win_count_of_18": wins,
        "one_sided_sign_test_p_value": p_values,
    }


def _base_white_stress(
    neutral_transmittance: np.ndarray,
    base_density: np.ndarray,
) -> dict[str, float | int]:
    valid = (
        np.isfinite(neutral_transmittance)
        & (neutral_transmittance >= TRANSMITTANCE_FLOOR)
        & (neutral_transmittance <= 1.0)
    )
    observed_density = -np.log10(neutral_transmittance[valid])
    predicted_transmittance = np.power(10.0, -base_density[valid])
    return {
        "visible_point_count": int(valid.sum()),
        "density_rmse_D": float(
            np.sqrt(np.mean(np.square(base_density[valid] - observed_density)))
        ),
        "transmittance_rmse_percentage_points": float(
            np.sqrt(
                np.mean(
                    np.square(
                        predicted_transmittance - neutral_transmittance[valid]
                    )
                )
            )
            * 100.0
        ),
    }


def _quantiles(values: list[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=float)
    return {
        "minimum": float(np.min(array)),
        "p05": float(np.quantile(array, 0.05)),
        "median": float(np.median(array)),
        "p95": float(np.quantile(array, 0.95)),
        "maximum": float(np.max(array)),
    }


def _variant_summary(
    variant_results: list[dict[str, Any]],
    candidate_name: str,
) -> dict[str, Any]:
    metrics = (
        "density_rmse_D",
        "transmittance_rmse_percentage_points",
    )
    improvement = {metric: [] for metric in metrics}
    wins_both = 0
    for result in variant_results:
        baseline = result["basis_only"]["bundled"]["micro"]
        candidate = result["basis_only"][candidate_name]["micro"]
        per_metric = {}
        for metric in metrics:
            value = float(
                100.0
                * (baseline[metric] - candidate[metric])
                / baseline[metric]
            )
            improvement[metric].append(value)
            per_metric[metric] = value
        if all(value > 0.0 for value in per_metric.values()):
            wins_both += 1
    return {
        "variant_count": len(variant_results),
        "both_micro_metrics_improve_count": int(wins_both),
        "improvement_percent_quantiles": {
            metric: _quantiles(values)
            for metric, values in improvement.items()
        },
    }


def _external_gate(
    comparisons_by_policy: dict[str, dict[str, Any]],
    variants_by_policy: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if tuple(comparisons_by_policy) != REFERENCE_POLICY_ORDER:
        raise ValueError("External gate requires every reference policy")
    if tuple(variants_by_policy) != REFERENCE_POLICY_ORDER:
        raise ValueError("External gate requires every policy's axis variants")
    checks = {}
    for policy_name in REFERENCE_POLICY_ORDER:
        comparison = comparisons_by_policy[policy_name]
        variants = variants_by_policy[policy_name]
        prefix = f"{policy_name}__"
        checks.update(
            {
                prefix + "primary_micro_density_improves": comparison[
                    "micro_improvement_percent"
                ]["density_rmse_D"]
                > 0.0,
                prefix + "primary_micro_transmittance_improves": comparison[
                    "micro_improvement_percent"
                ]["transmittance_rmse_percentage_points"]
                > 0.0,
                prefix
                + "all_axis_extraction_variants_improve_both_micro_metrics": (
                    variants["both_micro_metrics_improve_count"]
                    == variants["variant_count"]
                ),
                prefix + "majority_of_curves_win_density": comparison[
                    "curve_win_count_of_18"
                ]["density_rmse_D"]
                >= 10,
                prefix + "majority_of_curves_win_transmittance": comparison[
                    "curve_win_count_of_18"
                ]["transmittance_rmse_percentage_points"]
                >= 10,
                prefix + "density_sign_test_p_at_most_0_05": comparison[
                    "one_sided_sign_test_p_value"
                ]["density_rmse_D"]
                <= 0.05,
                prefix + "transmittance_sign_test_p_at_most_0_05": comparison[
                    "one_sided_sign_test_p_value"
                ]["transmittance_rmse_percentage_points"]
                <= 0.05,
            }
        )
    return {
        "passes": bool(all(checks.values())),
        "checks": checks,
        "required_reference_policies": list(REFERENCE_POLICY_ORDER),
        "sign_test_alpha": 0.05,
        "policy_origin": (
            "Spektrafilm conservative independent-source engineering gate; "
            "not an ISO or source-publisher threshold"
        ),
        "default_replacement_authorized": False,
    }


def _plot_overlay(
    path: Path,
    chromatic_image: np.ndarray,
    neutral_image: np.ndarray,
    extracted: dict[str, Any],
    colours: list[tuple[int, int, int]],
) -> None:
    figure, axes = plt.subplots(2, 1, figsize=(12, 11))
    axes[0].imshow(chromatic_image)
    axes[1].imshow(neutral_image)
    for curve_y, colour in zip(
        extracted["chromatic_y_pixels"], colours, strict=True
    ):
        finite = np.isfinite(curve_y)
        x = PRIMARY_AXIS["x_left_px"] + (WAVELENGTHS_NM - 400.0) * (
            PRIMARY_AXIS["x_right_px"] - PRIMARY_AXIS["x_left_px"]
        ) / 300.0
        axes[0].scatter(
            x[finite],
            curve_y[finite],
            s=7,
            facecolors="none",
            edgecolors=np.asarray(colour) / 255.0,
            linewidths=0.7,
        )
    neutral_y = extracted["neutral_white_y_pixels"]
    neutral_finite = np.isfinite(neutral_y)
    x = PRIMARY_AXIS["x_left_px"] + (WAVELENGTHS_NM - 400.0) * (
        PRIMARY_AXIS["x_right_px"] - PRIMARY_AXIS["x_left_px"]
    ) / 300.0
    axes[1].scatter(
        x[neutral_finite],
        neutral_y[neutral_finite],
        s=18,
        facecolors="none",
        edgecolors="red",
        linewidths=0.8,
    )
    axes[0].set_title("18 chromatic curves: visible exact-colour samples")
    axes[1].set_title("Highest neutral dotted curve: effective white samples")
    for axis in axes:
        axis.set_xlim(150, 990)
        axis.set_ylim(490, 10)
        axis.set_axis_off()
    figure.suptitle(
        "Velvia 100 MicroCalT24 graph extraction overlay\n"
        "Missing/overwritten line segments are not interpolated"
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(path, dpi=160, metadata={"Software": "Spektrafilm audit"})
    plt.close(figure)


def _plot_comparison(path: Path, primary: dict[str, Any]) -> None:
    names = ["bundled", "public_effective_basis", "manufacturer_primary_basis"]
    labels = ["Bundled", "Public effective", "Manufacturer graph"]
    density = [primary["basis_only"][name]["micro"]["density_rmse_D"] for name in names]
    transmittance = [
        primary["basis_only"][name]["micro"][
            "transmittance_rmse_percentage_points"
        ]
        for name in names
    ]
    figure, axes = plt.subplots(1, 2, figsize=(10, 4.5))
    axes[0].bar(labels, density, color=("#4c78a8", "#e45756", "#72b7b2"))
    axes[1].bar(
        labels,
        transmittance,
        color=("#4c78a8", "#e45756", "#72b7b2"),
    )
    axes[0].set_ylabel("Density RMSE (D)")
    axes[1].set_ylabel("Transmittance RMSE (percentage points)")
    for axis in axes:
        axis.tick_params(axis="x", labelrotation=18)
        axis.grid(axis="y", alpha=0.25)
    figure.suptitle("Independent MicroCalT24 basis-only reconstruction")
    figure.tight_layout(rect=(0, 0, 1, 0.93))
    figure.savefig(path, dpi=160, metadata={"Software": "Spektrafilm audit"})
    plt.close(figure)


def build_report(
    source_paths: dict[str, Path],
    output_dir: Path,
) -> dict[str, Any]:
    chromatic_image = _load_rgb(source_paths["chromatic_graph"])
    neutral_image = _load_rgb(source_paths["neutral_graph"])
    colours = _discover_chromatic_colours(chromatic_image)
    models, model_context = _load_models()

    primary_extracted = _extract_graphs(
        chromatic_image,
        neutral_image,
        PRIMARY_AXIS,
        colours,
    )
    primary_policies = _reference_policies(primary_extracted)
    primary_policy_results = {
        name: _evaluate_reference_policy(primary_extracted, models, policy)
        for name, policy in primary_policies.items()
    }
    primary_basis_only = primary_policy_results[
        "highest_neutral_all_joint_valid"
    ]["basis_only"]
    primary_absolute = {
        name: _evaluate_model(
            primary_extracted["chromatic_transmittance"], model
        )
        for name, model in models.items()
    }
    primary_base_stress = {
        name: _base_white_stress(
            primary_extracted["neutral_white_transmittance"], model["base"]
        )
        for name, model in models.items()
        if name in {"bundled", "public_grouped_base"}
    }
    primary = {
        "basis_only": primary_basis_only,
        "absolute_profile": primary_absolute,
        "effective_white_base_stress": primary_base_stress,
        "comparisons_vs_bundled_basis": {
            name: _comparison(primary_basis_only["bundled"], result)
            for name, result in primary_basis_only.items()
            if name != "bundled"
        },
    }

    variant_results_by_policy = {
        name: [] for name in REFERENCE_POLICY_ORDER
    }
    for axis in AXIS_VARIANTS:
        extracted = _extract_graphs(
            chromatic_image,
            neutral_image,
            axis,
            colours,
        )
        for policy_name, policy in _reference_policies(extracted).items():
            variant_results_by_policy[policy_name].append(
                _evaluate_reference_policy(extracted, models, policy)
            )

    policy_variant_summaries = {
        policy_name: {
            candidate_name: _variant_summary(variant_results, candidate_name)
            for candidate_name in (
                "public_effective_basis",
                "manufacturer_primary_basis",
            )
        }
        for policy_name, variant_results in variant_results_by_policy.items()
    }
    variant_summaries = policy_variant_summaries[
        "highest_neutral_all_joint_valid"
    ]
    external_gates = {
        name: _external_gate(
            {
                policy_name: result["comparisons_vs_bundled_basis"][name]
                for policy_name, result in primary_policy_results.items()
            },
            {
                policy_name: result[name]
                for policy_name, result in policy_variant_summaries.items()
            },
        )
        for name in (
            "public_effective_basis",
            "manufacturer_primary_basis",
        )
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    overlay_path = output_dir / "velvia_microcal_extraction_overlay.png"
    comparison_path = output_dir / "velvia_microcal_model_comparison.png"
    _plot_overlay(
        overlay_path,
        chromatic_image,
        neutral_image,
        primary_extracted,
        colours,
    )
    _plot_comparison(comparison_path, primary)

    report = {
        "created": "2026-07-16",
        "scope": {
            "profile": "fujifilm_velvia_100",
            "material": "Fujifilm Velvia 100",
            "evidence_role": "independent validation-only graph digitization",
            "bundled_profile_arrays_modified": False,
            "profile_candidates_emitted": False,
            "manufacturer_or_author_contact_used": False,
            "new_physical_film_used": False,
        },
        "source": {
            "product_page": SOURCE_PAGE_URL,
            "identity_statement": (
                "The Avian Rochester product page and brochure explicitly "
                "identify the MicroCalT24 film type as FujiFilm Velvia 100."
            ),
            "published_data_statement": (
                "The page describes the plotted values as nominal colour and "
                "spectral transmittance data; NIST-traceable individual data "
                "are supplied with a calibrated commercial target, not as a "
                "public numeric download."
            ),
            "graph_support_nm": [400.0, 700.0],
            "declared_patch_count": 24,
            "declared_chromatic_patch_count": 18,
            "declared_neutral_patch_count": 6,
            "licence": (
                "The source site states all rights reserved and publishes no "
                "open derivative licence. Source images and digitized arrays "
                "remain local and are not embedded in this repository report."
            ),
            "files": {
                key: {
                    "path": str(path.resolve()),
                    "url": SOURCE_SPECS[key]["url"],
                    "sha256": _sha256(path),
                }
                for key, path in source_paths.items()
            },
        },
        "analysis": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "software_versions": {
                "python": platform.python_version(),
                "python_implementation": platform.python_implementation(),
                "platform": platform.platform(),
                "numpy": np.__version__,
                "scipy": scipy.__version__,
                "matplotlib": matplotlib.__version__,
                "pillow": Image.__version__,
            },
            "wavelengths_nm": WAVELENGTHS_NM.tolist(),
            "transmittance_floor": TRANSMITTANCE_FLOOR,
            "relative_density_tolerance_D": RELATIVE_DENSITY_TOLERANCE_D,
            "primary_axis": PRIMARY_AXIS,
            "axis_extraction_variant_count": len(AXIS_VARIANTS),
            "visible_data_only": True,
            "missing_line_segments_interpolated": False,
            "patch_identity_required_for_nnls_reconstruction": False,
            "neutral_white_semantic_limit": (
                "highest plotted neutral curve; not labelled GS0, base-plus-"
                "fog, unexposed film, or analytical Dmin"
            ),
            "reference_policy_limit": (
                "All four common references are ranking sensitivities. The "
                "highest neutral is not documented Dmin; negative-point "
                "exclusion is outcome-dependent; the maximum envelope is "
                "constructed from evaluated curves; zero density is not a "
                "measured clear patch. None identifies a physical base."
            ),
            "model_context": model_context,
        },
        "extraction_qa": {
            "exact_chromatic_colour_count": len(colours),
            "chromatic_curve_visible_point_counts": np.isfinite(
                primary_extracted["chromatic_transmittance"]
            )
            .sum(axis=1)
            .astype(int)
            .tolist(),
            "chromatic_total_visible_point_count": int(
                np.isfinite(primary_extracted["chromatic_transmittance"]).sum()
            ),
            "neutral_white_visible_point_count": int(
                np.isfinite(
                    primary_extracted["neutral_white_transmittance"]
                ).sum()
            ),
            "highest_neutral_joint_visible_point_count": primary_basis_only[
                "bundled"
            ]["support_qa"][
                "joint_visible_point_count_before_policy_exclusion"
            ],
            "negative_relative_density_point_count_against_highest_neutral": (
                primary_basis_only["bundled"]["support_qa"][
                    "negative_relative_density_point_count"
                ]
            ),
            "curve_count_with_negative_relative_density": primary_basis_only[
                "bundled"
            ]["support_qa"]["curve_count_with_negative_relative_density"],
            "maximum_transmittance_envelope_support_count_range": [
                int(
                    min(
                        primary_policies["maximum_transmittance_envelope"][
                            "envelope_support_count_by_wavelength"
                        ]
                    )
                ),
                int(
                    max(
                        primary_policies["maximum_transmittance_envelope"][
                            "envelope_support_count_by_wavelength"
                        ]
                    )
                ),
            ],
            "chromatic_line_colours_rgb": [list(colour) for colour in colours],
        },
        "primary_result": primary,
        "axis_extraction_sensitivity": variant_summaries,
        "reference_policy_sensitivity": {
            "definitions": {
                name: {
                    key: value
                    for key, value in policy.items()
                    if key != "reference_transmittance"
                }
                for name, policy in primary_policies.items()
            },
            "primary_results": primary_policy_results,
            "axis_extraction_sensitivity": policy_variant_summaries,
        },
        "external_promotion_gates": external_gates,
        "conclusions": {
            "public_effective_basis_passes_independent_source_gate": (
                external_gates["public_effective_basis"]["passes"]
            ),
            "manufacturer_direct_replacement_passes_independent_source_gate": (
                external_gates["manufacturer_primary_basis"]["passes"]
            ),
            "public_grouped_base_default_promotion_supported": False,
            "base_reason": (
                "No common-reference policy identifies a physical base. The "
                "highest neutral is not documented GS0/base-plus-fog; the "
                "three generated alternatives are sensitivity checks only."
            ),
            "physical_cmy_identified": False,
            "default_profile_change_authorized": False,
            "candidate_policy_consequence": (
                "Retain bundled Velvia channel numbers. Demote the public "
                "effective-basis and grouped-base files to corpus-specific "
                "exploratory candidates because MicroCal does not independently "
                "confirm cross-source promotion; this is not proof that the "
                "candidates are physically false."
            ),
        },
        "artifacts": {
            "overlay": {
                "path": str(overlay_path.resolve()),
                "sha256": _sha256(overlay_path),
            },
            "comparison": {
                "path": str(comparison_path.resolve()),
                "sha256": _sha256(comparison_path),
            },
        },
    }
    report["result_sha256"] = _canonical_sha256(
        {
            "extraction_qa": report["extraction_qa"],
            "primary_result": report["primary_result"],
            "axis_extraction_sensitivity": report[
                "axis_extraction_sensitivity"
            ],
            "reference_policy_sensitivity": report[
                "reference_policy_sensitivity"
            ],
            "external_promotion_gates": report["external_promotion_gates"],
            "conclusions": report["conclusions"],
        }
    )
    return report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--download-missing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    source_paths = {
        key: _ensure_source(spec, args.source_dir, args.download_missing)
        for key, spec in SOURCE_SPECS.items()
    }
    report = build_report(source_paths, args.output_dir)
    report_path = args.output_dir / "velvia_microcal_validation.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(report_path.resolve()),
                "output_sha256": _sha256(report_path),
                "analysis_code_sha256": report["analysis"]["script_sha256"],
                "result_sha256": report["result_sha256"],
                "public_effective_basis_passes_independent_source_gate": report[
                    "conclusions"
                ]["public_effective_basis_passes_independent_source_gate"],
                "manufacturer_direct_replacement_passes_independent_source_gate": report[
                    "conclusions"
                ]["manufacturer_direct_replacement_passes_independent_source_gate"],
                "bundled_profiles_modified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
