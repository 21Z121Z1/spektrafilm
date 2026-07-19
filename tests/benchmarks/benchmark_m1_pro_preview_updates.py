#!/usr/bin/env python3
"""Benchmark bounded MLX preview-stage reuse against forced full recomputation."""

from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tests.benchmarks.benchmark_m1_pro_e2e import (  # noqa: E402
    RunConfig,
    build_params,
    generated_linear_image,
)


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "median": float(statistics.median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def _memory_value(backend: Any, name: str) -> int | None:
    for owner in (getattr(backend, "mx", None), getattr(getattr(backend, "mx", None), "metal", None)):
        getter = getattr(owner, name, None)
        if callable(getter):
            return int(getter())
    return None


def _render_update(pipeline: Any, image: np.ndarray) -> tuple[float, np.ndarray, dict[str, float]]:
    start = time.perf_counter()
    value = pipeline.process(image)
    pipeline._backend.eval(value)
    pipeline._backend.synchronize()
    output = pipeline._backend.to_numpy(value)
    pipeline._backend.synchronize()
    return time.perf_counter() - start, output, dict(pipeline.timings)


def _updated_params(base: Any, kind: str, index: int) -> Any:
    params = copy.deepcopy(base)
    if kind == "scanner":
        params.scanner.lens_blur = 0.15 if index % 2 == 0 else 0.25
    elif kind == "print":
        params.enlarger.print_exposure = 0.95 if index % 2 == 0 else 1.05
    elif kind == "output":
        params.io.output_clip_max = index % 2 == 0
    else:
        raise ValueError(f"unsupported update kind: {kind}")
    return params


def run_benchmark(*, width: int, height: int, runs: int, kind: str) -> dict[str, Any]:
    from spektrafilm.runtime.pipeline import SimulationPipeline

    config = RunConfig(
        width=width,
        height=height,
        backend="mlx",
        precision="float32",
        materialize_policy="backend",
        film_profile="kodak_portra_400",
        print_profile="kodak_portra_endura",
        route="paper",
        input_peak=4.0,
        runs=runs,
        auto_exposure=True,
        effects="default",
    )
    params = build_params(config)
    params.settings.preview_mode = True
    image = generated_linear_image(height, width, config.input_peak)
    cached_pipeline = SimulationPipeline(params)
    full_pipeline = SimulationPipeline(params)

    _render_update(cached_pipeline, image)
    _render_update(full_pipeline, image)
    cached_rows: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    for index in range(runs):
        updated = _updated_params(params, kind, index)

        cached_pipeline.update(updated)
        cached_seconds, cached_output, cached_timings = _render_update(cached_pipeline, image)
        cached_rows.append({
            "seconds": cached_seconds,
            "timings": cached_timings,
            "mlx_peak_bytes": _memory_value(cached_pipeline._backend, "get_peak_memory"),
            "mlx_cache_bytes": _memory_value(cached_pipeline._backend, "get_cache_memory"),
        })

        full_pipeline.update(updated)
        full_pipeline._preview_stage_cache.clear()
        full_seconds, full_output, full_timings = _render_update(full_pipeline, image)
        full_rows.append({
            "seconds": full_seconds,
            "timings": full_timings,
            "mlx_peak_bytes": _memory_value(full_pipeline._backend, "get_peak_memory"),
            "mlx_cache_bytes": _memory_value(full_pipeline._backend, "get_cache_memory"),
        })
        np.testing.assert_array_equal(cached_output, full_output)

    cached_summary = summarize([row["seconds"] for row in cached_rows])
    full_summary = summarize([row["seconds"] for row in full_rows])
    return {
        "schema": 1,
        "config": {"width": width, "height": height, "runs": runs, "kind": kind},
        "cached": {"summary": cached_summary, "runs": cached_rows},
        "forced_full": {"summary": full_summary, "runs": full_rows},
        "speedup": full_summary["median"] / cached_summary["median"],
        "bitwise_equal": True,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=1200)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--kind", choices=("scanner", "print", "output"), default="scanner")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args(argv)
    if args.width <= 0 or args.height <= 0 or args.runs <= 0:
        raise SystemExit("width, height, and runs must be positive")
    payload = run_benchmark(
        width=args.width,
        height=args.height,
        runs=args.runs,
        kind=args.kind,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
        print(args.output_json)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
