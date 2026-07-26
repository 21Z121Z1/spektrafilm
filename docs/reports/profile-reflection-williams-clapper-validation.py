#!/usr/bin/env python3
"""Closed-evidence Williams--Clapper validation for reflection papers.

This diagnostic consumes the cached public ColorReference black-backed 45/0
spectra.  It never edits or emits a bundled profile.  Complete ``PROD_DATE``
target-production-date proxy groups are held out, and every paper-white anchor
is estimated only from high-L*, low-chroma candidates in the training groups.

The Shore--Spoonhower generalized Williams--Clapper transform is evaluated
with high-order Gauss--Legendre quadrature.  Its inferred normal-transmission
density and all fitted rank-3/rank-4 generators are *effective latent model
quantities*: they are not claimed to be measured or uniquely identified CMY
dye densities.  Fujicolor Crystal Archive DP II is deliberately kept separate
from the bundled Crystal Archive Paper Type II profile.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from io import BytesIO
import importlib.metadata as importlib_metadata
import importlib.util
import json
import math
from pathlib import Path
import platform
import sys
from typing import Any
import zipfile

import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import linear_sum_assignment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = PROJECT_ROOT / "src" / "spektrafilm" / "data" / "profiles"
PUBLIC_VALIDATION_PATH = Path(__file__).with_name(
    "profile-public-batch-validation.py"
)
DEFAULT_CACHE_DIR = PROJECT_ROOT / "tmp" / "profile-public-batches"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "profile-reflection-wc"
CREATED_DATE = "2026-07-13"

SHORE_SPOONHOWER_URL = (
    "https://library.imaging.org/jist/articles/45/5/art00010"
)
WILLIAMS_CLAPPER_URL = (
    "https://opg.optica.org/josa/abstract.cfm?uri=josa-43-7-595"
)
COLORREFERENCE_INDEX_URL = "https://www.colorreference.de/targets/index.html"


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import analysis helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


PUBLIC = _load_module("profile_public_batch_validation_for_wc", PUBLIC_VALIDATION_PATH)
EVALUATION = PUBLIC.EVALUATION


@dataclass(frozen=True)
class ReflectionDatasetSpec:
    key: str
    material: str
    profile_slug: str | None
    identity_note: str


DATASET_SPECS = (
    ReflectionDatasetSpec(
        key="ultra_endura",
        material="Kodak Professional Ultra Endura",
        profile_slug="kodak_ultra_endura",
        identity_note="exact same-stock public reflection corpus",
    ),
    ReflectionDatasetSpec(
        key="endura_premier",
        material="Kodak Professional Endura Premier",
        profile_slug="kodak_endura_premier",
        identity_note="exact same-stock public reflection corpus",
    ),
    ReflectionDatasetSpec(
        key="crystal_archive_dp_ii",
        material="FUJICOLOR Crystal Archive DP II Paper",
        profile_slug=None,
        identity_note=(
            "DP II only; intentionally not mapped to bundled Crystal Archive "
            "Paper Type II"
        ),
    ),
)


CORE_METRICS = (
    "density_rmse_D",
    "reflection_rmse_percentage_points",
    "delta_e_2000_median",
    "delta_e_2000_p95",
)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha256_path(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _canonical_sha256(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def _software_versions() -> dict[str, str]:
    result = {
        "python": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
    }
    for distribution in ("numpy", "scipy", "colour-science"):
        try:
            result[distribution] = importlib_metadata.version(distribution)
        except importlib_metadata.PackageNotFoundError:
            result[distribution] = "not-installed"
    return result


def _fresnel_unpolarized(
    incident_angle: np.ndarray | float,
    n_from: float,
    n_to: float,
) -> np.ndarray:
    """Return unpolarized Fresnel energy reflectance, including TIR."""

    angle = np.asarray(incident_angle, dtype=float)
    sin_transmitted = (n_from / n_to) * np.sin(angle)
    tir = np.abs(sin_transmitted) >= 1.0
    clipped = np.clip(sin_transmitted, -1.0, 1.0)
    transmitted_angle = np.arcsin(clipped)
    cos_i = np.cos(angle)
    cos_t = np.cos(transmitted_angle)
    rs_denominator = n_from * cos_i + n_to * cos_t
    rp_denominator = n_to * cos_i + n_from * cos_t
    rs = np.divide(
        n_from * cos_i - n_to * cos_t,
        rs_denominator,
        out=np.zeros_like(angle),
        where=np.abs(rs_denominator) > 0.0,
    )
    rp = np.divide(
        n_to * cos_i - n_from * cos_t,
        rp_denominator,
        out=np.zeros_like(angle),
        where=np.abs(rp_denominator) > 0.0,
    )
    reflectance = 0.5 * (np.square(rs) + np.square(rp))
    return np.where(tir, 1.0, reflectance)


class WilliamsClapper45_0:
    """Generalized Williams--Clapper forward transform and monotone inverse."""

    def __init__(
        self,
        refractive_index: float,
        *,
        quadrature_order: int,
        table_size: int,
        minimum_transmittance: float = 1e-16,
    ) -> None:
        if not 1.0 < refractive_index < 2.0:
            raise ValueError("Paper/coating refractive index must lie in (1, 2)")
        if quadrature_order < 64:
            raise ValueError("Quadrature order below 64 is not accepted")
        if table_size < 2049:
            raise ValueError("Internal-reflection table must have at least 2049 points")
        self.n = float(refractive_index)
        self.quadrature_order = int(quadrature_order)
        self.table_size = int(table_size)
        self.minimum_transmittance = float(minimum_transmittance)

        nodes, weights = np.polynomial.legendre.leggauss(quadrature_order)
        self._theta = 0.25 * np.pi * (nodes + 1.0)
        self._weights = 0.25 * np.pi * weights
        self._angular_weight = self._weights * np.sin(2.0 * self._theta)
        self._internal_fresnel = _fresnel_unpolarized(
            self._theta,
            self.n,
            1.0,
        )
        self._path_exponent_internal = 2.0 / np.maximum(
            np.cos(self._theta),
            1e-15,
        )

        incident_external = np.deg2rad(45.0)
        viewing_external = 0.0
        incident_internal = math.asin(math.sin(incident_external) / self.n)
        viewing_internal = 0.0
        self.path_exponent = float(
            1.0 / math.cos(incident_internal)
            + 1.0 / math.cos(viewing_internal)
        )
        t01_incident = 1.0 - float(
            _fresnel_unpolarized(incident_external, 1.0, self.n)
        )
        t01_viewing = 1.0 - float(
            _fresnel_unpolarized(viewing_external, 1.0, self.n)
        )
        # Reflectance factor relative to a perfect Lambertian diffuser.  The
        # pi from radiance normalization cancels the Lambertian 1/pi term.
        self.interface_factor = float(t01_incident * t01_viewing / self.n**2)

        logarithmic_count = max(257, table_size // 8)
        linear_count = table_size - logarithmic_count + 1
        lower = np.geomspace(
            self.minimum_transmittance,
            1e-2,
            logarithmic_count,
            endpoint=False,
        )
        upper = np.linspace(1e-2, 1.0, linear_count)
        self._table_t = np.unique(np.concatenate((lower, upper)))
        self._table_r = self._integrate_internal_reflection(self._table_t)
        if np.any(np.diff(self._table_r) <= 0.0):
            raise RuntimeError("Williams--Clapper r(t) table is not strictly monotone")
        self._r_interpolator = PchipInterpolator(
            np.log(self._table_t),
            self._table_r,
            extrapolate=False,
        )

    def _integrate_internal_reflection(self, t: np.ndarray) -> np.ndarray:
        values = np.asarray(t, dtype=float).reshape(-1)
        result = np.empty_like(values)
        chunk_size = 1024
        for start in range(0, len(values), chunk_size):
            chunk = values[start : start + chunk_size]
            attenuation = np.exp(
                np.log(chunk)[:, None] * self._path_exponent_internal[None, :]
            )
            result[start : start + chunk_size] = attenuation @ (
                self._internal_fresnel * self._angular_weight
            )
        return result.reshape(np.asarray(t).shape)

    def internal_reflection(self, t: np.ndarray | float) -> np.ndarray:
        values = np.asarray(t, dtype=float)
        if np.any(~np.isfinite(values)) or np.any(
            (values < self.minimum_transmittance) | (values > 1.0)
        ):
            raise ValueError("Normal transmittance is outside the WC table domain")
        return np.asarray(self._r_interpolator(np.log(values)), dtype=float)

    def forward(
        self,
        t: np.ndarray | float,
        substrate_reflectance: np.ndarray | float,
    ) -> np.ndarray:
        values = np.asarray(t, dtype=float)
        rho = np.asarray(substrate_reflectance, dtype=float)
        r_t = self.internal_reflection(values)
        denominator = 1.0 - rho * r_t
        if np.any(~np.isfinite(rho)) or np.any(rho <= 0.0):
            raise ValueError("Substrate reflectance must be finite and positive")
        if np.any(denominator <= 0.0):
            raise ValueError("WC geometric-series denominator is non-positive")
        return (
            self.interface_factor
            * rho
            * np.power(values, self.path_exponent)
            / denominator
        )

    def substrate_from_white(self, white_reflectance: np.ndarray) -> np.ndarray:
        """Analytically invert the t=1 paper-white endpoint without clipping."""

        white = np.asarray(white_reflectance, dtype=float)
        r_one = float(self.internal_reflection(np.array(1.0)))
        return white / (self.interface_factor + white * r_one)

    def inverse(
        self,
        measured_reflectance: np.ndarray,
        substrate_reflectance: np.ndarray,
        *,
        iterations: int = 56,
    ) -> tuple[np.ndarray, dict[str, Any]]:
        """Monotonically invert R to t; invalid endpoints become NaN, not clips."""

        measured = np.asarray(measured_reflectance, dtype=float)
        rho = np.broadcast_to(
            np.asarray(substrate_reflectance, dtype=float),
            measured.shape,
        )
        minimum = self.forward(
            np.full(measured.shape, self.minimum_transmittance),
            rho,
        )
        maximum = self.forward(np.ones(measured.shape), rho)
        tolerance = 64.0 * np.finfo(float).eps * np.maximum(1.0, maximum)
        finite = np.isfinite(measured) & np.isfinite(rho)
        below = finite & (measured < minimum - tolerance)
        above = finite & (measured > maximum + tolerance)
        valid = finite & ~below & ~above & (measured >= 0.0)

        result = np.full(measured.shape, np.nan, dtype=float)
        if np.any(valid):
            target = measured[valid]
            active_rho = rho[valid]
            low_log = np.full(target.shape, math.log(self.minimum_transmittance))
            high_log = np.zeros(target.shape, dtype=float)
            for _ in range(iterations):
                middle_log = 0.5 * (low_log + high_log)
                middle = np.exp(middle_log)
                predicted = self.forward(middle, active_rho)
                move_low = predicted < target
                low_log = np.where(move_low, middle_log, low_log)
                high_log = np.where(move_low, high_log, middle_log)
            result[valid] = np.exp(0.5 * (low_log + high_log))

        return result, {
            "element_count": int(measured.size),
            "valid_count": int(np.sum(valid)),
            "nonfinite_count": int(np.sum(~finite)),
            "below_minimum_count": int(np.sum(below)),
            "above_paper_white_endpoint_count": int(np.sum(above)),
            "clipped_count": 0,
        }

    def numerical_qa(self) -> dict[str, Any]:
        test_t = np.geomspace(self.minimum_transmittance, 1.0, 1001)
        interpolated = self.internal_reflection(test_t)
        direct_indices = np.linspace(0, len(test_t) - 1, 129, dtype=int)
        direct_t = test_t[direct_indices]
        direct = self._integrate_internal_reflection(direct_t)
        table_error = np.max(np.abs(interpolated[direct_indices] - direct))

        rng = np.random.default_rng(20260713)
        inverse_t = np.exp(
            rng.uniform(
                math.log(self.minimum_transmittance),
                0.0,
                size=(37, 31),
            )
        )
        inverse_rho = rng.uniform(0.2, 0.995, size=(37, 31))
        reflected = self.forward(inverse_t, inverse_rho)
        recovered, inverse_stats = self.inverse(reflected, inverse_rho)
        inverse_error = np.nanmax(np.abs(recovered - inverse_t))
        relative_inverse_error = np.nanmax(
            np.abs(recovered - inverse_t) / np.maximum(inverse_t, 1e-15)
        )
        perfect_white = float(self.forward(np.array(1.0), np.array(1.0)))
        checks = {
            "quadrature_order_at_least_128": self.quadrature_order >= 128,
            "internal_reflection_strictly_monotone": bool(
                np.all(np.diff(interpolated) > 0.0)
            ),
            "table_vs_direct_max_absolute_error_at_most_1e-8": (
                float(table_error) <= 1e-8
            ),
            "forward_inverse_relative_error_at_most_1e-10": (
                float(relative_inverse_error) <= 1e-10
            ),
            "inverse_used_no_clipping": inverse_stats["clipped_count"] == 0,
        }
        return {
            "refractive_index": self.n,
            "quadrature_order": self.quadrature_order,
            "table_point_count": int(len(self._table_t)),
            "minimum_transmittance": self.minimum_transmittance,
            "interface_factor": self.interface_factor,
            "normal_path_exponent_45_0": self.path_exponent,
            "r_at_t_1": float(self.internal_reflection(np.array(1.0))),
            "perfect_substrate_t_1_reflectance_factor": perfect_white,
            "table_vs_direct_max_absolute_error": float(table_error),
            "forward_inverse_max_absolute_error": float(inverse_error),
            "forward_inverse_max_relative_error": float(relative_inverse_error),
            "checks": checks,
            "passes": all(checks.values()),
        }


def _load_cached_archives(
    cache_dir: Path,
) -> tuple[dict[str, bytes], dict[str, Any]]:
    index_path = cache_dir / "index.html"
    if not index_path.exists():
        raise FileNotFoundError(
            f"Missing cached ColorReference index: {index_path}"
        )
    index_bytes = index_path.read_bytes()
    links = PUBLIC._archive_links(index_bytes.decode("latin1"))
    if not links:
        raise ValueError("Cached ColorReference index has no archive links")
    archives: dict[str, bytes] = {}
    missing: list[str] = []
    for filename in links:
        path = cache_dir / filename
        if not path.exists():
            missing.append(filename)
            continue
        payload = path.read_bytes()
        PUBLIC._validate_zip_bytes(payload, filename)
        archives[filename] = payload
    if missing:
        raise FileNotFoundError(
            "Cached public corpus is incomplete; missing " + ", ".join(missing)
        )
    return archives, {
        "index_url": COLORREFERENCE_INDEX_URL,
        "index_path": str(index_path.resolve()),
        "index_sha256": _sha256_bytes(index_bytes),
        "archive_links": len(links),
        "archives_loaded": len(archives),
        "network_access_used": False,
    }


def _collect_dataset_batches(
    archives: dict[str, bytes],
    spec: ReflectionDatasetSpec,
) -> tuple[list[Any], list[dict[str, Any]]]:
    batches: list[Any] = []
    exclusions: list[dict[str, Any]] = []
    for filename, payload in sorted(archives.items()):
        batch_id = filename.removesuffix(".zip")
        with zipfile.ZipFile(BytesIO(payload)) as archive:
            metadata = PUBLIC._archive_metadata(archive, batch_id)
            if metadata.get("MATERIAL") != spec.material:
                continue
            try:
                names, wavelengths, values, member = (
                    PUBLIC._parse_reflection_archive(archive)
                )
                PUBLIC._validate_batch_arrays(
                    names,
                    wavelengths,
                    values,
                    batch_id,
                )
            except ValueError as exc:
                exclusions.append(
                    {
                        "batch": batch_id,
                        "material": spec.material,
                        "reason": str(exc),
                    }
                )
                continue
            batches.append(
                PUBLIC.BatchData(
                    batch_id=batch_id,
                    material=spec.material,
                    production_date=metadata.get("PROD_DATE"),
                    created=metadata.get("CREATED"),
                    wavelengths=wavelengths,
                    names=names,
                    values=values,
                    archive_sha256=_sha256_bytes(payload),
                    source_member=member,
                    raw_zero_value_count=int(np.sum(values == 0.0)),
                )
            )
    batches.sort(key=lambda batch: batch.batch_id)
    filtered, duplicate_exclusions = (
        PUBLIC._exclude_cross_production_date_duplicate_spectra(batches)
    )
    exclusions.extend(duplicate_exclusions)
    if len(filtered) < 2:
        raise ValueError(f"Need at least two exact-material archives for {spec.key}")
    return filtered, exclusions


def _prepare_dataset(
    batches: list[Any],
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray], list[tuple[str, np.ndarray]]]:
    wavelengths = PUBLIC._common_wavelengths(batches)
    if not np.array_equal(wavelengths, np.arange(400.0, 701.0, 10.0)):
        raise ValueError(f"Unexpected reflection wavelength grid: {wavelengths}")
    canonical_names = batches[0].names.copy()
    values = [
        PUBLIC._align_patch_rows(
            batch,
            PUBLIC._values_on_grid(batch, wavelengths),
            canonical_names,
        )
        for batch in batches
    ]
    groups = PUBLIC._production_groups(batches)
    if len(groups) < 2:
        raise ValueError("Need at least two complete PROD_DATE groups")
    return wavelengths, canonical_names, values, groups


def _group_equal_patch_median(
    values: list[np.ndarray],
    groups: list[tuple[str, np.ndarray]],
) -> np.ndarray:
    group_medians = [
        np.median(
            np.stack([values[int(index)] for index in indices]),
            axis=0,
        )
        for _, indices in groups
    ]
    return np.median(np.stack(group_medians), axis=0)


def _training_white_anchor(
    wavelengths: np.ndarray,
    names: np.ndarray,
    training_values: np.ndarray,
    *,
    minimum_lstar: float = 90.0,
    maximum_chroma: float = 5.0,
    minimum_candidate_count: int = 3,
) -> tuple[np.ndarray | None, dict[str, Any]]:
    lab = EVALUATION._spectral_to_lab(wavelengths, training_values)
    chroma = np.hypot(lab[:, 1], lab[:, 2])
    candidate_mask = (lab[:, 0] >= minimum_lstar) & (
        chroma <= maximum_chroma
    )
    indices = np.flatnonzero(candidate_mask)
    summary = {
        "selection_is_training_only": True,
        "minimum_lstar": minimum_lstar,
        "maximum_cab": maximum_chroma,
        "minimum_candidate_count": minimum_candidate_count,
        "candidate_count": int(len(indices)),
        "candidate_names": names[indices].astype(str).tolist(),
        "candidate_lstar_range": (
            [float(np.min(lab[indices, 0])), float(np.max(lab[indices, 0]))]
            if len(indices)
            else None
        ),
        "candidate_cab_range": (
            [float(np.min(chroma[indices])), float(np.max(chroma[indices]))]
            if len(indices)
            else None
        ),
        "fallback_used": False,
        "spectral_aggregation": (
            "wavelengthwise maximum across the qualifying training-only "
            "candidates; this is an explicit paper-white envelope, not clipping"
        ),
        "status": "passed" if len(indices) >= minimum_candidate_count else "blocked",
    }
    if len(indices) < minimum_candidate_count:
        return None, summary
    return np.max(training_values[indices], axis=0), summary


def _active_subset_nnls(
    design: np.ndarray,
    targets: np.ndarray,
    valid: np.ndarray,
) -> np.ndarray:
    """Exact small-rank NNLS by active-subset enumeration, batched by mask."""

    matrix = np.asarray(design, dtype=float)
    observations = np.asarray(targets, dtype=float)
    masks = np.asarray(valid, dtype=bool)
    if observations.ndim != 2 or masks.shape != observations.shape:
        raise ValueError("NNLS targets and valid mask must be 2-D and aligned")
    if matrix.shape[0] != observations.shape[1]:
        raise ValueError("NNLS design wavelength dimension is inconsistent")
    rank = matrix.shape[1]
    if not 1 <= rank <= 4:
        raise ValueError("Active-subset NNLS is limited to rank 1..4")
    result = np.zeros((len(observations), rank), dtype=float)

    grouped: dict[bytes, list[int]] = {}
    for row_index, row_mask in enumerate(masks):
        grouped.setdefault(np.packbits(row_mask).tobytes(), []).append(row_index)

    for row_indices in grouped.values():
        row_indices_array = np.asarray(row_indices, dtype=int)
        mask = masks[row_indices_array[0]]
        if int(np.sum(mask)) == 0:
            continue
        a = matrix[mask]
        y = observations[row_indices_array][:, mask]
        best_error = np.sum(np.square(y), axis=1)
        best = np.zeros((len(row_indices_array), rank), dtype=float)
        for subset_bits in range(1, 1 << rank):
            subset = [
                column for column in range(rank) if subset_bits & (1 << column)
            ]
            coefficients = np.linalg.lstsq(
                a[:, subset],
                y.T,
                rcond=None,
            )[0].T
            feasible = np.all(coefficients >= -1e-12, axis=1)
            coefficients = np.maximum(coefficients, 0.0)
            prediction = coefficients @ a[:, subset].T
            error = np.sum(np.square(prediction - y), axis=1)
            improve = feasible & (error < best_error)
            if np.any(improve):
                best_error[improve] = error[improve]
                best[np.ix_(improve, subset)] = coefficients[improve]
                other = [column for column in range(rank) if column not in subset]
                if other:
                    best[np.ix_(improve, other)] = 0.0
        result[row_indices_array] = best
    return result


def _select_initial_rows(
    density: np.ndarray,
    valid: np.ndarray,
    rank: int,
) -> np.ndarray:
    filled = np.where(valid, density, 0.0)
    shapes = filled / np.maximum(np.max(filled, axis=1, keepdims=True), 1e-12)
    selected: list[int] = [int(np.argmax(np.linalg.norm(shapes, axis=1)))]
    while len(selected) < rank:
        distances = np.min(
            np.stack(
                [
                    np.linalg.norm(shapes - shapes[index], axis=1)
                    for index in selected
                ]
            ),
            axis=0,
        )
        distances[selected] = -np.inf
        selected.append(int(np.argmax(distances)))
    return np.maximum(filled[selected].T, 1e-8)


def _fit_effective_basis(
    density: np.ndarray,
    *,
    rank: int,
    iterations: int,
    prior: np.ndarray | None,
) -> tuple[np.ndarray, dict[str, Any]]:
    values = np.asarray(density, dtype=float)
    valid = np.isfinite(values) & (values >= 0.0)
    if np.min(np.sum(valid, axis=1)) < rank:
        raise ValueError("Too few valid wavelengths in at least one training patch")

    if prior is not None:
        prior_values = np.asarray(prior, dtype=float)
        if prior_values.shape[0] != values.shape[1] or prior_values.shape[1] != 3:
            raise ValueError("Manufacturer prior must be wavelength x 3")
        normalized_prior = prior_values / np.maximum(
            np.max(prior_values, axis=0),
            1e-12,
        )
        if rank == 3:
            basis = normalized_prior.copy()
        elif rank == 4:
            prior_coefficients = _active_subset_nnls(
                normalized_prior,
                np.where(valid, values, 0.0),
                valid,
            )
            residual = np.where(
                valid,
                values - prior_coefficients @ normalized_prior.T,
                0.0,
            )
            residual = np.maximum(residual, 0.0)
            extra = residual[int(np.argmax(np.linalg.norm(residual, axis=1)))]
            if float(np.max(extra)) <= 1e-12:
                extra = _select_initial_rows(values, valid, 1)[:, 0]
            basis = np.column_stack((normalized_prior, extra))
        else:
            raise ValueError("Only rank 3 or 4 is supported")
    else:
        basis = _select_initial_rows(values, valid, rank)

    basis = np.maximum(basis, 1e-10)
    basis /= np.maximum(np.max(basis, axis=0), 1e-12)
    coefficients = np.zeros((len(values), rank), dtype=float)
    training_trace: list[float] = []
    target = np.where(valid, values, 0.0)

    for iteration in range(iterations):
        coefficients = _active_subset_nnls(basis, target, valid)
        for wavelength_index in range(values.shape[1]):
            wavelength_valid = valid[:, wavelength_index]
            solved = _active_subset_nnls(
                coefficients[wavelength_valid],
                values[wavelength_valid, wavelength_index][None, :],
                np.ones((1, int(np.sum(wavelength_valid))), dtype=bool),
            )[0]
            basis[wavelength_index] = solved
        if len(basis) > 2:
            basis[1:-1] = (
                basis[:-2] + 2.0 * basis[1:-1] + basis[2:]
            ) / 4.0
        scales = np.maximum(np.max(basis, axis=0), 1e-12)
        basis /= scales
        coefficients *= scales
        if iteration in {0, iterations - 1}:
            prediction = coefficients @ basis.T
            training_trace.append(
                float(np.sqrt(np.mean(np.square(prediction[valid] - values[valid]))))
            )

    coefficients = _active_subset_nnls(basis, target, valid)
    prediction = coefficients @ basis.T
    training_rmse = float(
        np.sqrt(np.mean(np.square(prediction[valid] - values[valid])))
    )
    alignment: dict[str, Any] | None = None
    if prior is not None:
        candidate_unit = basis / np.maximum(
            np.linalg.norm(basis, axis=0),
            1e-12,
        )
        prior_unit = prior / np.maximum(np.linalg.norm(prior, axis=0), 1e-12)
        similarities = candidate_unit.T @ prior_unit
        candidate_indices, prior_indices = linear_sum_assignment(-similarities)
        matched = similarities[candidate_indices, prior_indices]
        alignment = {
            "matched_candidate_columns": candidate_indices.tolist(),
            "matched_prior_columns": prior_indices.tolist(),
            "matched_cosines": matched.tolist(),
            "minimum_matched_cosine": float(np.min(matched)),
        }
        if rank == 3:
            order = np.empty(3, dtype=int)
            order[prior_indices] = candidate_indices
            basis = basis[:, order]

    return basis, {
        "rank": rank,
        "iteration_count": iterations,
        "valid_training_fraction": float(np.mean(valid)),
        "training_rmse_D": training_rmse,
        "training_trace_first_last_rmse_D": training_trace,
        "basis_sha256": _canonical_sha256(basis.tolist()),
        "manufacturer_prior_used_for_initialization": prior is not None,
        "alignment_to_manufacturer_prior": alignment,
        "semantic_status": "effective latent generators, not physical CMY",
    }


def _load_profile_prior(
    profile_slug: str | None,
    wavelengths: np.ndarray,
) -> tuple[np.ndarray | None, np.ndarray | None, dict[str, Any]]:
    if profile_slug is None:
        return None, None, {
            "available": False,
            "reason": (
                "No exact DP II bundled profile. Crystal Archive Paper Type II "
                "is a different product and is not used as a donor."
            ),
            "type_ii_mapping_forbidden": True,
        }
    profile_path = PROFILE_DIR / f"{profile_slug}.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    field_provenance = payload["metadata"]["provenance"]["fields"][
        "channel_density"
    ]
    measured_mask, selected_wavelengths, basis, base = (
        EVALUATION._load_profile_basis(profile_slug, wavelengths)
    )
    if not np.all(measured_mask) or not np.array_equal(selected_wavelengths, wavelengths):
        raise ValueError(f"Profile {profile_slug} does not cover 400--700 nm")
    if np.any(~np.isfinite(basis)) or np.any(basis < 0.0):
        raise ValueError(f"Profile {profile_slug} prior is not finite/non-negative")
    return basis, base, {
        "available": True,
        "profile_slug": profile_slug,
        "profile_path": str(profile_path.resolve()),
        "profile_file_sha256": _sha256_path(profile_path),
        "profile_data_sha256": _canonical_sha256(payload["data"]),
        "channel_origin": field_provenance.get("origin"),
        "channel_status": field_provenance.get("status"),
        "channel_sources": field_provenance.get("sources", []),
        "same_stock_prior": True,
        "prior_sha256": _canonical_sha256(basis.tolist()),
        "semantic_limit": (
            "source-derived manufacturer-graph prior; final amplitudes are "
            "processed and are not raw analytical dye measurements"
        ),
    }


def _restrict_to_profile_joint_support(
    profile_slug: str | None,
    wavelengths: np.ndarray,
    values: list[np.ndarray],
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Use one common observed grid for bundled and WC comparisons."""

    if profile_slug is None:
        return wavelengths, values
    profile_path = PROFILE_DIR / f"{profile_slug}.json"
    payload = json.loads(profile_path.read_text(encoding="utf-8"))["data"]
    profile_wavelengths = np.asarray(payload["wavelengths"], dtype=float)
    channels = np.asarray(payload["channel_density"], dtype=float)
    base = np.asarray(payload["base_density"], dtype=float)
    finite = np.all(np.isfinite(channels), axis=1) & np.isfinite(base)
    lower = float(np.min(profile_wavelengths[finite]))
    upper = float(np.max(profile_wavelengths[finite]))
    measured_mask = (wavelengths >= lower) & (wavelengths <= upper)
    if int(np.sum(measured_mask)) < 20:
        raise ValueError(f"Too little shared support for {profile_slug}")
    return wavelengths[measured_mask], [array[:, measured_mask] for array in values]


def _fit_predict_additive(
    reflectance: np.ndarray,
    basis: np.ndarray,
    base_density: np.ndarray,
    floor: float,
) -> np.ndarray:
    measured = np.asarray(reflectance, dtype=float)
    density = -np.log10(np.maximum(measured, np.finfo(float).tiny))
    valid = np.isfinite(density) & (measured >= floor)
    coefficients = _active_subset_nnls(
        basis,
        density - base_density[None, :],
        valid,
    )
    prediction_density = base_density + coefficients @ basis.T
    return np.power(10.0, -np.maximum(prediction_density, 0.0))


def _fit_predict_wc(
    transform: WilliamsClapper45_0,
    reflectance: np.ndarray,
    substrate_reflectance: np.ndarray,
    basis: np.ndarray,
) -> tuple[np.ndarray, dict[str, Any]]:
    transmittance, inverse_stats = transform.inverse(
        reflectance,
        substrate_reflectance,
    )
    density = -np.log10(transmittance)
    valid = np.isfinite(density)
    coefficients = _active_subset_nnls(
        basis,
        np.where(valid, density, 0.0),
        valid,
    )
    predicted_density = coefficients @ basis.T
    predicted_t = np.power(10.0, -np.maximum(predicted_density, 0.0))
    prediction = transform.forward(
        predicted_t,
        np.broadcast_to(substrate_reflectance, predicted_t.shape),
    )
    return prediction, inverse_stats


def _predict_wc_from_inverted_density(
    transform: WilliamsClapper45_0,
    density: np.ndarray,
    substrate_reflectance: np.ndarray,
    basis: np.ndarray,
) -> np.ndarray:
    """Fit latent coordinates after one shared, explicitly audited inversion."""

    valid = np.isfinite(density)
    coefficients = _active_subset_nnls(
        basis,
        np.where(valid, density, 0.0),
        valid,
    )
    predicted_density = coefficients @ basis.T
    predicted_t = np.power(10.0, -np.maximum(predicted_density, 0.0))
    return transform.forward(
        predicted_t,
        np.broadcast_to(substrate_reflectance, predicted_t.shape),
    )


def _reflection_metrics(
    wavelengths: np.ndarray,
    measured: np.ndarray,
    predicted: np.ndarray,
    floor: float,
) -> dict[str, float]:
    measured_density = -np.log10(np.maximum(measured, np.finfo(float).tiny))
    predicted_density = -np.log10(np.maximum(predicted, np.finfo(float).tiny))
    result = EVALUATION._summarize_predictions(
        wavelengths,
        measured,
        measured_density,
        predicted_density,
        floor,
    )
    result["reflection_rmse_percentage_points"] = result.pop(
        "transmittance_rmse_percentage_points"
    )
    return {key: float(value) for key, value in result.items()}


def _sum_inverse_stats(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "element_count",
        "valid_count",
        "nonfinite_count",
        "below_minimum_count",
        "above_paper_white_endpoint_count",
        "clipped_count",
    )
    return {key: int(sum(int(row[key]) for row in rows)) for key in keys}


def _mean_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    metric_names = tuple(rows[0]["metrics"])
    return {
        metric: float(np.mean([row["metrics"][metric] for row in rows]))
        for metric in metric_names
    }


def _metric_improvements(
    baseline: dict[str, float],
    candidate: dict[str, float],
) -> dict[str, float]:
    return {
        metric: float(
            100.0 * (baseline[metric] - candidate[metric]) / baseline[metric]
        )
        for metric in baseline
        if baseline[metric] != 0.0
    }


def _model_comparison_gate(
    model_name: str,
    baseline_name: str,
    per_group: list[dict[str, Any]],
    macro: dict[str, dict[str, float]],
    *,
    anchor_all_physical: bool,
    inverse_out_of_domain_count: int,
) -> dict[str, Any]:
    baseline = macro[baseline_name]
    candidate = macro[model_name]
    improvements = _metric_improvements(baseline, candidate)
    wins: dict[str, int] = {}
    maximum_regression: dict[str, float] = {}
    for metric in CORE_METRICS:
        baseline_values = np.array(
            [row["models"][baseline_name][metric] for row in per_group]
        )
        candidate_values = np.array(
            [row["models"][model_name][metric] for row in per_group]
        )
        wins[metric] = int(np.sum(candidate_values < baseline_values))
        maximum_regression[metric] = float(
            np.max(
                100.0
                * (candidate_values - baseline_values)
                / np.maximum(np.abs(baseline_values), 1e-12)
            )
        )
    group_count = len(per_group)
    sign_p = {
        metric: PUBLIC._one_sided_sign_test_p_value(wins[metric], group_count)
        for metric in CORE_METRICS
    }
    checks = {
        "at_least_8_production_groups": group_count >= 8,
        "all_training_white_anchors_physical": anchor_all_physical,
        "zero_inverse_out_of_domain_elements": inverse_out_of_domain_count == 0,
        "all_core_group_macro_metrics_improve": all(
            improvements[metric] > 0.0 for metric in CORE_METRICS
        ),
        "no_core_single_group_regression_above_5_percent": all(
            maximum_regression[metric] <= 5.0 for metric in CORE_METRICS
        ),
        "reflection_and_p95_sign_test_at_most_0_05": (
            sign_p["reflection_rmse_percentage_points"] <= 0.05
            and sign_p["delta_e_2000_p95"] <= 0.05
        ),
    }
    return {
        "baseline": baseline_name,
        "engineering_gate_not_iso_requirement": True,
        "group_macro_improvement_percent": improvements,
        "production_group_win_counts": wins,
        "one_sided_sign_test_p_values": sign_p,
        "maximum_single_group_regression_percent": maximum_regression,
        "checks": checks,
        "reconstruction_gate_passes": all(checks.values()),
        "profile_emission_allowed": False,
        "physical_cmy_claim_allowed": False,
        "reason_profile_emission_is_disabled": (
            "This script is diagnostic-only; reflection-only inversion remains "
            "model-dependent and does not uniquely identify analytical CMY."
        ),
    }


def _paired_model_comparison(
    baseline_name: str,
    candidate_name: str,
    per_group: list[dict[str, Any]],
    macro: dict[str, dict[str, float]],
) -> dict[str, Any]:
    improvements = _metric_improvements(
        macro[baseline_name],
        macro[candidate_name],
    )
    wins: dict[str, int] = {}
    for metric in CORE_METRICS:
        wins[metric] = int(
            sum(
                group["models"][candidate_name][metric]
                < group["models"][baseline_name][metric]
                for group in per_group
            )
        )
    return {
        "baseline": baseline_name,
        "candidate": candidate_name,
        "group_macro_improvement_percent": improvements,
        "production_group_win_counts": wins,
        "one_sided_sign_test_p_values": {
            metric: PUBLIC._one_sided_sign_test_p_value(
                wins[metric],
                len(per_group),
            )
            for metric in CORE_METRICS
        },
    }


def _evaluate_dataset_at_index(
    spec: ReflectionDatasetSpec,
    batches: list[Any],
    wavelengths: np.ndarray,
    names: np.ndarray,
    values: list[np.ndarray],
    groups: list[tuple[str, np.ndarray]],
    prior_basis: np.ndarray | None,
    current_base: np.ndarray | None,
    transform: WilliamsClapper45_0,
    *,
    iterations: int,
    floor: float,
) -> dict[str, Any]:
    model_names = ["reflection_additive_effective_rank3"]
    if prior_basis is not None:
        model_names.append("current_profile_additive")
        model_names.append("wc_manufacturer_prior_rank3")
    model_names.extend(("wc_effective_rank3", "wc_effective_rank4"))

    aggregate_measured: dict[str, list[np.ndarray]] = {
        model: [] for model in model_names
    }
    aggregate_predicted: dict[str, list[np.ndarray]] = {
        model: [] for model in model_names
    }
    per_group: list[dict[str, Any]] = []
    fold_anchors: list[dict[str, Any]] = []
    inverse_training_stats: list[dict[str, Any]] = []
    inverse_heldout_stats: list[dict[str, Any]] = []
    rank3_summaries: list[dict[str, Any]] = []
    rank4_summaries: list[dict[str, Any]] = []

    for held_position, (group_key, held_indices) in enumerate(groups):
        training_groups = [
            group for position, group in enumerate(groups) if position != held_position
        ]
        training_reflectance = _group_equal_patch_median(values, training_groups)
        white, white_summary = _training_white_anchor(
            wavelengths,
            names,
            training_reflectance,
        )
        if white is None:
            raise RuntimeError(
                f"Training white anchor blocked for {spec.key}/{group_key}: "
                f"{white_summary}"
            )
        rho = transform.substrate_from_white(white)
        anchor_physical = bool(
            np.all(np.isfinite(rho))
            and np.all(rho > 0.0)
            and np.all(rho <= 1.0 + 1e-12)
        )
        anchor_record = {
            "held_out_production_group": group_key,
            "held_out_archive_ids": [
                batches[int(index)].batch_id for index in held_indices
            ],
            "held_out_data_read_for_anchor": False,
            "white_candidate_selection": white_summary,
            "substrate_reflectance_min": float(np.min(rho)),
            "substrate_reflectance_max": float(np.max(rho)),
            "substrate_reflectance_above_1_count": int(np.sum(rho > 1.0 + 1e-12)),
            "substrate_reflectance_clipped_count": 0,
            "physical_0_to_1": anchor_physical,
        }
        fold_anchors.append(anchor_record)

        wc_training_t, wc_training_stats = transform.inverse(
            training_reflectance,
            rho,
        )
        inverse_training_stats.append(wc_training_stats)
        wc_training_density = -np.log10(wc_training_t)
        wc_rank3, rank3_summary = _fit_effective_basis(
            wc_training_density,
            rank=3,
            iterations=iterations,
            prior=prior_basis,
        )
        wc_rank4, rank4_summary = _fit_effective_basis(
            wc_training_density,
            rank=4,
            iterations=iterations,
            prior=prior_basis,
        )
        rank3_summary["held_out_production_group"] = group_key
        rank4_summary["held_out_production_group"] = group_key
        rank3_summaries.append(rank3_summary)
        rank4_summaries.append(rank4_summary)

        white_density = -np.log10(np.maximum(white, np.finfo(float).tiny))
        additive_training_density = -np.log10(
            np.maximum(training_reflectance, np.finfo(float).tiny)
        )
        additive_residual = additive_training_density - white_density
        additive_negative_count = int(np.sum(additive_residual < 0.0))
        additive_residual = np.where(additive_residual >= 0.0, additive_residual, np.nan)
        additive_rank3, additive_summary = _fit_effective_basis(
            additive_residual,
            rank=3,
            iterations=iterations,
            prior=prior_basis,
        )
        additive_summary["negative_training_residual_excluded_count"] = (
            additive_negative_count
        )

        archive_rows: list[dict[str, Any]] = []
        group_measured: dict[str, list[np.ndarray]] = {
            model: [] for model in model_names
        }
        group_predictions: dict[str, list[np.ndarray]] = {
            model: [] for model in model_names
        }
        for held_index in held_indices:
            batch = batches[int(held_index)]
            measured = values[int(held_index)]
            predictions: dict[str, np.ndarray] = {}
            predictions["reflection_additive_effective_rank3"] = (
                _fit_predict_additive(
                    measured,
                    additive_rank3,
                    white_density,
                    floor,
                )
            )
            held_t, held_inverse_stats = transform.inverse(measured, rho)
            held_wc_density = -np.log10(held_t)
            inverse_heldout_stats.append(held_inverse_stats)
            if prior_basis is not None:
                assert current_base is not None
                predictions["current_profile_additive"] = _fit_predict_additive(
                    measured,
                    prior_basis,
                    current_base,
                    floor,
                )
                manufacturer_prediction = _predict_wc_from_inverted_density(
                    transform,
                    held_wc_density,
                    rho,
                    prior_basis,
                )
                predictions["wc_manufacturer_prior_rank3"] = manufacturer_prediction
            rank3_prediction = _predict_wc_from_inverted_density(
                transform,
                held_wc_density,
                rho,
                wc_rank3,
            )
            rank4_prediction = _predict_wc_from_inverted_density(
                transform,
                held_wc_density,
                rho,
                wc_rank4,
            )
            predictions["wc_effective_rank3"] = rank3_prediction
            predictions["wc_effective_rank4"] = rank4_prediction

            metrics = {
                model: _reflection_metrics(
                    wavelengths,
                    measured,
                    prediction,
                    floor,
                )
                for model, prediction in predictions.items()
            }
            archive_rows.append(
                {
                    "batch": batch.batch_id,
                    "metrics": metrics,
                    "all_predictions_finite": all(
                        bool(np.all(np.isfinite(prediction)))
                        for prediction in predictions.values()
                    ),
                }
            )
            for model, prediction in predictions.items():
                aggregate_measured[model].append(measured)
                aggregate_predicted[model].append(prediction)
                group_measured[model].append(measured)
                group_predictions[model].append(prediction)

        group_models = {
            model: _reflection_metrics(
                wavelengths,
                np.concatenate(group_measured[model]),
                np.concatenate(group_predictions[model]),
                floor,
            )
            for model in model_names
        }
        per_group.append(
            {
                "production_group": group_key,
                "archive_count": int(len(held_indices)),
                "archive_ids": [
                    batches[int(index)].batch_id for index in held_indices
                ],
                "models": group_models,
                "per_archive": archive_rows,
                "training_additive_rank3": additive_summary,
            }
        )

    micro = {
        model: _reflection_metrics(
            wavelengths,
            np.concatenate(aggregate_measured[model]),
            np.concatenate(aggregate_predicted[model]),
            floor,
        )
        for model in model_names
    }
    macro = {
        model: {
            metric: float(
                np.mean([group["models"][model][metric] for group in per_group])
            )
            for metric in per_group[0]["models"][model]
        }
        for model in model_names
    }
    inverse_training_summary = _sum_inverse_stats(inverse_training_stats)
    inverse_heldout_summary = _sum_inverse_stats(inverse_heldout_stats)
    inverse_summary = {
        key: inverse_training_summary[key] + inverse_heldout_summary[key]
        for key in inverse_training_summary
    }
    inverse_out_of_domain = (
        inverse_summary["below_minimum_count"]
        + inverse_summary["above_paper_white_endpoint_count"]
        + inverse_summary["nonfinite_count"]
    )
    all_anchors_physical = all(
        anchor["physical_0_to_1"] for anchor in fold_anchors
    )

    gates: dict[str, Any] = {}
    baseline_name = (
        "current_profile_additive"
        if "current_profile_additive" in model_names
        else "reflection_additive_effective_rank3"
    )
    for model in model_names:
        if model == baseline_name:
            continue
        model_uses_wc = model.startswith("wc_")
        gates[model] = _model_comparison_gate(
            model,
            baseline_name,
            per_group,
            macro,
            anchor_all_physical=(all_anchors_physical if model_uses_wc else True),
            inverse_out_of_domain_count=(
                inverse_out_of_domain if model_uses_wc else 0
            ),
        )
    rank4_vs_rank3 = _paired_model_comparison(
        "wc_effective_rank3",
        "wc_effective_rank4",
        per_group,
        macro,
    )

    return {
        "refractive_index": transform.n,
        "held_out_unit": "complete PROD_DATE target-production-date proxy group",
        "production_group_count": len(groups),
        "model_semantics": {
            "current_profile_additive": (
                "bundled base_density plus same-stock manufacturer-graph channel "
                "prior, fitted directly to -log10(black-backed 45/0 R)"
            ),
            "reflection_additive_effective_rank3": (
                "training-white-anchored effective rank-3 factorization directly "
                "in reflection-density space"
            ),
            "wc_manufacturer_prior_rank3": (
                "WC normal-transmission latent density fitted to bundled same-stock "
                "manufacturer-graph prior; not a physical dye measurement"
            ),
            "wc_effective_rank3": (
                "training-only effective rank-3 WC latent generators, aligned to "
                "same-stock prior when one exists"
            ),
            "wc_effective_rank4": (
                "training-only effective rank-4 WC latent generators; diagnostic "
                "test of whether three-component structure is sufficient"
            ),
        },
        "micro_models": micro,
        "production_group_macro_models": macro,
        "per_production_group": per_group,
        "training_white_anchors": fold_anchors,
        "anchor_qa": {
            "all_folds_physical_0_to_1": all_anchors_physical,
            "minimum_candidate_count_across_folds": int(
                min(
                    anchor["white_candidate_selection"]["candidate_count"]
                    for anchor in fold_anchors
                )
            ),
            "maximum_substrate_reflectance": float(
                max(anchor["substrate_reflectance_max"] for anchor in fold_anchors)
            ),
            "clipped_count": 0,
            "held_out_data_read_for_anchor": False,
        },
        "inverse_qa": {
            **inverse_summary,
            "training": inverse_training_summary,
            "held_out": inverse_heldout_summary,
            "out_of_domain_count": inverse_out_of_domain,
            "held_out_above_paper_white_endpoint_fraction": float(
                inverse_heldout_summary["above_paper_white_endpoint_count"]
                / max(inverse_heldout_summary["element_count"], 1)
            ),
            "silent_clipping_used": False,
        },
        "rank3_training_summaries": rank3_summaries,
        "rank4_training_summaries": rank4_summaries,
        "comparison_gates": gates,
        "rank4_vs_rank3": rank4_vs_rank3,
        "best_group_macro_model_by_metric": {
            metric: min(model_names, key=lambda model: macro[model][metric])
            for metric in per_group[0]["models"][model_names[0]]
        },
        "any_profile_emission_allowed": False,
        "any_physical_cmy_claim_allowed": False,
    }


def _sensitivity_summary(
    index_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    model_names = sorted(
        set.intersection(
            *[
                set(result["production_group_macro_models"])
                for result in index_results.values()
            ]
        )
    )
    result: dict[str, Any] = {}
    for model in model_names:
        metrics: dict[str, Any] = {}
        for metric in next(iter(index_results.values()))[
            "production_group_macro_models"
        ][model]:
            by_index = {
                index: float(
                    index_result["production_group_macro_models"][model][metric]
                )
                for index, index_result in index_results.items()
            }
            values = list(by_index.values())
            metrics[metric] = {
                "by_refractive_index": by_index,
                "absolute_range": float(max(values) - min(values)),
                "range_percent_of_n_1_53": float(
                    100.0
                    * (max(values) - min(values))
                    / max(abs(by_index.get("1.53", values[0])), 1e-12)
                ),
            }
        result[model] = metrics
    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--refractive-indices",
        nargs="+",
        type=float,
        default=(1.53, 1.45, 1.60),
    )
    parser.add_argument("--quadrature-order", type=int, default=256)
    parser.add_argument("--table-size", type=int, default=8193)
    parser.add_argument("--nmf-iterations", type=int, default=16)
    parser.add_argument("--reflection-floor", type=float, default=1e-2)
    parser.add_argument(
        "--datasets",
        nargs="+",
        choices=[spec.key for spec in DATASET_SPECS],
        default=[spec.key for spec in DATASET_SPECS],
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if 1.53 not in args.refractive_indices:
        raise ValueError("The primary n=1.53 result must be included")
    if args.nmf_iterations < 1:
        raise ValueError("NMF iteration count must be positive")

    archives, acquisition = _load_cached_archives(args.cache_dir)
    transforms = {
        f"{index:.2f}": WilliamsClapper45_0(
            index,
            quadrature_order=args.quadrature_order,
            table_size=args.table_size,
        )
        for index in args.refractive_indices
    }
    transform_qa = {
        index: transform.numerical_qa()
        for index, transform in transforms.items()
    }
    if not all(summary["passes"] for summary in transform_qa.values()):
        raise RuntimeError(f"Williams--Clapper numerical QA failed: {transform_qa}")

    selected_specs = [spec for spec in DATASET_SPECS if spec.key in args.datasets]
    datasets: list[dict[str, Any]] = []
    all_exclusions: list[dict[str, Any]] = []
    for spec in selected_specs:
        print(f"evaluating {spec.key}", file=sys.stderr, flush=True)
        batches, exclusions = _collect_dataset_batches(archives, spec)
        all_exclusions.extend(exclusions)
        wavelengths, names, values, groups = _prepare_dataset(batches)
        wavelengths, values = _restrict_to_profile_joint_support(
            spec.profile_slug,
            wavelengths,
            values,
        )
        prior_basis, current_base, prior_summary = _load_profile_prior(
            spec.profile_slug,
            wavelengths,
        )
        index_results: dict[str, dict[str, Any]] = {}
        for index, transform in transforms.items():
            print(
                f"  n={index}, {len(batches)} archives/{len(groups)} groups",
                file=sys.stderr,
                flush=True,
            )
            index_results[index] = _evaluate_dataset_at_index(
                spec,
                batches,
                wavelengths,
                names,
                values,
                groups,
                prior_basis,
                current_base,
                transform,
                iterations=args.nmf_iterations,
                floor=args.reflection_floor,
            )
        source_manifest = [
            {
                "batch": batch.batch_id,
                "production_date_proxy": batch.production_date,
                "archive_sha256": batch.archive_sha256,
                "source_member": batch.source_member,
                "raw_zero_value_count": batch.raw_zero_value_count,
            }
            for batch in batches
        ]
        datasets.append(
            {
                "key": spec.key,
                "declared_material_exact_match": spec.material,
                "identity_note": spec.identity_note,
                "profile_slug": spec.profile_slug,
                "dp_ii_mapped_to_type_ii": False,
                "archive_count": len(batches),
                "production_group_count": len(groups),
                "production_groups": [
                    {
                        "production_group": key,
                        "archive_ids": [
                            batches[int(index)].batch_id for index in indices
                        ],
                    }
                    for key, indices in groups
                ],
                "wavelengths_nm": wavelengths.tolist(),
                "patch_count": len(names),
                "source_manifest": source_manifest,
                "source_manifest_sha256": _canonical_sha256(source_manifest),
                "manufacturer_prior": prior_summary,
                "results_by_refractive_index": index_results,
                "refractive_index_sensitivity": _sensitivity_summary(index_results),
            }
        )

    report = {
        "created": CREATED_DATE,
        "method": {
            "analysis": "black-backed 45/0 generalized Williams--Clapper validation",
            "formula": (
                "R = [T01(theta_i) T01(theta_o) / n^2] * "
                "rho_B * t^(sec(theta_i')+sec(theta_o')) / "
                "[1-rho_B integral(R10(theta)t^(2 sec(theta))sin(2theta)dtheta)]"
            ),
            "primary_reference": SHORE_SPOONHOWER_URL,
            "original_reference": WILLIAMS_CLAPPER_URL,
            "public_data_index": COLORREFERENCE_INDEX_URL,
            "analysis_code_sha256": _sha256_path(Path(__file__).resolve()),
            "public_validation_helper_sha256": _sha256_path(PUBLIC_VALIDATION_PATH),
            "measurement_evaluation_helper_sha256": _sha256_path(
                PUBLIC.COMPANION_PATH
            ),
            "software_versions": _software_versions(),
            "primary_refractive_index": 1.53,
            "sensitivity_refractive_indices": [1.45, 1.60],
            "quadrature": (
                f"{args.quadrature_order}-point Gauss-Legendre on internal "
                "hemisphere with a monotone PCHIP r(t) table"
            ),
            "inverse": (
                "56-step logarithmic monotone bisection; out-of-domain values "
                "become NaN and are counted; no endpoint clipping"
            ),
            "paper_white_anchor": (
                "training-only L*>=90 and C*ab<=5 patch candidates; explicit "
                "wavelengthwise maximum envelope; at least three candidates; "
                "no fallback and no clipping"
            ),
            "validation_split": (
                "complete PROD_DATE target-production-date proxy groups; "
                "held-out archives never contribute to white anchors or bases"
            ),
            "coefficient_fit": "exact active-subset non-negative least squares",
            "rank3_rank4_semantics": (
                "effective latent generators only; neither rank is a physical "
                "or uniquely identified CMY dye claim"
            ),
            "profile_arrays_modified": False,
            "profile_candidates_emitted": False,
            "output_scope": "tmp/profile-reflection-wc only",
            "licence_note": (
                "Public download does not establish permission to redistribute "
                "source spectra or derived arrays; this local report is diagnostic."
            ),
        },
        "acquisition": acquisition,
        "transform_numerical_qa": transform_qa,
        "exact_material_exclusions": all_exclusions,
        "datasets": datasets,
        "global_conclusions": {
            "dp_ii_is_type_ii": False,
            "physical_cmy_identified": False,
            "default_profile_change_authorized": False,
            "manufacturer_or_author_contact_used": False,
            "new_physical_film_or_paper_used": False,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    output_path = args.output_dir / "reflection-williams-clapper-validation.json"
    output_path.write_text(
        json.dumps(report, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    summary = {
        "output": str(output_path.resolve()),
        "output_sha256": _sha256_path(output_path),
        "analysis_code_sha256": report["method"]["analysis_code_sha256"],
        "datasets": {
            dataset["key"]: {
                "archive_count": dataset["archive_count"],
                "production_group_count": dataset["production_group_count"],
                "n_1_53_macro": dataset["results_by_refractive_index"]["1.53"][
                    "production_group_macro_models"
                ],
                "n_1_53_gates": dataset["results_by_refractive_index"]["1.53"][
                    "comparison_gates"
                ],
            }
            for dataset in datasets
        },
    }
    print(json.dumps(summary, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
