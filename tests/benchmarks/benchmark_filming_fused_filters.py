"""Benchmark the filming spatial chain: serial MLX vs fused MLX.

This script is intentionally not a pytest test.  Run it manually, for example:

    .venv/bin/python tests/benchmarks/benchmark_filming_fused_filters.py --height 3000 --width 4000
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from typing import Any, Callable

import numpy as np

from spektrafilm.gpu.backend import select_backend
from spektrafilm.model.diffusion import (
    apply_diffusion_filter_um,
    apply_fused_filming_filters,
    apply_gaussian_blur_um,
    apply_halation_um,
)
from spektrafilm.runtime.params_schema import DiffusionFilterParams, HalationParams


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


def _clear_cache(backend) -> None:
    clear = getattr(backend, "clear_cache", None)
    if callable(clear):
        clear()
        return
    mx = getattr(backend, "mx", None)
    clear = getattr(mx, "clear_cache", None)
    if callable(clear):
        clear()
        return
    metal = getattr(mx, "metal", None)
    clear = getattr(metal, "clear_cache", None)
    if callable(clear):
        clear()


def _sync(backend, value: Any) -> None:
    eval_fn = getattr(backend, "eval", None)
    if callable(eval_fn):
        eval_fn(value)


def _summary(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    p90_index = min(len(ordered) - 1, int(round(0.9 * (len(ordered) - 1))))
    return {
        "median_ms": statistics.median(samples) * 1000.0,
        "p90_ms": ordered[p90_index] * 1000.0,
        "min_ms": min(samples) * 1000.0,
        "max_ms": max(samples) * 1000.0,
    }


def _precision(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    diff = np.abs(reference.astype(np.float64) - candidate.astype(np.float64))
    return {
        "max_abs_diff": float(np.max(diff)),
        "mean_abs_diff": float(np.mean(diff)),
        "p90_abs_diff": float(np.percentile(diff, 90.0)),
    }


def _benchmark(name: str, fn: Callable[[], Any], backend, repeats: int) -> tuple[Any, dict[str, Any]]:
    samples: list[float] = []
    print(f"running {name} warmup", file=sys.stderr, flush=True)
    output = fn()
    _sync(backend, output)
    _clear_cache(backend)
    _reset_peak_memory(backend.mx)
    for index in range(repeats):
        print(f"running {name} repeat {index + 1}/{repeats}", file=sys.stderr, flush=True)
        start = time.perf_counter()
        output = fn()
        _sync(backend, output)
        samples.append(time.perf_counter() - start)
    peak = _peak_memory(backend.mx)
    return output, {
        "name": name,
        "summary": _summary(samples),
        "peak_memory_bytes": peak,
        "output_type": type(output).__name__,
        "backend_resident": bool(getattr(backend, "_is_mlx_array", lambda _value: False)(output)),
    }


def _params() -> tuple[DiffusionFilterParams, float, HalationParams, float]:
    diffusion = DiffusionFilterParams(
        active=True,
        filter_family="glimmerglass",
        strength=0.125,
        spatial_scale=0.2,
        halo_warmth=0.1,
    )
    halation = HalationParams(
        active=True,
        scatter_amount=0.4,
        halation_amount=0.2,
        scatter_core_um=(2.0, 3.0, 4.0),
        scatter_tail_um=(5.0, 6.0, 7.0),
        scatter_tail_weight=(0.2, 0.3, 0.4),
        halation_strength=(0.05, 0.02, 0.01),
        halation_first_sigma_um=(8.0, 6.0, 4.0),
        halation_n_bounces=2,
    )
    return diffusion, 4.0, halation, 4.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--path", choices=("both", "serial", "fused"), default="both")
    parser.add_argument("--reference", choices=("full", "small", "none"), default="full")
    parser.add_argument("--reference-height", type=int, default=256)
    parser.add_argument("--reference-width", type=int, default=256)
    args = parser.parse_args()

    backend = select_backend("mlx")
    rng = np.random.default_rng(args.seed)
    image = rng.random((args.height, args.width, 3), dtype=np.float32) + np.float32(0.1)
    diffusion, lens_blur_um, halation, pixel_size_um = _params()

    image_mlx = backend.asarray(image)

    def serial_mlx():
        raw = apply_diffusion_filter_um(image_mlx, diffusion, pixel_size_um, backend=backend)
        raw = apply_gaussian_blur_um(raw, lens_blur_um, pixel_size_um, backend=backend)
        return apply_halation_um(raw, halation, pixel_size_um, backend=backend)

    def fused_mlx():
        return apply_fused_filming_filters(
            image_mlx,
            diffusion_filter=diffusion,
            lens_blur_um=lens_blur_um,
            halation=halation,
            pixel_size_um=pixel_size_um,
            backend=backend,
        )

    outputs: dict[str, Any] = {}
    results: list[dict[str, Any]] = []
    if args.path in ("both", "serial"):
        serial_output, serial_result = _benchmark("serial_mlx", serial_mlx, backend, args.repeats)
        outputs["serial_mlx"] = serial_output
        results.append(serial_result)
        _clear_cache(backend)
    if args.path in ("both", "fused"):
        fused_output, fused_result = _benchmark("fused_mlx", fused_mlx, backend, args.repeats)
        outputs["fused_mlx"] = fused_output
        results.append(fused_result)
        _clear_cache(backend)

    if args.reference != "none":
        if args.reference == "full":
            reference_image = image
        else:
            reference_image = rng.random(
                (args.reference_height, args.reference_width, 3),
                dtype=np.float32,
            ) + np.float32(0.1)
        print(
            f"running {args.reference} NumPy fused reference "
            f"{reference_image.shape[0]}x{reference_image.shape[1]}",
            file=sys.stderr,
            flush=True,
        )
        fused_np_reference = apply_fused_filming_filters(
            reference_image,
            diffusion_filter=diffusion,
            lens_blur_um=lens_blur_um,
            halation=halation,
            pixel_size_um=pixel_size_um,
        )
        if args.reference == "full":
            for result in results:
                output = outputs[result["name"]]
                result["precision_vs_numpy_fused"] = _precision(
                    fused_np_reference,
                    backend.to_numpy(output),
                )
        else:
            reference_mlx = backend.asarray(reference_image)
            fused_small = apply_fused_filming_filters(
                reference_mlx,
                diffusion_filter=diffusion,
                lens_blur_um=lens_blur_um,
                halation=halation,
                pixel_size_um=pixel_size_um,
                backend=backend,
            )
            _sync(backend, fused_small)
            for result in results:
                if result["name"] == "fused_mlx":
                    result["precision_vs_numpy_fused_small"] = _precision(
                        fused_np_reference,
                        backend.to_numpy(fused_small),
                    )

    payload = {
        "suite": "filming_fused_filters",
        "shape": [args.height, args.width, 3],
        "path": args.path,
        "reference": args.reference,
        "results": results,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
