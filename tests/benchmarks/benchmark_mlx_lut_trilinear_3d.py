#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import statistics
import time
from collections.abc import Callable
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


def _time_mlx_call(mx, function: Callable[..., Any], lut_mx: Any, image_mx: Any) -> tuple[float, Any]:
    start = time.perf_counter()
    output = function(lut_mx, image_mx, mx=mx)
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
) -> dict[str, Any]:
    for _ in range(warmup):
        _, output = _time_mlx_call(mx, function, lut_mx, image_mx)
    mx.eval(output)
    _sync(mx)

    _reset_peak_memory(mx)
    timings: list[float] = []
    last_output = None
    for _ in range(runs):
        elapsed, last_output = _time_mlx_call(mx, function, lut_mx, image_mx)
        timings.append(elapsed)

    return {
        "name": name,
        "summary": summarize_ms(timings),
        "timings_ms": [value * 1000.0 for value in timings],
        "peak_memory_bytes": _peak_memory(mx),
        "output": last_output,
    }


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
    compiled_probe = apply_lut_trilinear_3d_mlx(lut_mx, image_mx, mx=mx)
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
    metal = benchmark_function(
        mx,
        "metal_kernel",
        apply_lut_trilinear_3d_mlx,
        lut_mx,
        image_mx,
        warmup=warmup,
        runs=runs,
    )

    reference = apply_lut_trilinear_3d_numpy(lut, image)
    metal_np = backend.to_numpy(metal.pop("output"))
    baseline["precision_vs_numpy"] = precision_metrics(reference, baseline_np)
    metal["precision_vs_numpy"] = precision_metrics(reference, metal_np)
    metal["precision_vs_mlx_ops_baseline"] = precision_metrics(baseline_np, metal_np)

    speedup = baseline["summary"]["median_ms"] / metal["summary"]["median_ms"]
    return {
        "status": "ok",
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
        "threadgroup": [256, 1, 1],
        "results": [baseline, metal],
        "median_speedup_metal_vs_mlx_ops": speedup,
    }


def format_markdown(payload: dict[str, Any]) -> str:
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
        lines.append(
            "| {name} | {median:.3f} ms | {p90:.3f} ms | {min_ms:.3f} ms | "
            "{max_ms:.3f} ms | {peak} | {diff:.3e} |".format(
                name=result["name"],
                median=summary["median_ms"],
                p90=summary["p90_ms"],
                min_ms=summary["min_ms"],
                max_ms=summary["max_ms"],
                peak=peak_text,
                diff=precision["max_abs_diff"],
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


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"mlx-lut-trilinear-3d-{stamp}.json"
    md_path = output_dir / f"mlx-lut-trilinear-3d-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--height", type=int, default=768)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--lut-size", type=int, default=33)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260619)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs" / "reports",
    )
    args = parser.parse_args(argv)

    payload = run_benchmark(
        height=args.height,
        width=args.width,
        lut_size=args.lut_size,
        warmup=args.warmup,
        runs=args.runs,
        seed=args.seed,
    )
    json_path, md_path = write_artifacts(args.output_dir, payload)
    print(format_markdown(payload))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
