#!/usr/bin/env python3
"""Validate fixed manufacturer CMY shapes against public batch spectra.

This script combines the auditable Fujifilm curve extraction with the existing
complete-PROD_DATE-group holdout machinery.  It asks two separate questions:

1. Does the bundled channel shape remain recognizably derived from the
   same-stock manufacturer curve after documented processing?
2. Would numerically replacing it with the newly extracted curve improve
   held-out same-stock patch reconstruction enough to justify a candidate?

The first question is a provenance check.  The second is a model-replacement
gate.  Passing the former never implies passing the latter, and neither turns
the graph into raw observations for a retained particular roll.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
PUBLIC_BATCH_SCRIPT = REPORT_DIR / "profile-public-batch-validation.py"
CURVE_SCRIPT = REPORT_DIR / "profile-source-curve-digitization.py"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "tmp"
    / "profile-source-curves"
    / "manufacturer_curve_batch_validation.json"
)
DEFAULT_CANDIDATE_OUTPUT_DIR = (
    PROJECT_ROOT / "tmp" / "profile-source-curves" / "candidates"
)
SOURCE_CANDIDATE_MANIFEST = (
    PROJECT_ROOT
    / "tmp"
    / "profile-source-curves"
    / "CURRENT_SOURCE_CURVE_CANDIDATES.json"
)
SOURCE_SUPPORT_NM = (400.0, 700.0)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import analysis module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUBLIC = _load_module("profile_public_batch_validation", PUBLIC_BATCH_SCRIPT)
CURVES = _load_module("profile_source_curve_digitization", CURVE_SCRIPT)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_matrix(
    bundled_basis: np.ndarray,
    wavelengths: np.ndarray,
    normalized_source: dict[str, list[float]],
    source_grid: np.ndarray,
) -> np.ndarray:
    result = np.asarray(bundled_basis, dtype=np.float64).copy()
    support = (wavelengths >= source_grid[0]) & (
        wavelengths <= source_grid[-1]
    )
    channel_to_column = {"C": 0, "M": 1, "Y": 2}
    bundled_scales = np.max(result, axis=0)
    for channel, column in channel_to_column.items():
        source_shape = np.asarray(normalized_source[channel], dtype=np.float64)
        result[support, column] = (
            np.interp(wavelengths[support], source_grid, source_shape)
            * bundled_scales[column]
        )
    return result


def _effective_candidate_matrix(
    bundled_basis: np.ndarray,
    wavelengths: np.ndarray,
):
    loaded = CURVES._load_effective_velvia_candidate()
    if loaded is None:
        return None, None
    candidate_channels, metadata = loaded
    source_grid = CURVES.PROFILE_GRID
    result = np.asarray(bundled_basis, dtype=np.float64).copy()
    channel_to_column = {"C": 0, "M": 1, "Y": 2}
    for channel, column in channel_to_column.items():
        result[:, column] = np.interp(
            wavelengths,
            source_grid,
            candidate_channels[channel],
        )
    return result, metadata


def _prepare_dataset(spec, batches):
    production_groups = PUBLIC._production_groups(batches)
    common_wavelengths = PUBLIC._common_wavelengths(batches)
    measured_mask, wavelengths, bundled_basis, bundled_base = (
        PUBLIC.EVALUATION._load_profile_basis(
            spec.profile_slug,
            common_wavelengths,
        )
    )
    canonical_names = batches[0].names.copy()
    values = [
        PUBLIC._align_patch_rows(
            batch,
            PUBLIC._values_on_grid(batch, common_wavelengths),
            canonical_names,
        )[:, measured_mask]
        for batch in batches
    ]
    if any(np.any(item <= 0.0) for item in values):
        raise ValueError(f"Non-positive value entered {spec.key} evaluation")
    density = [-np.log10(item) for item in values]
    return {
        "production_groups": production_groups,
        "wavelengths": wavelengths,
        "bundled_basis": bundled_basis,
        "bundled_base": bundled_base,
        "canonical_names": canonical_names,
        "values": values,
        "density": density,
    }


def _training_base(prepared, training_groups):
    canonical_names = prepared["canonical_names"]
    return PUBLIC._group_equal_median(
        [
            density[canonical_names == "GS0"][0]
            for density in prepared["density"]
        ],
        training_groups,
    )


def _evaluate_indices(
    spec,
    batches,
    prepared,
    indices: np.ndarray,
    bases: dict[str, np.ndarray],
    base_density: np.ndarray,
):
    canonical_names = prepared["canonical_names"]
    evaluation_mask = canonical_names != "GS0"
    aggregate_values = []
    aggregate_density = []
    predictions = {name: [] for name in bases}
    per_archive = {name: [] for name in bases}
    for index_value in indices:
        index = int(index_value)
        values = prepared["values"][index][evaluation_mask]
        density = prepared["density"][index][evaluation_mask]
        aggregate_values.append(values)
        aggregate_density.append(density)
        for model_name, basis in bases.items():
            prediction = PUBLIC.EVALUATION._fit_coefficients_and_predict(
                density,
                values,
                basis,
                base_density,
                spec.primary_floor,
            )
            predictions[model_name].append(prediction)
            per_archive[model_name].append(
                {
                    "batch": batches[index].batch_id,
                    "metrics": PUBLIC._summarize_predictions(
                        spec,
                        prepared["wavelengths"],
                        values,
                        density,
                        prediction,
                        spec.primary_floor,
                    ),
                }
            )
    concatenated_values = np.concatenate(aggregate_values)
    concatenated_density = np.concatenate(aggregate_density)
    metrics = {
        model_name: PUBLIC._summarize_predictions(
            spec,
            prepared["wavelengths"],
            concatenated_values,
            concatenated_density,
            np.concatenate(predictions[model_name]),
            spec.primary_floor,
        )
        for model_name in bases
    }
    return metrics, per_archive


def _full_group_holdout(spec, batches, prepared, bases):
    production_groups = prepared["production_groups"]
    aggregate_values = []
    aggregate_density = []
    aggregate_predictions = {name: [] for name in bases}
    per_archive = {name: [] for name in bases}
    evaluation_mask = prepared["canonical_names"] != "GS0"

    for held_position, (_, held_indices) in enumerate(production_groups):
        training_groups = [
            group
            for position, group in enumerate(production_groups)
            if position != held_position
        ]
        base = _training_base(prepared, training_groups)
        for index_value in held_indices:
            index = int(index_value)
            values = prepared["values"][index][evaluation_mask]
            density = prepared["density"][index][evaluation_mask]
            aggregate_values.append(values)
            aggregate_density.append(density)
            for model_name, basis in bases.items():
                prediction = PUBLIC.EVALUATION._fit_coefficients_and_predict(
                    density,
                    values,
                    basis,
                    base,
                    spec.primary_floor,
                )
                aggregate_predictions[model_name].append(prediction)
                per_archive[model_name].append(
                    {
                        "batch": batches[index].batch_id,
                        "metrics": PUBLIC._summarize_predictions(
                            spec,
                            prepared["wavelengths"],
                            values,
                            density,
                            prediction,
                            spec.primary_floor,
                        ),
                    }
                )

    all_values = np.concatenate(aggregate_values)
    all_density = np.concatenate(aggregate_density)
    micro = {
        model_name: PUBLIC._summarize_predictions(
            spec,
            prepared["wavelengths"],
            all_values,
            all_density,
            np.concatenate(aggregate_predictions[model_name]),
            spec.primary_floor,
        )
        for model_name in bases
    }
    group_rows = {
        model_name: PUBLIC._group_macro_rows(rows, batches)
        for model_name, rows in per_archive.items()
    }
    macro = {
        model_name: PUBLIC._mean_row_metrics(rows)
        for model_name, rows in group_rows.items()
    }
    return {
        "micro_metrics": micro,
        "production_group_macro_metrics": macro,
        "per_archive": per_archive,
        "per_production_group": group_rows,
    }


def _chronological_holdout(spec, batches, prepared, bases):
    production_groups = prepared["production_groups"]
    holdout_count = max(1, int(np.ceil(0.2 * len(production_groups))))
    training_groups = production_groups[:-holdout_count]
    test_groups = production_groups[-holdout_count:]
    test_indices = np.concatenate([indices for _, indices in test_groups])
    base = _training_base(prepared, training_groups)
    metrics, per_archive = _evaluate_indices(
        spec,
        batches,
        prepared,
        test_indices,
        bases,
        base,
    )
    group_rows = {
        model_name: PUBLIC._group_macro_rows(rows, batches)
        for model_name, rows in per_archive.items()
    }
    return {
        "held_out_group_count": holdout_count,
        "held_out_groups": [key for key, _ in test_groups],
        "role": "newest-20-percent chronological stress slice",
        "independent_replication": False,
        "independence_note": (
            "These groups also appear as held-out folds in complete group "
            "cross-validation; this is a temporal stress slice, not a second "
            "independent dataset."
        ),
        "metrics": metrics,
        "production_group_macro_metrics": {
            model_name: PUBLIC._mean_row_metrics(rows)
            for model_name, rows in group_rows.items()
        },
        "per_production_group": group_rows,
    }


def _joint_combined_holdout(
    spec,
    batches,
    prepared,
    candidate_basis: np.ndarray,
):
    """Compare the complete two-field candidate with the bundled default.

    The bundled model always keeps its bundled base.  In every fold the source
    candidate gets a GS0 base trained only from the other production groups.
    Patch coefficients are fitted independently within each held-out spectrum,
    exactly as in the component gates.
    """

    production_groups = prepared["production_groups"]
    evaluation_mask = prepared["canonical_names"] != "GS0"
    aggregate_values: list[np.ndarray] = []
    aggregate_density: list[np.ndarray] = []
    aggregate_predictions = {"bundled": [], "combined_candidate": []}
    per_archive = {"bundled": [], "combined_candidate": []}

    for held_position, (_, held_indices) in enumerate(production_groups):
        training_groups = [
            group
            for position, group in enumerate(production_groups)
            if position != held_position
        ]
        candidate_base = _training_base(prepared, training_groups)
        for index_value in held_indices:
            index = int(index_value)
            values = prepared["values"][index][evaluation_mask]
            density = prepared["density"][index][evaluation_mask]
            aggregate_values.append(values)
            aggregate_density.append(density)
            for model_name, basis, base in (
                (
                    "bundled",
                    prepared["bundled_basis"],
                    prepared["bundled_base"],
                ),
                ("combined_candidate", candidate_basis, candidate_base),
            ):
                prediction = PUBLIC.EVALUATION._fit_coefficients_and_predict(
                    density,
                    values,
                    basis,
                    base,
                    spec.primary_floor,
                )
                aggregate_predictions[model_name].append(prediction)
                per_archive[model_name].append(
                    {
                        "batch": batches[index].batch_id,
                        "metrics": PUBLIC._summarize_predictions(
                            spec,
                            prepared["wavelengths"],
                            values,
                            density,
                            prediction,
                            spec.primary_floor,
                        ),
                    }
                )

    all_values = np.concatenate(aggregate_values)
    all_density = np.concatenate(aggregate_density)
    micro = {
        model_name: PUBLIC._summarize_predictions(
            spec,
            prepared["wavelengths"],
            all_values,
            all_density,
            np.concatenate(predictions),
            spec.primary_floor,
        )
        for model_name, predictions in aggregate_predictions.items()
    }
    group_rows = {
        model_name: PUBLIC._group_macro_rows(rows, batches)
        for model_name, rows in per_archive.items()
    }
    return {
        "micro_metrics": micro,
        "production_group_macro_metrics": {
            model_name: PUBLIC._mean_row_metrics(rows)
            for model_name, rows in group_rows.items()
        },
        "per_archive": per_archive,
        "per_production_group": group_rows,
    }


def _joint_combined_chronological_holdout(
    spec,
    batches,
    prepared,
    candidate_basis: np.ndarray,
):
    production_groups = prepared["production_groups"]
    holdout_count = max(1, int(np.ceil(0.2 * len(production_groups))))
    training_groups = production_groups[:-holdout_count]
    test_groups = production_groups[-holdout_count:]
    test_indices = np.concatenate([indices for _, indices in test_groups])
    candidate_base = _training_base(prepared, training_groups)
    evaluation_mask = prepared["canonical_names"] != "GS0"
    aggregate_values: list[np.ndarray] = []
    aggregate_density: list[np.ndarray] = []
    predictions = {"bundled": [], "combined_candidate": []}
    per_archive = {"bundled": [], "combined_candidate": []}
    for index_value in test_indices:
        index = int(index_value)
        values = prepared["values"][index][evaluation_mask]
        density = prepared["density"][index][evaluation_mask]
        aggregate_values.append(values)
        aggregate_density.append(density)
        for model_name, basis, base in (
            (
                "bundled",
                prepared["bundled_basis"],
                prepared["bundled_base"],
            ),
            ("combined_candidate", candidate_basis, candidate_base),
        ):
            prediction = PUBLIC.EVALUATION._fit_coefficients_and_predict(
                density,
                values,
                basis,
                base,
                spec.primary_floor,
            )
            predictions[model_name].append(prediction)
            per_archive[model_name].append(
                {
                    "batch": batches[index].batch_id,
                    "metrics": PUBLIC._summarize_predictions(
                        spec,
                        prepared["wavelengths"],
                        values,
                        density,
                        prediction,
                        spec.primary_floor,
                    ),
                }
            )
    all_values = np.concatenate(aggregate_values)
    all_density = np.concatenate(aggregate_density)
    metrics = {
        model_name: PUBLIC._summarize_predictions(
            spec,
            prepared["wavelengths"],
            all_values,
            all_density,
            np.concatenate(model_predictions),
            spec.primary_floor,
        )
        for model_name, model_predictions in predictions.items()
    }
    group_rows = {
        model_name: PUBLIC._group_macro_rows(rows, batches)
        for model_name, rows in per_archive.items()
    }
    return {
        "held_out_group_count": holdout_count,
        "held_out_groups": [key for key, _ in test_groups],
        "role": "newest-20-percent chronological stress slice",
        "independent_replication": False,
        "independence_note": (
            "These groups also appear as held-out folds in complete group "
            "cross-validation; this is a temporal stress slice, not a second "
            "independent dataset."
        ),
        "metrics": metrics,
        "production_group_macro_metrics": {
            model_name: PUBLIC._mean_row_metrics(rows)
            for model_name, rows in group_rows.items()
        },
        "per_production_group": group_rows,
    }


def _model_comparison(evaluation, candidate_name: str):
    baseline_name = "bundled"
    baseline_micro = evaluation["micro_metrics"][baseline_name]
    candidate_micro = evaluation["micro_metrics"][candidate_name]
    baseline_macro = evaluation["production_group_macro_metrics"][baseline_name]
    candidate_macro = evaluation["production_group_macro_metrics"][candidate_name]
    baseline_groups = evaluation["per_production_group"][baseline_name]
    candidate_groups = evaluation["per_production_group"][candidate_name]
    metric_names = tuple(baseline_micro)
    wins = PUBLIC._basis_win_counts(baseline_groups, candidate_groups)
    return {
        "micro_improvement_percent": PUBLIC._metric_improvements(
            baseline_micro,
            candidate_micro,
        ),
        "production_group_macro_improvement_percent": (
            PUBLIC._metric_improvements(baseline_macro, candidate_macro)
        ),
        "production_group_win_counts": wins,
        "production_group_sign_test_p_values": {
            metric: PUBLIC._one_sided_sign_test_p_value(
                wins[metric],
                len(baseline_groups),
            )
            for metric in metric_names
        },
        "maximum_production_group_regression_percent": {
            metric: PUBLIC._maximum_relative_regression_percent(
                baseline_groups,
                candidate_groups,
                metric,
            )
            for metric in metric_names
        },
    }


def _shape_provenance_gate(curve_stock: dict[str, Any]):
    comparison = curve_stock["bundled_vs_manufacturer_primary"]
    channels = {}
    for channel in ("Y", "M", "C"):
        metrics = comparison[channel]
        passes = bool(
            metrics["cosine"] >= 0.995
            and abs(metrics["peak_shift_nm"]) <= 10.0
            and metrics["fwhm_left_nm"] is not None
            and metrics["fwhm_right_nm"] is not None
            and abs(metrics["fwhm_left_nm"] - metrics["fwhm_right_nm"])
            <= 10.0
        )
        channels[channel] = {
            "passes": passes,
            "minimum_cosine": 0.995,
            "maximum_peak_shift_nm": 10.0,
            "maximum_fwhm_shift_nm": 10.0,
            "observed": metrics,
        }
    return {
        "passes": all(value["passes"] for value in channels.values()),
        "channels": channels,
        "meaning": (
            "The processed bundled shape remains consistent with a same-stock "
            "manufacturer starting curve; this is not an exact-array or "
            "raw-measurement identity test."
        ),
        "policy_origin": "Spektrafilm conservative provenance policy",
    }


def _apply_manufacturer_shape_to_payload(
    payload: dict[str, Any],
    curve_report: dict[str, Any],
    *,
    stock_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Overlay a normalized manufacturer shape without inventing amplitude.

    Only the explicitly labelled 400--700 nm graph support is replaced.  The
    per-channel peak density remains the bundled value, because the published
    Fujifilm graph is normalized and does not identify absolute dye amount.
    """

    result = copy.deepcopy(payload)
    wavelengths = np.asarray(result["data"]["wavelengths"], dtype=np.float64)
    current = np.asarray(result["data"]["channel_density"], dtype=np.float64)
    if current.shape != (len(wavelengths), 3):
        raise ValueError("Candidate channel_density must be wavelengths by CMY")
    source_grid = np.asarray(
        curve_report["analysis"]["profile_grid_nm"],
        dtype=np.float64,
    )
    if (
        source_grid.ndim != 1
        or len(source_grid) < 2
        or np.any(np.diff(source_grid) <= 0.0)
        or not np.isclose(source_grid[0], SOURCE_SUPPORT_NM[0])
        or not np.isclose(source_grid[-1], SOURCE_SUPPORT_NM[1])
    ):
        raise ValueError(
            "Manufacturer source grid must be strictly increasing and cover "
            "exactly 400--700 nm"
        )
    source = curve_report["stocks"][stock_key]["primary_normalized"]
    support = (
        np.all(np.isfinite(current), axis=1)
        & (wavelengths >= SOURCE_SUPPORT_NM[0])
        & (wavelengths <= SOURCE_SUPPORT_NM[1])
    )
    if not np.any(support):
        raise ValueError("Manufacturer curve has no overlap with profile support")
    bundled_support = np.all(np.isfinite(current), axis=1)
    bundled_peaks = np.max(current[bundled_support], axis=0)
    candidate = current.copy()
    channel_to_column = {"C": 0, "M": 1, "Y": 2}
    for channel, column in channel_to_column.items():
        normalized = np.asarray(source[channel], dtype=np.float64)
        if normalized.shape != source_grid.shape:
            raise ValueError(f"Unexpected {channel} manufacturer curve shape")
        if not np.all(np.isfinite(normalized)) or np.any(normalized < 0.0):
            raise ValueError(f"Invalid {channel} manufacturer curve")
        if not np.isclose(np.max(normalized), 1.0, atol=1e-12):
            raise ValueError(f"{channel} manufacturer curve must be unit-peak")
        candidate[support, column] = (
            np.interp(wavelengths[support], source_grid, normalized)
            * bundled_peaks[column]
        )
    if not np.all(np.isfinite(candidate[support])) or np.any(candidate[support] < 0):
        raise ValueError("Manufacturer overlay produced invalid channel values")

    serialized = copy.deepcopy(result["data"]["channel_density"])
    for index in np.flatnonzero(support):
        serialized[int(index)] = candidate[int(index)].tolist()
    result["data"]["channel_density"] = serialized
    candidate_peaks = np.max(candidate[bundled_support], axis=0)
    outside_unchanged = bool(
        np.array_equal(
            candidate[~support],
            current[~support],
            equal_nan=True,
        )
    )
    changed = candidate - current
    return result, {
        "source_grid_nm": source_grid.tolist(),
        "replacement_range_nm": list(SOURCE_SUPPORT_NM),
        "replacement_point_count": int(np.sum(support)),
        "unchanged_point_count": int(np.sum(~support)),
        "channel_runtime_order": ["C", "M", "Y"],
        "channel_peak_scale_restoration": {
            "bundled_channel_peaks_D": bundled_peaks.tolist(),
            "candidate_channel_peaks_D": candidate_peaks.tolist(),
            "maximum_absolute_difference_D": float(
                np.max(np.abs(candidate_peaks - bundled_peaks))
            ),
        },
        "mean_absolute_change_D_on_support": float(
            np.mean(np.abs(changed[support]))
        ),
        "max_absolute_change_D_on_support": float(
            np.max(np.abs(changed[support]))
        ),
        "outside_source_support_exactly_unchanged": outside_unchanged,
        "semantics": (
            "manufacturer-published normalized separated-light spectral diffuse "
            "density shape derived under the stated manufacturer measurement "
            "method; bundled absolute channel peak scales retained"
        ),
    }


def _build_combined_provia_candidate(
    spec,
    batches,
    curve_report: dict[str, Any],
    base_wavelengths: np.ndarray,
    median_gs0_density: np.ndarray,
    *,
    interpolation: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload, base_summary = PUBLIC._build_multibatch_candidate_payload(
        spec,
        batches,
        base_wavelengths,
        median_gs0_density,
        interpolation=interpolation,
    )
    payload, channel_summary = _apply_manufacturer_shape_to_payload(
        payload,
        curve_report,
        stock_key="provia_100f",
    )

    product = CURVES.PDF_SPECS["provia_product_2000"]
    guide = CURVES.PDF_SPECS["professional_data_guide_2005"]
    product_source = "FUJI_PROVIA_100F_AF3_036E_2000"
    guide_source = "FUJI_PROFESSIONAL_FILM_DATA_GUIDE_2005"
    provenance = payload["metadata"]["provenance"]
    provenance["source_references"][product_source] = (
        f"Fujichrome Provia 100F / RDP III Data Sheet AF3-036E (2000), "
        f"page 6, Spectral Dye Density Curves; {product.url}; PDF SHA-256 "
        f"{product.sha256}. The PDF contains separate one-bit image masks for "
        "yellow, magenta, and cyan curves."
    )
    provenance["source_references"][guide_source] = (
        f"Fujifilm Professional Film Data Guide (2005), pages 23 and 25; "
        f"{guide.url}; PDF SHA-256 {guide.sha256}. Page 23 defines reversal-film "
        "spectral dye density as three spectrophotometer/color-analyzer curves "
        "whose obtained density level is set to 1.0; page 25 supplies the "
        "cross-edition Provia 100F graph."
    )
    previous = provenance["fields"]["channel_density"]
    previous_sources = previous.get("sources", [])
    provenance["fields"]["channel_density"] = {
        "origin": "manufacturer-graph",
        "status": "source-derived",
        "sources": list(
            dict.fromkeys(
                [*previous_sources, product_source, guide_source]
            )
        ),
        "derived_from": (
            f"{product_source}:page-6-spectral-dye-density-curves"
        ),
        "transformations": [
            "exact-stock-manufacturer-document-selection",
            "native-separated-one-bit-pdf-mask-extraction",
            "piecewise-major-gridline-axis-calibration",
            "median-per-column-curve-centerline",
            "alternate-global-affine-axis-sensitivity-check",
            "alternate-midrange-centerline-sensitivity-check",
            "linear-resampling-to-common-5-nm-grid",
            "negative-graph-excursion-clipped-to-zero",
            "bundled-per-channel-peak-scale-restoration",
            "complete-production-date-group-held-out-validation",
            "newest-20-percent-production-date-group-stress-slice",
            "outside-400-700-nm-retained-from-bundled-profile",
        ],
        "notes": (
            "Experimental non-default candidate. The source fixes normalized "
            "same-stock CMY shape, not raw instrument observations or absolute "
            "dye concentration. Independent Fujifilm editions define a source-"
            "revision envelope rather than extraction noise. Characteristic "
            "curves, sensitivity, and midscale neutral remain bundled because "
            "no calibrated exposure-to-dye-amount mapping was found."
        ),
    }
    provenance["notes"] = (
        provenance.get("notes", "").rstrip()
        + " Exact-stock Fujifilm normalized CMY source candidate generated "
        "2026-07-13; not a bundled default."
    ).strip()

    validation_script_sha256 = _sha256(Path(__file__).resolve())
    context = {
        "base_candidate_context_sha256": base_summary[
            "candidate_context_sha256"
        ],
        "curve_result_sha256": curve_report["result_sha256"],
        "curve_extraction_script_sha256": curve_report["analysis"][
            "script_sha256"
        ],
        "manufacturer_validation_script_sha256": validation_script_sha256,
        "product_pdf_sha256": product.sha256,
        "guide_pdf_sha256": guide.sha256,
        "support_nm": list(SOURCE_SUPPORT_NM),
        "amplitude_policy": "restore-bundled-per-channel-peak",
        "base_interpolation": interpolation,
        "candidate_policy_version": 1,
        "base_interpolation_selection_policy": (
            "linear-selected-as-lower-assumption; pchip-sensitivity-only"
        ),
    }
    candidate_context_sha256 = PUBLIC._canonical_json_sha256(context)
    candidate_id = (
        f"{spec.profile_slug}_public_grouped_gs0_base_fuji_normalized_cmy_"
        f"{base_summary['source_manifest_sha256'][:8]}_"
        f"{product.sha256[:8]}_{candidate_context_sha256[:8]}"
        + ("_candidate" if interpolation == "pchip" else f"_{interpolation}_candidate")
    )
    payload["info"]["name"] = (
        "Fujifilm Provia 100F (Public GS0 Base + Published Normalized CMY "
        f"{interpolation.upper()} Candidate)"
    )
    payload["metadata"]["datasource"] = (
        "Experimental non-default profile candidate. data.base_density is the "
        "group-equal exact-material public multibatch GS0 reconstruction; "
        "data.channel_density uses the normalized Provia 100F AF3-036E "
        "manufacturer graph from 400--700 nm with bundled channel peak scales. "
        "No raw public patch spectra are embedded. The channel field contains "
        "a derived published-graph array; all exposure/sensitivity/curve fields "
        "remain bundled."
    )
    payload["metadata"]["license"] = (
        payload["metadata"]["license"].rstrip()
        + " The normalized manufacturer graph is a copyrighted external source; "
        "keep this candidate local until redistribution and derivative-data "
        "permissions are reviewed."
    )
    summary = {
        "candidate_id": candidate_id,
        "candidate_context_sha256": candidate_context_sha256,
        "candidate_context": context,
        "profile_stock": base_summary["profile_stock"],
        "material": base_summary["material"],
        "measurement_kind": base_summary["measurement_kind"],
        "measurement_status": base_summary["measurement_status"],
        "source_archive_count": base_summary["source_archive_count"],
        "source_production_group_count": base_summary[
            "source_production_group_count"
        ],
        "source_production_groups": base_summary["source_production_groups"],
        "source_batch_ids": base_summary["source_batch_ids"],
        "source_manifest": base_summary["source_manifest"],
        "source_manifest_sha256": base_summary["source_manifest_sha256"],
        "bundled_data_sha256": base_summary["bundled_data_sha256"],
        "base_analysis_code_sha256": base_summary["analysis_code_sha256"],
        "analysis_software_versions": base_summary[
            "analysis_software_versions"
        ],
        "fields_changed": ["base_density", "channel_density"],
        "base_reconstruction": {
            "field": "base_density",
            "status": base_summary["provenance_status"],
            "changed_point_count": base_summary["changed_point_count"],
            "unchanged_point_count": base_summary["unchanged_point_count"],
            "mean_absolute_change_D_on_support": base_summary[
                "mean_absolute_change_D_on_support"
            ],
            "max_absolute_change_D_on_support": base_summary[
                "max_absolute_change_D_on_support"
            ],
            "interpolation": base_summary["interpolation"],
            "base_candidate_context_sha256": base_summary[
                "candidate_context_sha256"
            ],
        },
        "channel_source": {
            "primary": product_source,
            "cross_edition": guide_source,
            "primary_pdf_sha256": product.sha256,
            "cross_edition_pdf_sha256": guide.sha256,
            "curve_result_sha256": curve_report["result_sha256"],
        },
        "channel_reconstruction": channel_summary,
        "channel_semantics": (
            "manufacturer-published normalized shape; absolute peak inherited"
        ),
        "characteristic_curves_changed": False,
        "log_sensitivity_changed": False,
        "midscale_neutral_density_changed": False,
        "default_profile_modified": False,
    }
    return payload, summary


def _evaluate_combined_runtime(
    spec,
    bundled_payload: dict[str, Any],
    pchip_payload: dict[str, Any],
    linear_payload: dict[str, Any],
) -> dict[str, Any]:
    image, neutral_patch_count = PUBLIC.EVALUATION._runtime_validation_image()
    payloads = {
        "bundled": bundled_payload,
        "combined_pchip": pchip_payload,
        "combined_linear": linear_payload,
    }
    arrays: dict[str, dict[str, np.ndarray]] = {}
    profiles: dict[str, dict[str, Any]] = {}
    for name, payload in payloads.items():
        arrays[name], profiles[name] = PUBLIC._run_runtime_payload(
            spec,
            payload,
            image,
            neutral_patch_count,
        )
    repeated, _ = PUBLIC._run_runtime_payload(
        spec,
        linear_payload,
        image,
        neutral_patch_count,
    )
    repeat_max = max(
        float(np.max(np.abs(arrays["combined_linear"][name] - value)))
        for name, value in repeated.items()
    )

    def summarize_difference(reference_name: str, candidate_name: str):
        summary = PUBLIC.EVALUATION._summarize_runtime_difference(
            arrays[reference_name],
            arrays[candidate_name],
        )
        density_difference = np.abs(
            arrays[reference_name]["density_cmy"]
            - arrays[candidate_name]["density_cmy"]
        )
        summary["density_cmy_mean_absolute_difference"] = float(
            np.mean(density_difference)
        )
        summary["density_cmy_max_absolute_difference"] = float(
            np.max(density_difference)
        )
        return summary

    return {
        "route": "positive-film light-table scan",
        "patch_count": int(image.shape[0] * image.shape[1]),
        "neutral_patch_count": neutral_patch_count,
        "profiles": profiles,
        "selected_linear_repeat_max_absolute_difference": repeat_max,
        "differences": {
            "bundled_to_selected_combined_linear": (
                summarize_difference("bundled", "combined_linear")
            ),
            "bundled_to_combined_pchip": (
                summarize_difference("bundled", "combined_pchip")
            ),
            "pchip_to_linear_base_interpolation": (
                summarize_difference("combined_pchip", "combined_linear")
            ),
        },
        "interpretation": (
            "Safety, determinism, and base-interpolation sensitivity only; this "
            "does not validate exposure-to-dye mapping."
        ),
    }


def _emit_combined_provia_candidate(
    spec,
    batches,
    curve_report: dict[str, Any],
    manufacturer_result: dict[str, Any],
    candidate_output_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    base_evaluation, base_wavelengths, median_gs0_density = (
        PUBLIC._evaluate_cross_batch_base(
            spec,
            batches,
            floors=(spec.primary_floor,),
        )
    )
    base_gate = PUBLIC._evaluate_base_candidate_gate(spec, base_evaluation)
    prepared = _prepare_dataset(spec, batches)
    source_grid = np.asarray(
        curve_report["analysis"]["profile_grid_nm"],
        dtype=np.float64,
    )
    candidate_basis = _source_matrix(
        prepared["bundled_basis"],
        prepared["wavelengths"],
        curve_report["stocks"]["provia_100f"]["primary_normalized"],
        source_grid,
    )
    joint_evaluation = _joint_combined_holdout(
        spec,
        batches,
        prepared,
        candidate_basis,
    )
    joint_chronological = _joint_combined_chronological_holdout(
        spec,
        batches,
        prepared,
        candidate_basis,
    )
    joint_comparison = _model_comparison(
        joint_evaluation,
        "combined_candidate",
    )
    joint_gate = _replacement_gate(
        joint_comparison,
        joint_chronological,
        "combined_candidate",
    )
    pchip_payload, pchip_summary = _build_combined_provia_candidate(
        spec,
        batches,
        curve_report,
        base_wavelengths,
        median_gs0_density,
        interpolation="pchip",
    )
    linear_payload, linear_summary = _build_combined_provia_candidate(
        spec,
        batches,
        curve_report,
        base_wavelengths,
        median_gs0_density,
        interpolation="linear",
    )
    bundled_payload = json.loads(
        (PUBLIC.PROFILE_DIR / f"{spec.profile_slug}.json").read_text(
            encoding="utf-8"
        )
    )
    runtime = _evaluate_combined_runtime(
        spec,
        bundled_payload,
        pchip_payload,
        linear_payload,
    )
    candidate_profiles = {
        name: runtime["profiles"][name]
        for name in ("combined_pchip", "combined_linear")
    }
    pchip_base_interpolation = pchip_summary["base_reconstruction"][
        "interpolation"
    ]
    pchip_channel = pchip_summary["channel_reconstruction"]
    linear_channel = linear_summary["channel_reconstruction"]
    pchip_channels = pchip_payload["data"]["channel_density"]
    linear_channels = linear_payload["data"]["channel_density"]
    pchip_base = np.asarray(
        pchip_payload["data"]["base_density"],
        dtype=np.float64,
    )
    linear_base = np.asarray(
        linear_payload["data"]["base_density"],
        dtype=np.float64,
    )
    profile_wavelengths = np.asarray(
        pchip_payload["data"]["wavelengths"],
        dtype=np.float64,
    )
    shared_min, shared_max = pchip_base_interpolation[
        "shared_support_range_nm"
    ]
    finite_base = (
        np.isfinite(pchip_base)
        & np.isfinite(linear_base)
        & (profile_wavelengths >= shared_min)
        & (profile_wavelengths <= shared_max)
    )
    base_interpolation_delta = np.abs(
        pchip_base[finite_base] - linear_base[finite_base]
    )
    supported_wavelengths = profile_wavelengths[finite_base]
    max_interpolation_index = int(np.argmax(base_interpolation_delta))
    runtime_interpolation = runtime["differences"][
        "pchip_to_linear_base_interpolation"
    ]
    selected_runtime_difference = runtime["differences"][
        "bundled_to_selected_combined_linear"
    ]
    runtime_checks = {
        "all_candidate_arrays_finite": all(
            item["all_arrays_finite"] for item in candidate_profiles.values()
        ),
        "neutral_ramp_monotonic_non_decreasing": all(
            item["neutral_ramp_monotonic_non_decreasing"]
            for item in candidate_profiles.values()
        ),
        "selected_linear_repeat_exact": (
            runtime["selected_linear_repeat_max_absolute_difference"] == 0.0
        ),
        "base_pchip_linear_p95_difference_at_most_0_015_D": (
            float(np.quantile(base_interpolation_delta, 0.95)) <= 0.015
        ),
        "runtime_interpolation_p95_delta_e_2000_at_most_0_1": (
            runtime_interpolation["clipped_linear_srgb_delta_e_2000_p95"]
            <= 0.1
        ),
        "runtime_interpolation_max_sdr_difference_at_most_0_001": (
            runtime_interpolation["sdr_output_max_absolute_difference"]
            <= 0.001
        ),
        "exposure_to_density_mapping_exactly_unchanged": (
            selected_runtime_difference[
                "density_cmy_max_absolute_difference"
            ]
            == 0.0
        ),
        "manufacturer_channels_independent_of_base_interpolation": (
            pchip_channels == linear_channels
        ),
        "bundled_channel_peak_scale_preserved": (
            pchip_channel["channel_peak_scale_restoration"][
                "maximum_absolute_difference_D"
            ]
            <= 1e-12
            and linear_channel["channel_peak_scale_restoration"][
                "maximum_absolute_difference_D"
            ]
            <= 1e-12
        ),
        "channel_density_outside_400_700_exactly_unchanged": (
            pchip_channel["outside_source_support_exactly_unchanged"]
            and linear_channel["outside_source_support_exactly_unchanged"]
        ),
    }
    passes = bool(
        manufacturer_result["candidate_ready_for_runtime_validation"]
        and base_gate["reconstruction_passes"]
        and joint_gate["passes"]
        and all(runtime_checks.values())
    )
    gate = {
        "passes": passes,
        "manufacturer_shape_and_holdout_gate_passes": manufacturer_result[
            "candidate_ready_for_runtime_validation"
        ],
        "multibatch_base_reconstruction_gate_passes": base_gate[
            "reconstruction_passes"
        ],
        "joint_two_field_holdout_gate_passes": joint_gate["passes"],
        "runtime_status": "passed" if all(runtime_checks.values()) else "failed",
        "runtime_checks": runtime_checks,
        "default_replacement_authorized": False,
        "policy_origin": "Spektrafilm conservative engineering policy",
        "threshold_status": (
            "Explicit local engineering thresholds, not ISO limits or "
            "manufacturer specifications"
        ),
    }
    linear_summary["combined_candidate_gate"] = gate
    linear_summary["runtime_validation"] = runtime
    linear_summary["selected_base_interpolation"] = {
        "method": "linear",
        "reason": (
            "The public values are tabulated at 10 nm after an earlier source "
            "interpolation. Linear 10-to-5 nm resampling is the lower-assumption, "
            "non-overshooting choice; PCHIP is retained only as sensitivity."
        ),
        "pchip_vs_linear_p95_absolute_difference_D": float(
            np.quantile(base_interpolation_delta, 0.95)
        ),
        "pchip_vs_linear_max_absolute_difference_D": pchip_base_interpolation[
            "pchip_vs_linear_max_absolute_difference_D"
        ],
        "maximum_difference": {
            "wavelength_nm": float(
                supported_wavelengths[max_interpolation_index]
            ),
            "pchip_D": float(pchip_base[finite_base][max_interpolation_index]),
            "linear_D": float(linear_base[finite_base][max_interpolation_index]),
            "absolute_difference_D": float(
                base_interpolation_delta[max_interpolation_index]
            ),
        },
    }
    linear_summary["output"] = None
    if passes:
        linear_summary["output"] = PUBLIC.EVALUATION._write_candidate_payload(
            linear_payload,
            candidate_output_dir,
            candidate_id=linear_summary["candidate_id"],
        )
    base_reconstruction_subgate = {
        key: value
        for key, value in base_gate.items()
        if key
        not in {
            "passes",
            "runtime_status",
            "candidate_may_be_emitted",
        }
    }
    base_reconstruction_subgate.update(
        {
            "passes": base_gate["reconstruction_passes"],
            "scope": (
                "reconstruction-only subgate; runtime is evaluated by the "
                "combined two-field candidate gate"
            ),
        }
    )
    return linear_summary, {
        "base_reconstruction_subgate": base_reconstruction_subgate,
        "joint_two_field_validation": {
            "evaluation": joint_evaluation,
            "comparison_vs_bundled_default": joint_comparison,
            "chronological_holdout": joint_chronological,
            "gate": joint_gate,
        },
        "pchip_sensitivity_candidate": pchip_summary,
        "runtime": runtime,
        "gate": gate,
    }


def _replacement_gate(
    comparison: dict[str, Any],
    chronological: dict[str, Any],
    candidate_name: str,
):
    metric_names = tuple(comparison["micro_improvement_percent"])
    chronological_micro = PUBLIC._metric_improvements(
        chronological["metrics"]["bundled"],
        chronological["metrics"][candidate_name],
    )
    chronological_macro = PUBLIC._metric_improvements(
        chronological["production_group_macro_metrics"]["bundled"],
        chronological["production_group_macro_metrics"][candidate_name],
    )
    passes = bool(
        all(
            comparison["micro_improvement_percent"][metric] > 0.0
            and comparison["production_group_macro_improvement_percent"][metric]
            > 0.0
            for metric in metric_names
        )
        and all(
            comparison["maximum_production_group_regression_percent"][metric]
            <= 5.0
            for metric in metric_names
        )
        and all(
            comparison["production_group_sign_test_p_values"][metric] <= 0.05
            for metric in metric_names
        )
        and all(
            chronological_micro[metric] > 0.0
            and chronological_macro[metric] > 0.0
            for metric in metric_names
        )
    )
    return {
        "passes": passes,
        "all_micro_and_group_macro_metrics_must_improve": True,
        "maximum_single_group_regression_percent": 5.0,
        "maximum_production_group_sign_test_p_value": 0.05,
        "production_group_sign_test_p_values": comparison[
            "production_group_sign_test_p_values"
        ],
        "chronological_micro_improvement_percent": chronological_micro,
        "chronological_group_macro_improvement_percent": chronological_macro,
        "default_replacement_authorized": False,
        "chronological_slice_is_independent_replication": False,
        "policy_origin": "Spektrafilm conservative engineering policy",
    }


def _evaluate_stock(spec, batches, curve_report, paths):
    prepared = _prepare_dataset(spec, batches)
    curve_stock = curve_report["stocks"][spec.key]
    source_grid = np.asarray(curve_report["analysis"]["profile_grid_nm"])
    bases = {
        "bundled": prepared["bundled_basis"],
        "manufacturer_primary": _source_matrix(
            prepared["bundled_basis"],
            prepared["wavelengths"],
            curve_stock["primary_normalized"],
            source_grid,
        ),
        "manufacturer_cross_edition": _source_matrix(
            prepared["bundled_basis"],
            prepared["wavelengths"],
            curve_stock["secondary_normalized"],
            source_grid,
        ),
    }
    if spec.key == "provia_100f":
        extraction_variants = {
            "manufacturer_primary_affine_axis": CURVES._normalized(
                CURVES._extract_provia_product_curves(
                    paths,
                    affine_axis=True,
                )["channels"]
            ),
            "manufacturer_primary_midrange": CURVES._normalized(
                CURVES._extract_provia_product_curves(
                    paths,
                    center_method="midrange",
                )["channels"]
            ),
            "manufacturer_primary_affine_midrange": CURVES._normalized(
                CURVES._extract_provia_product_curves(
                    paths,
                    affine_axis=True,
                    center_method="midrange",
                )["channels"]
            ),
        }
    else:
        extraction_variants = {
            "manufacturer_primary_affine_axis": CURVES._normalized(
                CURVES._extract_vector_curves(
                    CURVES.VELVIA_PRODUCT_VECTOR,
                    paths,
                    samples_per_segment=8192,
                    affine_axis=True,
                )["channels"]
            ),
            "manufacturer_primary_lower_sampling": CURVES._normalized(
                CURVES._extract_vector_curves(
                    CURVES.VELVIA_PRODUCT_VECTOR,
                    paths,
                    samples_per_segment=2048,
                )["channels"]
            ),
        }
    for model_name, normalized in extraction_variants.items():
        bases[model_name] = _source_matrix(
            prepared["bundled_basis"],
            prepared["wavelengths"],
            normalized,
            source_grid,
        )
    effective_metadata = None
    if spec.key == "velvia_100":
        effective_basis, effective_metadata = _effective_candidate_matrix(
            prepared["bundled_basis"],
            prepared["wavelengths"],
        )
        if effective_basis is not None:
            bases["batch_effective_candidate"] = effective_basis

    evaluation = _full_group_holdout(spec, batches, prepared, bases)
    chronological = _chronological_holdout(spec, batches, prepared, bases)
    comparisons = {
        name: _model_comparison(evaluation, name)
        for name in bases
        if name != "bundled"
    }
    source_gate = _shape_provenance_gate(curve_stock)
    replacement_gate = _replacement_gate(
        comparisons["manufacturer_primary"],
        chronological,
        "manufacturer_primary",
    )
    extraction_variant_gates = {
        model_name: _replacement_gate(
            comparisons[model_name],
            chronological,
            model_name,
        )
        for model_name in extraction_variants
    }
    extraction_uncertainty_passes = all(
        gate["passes"] for gate in extraction_variant_gates.values()
    )
    candidate_ready_for_runtime = bool(
        source_gate["passes"]
        and replacement_gate["passes"]
        and extraction_uncertainty_passes
    )
    decision = (
        "build a local source-derived candidate and run runtime gates"
        if candidate_ready_for_runtime
        else
        "retain bundled channel numbers; same-stock source derivation is "
        "quantitatively supported and direct replacement did not clear the "
        "held-out improvement gate"
        if source_gate["passes"] and not replacement_gate["passes"]
        else "manufacturer source candidate requires further review"
    )
    return {
        "material": spec.material,
        "profile": spec.profile_slug,
        "archive_count": len(batches),
        "production_group_count": len(prepared["production_groups"]),
        "wavelengths_nm": prepared["wavelengths"].tolist(),
        "fixed_basis_semantics": (
            "manufacturer peak-normalized Y/M/C shapes with bundled channel "
            "peak scales restored; source support replaces 400-700 nm only"
        ),
        "manufacturer_channel_values_outside_400_700": (
            "bundled and unchanged"
        ),
        "shape_provenance_gate": source_gate,
        "fixed_manufacturer_replacement_gate": replacement_gate,
        "extraction_uncertainty_gate": {
            "passes": extraction_uncertainty_passes,
            "variants": extraction_variant_gates,
            "meaning": (
                "The replacement decision must survive alternate axis "
                "calibration and curve-center extraction or sampling."
            ),
        },
        "candidate_ready_for_runtime_validation": candidate_ready_for_runtime,
        "decision": decision,
        "models": evaluation["micro_metrics"],
        "production_group_macro_models": evaluation[
            "production_group_macro_metrics"
        ],
        "comparisons_vs_bundled": comparisons,
        "chronological_holdout": chronological,
        "effective_candidate_metadata": effective_metadata,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=PUBLIC.DEFAULT_CACHE_DIR,
    )
    parser.add_argument(
        "--pdf-dir",
        type=Path,
        default=CURVES.DEFAULT_PDF_DIR,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument(
        "--emit-candidate",
        action="store_true",
        help=(
            "Build the Provia combined Dmin + manufacturer-CMY candidate, "
            "run runtime gates, and write it only if every gate passes."
        ),
    )
    parser.add_argument(
        "--candidate-output-dir",
        type=Path,
        default=DEFAULT_CANDIDATE_OUTPUT_DIR,
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=SOURCE_CANDIDATE_MANIFEST,
    )
    args = parser.parse_args()

    paths = {
        key: CURVES._ensure_pdf(spec, args.pdf_dir, False)
        for key, spec in CURVES.PDF_SPECS.items()
    }
    curve_report = CURVES.build_report(
        paths,
        CURVES.DEFAULT_OUTPUT_DIR,
    )
    archives, acquisition = PUBLIC._load_or_download_archives(
        args.cache_dir,
        download=False,
        refresh=False,
        max_workers=args.max_workers,
    )
    datasets, exclusions = PUBLIC._collect_exact_material_batches(archives)

    results = {}
    for spec in PUBLIC.DATASET_SPECS:
        if spec.key not in {"provia_100f", "velvia_100"}:
            continue
        results[spec.key] = _evaluate_stock(
            spec,
            datasets[spec.material],
            curve_report,
            paths,
        )

    candidate_run = None
    candidate_manifest = None
    if args.emit_candidate:
        provia_spec = next(
            spec for spec in PUBLIC.DATASET_SPECS if spec.key == "provia_100f"
        )
        candidate_summary, candidate_details = _emit_combined_provia_candidate(
            provia_spec,
            datasets[provia_spec.material],
            curve_report,
            results["provia_100f"],
            args.candidate_output_dir,
        )
        candidate_run = {
            "summary": candidate_summary,
            "details": candidate_details,
        }
        results["provia_100f"]["combined_source_candidate"] = candidate_run
        gate = candidate_details["gate"]
        authoritative = []
        rejected = []
        manifest_entry = {
            "profile": provia_spec.profile_slug,
            "candidate_id": candidate_summary["candidate_id"],
            "candidate_kind": "multibatch_dmin_plus_manufacturer_cmy",
            "candidate_context_sha256": candidate_summary[
                "candidate_context_sha256"
            ],
            "gate_passes": gate["passes"],
            "output": candidate_summary["output"],
        }
        if gate["passes"]:
            authoritative.append(manifest_entry)
        else:
            rejected.append(manifest_entry)
        candidate_manifest = {
            "created": "2026-07-13",
            "authoritative_for_this_run": authoritative,
            "rejected_or_not_emitted": rejected,
            "bundled_defaults_modified": False,
            "default_replacement_authorized": False,
            "analysis_code_sha256": _sha256(Path(__file__).resolve()),
            "curve_extraction_code_sha256": _sha256(CURVE_SCRIPT),
            "curve_result_sha256": curve_report["result_sha256"],
            "warning": (
                "This manifest authorizes only a local evidence candidate. "
                "It does not authorize replacing or redistributing a bundled "
                "profile."
            ),
        }
        args.candidate_manifest.parent.mkdir(parents=True, exist_ok=True)
        args.candidate_manifest.write_text(
            json.dumps(
                candidate_manifest,
                indent=2,
                sort_keys=True,
                allow_nan=False,
            )
            + "\n"
        )

    report = {
        "created": "2026-07-13",
        "scope": {
            "bundled_profiles_modified": False,
            "candidate_profiles_emitted": bool(
                candidate_run is not None
                and candidate_run["details"]["gate"]["passes"]
            ),
            "closed_evidence": True,
            "contacted_external_parties": False,
            "new_physical_film_required": False,
        },
        "analysis": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "public_batch_script_sha256": _sha256(PUBLIC_BATCH_SCRIPT),
            "curve_extraction_script_sha256": _sha256(CURVE_SCRIPT),
            "held_out_unit": "complete PROD_DATE target-production-date proxy",
            "patch_coefficients": "NNLS fitted independently from held-out spectra",
            "base": (
                "group-equal GS0 median trained only from non-held-out groups"
            ),
        },
        "source_curve_result_sha256": curve_report["result_sha256"],
        "public_archive_acquisition": acquisition,
        "relevant_exclusions": [
            exclusion
            for exclusion in exclusions
            if exclusion.get("material")
            in {
                "Fujichrome Provia 100F (RDP III)",
                "Fujichrome Velvia 100 (RVP 100)",
            }
        ],
        "stocks": results,
    }
    if candidate_manifest is not None:
        report["candidate_manifest"] = {
            "path": str(args.candidate_manifest.resolve()),
            "sha256": _sha256(args.candidate_manifest),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    print(
        json.dumps(
            {
                "output": str(args.output.resolve()),
                "sha256": _sha256(args.output),
                "decisions": {
                    stock: result["decision"] for stock, result in results.items()
                },
                "candidate_manifest": (
                    {
                        "path": str(args.candidate_manifest.resolve()),
                        "sha256": _sha256(args.candidate_manifest),
                    }
                    if candidate_manifest is not None
                    else None
                ),
                "bundled_profiles_modified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
