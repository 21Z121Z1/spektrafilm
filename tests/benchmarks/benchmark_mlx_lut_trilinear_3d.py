#!/usr/bin/env python
from __future__ import annotations

import argparse
import gc
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.lut import (
    apply_lut_trilinear_3d_mlx,
    apply_lut_trilinear_3d_mlx_ops,
    apply_lut_trilinear_3d_numpy,
)


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_THREADGROUP_SIZE = 256
THREADGROUP_CANDIDATES = (64, 128, 256, 512)


@dataclass(frozen=True)
class BenchmarkCase:
    label: str
    height: int
    width: int
    lut_size: int
    warmup: int
    runs: int


def acceptance_cases() -> list[BenchmarkCase]:
    return [
        BenchmarkCase("preview_256_lut17", height=256, width=256, lut_size=17, warmup=5, runs=30),
        BenchmarkCase("medium_768x1024_lut33", height=768, width=1024, lut_size=33, warmup=5, runs=30),
        BenchmarkCase("full_3024x4032_lut33", height=3024, width=4032, lut_size=33, warmup=3, runs=10),
    ]


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (q / 100.0)
    lower = int(np.floor(position))
    upper = int(np.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_ms(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("summarize_ms requires at least one timing")
    return {
        "runs": len(values),
        "median_ms": statistics.median(values) * 1000.0,
        "p90_ms": percentile(values, 90.0) * 1000.0,
        "min_ms": min(values) * 1000.0,
        "max_ms": max(values) * 1000.0,
    }


def make_case(height: int, width: int, lut_size: int, seed: int) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    lut = rng.random((lut_size, lut_size, lut_size, 3), dtype=np.float32)
    image = rng.uniform(-0.1, 1.1, size=(height, width, 3)).astype(np.float32)
    return lut, image


def _reset_peak_memory(mx) -> None:
    reset_peak = getattr(mx, "reset_peak_memory", None)
    if callable(reset_peak):
        reset_peak()


def _peak_memory(mx) -> int | None:
    get_peak = getattr(mx, "get_peak_memory", None)
    if callable(get_peak):
        return int(get_peak())
    metal = getattr(mx, "metal", None)
    get_peak = getattr(metal, "get_peak_memory", None)
    if callable(get_peak):
        return int(get_peak())
    return None


def _sync(mx) -> None:
    sync = getattr(mx, "synchronize", None)
    if callable(sync):
        sync()


def _time_mlx_call(
    mx,
    function: Callable[..., Any],
    lut_mx: Any,
    image_mx: Any,
    *,
    threadgroup_size: int | None = None,
) -> tuple[float, Any]:
    start = time.perf_counter()
    if threadgroup_size is None:
        output = function(lut_mx, image_mx, mx=mx)
    else:
        output = function(lut_mx, image_mx, mx=mx, threadgroup_size=threadgroup_size)
    mx.eval(output)
    _sync(mx)
    return time.perf_counter() - start, output


def benchmark_function(
    mx,
    name: str,
    function: Callable[..., Any],
    lut_mx: Any,
    image_mx: Any,
    *,
    warmup: int,
    runs: int,
    threadgroup_size: int | None = None,
) -> dict[str, Any]:
    for _ in range(warmup):
        _, output = _time_mlx_call(mx, function, lut_mx, image_mx, threadgroup_size=threadgroup_size)
    mx.eval(output)
    _sync(mx)

    _reset_peak_memory(mx)
    timings: list[float] = []
    last_output = None
    for _ in range(runs):
        elapsed, last_output = _time_mlx_call(mx, function, lut_mx, image_mx, threadgroup_size=threadgroup_size)
        timings.append(elapsed)

    result = {
        "name": name,
        "summary": summarize_ms(timings),
        "timings_ms": [value * 1000.0 for value in timings],
        "peak_memory_bytes": _peak_memory(mx),
        "output": last_output,
    }
    if threadgroup_size is not None:
        result["threadgroup"] = [threadgroup_size, 1, 1]
    return result


def precision_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    diff = np.abs(np.asarray(reference, dtype=np.float64) - np.asarray(candidate, dtype=np.float64))
    return {
        "max_abs_diff": float(np.max(diff)),
        "mean_abs_diff": float(np.mean(diff)),
        "p90_abs_diff": float(np.percentile(diff, 90.0)),
    }


def run_benchmark(
    *,
    height: int,
    width: int,
    lut_size: int,
    warmup: int,
    runs: int,
    seed: int,
    label: str = "single",
    threadgroup_size: int = DEFAULT_THREADGROUP_SIZE,
    compute_numpy_reference: bool = True,
) -> dict[str, Any]:
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"status": "skipped", "reason": str(exc)}

    mx = backend.mx
    lut, image = make_case(height, width, lut_size, seed)
    lut_mx = backend.asarray(lut, dtype=mx.float32)
    image_mx = backend.asarray(image, dtype=mx.float32)

    # Compile/setup is intentionally outside the timed regions.
    compiled_probe = apply_lut_trilinear_3d_mlx(lut_mx, image_mx, mx=mx, threadgroup_size=threadgroup_size)
    mx.eval(compiled_probe)
    _sync(mx)
    _reset_peak_memory(mx)

    baseline = benchmark_function(
        mx,
        "mlx_ops_baseline",
        apply_lut_trilinear_3d_mlx_ops,
        lut_mx,
        image_mx,
        warmup=warmup,
        runs=runs,
    )
    baseline_output = baseline.pop("output")
    baseline_np = backend.to_numpy(baseline_output)
    del baseline_output
    gc.collect()
    metal = benchmark_function(
        mx,
        "metal_kernel",
        apply_lut_trilinear_3d_mlx,
        lut_mx,
        image_mx,
        warmup=warmup,
        runs=runs,
        threadgroup_size=threadgroup_size,
    )

    metal_np = backend.to_numpy(metal.pop("output"))
    if compute_numpy_reference:
        reference = apply_lut_trilinear_3d_numpy(lut, image)
        baseline["precision_vs_numpy"] = precision_metrics(reference, baseline_np)
        metal["precision_vs_numpy"] = precision_metrics(reference, metal_np)
    else:
        baseline["precision_vs_numpy"] = None
        metal["precision_vs_numpy"] = None
    metal["precision_vs_mlx_ops_baseline"] = precision_metrics(baseline_np, metal_np)

    speedup = baseline["summary"]["median_ms"] / metal["summary"]["median_ms"]
    return {
        "status": "ok",
        "label": label,
        "case": {
            "height": height,
            "width": width,
            "lut_size": lut_size,
            "dtype": "float32",
            "seed": seed,
        },
        "warmup": warmup,
        "runs": runs,
        "compile_setup_excluded": True,
        "threadgroup": [threadgroup_size, 1, 1],
        "results": [baseline, metal],
        "median_speedup_metal_vs_mlx_ops": speedup,
    }


def run_threadgroup_candidate(
    backend,
    *,
    label: str,
    lut: np.ndarray,
    image: np.ndarray,
    lut_mx: Any,
    image_mx: Any,
    baseline_np: np.ndarray,
    warmup: int,
    runs: int,
    threadgroup_size: int,
    compute_numpy_reference: bool,
) -> dict[str, Any]:
    mx = backend.mx
    compiled_probe = apply_lut_trilinear_3d_mlx(lut_mx, image_mx, mx=mx, threadgroup_size=threadgroup_size)
    mx.eval(compiled_probe)
    _sync(mx)
    _reset_peak_memory(mx)
    result = benchmark_function(
        mx,
        f"metal_threadgroup_{threadgroup_size}",
        apply_lut_trilinear_3d_mlx,
        lut_mx,
        image_mx,
        warmup=warmup,
        runs=runs,
        threadgroup_size=threadgroup_size,
    )
    metal_np = backend.to_numpy(result.pop("output"))
    if compute_numpy_reference:
        reference = apply_lut_trilinear_3d_numpy(lut, image)
        result["precision_vs_numpy"] = precision_metrics(reference, metal_np)
    else:
        result["precision_vs_numpy"] = None
    result["precision_vs_mlx_ops_baseline"] = precision_metrics(baseline_np, metal_np)
    result["label"] = label
    return result


def evaluate_threadgroup_candidate(
    accepted: dict[str, Any],
    candidate: dict[str, Any],
    *,
    median_threshold: float = 0.03,
    p90_regression_limit: float = 0.03,
    memory_regression_limit: float = 0.05,
) -> dict[str, Any]:
    accepted_summary = accepted["summary"]
    candidate_summary = candidate["summary"]
    median_change = (
        accepted_summary["median_ms"] - candidate_summary["median_ms"]
    ) / accepted_summary["median_ms"]
    p90_change = (candidate_summary["p90_ms"] - accepted_summary["p90_ms"]) / accepted_summary["p90_ms"]
    accepted_peak = accepted.get("peak_memory_bytes")
    candidate_peak = candidate.get("peak_memory_bytes")
    if accepted_peak in {None, 0} or candidate_peak is None:
        memory_change = 0.0
    else:
        memory_change = (candidate_peak - accepted_peak) / accepted_peak
    accepted_decision = (
        median_change > median_threshold
        and p90_change <= p90_regression_limit
        and memory_change <= memory_regression_limit
    )
    return {
        "accepted": accepted_decision,
        "median_change": median_change,
        "p90_change": p90_change,
        "memory_change": memory_change,
        "reason": (
            "accepted"
            if accepted_decision
            else "rejected: requires >3% median improvement, <=3% p90 regression, and no clear memory increase"
        ),
    }


def run_threadgroup_sweep_case(
    *,
    case: BenchmarkCase,
    seed: int,
    candidates: tuple[int, ...] = THREADGROUP_CANDIDATES,
    compute_numpy_reference: bool = True,
) -> dict[str, Any]:
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"status": "skipped", "reason": str(exc), "label": case.label}

    mx = backend.mx
    lut, image = make_case(case.height, case.width, case.lut_size, seed)
    lut_mx = backend.asarray(lut, dtype=mx.float32)
    image_mx = backend.asarray(image, dtype=mx.float32)

    baseline = benchmark_function(
        mx,
        "mlx_ops_baseline",
        apply_lut_trilinear_3d_mlx_ops,
        lut_mx,
        image_mx,
        warmup=case.warmup,
        runs=case.runs,
    )
    baseline_output = baseline.pop("output")
    baseline_np = backend.to_numpy(baseline_output)
    del baseline_output
    gc.collect()
    if compute_numpy_reference:
        reference = apply_lut_trilinear_3d_numpy(lut, image)
        baseline["precision_vs_numpy"] = precision_metrics(reference, baseline_np)
    else:
        baseline["precision_vs_numpy"] = None

    candidate_results = []
    accepted_result = None
    decisions = []
    for candidate in candidates:
        result = run_threadgroup_candidate(
            backend,
            label=case.label,
            lut=lut,
            image=image,
            lut_mx=lut_mx,
            image_mx=image_mx,
            baseline_np=baseline_np,
            warmup=case.warmup,
            runs=case.runs,
            threadgroup_size=candidate,
            compute_numpy_reference=compute_numpy_reference,
        )
        candidate_results.append(result)
        if candidate == DEFAULT_THREADGROUP_SIZE:
            accepted_result = result

    if accepted_result is None:
        raise ValueError("threadgroup candidates must include the current accepted size 256")

    current_best = accepted_result
    for result in candidate_results:
        candidate = int(result["threadgroup"][0])
        if candidate == DEFAULT_THREADGROUP_SIZE:
            decision = {
                "threadgroup_size": candidate,
                "accepted": True,
                "baseline": True,
                "median_change": 0.0,
                "p90_change": 0.0,
                "memory_change": 0.0,
                "reason": "current accepted implementation",
            }
        else:
            evaluation = evaluate_threadgroup_candidate(current_best, result)
            decision = {
                "threadgroup_size": candidate,
                "baseline": False,
                **evaluation,
            }
            if evaluation["accepted"]:
                current_best = result
        decisions.append(decision)

    return {
        "status": "ok",
        "suite": "threadgroup_sweep",
        "label": case.label,
        "case": {
            "height": case.height,
            "width": case.width,
            "lut_size": case.lut_size,
            "dtype": "float32",
            "seed": seed,
        },
        "warmup": case.warmup,
        "runs": case.runs,
        "compile_setup_excluded": True,
        "baseline": baseline,
        "candidates": candidate_results,
        "decisions": decisions,
        "accepted_threadgroup_size": int(current_best["threadgroup"][0]),
    }


def run_suite(
    *,
    suite: str,
    seed: int,
    candidates: tuple[int, ...] = THREADGROUP_CANDIDATES,
) -> dict[str, Any]:
    cases = acceptance_cases()
    if suite == "acceptance":
        runs = [
            run_benchmark(
                label=case.label,
                height=case.height,
                width=case.width,
                lut_size=case.lut_size,
                warmup=case.warmup,
                runs=case.runs,
                seed=seed,
                threadgroup_size=DEFAULT_THREADGROUP_SIZE,
                compute_numpy_reference=case.height * case.width <= 1024 * 1024,
            )
            for case in cases
        ]
    elif suite == "threadgroup-sweep":
        runs = [
            run_threadgroup_sweep_case(
                case=case,
                seed=seed,
                candidates=candidates,
                compute_numpy_reference=case.height * case.width <= 1024 * 1024,
            )
            for case in cases
        ]
    else:
        raise ValueError(f"unknown suite: {suite}")
    return {
        "status": "ok" if all(run.get("status") == "ok" for run in runs) else "partial",
        "suite": suite,
        "seed": seed,
        "runs": runs,
    }


def format_markdown(payload: dict[str, Any]) -> str:
    if "runs" in payload and isinstance(payload["runs"], list):
        return format_suite_markdown(payload)

    if payload.get("status") != "ok":
        return f"# MLX 3D LUT Benchmark\n\nSkipped: {payload.get('reason', 'unknown reason')}\n"

    case = payload["case"]
    lines = [
        "# MLX 3D LUT Benchmark",
        "",
        f"- Image: {case['height']}x{case['width']}x3 float32",
        f"- LUT: {case['lut_size']}x{case['lut_size']}x{case['lut_size']}x3 float32",
        f"- Warmup: {payload['warmup']}",
        f"- Runs: {payload['runs']}",
        f"- Compile/setup excluded: {payload['compile_setup_excluded']}",
        f"- Threadgroup: {payload['threadgroup']}",
        "",
        "| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in payload["results"]:
        summary = result["summary"]
        peak = result["peak_memory_bytes"]
        peak_text = "n/a" if peak is None else f"{peak / (1024 * 1024):.1f} MiB"
        precision = result["precision_vs_numpy"]
        diff_text = "n/a" if precision is None else f"{precision['max_abs_diff']:.3e}"
        lines.append(
            "| {name} | {median:.3f} ms | {p90:.3f} ms | {min_ms:.3f} ms | "
            "{max_ms:.3f} ms | {peak} | {diff} |".format(
                name=result["name"],
                median=summary["median_ms"],
                p90=summary["p90_ms"],
                min_ms=summary["min_ms"],
                max_ms=summary["max_ms"],
                peak=peak_text,
                diff=diff_text,
            )
        )
    lines.extend(
        [
            "",
            "## Metal vs MLX Ops",
            "",
            f"- Median speedup: {payload['median_speedup_metal_vs_mlx_ops']:.3f}x",
            "- Max diff vs MLX ops baseline: "
            f"{payload['results'][1]['precision_vs_mlx_ops_baseline']['max_abs_diff']:.3e}",
            "",
        ]
    )
    return "\n".join(lines)


def format_suite_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# MLX 3D LUT Benchmark Suite",
        "",
        f"- Suite: {payload['suite']}",
        f"- Seed: {payload['seed']}",
        "",
    ]
    for run in payload["runs"]:
        lines.append(f"## {run.get('label', 'case')}")
        if run.get("status") != "ok":
            lines.append(f"Skipped: {run.get('reason', 'unknown reason')}")
            lines.append("")
            continue
        case = run["case"]
        lines.extend(
            [
                "",
                f"- Image: {case['height']}x{case['width']}x3 float32",
                f"- LUT: {case['lut_size']}x{case['lut_size']}x{case['lut_size']}x3 float32",
                f"- Warmup: {run['warmup']}",
                f"- Runs: {run['runs']}",
                f"- Compile/setup excluded: {run['compile_setup_excluded']}",
                "",
            ]
        )
        if run.get("suite") == "threadgroup_sweep":
            baseline = run["baseline"]
            baseline_summary = baseline["summary"]
            baseline_peak = baseline["peak_memory_bytes"]
            baseline_peak_text = "n/a" if baseline_peak is None else f"{baseline_peak / (1024 * 1024):.1f} MiB"
            lines.extend(
                [
                    f"- MLX ops baseline median: {baseline_summary['median_ms']:.3f} ms",
                    f"- MLX ops baseline p90: {baseline_summary['p90_ms']:.3f} ms",
                    f"- MLX ops baseline peak memory: {baseline_peak_text}",
                    "",
                    "| Threadgroup | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops | Decision |",
                    "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
                ]
            )
            decisions = {decision["threadgroup_size"]: decision for decision in run["decisions"]}
            for result in run["candidates"]:
                summary = result["summary"]
                peak = result["peak_memory_bytes"]
                peak_text = "n/a" if peak is None else f"{peak / (1024 * 1024):.1f} MiB"
                precision = result["precision_vs_numpy"]
                numpy_diff = "n/a" if precision is None else f"{precision['max_abs_diff']:.3e}"
                baseline_diff = result["precision_vs_mlx_ops_baseline"]["max_abs_diff"]
                threadgroup = int(result["threadgroup"][0])
                decision = decisions[threadgroup]
                decision_text = "accepted" if decision["accepted"] else "rejected"
                if decision.get("baseline"):
                    decision_text = "baseline"
                lines.append(
                    "| {tg} | {median:.3f} ms | {p90:.3f} ms | {min_ms:.3f} ms | "
                    "{max_ms:.3f} ms | {peak} | {numpy_diff} | {baseline_diff:.3e} | {decision} |".format(
                        tg=threadgroup,
                        median=summary["median_ms"],
                        p90=summary["p90_ms"],
                        min_ms=summary["min_ms"],
                        max_ms=summary["max_ms"],
                        peak=peak_text,
                        numpy_diff=numpy_diff,
                        baseline_diff=baseline_diff,
                        decision=decision_text,
                    )
                )
            lines.extend(
                [
                    "",
                    f"- Accepted threadgroup size: {run['accepted_threadgroup_size']}",
                    "",
                ]
            )
        else:
            lines.extend(
                [
                    f"- Threadgroup: {run['threadgroup']}",
                    "",
                    "| Path | Median | P90 | Min | Max | Peak memory | Max diff vs NumPy | Max diff vs MLX ops |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for result in run["results"]:
                summary = result["summary"]
                peak = result["peak_memory_bytes"]
                peak_text = "n/a" if peak is None else f"{peak / (1024 * 1024):.1f} MiB"
                precision = result["precision_vs_numpy"]
                numpy_diff = "n/a" if precision is None else f"{precision['max_abs_diff']:.3e}"
                baseline_precision = result.get("precision_vs_mlx_ops_baseline")
                baseline_diff = "n/a" if baseline_precision is None else f"{baseline_precision['max_abs_diff']:.3e}"
                lines.append(
                    "| {name} | {median:.3f} ms | {p90:.3f} ms | {min_ms:.3f} ms | "
                    "{max_ms:.3f} ms | {peak} | {numpy_diff} | {baseline_diff} |".format(
                        name=result["name"],
                        median=summary["median_ms"],
                        p90=summary["p90_ms"],
                        min_ms=summary["min_ms"],
                        max_ms=summary["max_ms"],
                        peak=peak_text,
                        numpy_diff=numpy_diff,
                        baseline_diff=baseline_diff,
                    )
                )
            lines.extend(
                [
                    "",
                    f"- Median speedup metal vs MLX ops: {run['median_speedup_metal_vs_mlx_ops']:.3f}x",
                    "",
                ]
            )
    return "\n".join(lines)


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    suite = payload.get("suite", "single")
    json_path = output_dir / f"mlx-lut-trilinear-3d-{suite}-{stamp}.json"
    md_path = output_dir / f"mlx-lut-trilinear-3d-{suite}-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=("single", "acceptance", "threadgroup-sweep"),
        default="single",
    )
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--lut-size", type=int, default=33)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260619)
    parser.add_argument("--threadgroup-size", type=int, default=DEFAULT_THREADGROUP_SIZE)
    parser.add_argument("--threadgroup-candidates", default="64,128,256,512")
    parser.add_argument("--no-numpy-reference", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "reports",
    )
    args = parser.parse_args(argv)

    if args.suite == "single":
        payload = run_benchmark(
            height=args.height,
            width=args.width,
            lut_size=args.lut_size,
            warmup=args.warmup,
            runs=args.runs,
            seed=args.seed,
            threadgroup_size=args.threadgroup_size,
            compute_numpy_reference=not args.no_numpy_reference,
        )
    else:
        candidates = tuple(int(value) for value in args.threadgroup_candidates.split(",") if value)
        payload = run_suite(suite=args.suite, seed=args.seed, candidates=candidates)
    json_path, md_path = write_artifacts(args.output_dir, payload)
    print(format_markdown(payload))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
