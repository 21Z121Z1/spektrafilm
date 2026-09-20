"""Synchronized Gaussian microbenchmark, NOT a complete film-pipeline benchmark."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
from time import perf_counter

import numpy as np

from spektrafilm.gpu.native_metal import NativeMetalSpatial, prepare_gaussian
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--sigma", type=float, default=20)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.width <= 16384 or not 1 <= args.height <= 16384 or args.runs < 1:
        parser.error("invalid dimensions or run count")
    image = np.random.default_rng(2109).random((args.height, args.width, 3), dtype=np.float32)
    image *= np.float32(16)
    setup_start = perf_counter()
    plan = prepare_gaussian(args.sigma, 3)
    with NativeMetalSpatial(args.bundle) as engine:
        setup = perf_counter() - setup_start
        actual, cold = engine.apply(image, plan)
        start = perf_counter()
        reference = fast_gaussian_filter(image, args.sigma)
        cpu_cold = perf_counter() - start
        cpu_times, native_times = [], []
        for _ in range(args.runs):
            start = perf_counter()
            reference = fast_gaussian_filter(image, args.sigma)
            cpu_times.append(perf_counter() - start)
            actual, stats = engine.apply(image, plan)
            native_times.append(stats.synchronized_seconds)
            np.testing.assert_allclose(actual, reference, rtol=1e-6, atol=1e-6)
        # Also compare to CPU float64, outside both timing boundaries.
        reference64 = fast_gaussian_filter(image.astype(np.float64), args.sigma)
        np.testing.assert_allclose(actual, reference64, rtol=1e-6, atol=1e-6)
        max_abs = float(np.max(np.abs(actual - reference64)))
    report = {
        "scope": "standalone Gaussian; includes image upload, wait and readback; excludes RAW/film/grain/HDR/UI",
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "numpy": np.__version__,
        "commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "shape": list(image.shape), "sigma": args.sigma, "truncate": 3.0,
        "native_context_and_plan_seconds": setup, "cpu_cold_including_jit_seconds": cpu_cold,
        "native_first": asdict(cold), "native_last": asdict(stats),
        "cpu_seconds": cpu_times, "native_seconds": native_times,
        "cpu_median_seconds": statistics.median(cpu_times),
        "native_median_seconds": statistics.median(native_times),
        "max_abs_vs_cpu64": max_abs, "atol": 1e-6, "rtol": 1e-6,
        "output_sha256": hashlib.sha256(actual.tobytes()).hexdigest(),
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "peak_rss_scope": "whole benchmark, including both CPU references; macOS bytes",
        "production_backend_changed": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
