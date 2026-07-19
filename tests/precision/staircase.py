from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable, Mapping

import colour
import numpy as np


CONTRACT_PATH = Path(__file__).with_name("staircase_contract.json")


@dataclass(frozen=True, slots=True)
class StageSnapshot:
    values: np.ndarray
    condition_labels: np.ndarray | None = None


def load_contract(path: Path = CONTRACT_PATH) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def representative_rgb(height: int = 13, width: int = 19) -> tuple[np.ndarray, np.ndarray]:
    """Return a deterministic stress image and per-pixel condition labels."""
    if height < 5 or width < 8:
        raise ValueError("representative precision images must be at least 5x8")

    x = np.linspace(-0.05, 4.0, width, dtype=np.float64)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float64)[:, None]
    smooth = np.stack(
        (
            np.broadcast_to(x, (height, width)),
            np.broadcast_to(y, (height, width)),
            0.5 * np.broadcast_to(x, (height, width)) + 0.5 * y,
        ),
        axis=-1,
    )
    checker = ((np.indices((height, width)).sum(axis=0) & 1) * 2 - 1)[..., None]
    image = smooth + checker * np.array([0.015, -0.01, 0.02], dtype=np.float64)

    patches = np.array(
        [
            [0.0, 1e-8, 1e-6],
            [-0.05, 0.02, 0.08],
            [0.18, 0.18, 0.18],
            [0.999, 1.0, 1.001],
            [2.0, 4.0, 8.0],
            [1.3, -0.1, 0.05],
            [-0.1, 1.4, 0.1],
            [0.05, -0.08, 1.5],
        ],
        dtype=np.float64,
    )
    image[0, : patches.shape[0], :] = patches

    labels = np.full((height, width), "smooth_gradient", dtype="U32")
    labels[(np.indices((height, width)).sum(axis=0) & 1) == 1] = "high_frequency_texture"
    labels[:, -1] = "unaligned_image_boundary"
    labels[0, : patches.shape[0]] = np.array(
        [
            "near_zero_shadow",
            "negative_or_out_of_range",
            "neutral_ramp",
            "sdr_white_boundary",
            "hdr_highlight",
            "wide_gamut_saturated",
            "wide_gamut_saturated",
            "wide_gamut_saturated",
        ]
    )
    return image, labels


def _ordered_float32(values: np.ndarray) -> np.ndarray:
    bits = np.asarray(values, dtype=np.float32).view(np.uint32)
    negative = (bits & np.uint32(0x80000000)) != 0
    return np.where(negative, ~bits, bits | np.uint32(0x80000000)).astype(np.uint32)


def _location(index: tuple[int, ...], shape: tuple[int, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {"index": list(index)}
    if len(shape) >= 2:
        result["pixel"] = list(index[:2])
    if len(shape) >= 3:
        result["channel"] = int(index[-1])
    return result


def _clip_classes(values: np.ndarray, bounds: tuple[float | None, float | None] | None) -> np.ndarray | None:
    if bounds is None:
        return None
    lower, upper = bounds
    classes = np.zeros(values.shape, dtype=np.int8)
    if lower is not None:
        classes[values < lower] = -1
    if upper is not None:
        classes[values > upper] = 1
    return classes


def numeric_metrics(
    reference: Any,
    candidate: Any,
    *,
    condition_labels: np.ndarray | None = None,
    clip_bounds: tuple[float | None, float | None] | None = None,
) -> dict[str, Any]:
    """Compute tail-sensitive error, ULP, location, and classification metrics."""
    ref = np.asarray(reference)
    got = np.asarray(candidate)
    if ref.shape != got.shape:
        raise ValueError(f"shape mismatch: {ref.shape} != {got.shape}")

    ref64 = ref.astype(np.float64, copy=False)
    got64 = got.astype(np.float64, copy=False)
    finite_ref = np.isfinite(ref64)
    finite_got = np.isfinite(got64)
    finite_pair = finite_ref & finite_got
    finite_mismatch = finite_ref ^ finite_got
    diff = np.zeros(ref.shape, dtype=np.float64)
    diff[finite_pair] = got64[finite_pair] - ref64[finite_pair]
    abs_diff = np.abs(diff[finite_pair])
    ref_finite = np.abs(ref64[finite_pair])
    scale = max(float(np.max(ref_finite)) if ref_finite.size else 1.0, 1.0)
    relative = abs_diff / np.maximum(ref_finite, np.finfo(np.float32).eps * scale)

    if finite_pair.any():
        location_source = np.where(finite_pair, np.abs(diff), -1.0)
        max_index = tuple(int(i) for i in np.unravel_index(int(np.argmax(location_source)), ref.shape))
        max_location = _location(max_index, ref.shape)
        if condition_labels is not None and len(max_index) >= 2:
            max_location["input_condition"] = str(np.asarray(condition_labels)[max_index[:2]])
    else:
        max_location = {"index": None, "pixel": None, "channel": None}

    ref32 = ref64.astype(np.float32)
    got32 = got64.astype(np.float32)
    ulp_mask = np.isfinite(ref32) & np.isfinite(got32)
    ulp = np.abs(
        _ordered_float32(ref32[ulp_mask]).astype(np.int64)
        - _ordered_float32(got32[ulp_mask]).astype(np.int64)
    )
    ref_classes = _clip_classes(ref64, clip_bounds)
    got_classes = _clip_classes(got64, clip_bounds)
    class_changes = 0 if ref_classes is None else int(np.count_nonzero(ref_classes != got_classes))

    def percentile(values: np.ndarray, q: float) -> float:
        return float(np.percentile(values, q)) if values.size else 0.0

    return {
        "shape": list(ref.shape),
        "dtype_reference": str(ref.dtype),
        "dtype_candidate": str(got.dtype),
        "mean_abs": float(np.mean(abs_diff)) if abs_diff.size else 0.0,
        "rms": float(np.sqrt(np.mean(np.square(abs_diff)))) if abs_diff.size else 0.0,
        "p95_abs": percentile(abs_diff, 95.0),
        "p99_abs": percentile(abs_diff, 99.0),
        "p99_9_abs": percentile(abs_diff, 99.9),
        "max_abs": float(np.max(abs_diff)) if abs_diff.size else 0.0,
        "mean_relative": float(np.mean(relative)) if relative.size else 0.0,
        "p99_relative": percentile(relative, 99.0),
        "max_relative": float(np.max(relative)) if relative.size else 0.0,
        "ulp": {
            "p50": percentile(ulp, 50.0),
            "p95": percentile(ulp, 95.0),
            "p99": percentile(ulp, 99.0),
            "p99_9": percentile(ulp, 99.9),
            "max": int(np.max(ulp)) if ulp.size else 0,
        },
        "max_error_location": max_location,
        "finite": {
            "reference_nan": int(np.count_nonzero(np.isnan(ref64))),
            "candidate_nan": int(np.count_nonzero(np.isnan(got64))),
            "reference_inf": int(np.count_nonzero(np.isinf(ref64))),
            "candidate_inf": int(np.count_nonzero(np.isinf(got64))),
            "classification_mismatch": int(np.count_nonzero(finite_mismatch)),
        },
        "clip_classification_changes": class_changes,
        "bitwise_equal": bool(ref.dtype == got.dtype and np.array_equal(ref, got, equal_nan=True)),
    }


def _summary(values: np.ndarray) -> dict[str, float]:
    flat = np.asarray(values, dtype=np.float64).ravel()
    return {
        "mean": float(np.mean(flat)) if flat.size else 0.0,
        "p95": float(np.percentile(flat, 95)) if flat.size else 0.0,
        "p99": float(np.percentile(flat, 99)) if flat.size else 0.0,
        "p99_9": float(np.percentile(flat, 99.9)) if flat.size else 0.0,
        "max": float(np.max(flat)) if flat.size else 0.0,
    }


def color_metrics(reference_rgb: Any, candidate_rgb: Any, *, color_space: str = "sRGB") -> dict[str, Any]:
    ref = np.clip(np.asarray(reference_rgb, dtype=np.float64), 0.0, 1.0)
    got = np.clip(np.asarray(candidate_rgb, dtype=np.float64), 0.0, 1.0)
    if ref.shape != got.shape or ref.shape[-1] != 3:
        raise ValueError("color metrics require equal RGB arrays")
    cs = colour.RGB_COLOURSPACES[color_space]
    xyz_ref = colour.RGB_to_XYZ(ref, colourspace=color_space, illuminant=cs.whitepoint, apply_cctf_decoding=True)
    xyz_got = colour.RGB_to_XYZ(got, colourspace=color_space, illuminant=cs.whitepoint, apply_cctf_decoding=True)
    delta = np.asarray(colour.delta_E(colour.XYZ_to_Lab(xyz_ref), colour.XYZ_to_Lab(xyz_got), method="CIE 2000"))

    linear_ref = np.asarray(cs.cctf_decoding(ref), dtype=np.float64)
    luminance = np.tensordot(linear_ref, np.asarray([0.2126, 0.7152, 0.0722]), axes=([-1], [0]))
    saturation = np.max(ref, axis=-1) - np.min(ref, axis=-1)
    partitions = {
        "shadow": luminance < 0.1,
        "midtone": (luminance >= 0.1) & (luminance < 0.7),
        "highlight": luminance >= 0.7,
        "high_saturation": saturation >= 0.6,
    }
    return {
        "delta_e00": _summary(delta),
        "partitions": {
            name: ({**_summary(delta[mask]), "count": int(np.count_nonzero(mask))} if np.any(mask) else {**_summary(np.array([])), "count": 0})
            for name, mask in partitions.items()
        },
    }


def quantized_code_metrics(reference: Any, candidate: Any, *, bit_depth: int) -> dict[str, Any]:
    maximum = (1 << bit_depth) - 1
    ref_code = np.rint(np.clip(reference, 0.0, 1.0) * maximum).astype(np.int64)
    got_code = np.rint(np.clip(candidate, 0.0, 1.0) * maximum).astype(np.int64)
    diff = np.abs(got_code - ref_code)
    return {
        "bit_depth": bit_depth,
        "different_count": int(np.count_nonzero(diff)),
        "p99_code_difference": float(np.percentile(diff, 99)) if diff.size else 0.0,
        "max_code_difference": int(np.max(diff)) if diff.size else 0,
    }


def hdr_metrics(
    reference_hdr: Any,
    candidate_hdr: Any,
    *,
    diffuse_white_nits: float,
    reference_headroom: float,
    candidate_headroom: float,
) -> dict[str, Any]:
    ref_nits = np.asarray(reference_hdr, dtype=np.float64) * diffuse_white_nits
    got_nits = np.asarray(candidate_hdr, dtype=np.float64) * diffuse_white_nits
    abs_nits = np.abs(got_nits - ref_nits)
    return {
        "nits": _summary(abs_nits),
        "headroom_abs": abs(float(candidate_headroom) - float(reference_headroom)),
        "capacity_max_abs": abs(float(candidate_headroom) - float(reference_headroom)),
    }


def grain_statistics(
    values: Any,
    *,
    exposure: Any | None = None,
    quantiles: tuple[float, ...] = (0.01, 0.05, 0.5, 0.95, 0.99),
    exposure_bins: tuple[float, ...] = (0.0, 0.2, 0.5, 0.8, 1.01),
    power_spectrum_bins: int = 8,
) -> dict[str, Any]:
    data = np.asarray(values, dtype=np.float64)
    if data.ndim == 2:
        data = data[..., None]
    if data.ndim != 3:
        raise ValueError("grain statistics require HxW or HxWxC data")

    centered = data - np.mean(data, axis=(0, 1), keepdims=True)
    variance = np.var(data, axis=(0, 1))
    denom = np.maximum(variance, np.finfo(np.float64).tiny)
    autocorr_x = np.mean(centered[:, :-1] * centered[:, 1:], axis=(0, 1)) / denom
    autocorr_y = np.mean(centered[:-1, :] * centered[1:, :], axis=(0, 1)) / denom
    flattened = data.reshape(-1, data.shape[-1])
    channel_corr = np.nan_to_num(np.corrcoef(flattened, rowvar=False), nan=0.0)
    if np.ndim(channel_corr) == 0:
        channel_corr = np.asarray([[float(channel_corr)]])

    psd = np.mean(np.abs(np.fft.fftshift(np.fft.fft2(centered, axes=(0, 1)), axes=(0, 1))) ** 2, axis=-1)
    yy, xx = np.indices(psd.shape)
    radius = np.sqrt((yy - (psd.shape[0] - 1) / 2) ** 2 + (xx - (psd.shape[1] - 1) / 2) ** 2)
    edges = np.linspace(0.0, float(np.max(radius)) + np.finfo(float).eps, power_spectrum_bins + 1)
    spectrum = np.asarray([np.mean(psd[(radius >= lo) & (radius < hi)]) for lo, hi in zip(edges[:-1], edges[1:])])
    spectrum /= max(float(np.sum(spectrum)), np.finfo(float).tiny)

    by_exposure: list[dict[str, Any]] = []
    if exposure is not None:
        exposure_array = np.asarray(exposure, dtype=np.float64)
        if exposure_array.shape != data.shape[:2]:
            raise ValueError("exposure must match grain spatial shape")
        for lo, hi in zip(exposure_bins[:-1], exposure_bins[1:]):
            mask = (exposure_array >= lo) & (exposure_array < hi)
            selected = data[mask]
            by_exposure.append({
                "range": [lo, hi],
                "count": int(np.count_nonzero(mask)),
                "mean": np.mean(selected, axis=0).tolist() if selected.size else [],
                "std": np.std(selected, axis=0).tolist() if selected.size else [],
            })

    return {
        "mean": np.mean(data, axis=(0, 1)).tolist(),
        "variance": variance.tolist(),
        "quantiles": {str(q): np.quantile(data, q, axis=(0, 1)).tolist() for q in quantiles},
        "autocorrelation_x": autocorr_x.tolist(),
        "autocorrelation_y": autocorr_y.tolist(),
        "channel_correlation": channel_corr.tolist(),
        "exposure_bins": by_exposure,
        "normalized_power_spectrum": spectrum.tolist(),
    }


def compare_grain_statistics(
    reference: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    sample_count: int,
    contract: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare native RNG distributions using predeclared sampling budgets."""
    resolved = load_contract()["grain_native_rng"] if contract is None else contract
    ref_mean = np.asarray(reference["mean"], dtype=np.float64)
    got_mean = np.asarray(candidate["mean"], dtype=np.float64)
    ref_var = np.asarray(reference["variance"], dtype=np.float64)
    got_var = np.asarray(candidate["variance"], dtype=np.float64)
    mean_se = np.sqrt((ref_var + got_var) / max(sample_count, 1))
    mean_limit = float(resolved["mean_standard_error_sigma"]) * mean_se + np.finfo(np.float32).eps
    relative_variance = np.abs(got_var - ref_var) / np.maximum(ref_var, np.finfo(np.float32).eps)

    quantile_difference = {
        key: np.abs(np.asarray(candidate["quantiles"][key]) - np.asarray(reference["quantiles"][key])).tolist()
        for key in reference["quantiles"]
    }
    autocorrelation_difference = np.maximum(
        np.abs(np.asarray(candidate["autocorrelation_x"]) - np.asarray(reference["autocorrelation_x"])),
        np.abs(np.asarray(candidate["autocorrelation_y"]) - np.asarray(reference["autocorrelation_y"])),
    )
    channel_correlation_difference = np.abs(
        np.asarray(candidate["channel_correlation"]) - np.asarray(reference["channel_correlation"])
    )
    ref_power = np.asarray(reference["normalized_power_spectrum"])
    got_power = np.asarray(candidate["normalized_power_spectrum"])
    relative_power = np.abs(got_power - ref_power) / np.maximum(ref_power, 1.0 / (100.0 * len(ref_power)))

    failures: list[str] = []
    if np.any(np.abs(got_mean - ref_mean) > mean_limit):
        failures.append("mean exceeds six-standard-error sampling budget")
    if np.max(relative_variance) > float(resolved["relative_variance_budget"]):
        failures.append("variance exceeds relative budget")
    if max(float(np.max(value)) for value in map(np.asarray, quantile_difference.values())) > float(resolved["absolute_quantile_budget"]):
        failures.append("quantile exceeds absolute budget")
    if np.max(autocorrelation_difference) > float(resolved["autocorrelation_budget"]):
        failures.append("spatial autocorrelation exceeds budget")
    if np.max(channel_correlation_difference) > float(resolved["channel_correlation_budget"]):
        failures.append("channel correlation exceeds budget")
    if np.max(relative_power) > float(resolved["relative_power_spectrum_budget"]):
        failures.append("power spectrum exceeds relative budget")
    return {
        "mean_abs_difference": np.abs(got_mean - ref_mean).tolist(),
        "mean_sampling_limit": mean_limit.tolist(),
        "relative_variance_difference": relative_variance.tolist(),
        "absolute_quantile_difference": quantile_difference,
        "autocorrelation_difference": autocorrelation_difference.tolist(),
        "channel_correlation_max_difference": float(np.max(channel_correlation_difference)),
        "relative_power_spectrum_difference": relative_power.tolist(),
        "failures": failures,
    }


def compare_snapshots(
    reference: Mapping[str, StageSnapshot],
    candidate: Mapping[str, StageSnapshot],
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for stage, stage_contract in contract["stages"].items():
        if stage not in reference or stage not in candidate:
            continue
        labels = reference[stage].condition_labels
        bounds = stage_contract["clip_bounds"]
        clip_bounds = None if bounds is None else (bounds[0], bounds[1])
        result[stage] = numeric_metrics(
            reference[stage].values,
            candidate[stage].values,
            condition_labels=labels,
            clip_bounds=clip_bounds,
        )
    return result


def assess_relation(
    metrics: Mapping[str, Mapping[str, Any]],
    *,
    relation: str,
    contract: Mapping[str, Any],
) -> list[str]:
    failures: list[str] = []
    epsilon = float(contract["derivation"]["float32_epsilon"])
    relation_contract = contract["relations"][relation]
    scale = float(relation_contract["budget_scale"])
    for stage, values in metrics.items():
        stage_contract = contract["stages"][stage]
        explicitly_bitwise = stage in relation_contract.get("bitwise_stages", ())
        if relation == "mlx32_unfused_to_candidate" and (
            explicitly_bitwise or (stage_contract["class"] == "a" and relation_contract["class_a_bitwise"])
        ):
            if not values["bitwise_equal"]:
                failures.append(f"{stage}: class A candidate is not bitwise equal")
            continue
        budget = epsilon * float(stage_contract["conditioning_factor"]) * scale
        if float(values["max_abs"]) > budget:
            failures.append(f"{stage}: max_abs {values['max_abs']:.9g} > {budget:.9g}")
        if relation_contract["require_no_new_nonfinite"] and values["finite"]["classification_mismatch"]:
            failures.append(f"{stage}: finite classification changed")
        if relation_contract["require_same_clip_class"] and values["clip_classification_changes"]:
            failures.append(f"{stage}: clipping classification changed")
    return failures


def build_report(
    snapshots: Mapping[str, Mapping[str, StageSnapshot]],
    *,
    contract: Mapping[str, Any] | None = None,
    generated_by: str = "tests.precision.staircase",
) -> dict[str, Any]:
    resolved = load_contract() if contract is None else dict(contract)
    pairs = {
        "cpu64_to_cpu32": ("cpu64", "cpu32"),
        "cpu32_to_mlx32_unfused": ("cpu32", "mlx32_unfused"),
        "cpu64_to_mlx32_unfused": ("cpu64", "mlx32_unfused"),
        "mlx32_unfused_to_candidate": ("mlx32_unfused", "mlx32_candidate"),
        "cpu64_to_candidate": ("cpu64", "mlx32_candidate"),
    }
    comparisons: dict[str, Any] = {}
    for relation, (reference_name, candidate_name) in pairs.items():
        if reference_name not in snapshots or candidate_name not in snapshots:
            continue
        stage_metrics = compare_snapshots(snapshots[reference_name], snapshots[candidate_name], resolved)
        comparisons[relation] = {
            "stages": stage_metrics,
            "failures": assess_relation(stage_metrics, relation=relation, contract=resolved),
        }
    if "cpu64_to_candidate" in comparisons and "cpu64_to_mlx32_unfused" in comparisons:
        candidate_comparison = comparisons["cpu64_to_candidate"]
        baseline_stages = comparisons["cpu64_to_mlx32_unfused"]["stages"]
        ratio = float(resolved["relations"]["cpu64_to_candidate"]["max_baseline_error_ratio"])
        epsilon = float(resolved["derivation"]["float32_epsilon"])
        for stage, candidate_metrics in candidate_comparison["stages"].items():
            baseline_max = float(baseline_stages[stage]["max_abs"])
            # Below one stage budget the absolute contract is the meaningful
            # floor; above it, a candidate may worsen the observed reference
            # error by at most the predeclared ratio.
            meaningful_floor = epsilon * float(resolved["stages"][stage]["conditioning_factor"])
            degradation_limit = max(baseline_max * ratio, meaningful_floor)
            if float(candidate_metrics["max_abs"]) > degradation_limit:
                candidate_comparison["failures"].append(
                    f"{stage}: CPU64 error worsened beyond {ratio:.3g}x baseline"
                )
    return {
        "schema_version": 1,
        "contract_id": resolved["contract_id"],
        "generated_by": generated_by,
        "available_paths": list(snapshots),
        "comparisons": comparisons,
    }


def write_report(report: Mapping[str, Any], output: Path) -> None:
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


SnapshotFactory = Callable[[], Mapping[str, StageSnapshot]]
