from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.precision.staircase import (
    build_report,
    color_metrics,
    compare_grain_statistics,
    grain_statistics,
    hdr_metrics,
    load_contract,
    quantized_code_metrics,
    write_report,
)
from tests.precision.synthetic_pipeline import (
    run_contract_case_staircases,
    run_synthetic_staircase,
)


def _add_terminal_metrics(report, snapshots, contract) -> None:
    final = contract["final_output"]
    for relation, (reference_name, candidate_name) in {
        "cpu64_to_cpu32": ("cpu64", "cpu32"),
        "cpu32_to_mlx32_unfused": ("cpu32", "mlx32_unfused"),
        "cpu64_to_mlx32_unfused": ("cpu64", "mlx32_unfused"),
        "mlx32_unfused_to_candidate": ("mlx32_unfused", "mlx32_candidate"),
        "cpu64_to_candidate": ("cpu64", "mlx32_candidate"),
    }.items():
        if reference_name not in snapshots or candidate_name not in snapshots:
            continue
        reference = snapshots[reference_name]
        candidate = snapshots[candidate_name]
        comparison = report["comparisons"][relation]
        comparison["final_color"] = color_metrics(
            reference["decoded_final_sdr"].values,
            candidate["decoded_final_sdr"].values,
        )
        comparison["sdr_code_values"] = quantized_code_metrics(
            reference["decoded_final_sdr"].values,
            candidate["decoded_final_sdr"].values,
            bit_depth=int(final["sdr_bit_depth"]),
        )
        if "gain_map" not in reference or "gain_map" not in candidate:
            continue
        comparison["gain_map_code_values"] = quantized_code_metrics(
            reference["gain_map"].values,
            candidate["gain_map"].values,
            bit_depth=int(final["gain_map_bit_depth"]),
        )
        comparison["hdr"] = hdr_metrics(
            reference["decoded_final_hdr"].values,
            candidate["decoded_final_hdr"].values,
            diffuse_white_nits=float(final["hdr_diffuse_white_nits"]),
            reference_headroom=float(reference["hdr_headroom"].values[0]),
            candidate_headroom=float(candidate["hdr_headroom"].values[0]),
        )


def _native_grain_report(contract):
    import numpy as np

    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
    from spektrafilm.model.grain import apply_grain_to_density

    grain_contract = contract["grain_native_rng"]
    height, width, _ = grain_contract["shape"]
    exposure = np.linspace(0.0, 1.0, height * width, dtype=np.float32).reshape(height, width)
    density = np.repeat((0.08 + exposure[..., None] * np.asarray([0.8, 1.1, 1.4], dtype=np.float32)), 1, axis=-1)
    kwargs = dict(pixel_size_um=5.0, grain_blur=0.0, n_sub_layers=2, fixed_seed=int(grain_contract["seed"]))
    cpu = apply_grain_to_density(density.astype(np.float64), **kwargs)
    statistics_kwargs = dict(
        exposure=exposure,
        quantiles=tuple(grain_contract["quantiles"]),
        exposure_bins=tuple(grain_contract["exposure_bins"]),
        power_spectrum_bins=int(grain_contract["power_spectrum_bins"]),
    )
    report = {"cpu_native": grain_statistics(cpu, **statistics_kwargs)}
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        report["mlx_status"] = {"available": False, "reason": str(exc)}
        return report
    mlx = apply_grain_to_density(backend.asarray(density), backend=backend, **kwargs)
    backend.eval(mlx)
    mlx_stats = grain_statistics(backend.to_numpy(mlx), **statistics_kwargs)
    report["mlx_native"] = mlx_stats
    report["comparison"] = compare_grain_statistics(
        report["cpu_native"], mlx_stats, sample_count=height * width, contract=grain_contract,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the fixed Spektrafilm precision staircase report")
    parser.add_argument("--output", type=Path, help="write canonical JSON to this path; stdout is used otherwise")
    parser.add_argument("--cpu-only", action="store_true", help="omit MLX paths even when available")
    parser.add_argument("--native-grain", action="store_true", help="also sample and compare native CPU/MLX grain RNGs")
    parser.add_argument(
        "--hanatos-fallback",
        action="store_true",
        help="compare the monkeypatched pre-candidate Hanatos fallback with the production candidate",
    )
    args = parser.parse_args()

    contract = load_contract()
    snapshots = run_synthetic_staircase(include_mlx=not args.cpu_only)
    report = build_report(snapshots, contract=contract, generated_by="tests/precision/generate_precision_report.py")
    _add_terminal_metrics(report, snapshots, contract)
    case_definitions = {str(case["id"]): case for case in contract["sample_set"]}
    report["sample_set"] = contract["sample_set"]
    report["contract_cases"] = {}
    for case_id, case_snapshots in run_contract_case_staircases(
        contract,
        include_mlx=not args.cpu_only,
    ).items():
        case_report = build_report(
            case_snapshots,
            contract=contract,
            generated_by="tests/precision/generate_precision_report.py:contract_case",
        )
        case_report["case"] = case_definitions[case_id]
        _add_terminal_metrics(case_report, case_snapshots, contract)
        report["contract_cases"][case_id] = case_report

    if args.native_grain:
        report["native_grain"] = _native_grain_report(contract)
    if args.hanatos_fallback:
        from tests.precision.hanatos_fallback import run_hanatos_fallback_audit

        report["hanatos_balanced_fallback"] = run_hanatos_fallback_audit()

    failures = [
        f"aggregate/{relation}: {failure}"
        for relation, comparison in report["comparisons"].items()
        for failure in comparison["failures"]
    ]
    failures.extend(
        f"{case_id}/{relation}: {failure}"
        for case_id, case_report in report["contract_cases"].items()
        for relation, comparison in case_report["comparisons"].items()
        for failure in comparison["failures"]
    )
    if "native_grain" in report:
        failures.extend(
            f"native_grain: {failure}"
            for failure in report["native_grain"].get("comparison", {}).get("failures", [])
        )
    if "hanatos_balanced_fallback" in report:
        failures.extend(
            f"hanatos_balanced_fallback: {failure}"
            for failure in report["hanatos_balanced_fallback"].get("failures", [])
        )
    report["all_contract_failures"] = failures

    if args.output:
        write_report(report, args.output)
    else:
        print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
