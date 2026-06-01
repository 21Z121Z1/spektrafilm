#!/usr/bin/env python3
"""Benchmark stable-shape MLX element-wise chains with and without mx.compile."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark stable-shape MLX element-wise chains with mx.compile."
    )
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--wavelengths", type=int, default=81)
    parser.add_argument("--seed", type=int, default=20260531)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "docs/dev/benchmark-artifacts/mlx_compile_elementwise_20260531",
    )
    return parser.parse_args()


def _summary_ms(samples: list[float]) -> dict[str, float]:
    values = [sample * 1000.0 for sample in samples]
    sorted_values = sorted(values)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2:
        median = sorted_values[mid]
    else:
        median = (sorted_values[mid - 1] + sorted_values[mid]) / 2.0
    return {
        "best_ms": min(values),
        "median_ms": median,
        "mean_ms": sum(values) / len(values),
    }


def _time_chain(
    backend,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    *,
    warmup: int,
    iterations: int,
) -> tuple[list[float], Any]:
    result = None
    for _ in range(warmup):
        result = function(*args)
        backend.eval(result)
        backend.synchronize()

    samples = []
    for _ in range(iterations):
        start = time.perf_counter()
        result = function(*args)
        backend.eval(result)
        backend.synchronize()
        samples.append(time.perf_counter() - start)
    return samples, result


def _max_abs_diff(backend, left: Any, right: Any) -> float:
    left_np = backend.to_numpy(left).astype(np.float32, copy=False)
    right_np = backend.to_numpy(right).astype(np.float32, copy=False)
    return float(np.max(np.abs(left_np - right_np)))


def _benchmark_case(
    backend,
    *,
    name: str,
    function: Callable[..., Any],
    args: tuple[Any, ...],
    warmup: int,
    iterations: int,
) -> dict[str, Any]:
    compiled = backend.compiled_elementwise(f"benchmark.{name}", function, *args)
    baseline_samples, baseline_result = _time_chain(
        backend, function, args, warmup=warmup, iterations=iterations,
    )
    compiled_samples, compiled_result = _time_chain(
        backend, compiled, args, warmup=warmup, iterations=iterations,
    )
    baseline = _summary_ms(baseline_samples)
    compiled_summary = _summary_ms(compiled_samples)
    speedup = baseline["median_ms"] / compiled_summary["median_ms"]
    return {
        "name": name,
        "baseline": baseline,
        "compiled": compiled_summary,
        "median_speedup": speedup,
        "max_abs_diff": _max_abs_diff(backend, baseline_result, compiled_result),
    }


def _write_artifacts(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"benchmark-{stamp}.json"
    md_path = output_dir / f"benchmark-{stamp}.md"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    rows = [
        "| Chain | Baseline median | Compiled median | Median speedup | Max abs diff |",
        "|---|---:|---:|---:|---:|",
    ]
    for result in payload["results"]:
        rows.append(
            "| {name} | {base:.3f} ms | {compiled:.3f} ms | {speedup:.3f}x | {diff:.3e} |".format(
                name=result["name"],
                base=result["baseline"]["median_ms"],
                compiled=result["compiled"]["median_ms"],
                speedup=result["median_speedup"],
                diff=result["max_abs_diff"],
            )
        )
    md = "\n".join(
        [
            "# MLX Compile Element-Wise Benchmark",
            "",
            f"- Shape: `{payload['shape']}`",
            f"- Dtype: `{payload['dtype']}`",
            f"- Iterations: `{payload['iterations']}`",
            f"- Warmup: `{payload['warmup']}`",
            f"- Seed: `{payload['seed']}`",
            "",
            *rows,
            "",
        ]
    )
    md_path.write_text(md, encoding="utf-8")
    return json_path, md_path


def main() -> int:
    args = _parse_args()
    if args.height <= 0 or args.width <= 0:
        raise SystemExit("--height and --width must be positive")
    if args.iterations <= 0:
        raise SystemExit("--iterations must be positive")

    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend

    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        print(f"MLX unavailable: {exc}")
        return 0

    mx = backend.mx
    rng = np.random.default_rng(args.seed)
    shape = (args.height, args.width, 3)
    image = backend.asarray(rng.uniform(-0.05, 1.5, shape).astype(np.float32))
    positive = backend.asarray(rng.uniform(1.0e-6, 4.0, shape).astype(np.float32))
    density = backend.asarray(
        rng.uniform(0.0, 3.0, (args.height, args.width, args.wavelengths)).astype(np.float32)
    )
    illuminant = backend.asarray(rng.uniform(0.1, 1.0, (args.wavelengths,)).astype(np.float32))

    boost_range = 0.5
    boost_ev = 1.0
    raw_x0 = 0.184
    a = 28.0 ** (1.0 - boost_range)
    denom = math.exp(a * (1.0 - raw_x0)) - a * (1.0 - raw_x0) - 1.0
    boost_scale = (2.0 ** boost_ev - 1.0) / denom
    boost_params = backend.asarray([raw_x0, a, boost_scale, 1.0])

    def safe_log10(values):
        return mx.log10(mx.maximum(values, 0.0) + 1.0e-10)

    def density_to_light(values, illum):
        transmitted = mx.exp(-values * math.log(10.0)) * illum
        transmitted = mx.where(mx.isnan(transmitted), 0.0, transmitted)
        big = np.finfo(np.float32).max
        transmitted = mx.where(mx.isinf(transmitted) & (transmitted > 0), big, transmitted)
        return mx.where(mx.isinf(transmitted) & (transmitted < 0), -big, transmitted)

    def cctf_encode_srgb(values):
        magnitude = mx.power(mx.abs(values), 1.0 / 2.4)
        signed = mx.where(values < 0, -magnitude, magnitude)
        nonlinear = 1.055 * signed - 0.055
        return mx.where(values <= 0.0031308, values * 12.92, nonlinear)

    def boost_highlights(values, factors):
        raw_x0_v = factors[0]
        a_v = factors[1]
        boost_scale_v = factors[2]
        inv_max_v = factors[3]
        dx = mx.maximum(values - raw_x0_v, 0.0) * inv_max_v
        adx = dx * a_v
        b = boost_scale_v * (mx.exp(adx) - adx - 1.0)
        return values + b

    cases = [
        ("safe_log10", safe_log10, (positive,)),
        ("density_to_light", density_to_light, (density, illuminant)),
        ("cctf_encode_srgb", cctf_encode_srgb, (image,)),
        ("boost_highlights", boost_highlights, (image, boost_params)),
    ]

    results = []
    for name, function, case_args in cases:
        print(f"Benchmarking {name}...", flush=True)
        results.append(
            _benchmark_case(
                backend,
                name=name,
                function=function,
                args=case_args,
                warmup=args.warmup,
                iterations=args.iterations,
            )
        )
    payload = {
        "backend": "mlx",
        "shape": list(shape),
        "spectral_shape": [args.height, args.width, args.wavelengths],
        "dtype": "float32",
        "iterations": args.iterations,
        "warmup": args.warmup,
        "seed": args.seed,
        "results": results,
    }
    json_path, md_path = _write_artifacts(args.output_dir, payload)

    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    for result in results:
        print(
            "{name}: baseline median={base:.3f} ms compiled median={compiled:.3f} ms "
            "speedup={speedup:.3f}x max_abs_diff={diff:.3e}".format(
                name=result["name"],
                base=result["baseline"]["median_ms"],
                compiled=result["compiled"]["median_ms"],
                speedup=result["median_speedup"],
                diff=result["max_abs_diff"],
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
