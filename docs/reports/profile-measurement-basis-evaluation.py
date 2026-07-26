#!/usr/bin/env python3
"""Evaluate bundled film bases against external measured target spectra.

By default the script is read-only. It reads the two same-stock ColorAid IT8
target batches from a user-supplied downloads directory and prints a JSON
report. Passing ``--candidate-output-dir`` explicitly writes local experimental
profile copies whose base density is reconstructed from the measured GS0 Dmin
patch. It never writes or redistributes the external source spectra.

The fitted NMF components are effective full-film density generators, not
identified analytical CMY dyes. They are used only as a cross-validation
benchmark for the bundled channel-density shapes.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import colour
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import linear_sum_assignment, nnls


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = PROJECT_ROOT / "src" / "spektrafilm" / "data" / "profiles"
DEFAULT_DOWNLOADS_ROOT = Path.home() / "Downloads"
DEFAULT_SEED = 20260711
PRIMARY_TRANSMITTANCE_FLOOR = 1e-3
CANDIDATE_CREATED = "2026-07-12"
COLORAID_TARGETS_URL = "http://www.colorreference.de/targets/index.html"

DATASETS = (
    ("F240222", "fujifilm_provia_100f"),
    ("N230513", "fujifilm_velvia_100"),
)

DMIN_EVIDENCE = {
    "F240222": {
        "source_id": "COLORAID_F240222_GS0_DMIN",
        "material": "Fujichrome Provia 100F (RDP III)",
    },
    "N230513": {
        "source_id": "COLORAID_N230513_GS0_DMIN",
        "material": "Fujichrome Velvia 100 (RVP 100)",
    },
}

# Approximate manual digitization of Scarpace & Friederichs (1978), Figure 5.
# Columns are Y, M, C, normalized to unit peak. Typical reading uncertainty is
# about 0.015, rising to 0.02-0.03 around overlaps and heavy plot marks.
K64_FIGURE_5_WAVELENGTHS = np.arange(400.0, 701.0, 20.0)
K64_FIGURE_5_YMC = np.array(
    [
        [0.58, 0.38, 0.18],
        [0.84, 0.30, 0.12],
        [1.00, 0.24, 0.06],
        [0.93, 0.23, 0.03],
        [0.64, 0.37, 0.02],
        [0.31, 0.62, 0.02],
        [0.12, 0.89, 0.02],
        [0.04, 1.00, 0.04],
        [0.02, 0.88, 0.08],
        [0.00, 0.61, 0.18],
        [0.00, 0.34, 0.40],
        [0.00, 0.18, 0.77],
        [0.00, 0.10, 1.00],
        [0.00, 0.06, 0.89],
        [0.00, 0.04, 0.66],
        [0.00, 0.02, 0.47],
    ],
    dtype=float,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_it8_tsv(path: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="latin1").splitlines()
    header_index = next(
        index
        for index, line in enumerate(lines)
        if line.startswith("ID\tName\tX\tY\tZ")
    )
    rows = list(csv.DictReader(lines[header_index:], delimiter="\t"))
    spectral_fields = [
        field
        for field in rows[0]
        if field is not None and field.endswith("nm")
    ]
    wavelengths = np.array([float(field[:-2]) for field in spectral_fields])
    names = np.array([row["Name"].strip() for row in rows])
    transmittance = np.array(
        [[float(row[field]) for field in spectral_fields] for row in rows],
        dtype=float,
    )
    if transmittance.shape != (288, 41):
        raise ValueError(
            f"Expected 288 patches by 41 bands in {path}, got "
            f"{transmittance.shape}"
        )
    if not np.all((transmittance > 0.0) & (transmittance <= 1.0)):
        raise ValueError(f"Invalid transmittance values in {path}")
    return names, wavelengths, transmittance


def _resample_gs0_dmin_to_profile_grid(
    profile_wavelengths: np.ndarray,
    current_base: np.ndarray,
    channel_density: np.ndarray,
    measured_wavelengths: np.ndarray,
    measured_dmin: np.ndarray,
    *,
    interpolation: str = "pchip",
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    """Reconstruct a local Dmin candidate on the profile wavelength grid.

    The measured Dmin replaces the base only where all three bundled dye
    channels are finite. Outside that shared support the current base is kept
    unchanged and remains inherited rather than measurement-derived.
    """

    if interpolation not in {"pchip", "linear"}:
        raise ValueError("Interpolation must be 'pchip' or 'linear'")

    profile_wavelengths = np.asarray(profile_wavelengths, dtype=float)
    current_base = np.asarray(current_base, dtype=float)
    channel_density = np.asarray(channel_density, dtype=float)
    measured_wavelengths = np.asarray(measured_wavelengths, dtype=float)
    measured_dmin = np.asarray(measured_dmin, dtype=float)

    if profile_wavelengths.ndim != 1 or current_base.shape != profile_wavelengths.shape:
        raise ValueError("Profile wavelengths and base must be matching 1D arrays")
    if channel_density.shape != (len(profile_wavelengths), 3):
        raise ValueError("Channel density must have shape (wavelengths, 3)")
    if measured_wavelengths.ndim != 1 or measured_dmin.shape != measured_wavelengths.shape:
        raise ValueError("Measured wavelengths and Dmin must be matching 1D arrays")
    if len(measured_wavelengths) < 2 or np.any(np.diff(measured_wavelengths) <= 0):
        raise ValueError("Measured wavelengths must be strictly increasing")
    if not np.all(np.isfinite(measured_dmin)) or np.any(measured_dmin < 0.0):
        raise ValueError("Measured Dmin must be finite and non-negative")

    shared_support = np.all(np.isfinite(channel_density), axis=1) & np.isfinite(
        current_base
    )
    if not np.any(shared_support):
        raise ValueError("Profile has no shared finite CMY/base support")
    supported_wavelengths = profile_wavelengths[shared_support]
    if (
        supported_wavelengths[0] < measured_wavelengths[0]
        or supported_wavelengths[-1] > measured_wavelengths[-1]
    ):
        raise ValueError("Measured Dmin does not cover the shared profile support")

    pchip_values = PchipInterpolator(
        measured_wavelengths,
        measured_dmin,
        extrapolate=False,
    )(supported_wavelengths)
    linear_values = np.interp(
        supported_wavelengths,
        measured_wavelengths,
        measured_dmin,
    )
    selected_values = pchip_values if interpolation == "pchip" else linear_values
    if not np.all(np.isfinite(selected_values)) or np.any(selected_values < 0.0):
        raise ValueError(f"{interpolation} produced an invalid Dmin candidate")

    candidate = current_base.copy()
    candidate[shared_support] = selected_values
    interpolation_check = {
        "method": interpolation,
        "source_interval_nm": float(np.median(np.diff(measured_wavelengths))),
        "target_interval_nm": float(np.median(np.diff(profile_wavelengths))),
        "shared_support_point_count": int(np.sum(shared_support)),
        "shared_support_range_nm": [
            float(supported_wavelengths[0]),
            float(supported_wavelengths[-1]),
        ],
        "pchip_vs_linear_mean_absolute_difference_D": float(
            np.mean(np.abs(pchip_values - linear_values))
        ),
        "pchip_vs_linear_max_absolute_difference_D": float(
            np.max(np.abs(pchip_values - linear_values))
        ),
        "outside_shared_support": "retained from bundled base_density",
    }
    return candidate, shared_support, interpolation_check


def _build_gs0_dmin_candidate_payload(
    profile_slug: str,
    batch: str,
    measured_wavelengths: np.ndarray,
    measured_dmin: np.ndarray,
    source_sha256: str,
    *,
    interpolation: str = "pchip",
) -> tuple[dict[str, Any], dict[str, Any]]:
    profile_path = PROFILE_DIR / f"{profile_slug}.json"
    with profile_path.open(encoding="utf-8") as handle:
        original = json.load(handle)
    candidate_payload = copy.deepcopy(original)

    profile_wavelengths = np.asarray(original["data"]["wavelengths"], dtype=float)
    current_base = np.asarray(original["data"]["base_density"], dtype=float)
    channel_density = np.asarray(original["data"]["channel_density"], dtype=float)
    candidate_base, shared_support, interpolation_check = (
        _resample_gs0_dmin_to_profile_grid(
            profile_wavelengths,
            current_base,
            channel_density,
            measured_wavelengths,
            measured_dmin,
            interpolation=interpolation,
        )
    )

    evidence = DMIN_EVIDENCE[batch]
    source_id = evidence["source_id"]
    provenance = candidate_payload["metadata"]["provenance"]
    provenance["measurement_status"] = "partial-instrument-data"
    provenance["source_references"][source_id] = (
        f"Wolf Faust/ColorAid {batch} batch-average spectral reference data; "
        f"material {evidence['material']}; GS0 identified by the target vendor "
        f"as Dmin; external file SHA-256 {source_sha256}; official target index "
        f"{COLORAID_TARGETS_URL}; accessed 2026-07-11."
    )
    previous_base_sources = provenance["fields"]["base_density"].get("sources", [])
    interpolation_transformation = (
        "pchip-10-nm-to-5-nm"
        if interpolation == "pchip"
        else "linear-10-nm-to-5-nm"
    )
    provenance["fields"]["base_density"] = {
        "origin": "published-measurement",
        "status": "reconstructed",
        "sources": list(dict.fromkeys([*previous_base_sources, source_id])),
        "derived_from": f"bundled:{profile_slug}.data.base_density",
        "transformations": [
            "external-batch-average-gs0-dmin-patch",
            "transmittance-to-base10-density",
            interpolation_transformation,
            "shared-finite-cmy-support-replacement",
            "outside-shared-cmy-support-retained-from-bundled-profile",
        ],
        "notes": (
            "Experimental candidate only. ColorAid identifies GS0 as the target "
            "Dmin patch. ISO Dmin is the maximum-transmittance product endpoint; "
            "it is not necessarily neutral and is not a claim of bare clear base. "
            "The external 10 nm batch average is not raw 3 nm instrument output, "
            "and redistribution/derivative licensing remains unconfirmed."
        ),
    }
    provenance["notes"] = (
        provenance.get("notes", "").rstrip()
        + " Experimental GS0 Dmin candidate generated 2026-07-12; not a bundled default."
    ).strip()

    original_stock = original["info"]["stock"]
    candidate_id = (
        f"{original_stock}_gs0_dmin_candidate"
        if interpolation == "pchip"
        else f"{original_stock}_gs0_dmin_{interpolation}_candidate"
    )
    # Keep the real stock identifier so runtime stock-specific parameters are
    # exactly the same as the bundled source profile. Candidate identity lives
    # in the local filename and metadata, not in the physical stock name.
    candidate_payload["info"]["stock"] = original_stock
    candidate_payload["info"]["name"] = (
        f"{original['info']['name']} (GS0 Dmin {interpolation.upper()} Candidate)"
    )
    candidate_payload["metadata"]["created"] = CANDIDATE_CREATED
    candidate_payload["metadata"]["license"] = (
        original["metadata"]["license"].rstrip()
        + " This local experimental candidate contains a reconstructed field "
        "derived from external measurement data; do not redistribute it until "
        "the external-data and derivative-work permissions are confirmed."
    )
    candidate_payload["metadata"]["datasource"] = (
        "Experimental non-default profile candidate. Only base_density within "
        "the shared finite CMY support is reconstructed from an external "
        f"same-product ColorAid {batch} GS0 Dmin spectrum. Other fields remain "
        "the bundled processed profile. Source spectra are not embedded."
    )
    candidate_payload["data"]["base_density"] = candidate_base.tolist()

    changed = candidate_base - current_base
    candidate_summary = {
        "candidate_id": candidate_id,
        "profile_stock": original_stock,
        "source_profile": original_stock,
        "source_batch": batch,
        "field_changed": "base_density",
        "default_profile_modified": False,
        "profile_grid_point_count": int(len(profile_wavelengths)),
        "changed_point_count": int(np.sum(shared_support)),
        "unchanged_point_count": int(np.sum(~shared_support)),
        "mean_absolute_change_D_on_support": float(
            np.mean(np.abs(changed[shared_support]))
        ),
        "max_absolute_change_D_on_support": float(
            np.max(np.abs(changed[shared_support]))
        ),
        "interpolation": interpolation_check,
        "provenance_status": "reconstructed",
        "measurement_status": provenance["measurement_status"],
    }
    return candidate_payload, candidate_summary


def _write_candidate_payload(
    candidate_payload: dict[str, Any],
    output_dir: Path,
    *,
    candidate_id: str,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{candidate_id}.json"
    output_path.write_text(
        json.dumps(candidate_payload, indent=4, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return {
        "path": str(output_path.resolve()),
        "sha256": _sha256(output_path),
    }


def _load_profile_basis(
    slug: str,
    measured_wavelengths: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    with (PROFILE_DIR / f"{slug}.json").open(encoding="utf-8") as handle:
        data = json.load(handle)["data"]

    wavelengths = np.asarray(data["wavelengths"], dtype=float)
    channels = np.asarray(data["channel_density"], dtype=float)
    base = np.asarray(data["base_density"], dtype=float)
    joint_finite = np.all(np.isfinite(channels), axis=1) & np.isfinite(base)
    lower = wavelengths[joint_finite].min()
    upper = wavelengths[joint_finite].max()
    measured_mask = (
        (measured_wavelengths >= lower) & (measured_wavelengths <= upper)
    )
    selected_wavelengths = measured_wavelengths[measured_mask]
    selected_channels = np.column_stack(
        [
            np.interp(
                selected_wavelengths,
                wavelengths[joint_finite],
                channels[joint_finite, channel],
            )
            for channel in range(3)
        ]
    )
    selected_base = np.interp(
        selected_wavelengths,
        wavelengths[joint_finite],
        base[joint_finite],
    )
    return measured_mask, selected_wavelengths, selected_channels, selected_base


def _fit_coefficients_and_predict(
    density: np.ndarray,
    transmittance: np.ndarray,
    basis: np.ndarray,
    base: np.ndarray,
    transmittance_floor: float,
) -> np.ndarray:
    predictions = np.empty_like(density)
    for patch_index, (patch_density, patch_transmittance) in enumerate(
        zip(density, transmittance, strict=True)
    ):
        valid = patch_transmittance >= transmittance_floor
        coefficients = nnls(
            basis[valid],
            patch_density[valid] - base[valid],
            maxiter=1000,
        )[0]
        predictions[patch_index] = base + basis @ coefficients
    return predictions


def _normalize_basis(basis: np.ndarray) -> np.ndarray:
    return basis / np.maximum(np.max(basis, axis=0), 1e-12)


def _fit_effective_nmf_basis(
    density: np.ndarray,
    transmittance: np.ndarray,
    base: np.ndarray,
    initial_basis: np.ndarray,
    transmittance_floor: float,
    *,
    random_seed: int | None,
    iterations: int,
) -> tuple[np.ndarray, float]:
    residual = density - base
    if random_seed is None:
        basis = np.maximum(initial_basis, 0.0).copy()
    else:
        generator = np.random.default_rng(random_seed)
        patch_indices = generator.choice(len(density), 3, replace=False)
        basis = np.maximum(residual[patch_indices].T, 1e-8)
    basis = _normalize_basis(basis)
    coefficients = np.zeros((len(density), 3), dtype=float)

    for _ in range(iterations):
        for patch_index in range(len(density)):
            valid = transmittance[patch_index] >= transmittance_floor
            coefficients[patch_index] = nnls(
                basis[valid],
                residual[patch_index, valid],
                maxiter=1000,
            )[0]

        for wavelength_index in range(density.shape[1]):
            valid = transmittance[:, wavelength_index] >= transmittance_floor
            basis[wavelength_index] = nnls(
                coefficients[valid],
                residual[valid, wavelength_index],
                maxiter=1000,
            )[0]

        # A one-bin [1, 2, 1] smoother prevents noise-floor wiggles from being
        # rewarded as dye structure while retaining the 10 nm data resolution.
        basis[1:-1] = (
            basis[:-2] + 2.0 * basis[1:-1] + basis[2:]
        ) / 4.0
        scales = np.maximum(np.max(basis, axis=0), 1e-12)
        basis /= scales
        coefficients *= scales

    prediction = base + coefficients @ basis.T
    valid = transmittance >= transmittance_floor
    training_rmse = float(
        np.sqrt(np.mean(np.square(prediction[valid] - density[valid])))
    )
    return basis, training_rmse


def _align_basis_to_profile(
    candidate: np.ndarray,
    profile_basis: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    candidate_unit = candidate / np.maximum(
        np.linalg.norm(candidate, axis=0), 1e-12
    )
    profile_unit = profile_basis / np.maximum(
        np.linalg.norm(profile_basis, axis=0), 1e-12
    )
    similarities = candidate_unit.T @ profile_unit
    candidate_indices, profile_indices = linear_sum_assignment(-similarities)
    order = np.empty(3, dtype=int)
    order[profile_indices] = candidate_indices
    return candidate[:, order], similarities[order, np.arange(3)]


def _spectral_to_lab(
    wavelengths: np.ndarray,
    transmittance: np.ndarray,
) -> np.ndarray:
    colour_mask = (wavelengths >= 400.0) & (wavelengths <= 700.0)
    selected_wavelengths = wavelengths[colour_mask]
    selected_transmittance = transmittance[:, colour_mask]
    shape = colour.SpectralShape(
        float(selected_wavelengths[0]),
        float(selected_wavelengths[-1]),
        10.0,
    )
    cmfs = colour.MSDS_CMFS[
        "CIE 1931 2 Degree Standard Observer"
    ].copy().align(shape).values
    illuminant = colour.SDS_ILLUMINANTS["D50"].copy().align(shape).values
    normalization = 100.0 / np.sum(illuminant * cmfs[:, 1])

    def integrate(values: np.ndarray) -> np.ndarray:
        return normalization * np.einsum(
            "nw,w,wc->nc",
            values,
            illuminant,
            cmfs,
        )

    white_xyz = integrate(np.ones((1, len(selected_wavelengths))))[0] / 100.0
    white_xy = colour.XYZ_to_xy(white_xyz)
    xyz = integrate(selected_transmittance) / 100.0
    return colour.XYZ_to_Lab(xyz, white_xy)


def _summarize_predictions(
    wavelengths: np.ndarray,
    measured_transmittance: np.ndarray,
    measured_density: np.ndarray,
    predicted_density: np.ndarray,
    transmittance_floor: float,
) -> dict[str, Any]:
    valid = measured_transmittance >= transmittance_floor
    predicted_transmittance = np.power(
        10.0,
        -np.maximum(predicted_density, 0.0),
    )
    measured_lab = _spectral_to_lab(wavelengths, measured_transmittance)
    predicted_lab = _spectral_to_lab(wavelengths, predicted_transmittance)
    delta_e = colour.delta_E(measured_lab, predicted_lab, method="CIE 2000")
    return {
        "density_rmse_D": float(
            np.sqrt(
                np.mean(
                    np.square(predicted_density[valid] - measured_density[valid])
                )
            )
        ),
        "transmittance_rmse_percentage_points": float(
            100.0
            * np.sqrt(
                np.mean(
                    np.square(
                        predicted_transmittance[valid]
                        - measured_transmittance[valid]
                    )
                )
            )
        ),
        "delta_e_2000_median": float(np.median(delta_e)),
        "delta_e_2000_mean": float(np.mean(delta_e)),
        "delta_e_2000_p95": float(np.quantile(delta_e, 0.95)),
    }


def _metric_improvement_percent(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, float]:
    improvements: dict[str, float] = {}
    for metric_name in (
        "density_rmse_D",
        "transmittance_rmse_percentage_points",
        "delta_e_2000_median",
        "delta_e_2000_mean",
        "delta_e_2000_p95",
    ):
        baseline_value = float(baseline[metric_name])
        candidate_value = float(candidate[metric_name])
        improvements[metric_name] = float(
            100.0 * (baseline_value - candidate_value) / baseline_value
        )
    return improvements


def _evaluate_gs0_dmin_candidate(
    names: np.ndarray,
    wavelengths: np.ndarray,
    transmittance: np.ndarray,
    density: np.ndarray,
    profile_basis: np.ndarray,
    profile_base: np.ndarray,
    gs0_dmin: np.ndarray,
    transmittance_floors: tuple[float, ...],
) -> dict[str, Any]:
    calibration_mask = names == "GS0"
    if int(np.sum(calibration_mask)) != 1:
        raise ValueError("Expected exactly one GS0 calibration patch")
    evaluation_mask = ~calibration_mask
    gray_evaluation_mask = np.array(
        [name.startswith("GS") and name != "GS0" for name in names],
        dtype=bool,
    )

    floor_results: dict[str, Any] = {}
    for transmittance_floor in transmittance_floors:
        model_results: dict[str, Any] = {}
        for model_name, base in (
            ("bundled_base", profile_base),
            ("measured_gs0_dmin_candidate", gs0_dmin),
        ):
            prediction = _fit_coefficients_and_predict(
                density[evaluation_mask],
                transmittance[evaluation_mask],
                profile_basis,
                base,
                transmittance_floor,
            )
            gray_prediction = _fit_coefficients_and_predict(
                density[gray_evaluation_mask],
                transmittance[gray_evaluation_mask],
                profile_basis,
                base,
                transmittance_floor,
            )
            model_results[model_name] = {
                "all_non_calibration_patches": _summarize_predictions(
                    wavelengths,
                    transmittance[evaluation_mask],
                    density[evaluation_mask],
                    prediction,
                    transmittance_floor,
                ),
                "gray_patches_gs1_to_gs23": _summarize_predictions(
                    wavelengths,
                    transmittance[gray_evaluation_mask],
                    density[gray_evaluation_mask],
                    gray_prediction,
                    transmittance_floor,
                ),
            }

        baseline = model_results["bundled_base"]
        candidate = model_results["measured_gs0_dmin_candidate"]
        floor_results[f"{transmittance_floor:g}"] = {
            "models": model_results,
            "candidate_improvement_percent": {
                "all_non_calibration_patches": _metric_improvement_percent(
                    baseline["all_non_calibration_patches"],
                    candidate["all_non_calibration_patches"],
                ),
                "gray_patches_gs1_to_gs23": _metric_improvement_percent(
                    baseline["gray_patches_gs1_to_gs23"],
                    candidate["gray_patches_gs1_to_gs23"],
                ),
            },
        }

    return {
        "calibration_patch": "GS0",
        "calibration_patch_excluded_from_evaluation": True,
        "evaluation_patch_count": int(np.sum(evaluation_mask)),
        "gray_evaluation_patch_count": int(np.sum(gray_evaluation_mask)),
        "candidate_changes_only": "base_density",
        "channel_density": "bundled and unchanged",
        "results_by_transmittance_floor": floor_results,
    }


def _runtime_validation_image() -> tuple[np.ndarray, int]:
    """Return deterministic neutral and colour patches for film-scan QA."""

    neutral_levels = np.geomspace(0.003, 4.0, 32)
    neutral = np.repeat(neutral_levels[:, None], 3, axis=1)
    colour_levels = (0.02, 0.18, 1.0, 2.0)
    colour_cube = np.array(
        [
            (red, green, blue)
            for red in colour_levels
            for green in colour_levels
            for blue in colour_levels
        ],
        dtype=float,
    )
    patches = np.vstack((neutral, colour_cube))
    return patches.reshape(8, 12, 3), len(neutral)


def _runtime_candidate_params(profile_slug: str, payload: dict[str, Any]):
    """Build identical deterministic params around one injected profile."""

    from spektrafilm.profiles.io import profile_from_dict
    from spektrafilm.runtime.params_builder import digest_params, init_params
    from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec

    params = init_params(
        film_profile=profile_slug,
        print_profile="kodak_portra_endura",
    )
    params.film = profile_from_dict(payload)
    if params.film.info.stock != profile_slug:
        raise ValueError(
            "Runtime candidate must retain the physical source stock identifier"
        )
    params.debug.lut_mode = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.neutral_print_filters_from_database = False
    params.settings.hdr_route_sidecar_policy = "full"
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="off")
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.io.scan_film = True
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params)


def _runtime_coupler_signature(params) -> dict[str, list[float]]:
    couplers = params.film_render.dir_couplers
    return {
        "gamma_samelayer_rgb": list(couplers.gamma_samelayer_rgb),
        "gamma_interlayer_r_to_gb": list(couplers.gamma_interlayer_r_to_gb),
        "gamma_interlayer_g_to_rb": list(couplers.gamma_interlayer_g_to_rb),
        "gamma_interlayer_b_to_rg": list(couplers.gamma_interlayer_b_to_rg),
    }


def _run_runtime_profile(
    profile_slug: str,
    payload: dict[str, Any],
    image: np.ndarray,
    neutral_patch_count: int,
) -> tuple[dict[str, np.ndarray], dict[str, Any], dict[str, list[float]]]:
    from spektrafilm.runtime.process import Simulator

    params = _runtime_candidate_params(profile_slug, payload)
    result = Simulator(params).process_with_master(image, hdr_mode="light_table")
    if result.route_master is None:
        raise RuntimeError("Film-scan runtime validation produced no RouteMaster")
    arrays = {
        "route_linear_rgb": np.asarray(
            result.route_master.route_linear_rgb,
            dtype=float,
        ),
        "route_luminance_y": np.asarray(
            result.route_master.route_luminance_y,
            dtype=float,
        ),
        "density_cmy": np.asarray(result.route_master.density_cmy, dtype=float),
        "sdr_output": np.asarray(result.image, dtype=float),
    }
    neutral_y = arrays["route_luminance_y"].reshape(-1)[:neutral_patch_count]
    neutral_steps = np.diff(neutral_y)
    summary = {
        "all_arrays_finite": bool(
            all(np.all(np.isfinite(value)) for value in arrays.values())
        ),
        "neutral_ramp_monotonic_non_decreasing": bool(
            np.all(neutral_steps >= -1e-12)
        ),
        "neutral_ramp_minimum_step_y": float(np.min(neutral_steps)),
        "route_linear_rgb_range": [
            float(np.min(arrays["route_linear_rgb"])),
            float(np.max(arrays["route_linear_rgb"])),
        ],
        "sdr_output_range": [
            float(np.min(arrays["sdr_output"])),
            float(np.max(arrays["sdr_output"])),
        ],
    }
    return arrays, summary, _runtime_coupler_signature(params)


def _summarize_runtime_difference(
    reference: dict[str, np.ndarray],
    candidate: dict[str, np.ndarray],
) -> dict[str, Any]:
    route_difference = np.abs(
        reference["route_linear_rgb"] - candidate["route_linear_rgb"]
    )
    luminance_difference = np.abs(
        reference["route_luminance_y"] - candidate["route_luminance_y"]
    )
    sdr_difference = np.abs(reference["sdr_output"] - candidate["sdr_output"])

    reference_rgb = np.clip(reference["route_linear_rgb"], 0.0, 1.0)
    candidate_rgb = np.clip(candidate["route_linear_rgb"], 0.0, 1.0)
    reference_xyz = colour.RGB_to_XYZ(
        reference_rgb,
        colourspace="sRGB",
        apply_cctf_decoding=False,
    )
    candidate_xyz = colour.RGB_to_XYZ(
        candidate_rgb,
        colourspace="sRGB",
        apply_cctf_decoding=False,
    )
    d65 = colour.CCS_ILLUMINANTS[
        "CIE 1931 2 Degree Standard Observer"
    ]["D65"]
    delta_e = colour.delta_E(
        colour.XYZ_to_Lab(reference_xyz, d65),
        colour.XYZ_to_Lab(candidate_xyz, d65),
        method="CIE 2000",
    )
    return {
        "route_linear_rgb_mean_absolute_difference": float(
            np.mean(route_difference)
        ),
        "route_linear_rgb_p95_absolute_difference": float(
            np.quantile(route_difference, 0.95)
        ),
        "route_linear_rgb_max_absolute_difference": float(
            np.max(route_difference)
        ),
        "route_luminance_y_mean_absolute_difference": float(
            np.mean(luminance_difference)
        ),
        "route_luminance_y_max_absolute_difference": float(
            np.max(luminance_difference)
        ),
        "sdr_output_mean_absolute_difference": float(np.mean(sdr_difference)),
        "sdr_output_max_absolute_difference": float(np.max(sdr_difference)),
        "clipped_linear_srgb_delta_e_2000_median": float(np.median(delta_e)),
        "clipped_linear_srgb_delta_e_2000_p95": float(
            np.quantile(delta_e, 0.95)
        ),
    }


def _evaluate_runtime_candidates(
    profile_slug: str,
    bundled_payload: dict[str, Any],
    pchip_payload: dict[str, Any],
    linear_payload: dict[str, Any],
) -> dict[str, Any]:
    image, neutral_patch_count = _runtime_validation_image()
    payloads = {
        "bundled": bundled_payload,
        "gs0_dmin_pchip": pchip_payload,
        "gs0_dmin_linear": linear_payload,
    }
    arrays: dict[str, dict[str, np.ndarray]] = {}
    summaries: dict[str, dict[str, Any]] = {}
    signatures: dict[str, dict[str, list[float]]] = {}
    for name, payload in payloads.items():
        arrays[name], summaries[name], signatures[name] = _run_runtime_profile(
            profile_slug,
            payload,
            image,
            neutral_patch_count,
        )

    repeat_arrays, _, _ = _run_runtime_profile(
        profile_slug,
        pchip_payload,
        image,
        neutral_patch_count,
    )
    repeat_max_difference = max(
        float(np.max(np.abs(arrays["gs0_dmin_pchip"][name] - repeated)))
        for name, repeated in repeat_arrays.items()
    )
    return {
        "route": "positive-film light-table scan",
        "input_color_space": "linear ProPhoto RGB",
        "patch_count": int(image.shape[0] * image.shape[1]),
        "neutral_patch_count": neutral_patch_count,
        "spatial_and_stochastic_effects_disabled": True,
        "profiles": summaries,
        "stock_specific_coupler_parameters_preserved": bool(
            signatures["bundled"]
            == signatures["gs0_dmin_pchip"]
            == signatures["gs0_dmin_linear"]
        ),
        "pchip_repeat_max_absolute_difference": repeat_max_difference,
        "differences": {
            "bundled_to_gs0_dmin_pchip": _summarize_runtime_difference(
                arrays["bundled"],
                arrays["gs0_dmin_pchip"],
            ),
            "pchip_to_linear_interpolation": _summarize_runtime_difference(
                arrays["gs0_dmin_pchip"],
                arrays["gs0_dmin_linear"],
            ),
        },
        "interpretation": (
            "Runtime safety and interpolation-sensitivity check only; it does "
            "not independently validate colour accuracy or authorize a bundled "
            "default replacement."
        ),
    }


def _cross_validate_dataset(
    downloads_root: Path,
    batch: str,
    profile_slug: str,
    *,
    transmittance_floors: tuple[float, ...],
    folds: int,
    iterations: int,
    seed: int,
    candidate_output_dir: Path | None,
    runtime_validation: bool,
) -> dict[str, Any]:
    source_path = downloads_root / batch / "EXTRAS" / f"{batch}.xls"
    source_sha256 = _sha256(source_path)
    names, measured_wavelengths, full_transmittance = _load_it8_tsv(source_path)
    gs0_full_density = -np.log10(full_transmittance[names == "GS0"][0])
    candidate_payload, candidate_summary = _build_gs0_dmin_candidate_payload(
        profile_slug,
        batch,
        measured_wavelengths,
        gs0_full_density,
        source_sha256,
    )
    linear_candidate_payload, _ = _build_gs0_dmin_candidate_payload(
        profile_slug,
        batch,
        measured_wavelengths,
        gs0_full_density,
        source_sha256,
        interpolation="linear",
    )
    if candidate_output_dir is not None:
        candidate_summary["output"] = _write_candidate_payload(
            candidate_payload,
            candidate_output_dir,
            candidate_id=candidate_summary["candidate_id"],
        )
    else:
        candidate_summary["output"] = None

    measured_mask, wavelengths, profile_basis, profile_base = _load_profile_basis(
        profile_slug,
        measured_wavelengths,
    )
    transmittance = full_transmittance[:, measured_mask]
    density = -np.log10(transmittance)
    permutation = np.random.default_rng(seed).permutation(len(density))
    fold_indices = np.array_split(permutation, folds)
    floor_results: dict[str, Any] = {}

    for transmittance_floor in transmittance_floors:
        model_predictions = {
            "bundled_basis_and_base": np.empty_like(density),
            "bundled_basis_with_training_lower_envelope": np.empty_like(density),
            "free_effective_nmf_with_training_lower_envelope": np.empty_like(density),
        }
        fold_bases: list[np.ndarray] = []
        fold_candidates: list[np.ndarray] = []
        fold_similarities: list[np.ndarray] = []
        fold_peaks: list[np.ndarray] = []

        for fold_index, test_indices in enumerate(fold_indices):
            train_indices = np.setdiff1d(
                np.arange(len(density)),
                test_indices,
                assume_unique=True,
            )
            lower_envelope = np.min(density[train_indices], axis=0)
            fold_bases.append(lower_envelope)

            model_predictions["bundled_basis_and_base"][test_indices] = (
                _fit_coefficients_and_predict(
                    density[test_indices],
                    transmittance[test_indices],
                    profile_basis,
                    profile_base,
                    transmittance_floor,
                )
            )
            model_predictions[
                "bundled_basis_with_training_lower_envelope"
            ][test_indices] = _fit_coefficients_and_predict(
                density[test_indices],
                transmittance[test_indices],
                profile_basis,
                lower_envelope,
                transmittance_floor,
            )

            candidates = [
                _fit_effective_nmf_basis(
                    density[train_indices],
                    transmittance[train_indices],
                    lower_envelope,
                    profile_basis,
                    transmittance_floor,
                    random_seed=None,
                    iterations=iterations,
                )
            ]
            for initialization_index in range(2):
                candidates.append(
                    _fit_effective_nmf_basis(
                        density[train_indices],
                        transmittance[train_indices],
                        lower_envelope,
                        profile_basis,
                        transmittance_floor,
                        random_seed=(
                            seed + fold_index * 100 + initialization_index + 1
                        ),
                        iterations=iterations,
                    )
                )
            candidate, _ = min(candidates, key=lambda item: item[1])
            candidate, similarity = _align_basis_to_profile(
                candidate,
                profile_basis,
            )
            fold_candidates.append(candidate)
            fold_similarities.append(similarity)
            fold_peaks.append(wavelengths[np.argmax(candidate, axis=0)])
            model_predictions[
                "free_effective_nmf_with_training_lower_envelope"
            ][test_indices] = _fit_coefficients_and_predict(
                density[test_indices],
                transmittance[test_indices],
                candidate,
                lower_envelope,
                transmittance_floor,
            )

        mean_candidate = np.mean(fold_candidates, axis=0)
        fold_stability = np.array(
            [
                np.sum(candidate * mean_candidate, axis=0)
                / (
                    np.linalg.norm(candidate, axis=0)
                    * np.linalg.norm(mean_candidate, axis=0)
                )
                for candidate in fold_candidates
            ]
        )
        floor_results[f"{transmittance_floor:g}"] = {
            "models": {
                model_name: _summarize_predictions(
                    wavelengths,
                    transmittance,
                    density,
                    prediction,
                    transmittance_floor,
                )
                for model_name, prediction in model_predictions.items()
            },
            "candidate_basis": {
                "channel_order_after_alignment": ["C", "M", "Y"],
                "mean_cosine_similarity_to_bundled_basis": np.mean(
                    fold_similarities,
                    axis=0,
                ).tolist(),
                "mean_cosine_similarity_to_cross_fold_mean": np.mean(
                    fold_stability,
                    axis=0,
                ).tolist(),
                "peak_wavelengths_nm_by_fold": np.asarray(fold_peaks).tolist(),
            },
            "training_lower_envelope": {
                "mean_across_folds_D": float(np.mean(fold_bases)),
                "not_a_physical_base_claim": True,
            },
        }

    gray_zero = density[names == "GS0"][0]
    full_lower_envelope = np.min(density, axis=0)
    centered_density = density - np.mean(density, axis=0, keepdims=True)
    singular_values = np.linalg.svd(centered_density, compute_uv=False)
    explained_first_three = float(
        np.sum(np.square(singular_values[:3])) / np.sum(np.square(singular_values))
    )
    with (PROFILE_DIR / f"{profile_slug}.json").open(encoding="utf-8") as handle:
        bundled_payload = json.load(handle)
    runtime_result = (
        _evaluate_runtime_candidates(
            profile_slug,
            bundled_payload,
            candidate_payload,
            linear_candidate_payload,
        )
        if runtime_validation
        else None
    )
    return {
        "batch": batch,
        "profile": profile_slug,
        "source_file": source_path.name,
        "source_sha256": source_sha256,
        "patch_count": int(len(density)),
        "wavelength_count_used": int(len(wavelengths)),
        "wavelength_range_used_nm": [
            float(wavelengths[0]),
            float(wavelengths[-1]),
        ],
        "centered_density_pca_first_three_variance_fraction": (
            explained_first_three
        ),
        "low_density_patch_check": {
            "gs0_vs_bundled_base_rmse_D": float(
                np.sqrt(np.mean(np.square(gray_zero - profile_base)))
            ),
            "gs0_vs_full_patchwise_lower_envelope_rmse_D": float(
                np.sqrt(
                    np.mean(np.square(gray_zero - full_lower_envelope))
                )
            ),
            "interpretation": (
                "The target vendor identifies GS0 as Dmin. ISO Dmin is the "
                "maximum-transmittance product endpoint; it is not necessarily "
                "neutral and must not be relabeled as bare clear base."
            ),
        },
        "gs0_dmin_candidate": {
            "profile_candidate": candidate_summary,
            "patch_reconstruction": _evaluate_gs0_dmin_candidate(
                names,
                wavelengths,
                transmittance,
                density,
                profile_basis,
                profile_base,
                gray_zero,
                transmittance_floors,
            ),
            "runtime_validation": runtime_result,
        },
        "cross_validation": floor_results,
    }


def _compare_k64_figure() -> dict[str, Any]:
    with (PROFILE_DIR / "kodak_kodachrome_64.json").open(
        encoding="utf-8"
    ) as handle:
        data = json.load(handle)["data"]
    wavelengths = np.asarray(data["wavelengths"], dtype=float)
    cmy = np.asarray(data["channel_density"], dtype=float)
    finite = np.all(np.isfinite(cmy), axis=1)
    common = (
        (K64_FIGURE_5_WAVELENGTHS >= wavelengths[finite].min())
        & (K64_FIGURE_5_WAVELENGTHS <= wavelengths[finite].max())
    )
    comparison_wavelengths = K64_FIGURE_5_WAVELENGTHS[common]
    measured_ymc = K64_FIGURE_5_YMC[common]
    profile_ymc = np.column_stack(
        [
            np.interp(
                comparison_wavelengths,
                wavelengths[finite],
                cmy[finite, channel],
            )
            for channel in (2, 1, 0)
        ]
    )
    profile_ymc /= np.max(profile_ymc, axis=0)
    channels: dict[str, Any] = {}
    for channel_index, channel_name in enumerate(("Y", "M", "C")):
        measured = measured_ymc[:, channel_index]
        profile = profile_ymc[:, channel_index]
        channels[channel_name] = {
            "correlation": float(np.corrcoef(measured, profile)[0, 1]),
            "rmse_normalized_density": float(
                np.sqrt(np.mean(np.square(measured - profile)))
            ),
            "mae_normalized_density": float(np.mean(np.abs(measured - profile))),
            "figure_peak_nm": float(
                comparison_wavelengths[np.argmax(measured)]
            ),
            "profile_peak_nm": float(
                comparison_wavelengths[np.argmax(profile)]
            ),
        }
    return {
        "source": (
            "Scarpace and Friederichs, A Method of Determining Spectral "
            "Analytical Dye Densities, PE&RS 44(10), 1978, Figure 5"
        ),
        "comparison_wavelength_range_nm": [
            float(comparison_wavelengths[0]),
            float(comparison_wavelengths[-1]),
        ],
        "comparison_interval_nm": 20,
        "digitization_uncertainty_normalized_density": {
            "typical": 0.015,
            "overlap_or_heavy_mark_regions": 0.03,
        },
        "channels": channels,
        "overall_rmse_normalized_density": float(
            np.sqrt(np.mean(np.square(measured_ymc - profile_ymc)))
        ),
        "classification": "validation-only",
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--downloads-root",
        type=Path,
        default=DEFAULT_DOWNLOADS_ROOT,
        help="Directory containing F240222 and N230513.",
    )
    parser.add_argument(
        "--transmittance-floors",
        type=float,
        nargs="+",
        default=(1e-2, 1e-3, 1e-4),
    )
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--iterations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--candidate-output-dir",
        type=Path,
        default=None,
        help=(
            "Explicitly write local experimental GS0 Dmin profile copies to "
            "this directory. Bundled defaults are never modified."
        ),
    )
    parser.add_argument(
        "--runtime-validation",
        action="store_true",
        help=(
            "Run deterministic light-table film-scan checks for the bundled, "
            "PCHIP GS0 Dmin, and linear GS0 Dmin profiles."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    if not 2 <= args.folds <= 10:
        raise ValueError("--folds must be between 2 and 10")
    if args.iterations < 1:
        raise ValueError("--iterations must be positive")
    transmittance_floors = tuple(args.transmittance_floors)
    if not all(0.0 < floor < 1.0 for floor in transmittance_floors):
        raise ValueError("Transmittance floors must be between 0 and 1")

    report = {
        "method": {
            "density_definition": "D(lambda) = -log10(T(lambda))",
            "cross_validation_folds": args.folds,
            "random_seed": args.seed,
            "nmf_iterations": args.iterations,
            "nmf_initializations_per_fold": 3,
            "coefficient_constraint": "non-negative least squares",
            "candidate_constraint": "non-negative rank 3 with one-bin smoothing",
            "candidate_semantics": "effective full-film density generators",
            "primary_transmittance_floor": PRIMARY_TRANSMITTANCE_FLOOR,
            "gs0_semantics": (
                "ColorAid target Dmin patch; not necessarily neutral and not "
                "a bare clear-base claim"
            ),
            "candidate_output_requested": args.candidate_output_dir is not None,
            "runtime_validation_requested": args.runtime_validation,
            "bundled_profile_arrays_modified": False,
        },
        "datasets": [
            _cross_validate_dataset(
                args.downloads_root,
                batch,
                profile_slug,
                transmittance_floors=transmittance_floors,
                folds=args.folds,
                iterations=args.iterations,
                seed=args.seed,
                candidate_output_dir=args.candidate_output_dir,
                runtime_validation=args.runtime_validation,
            )
            for batch, profile_slug in DATASETS
        ],
        "kodachrome_64_figure_comparison": _compare_k64_figure(),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
