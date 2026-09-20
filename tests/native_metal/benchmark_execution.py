"""Matched post-upsampling film-stage benchmark. Not RAW-to-RGB timing."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
from statistics import median
import subprocess
from time import perf_counter

import numpy as np

from spektrafilm.gpu.native_metal.executor import NativeExecutor, NativeSession
from spektrafilm.gpu.native_metal.program import Builder, LOG10, prepare_spatial, prepare_development
from spektrafilm.model.develop import develop
from spektrafilm.model.diffusion import apply_halation_um
from spektrafilm.profiles.io import load_profile
from spektrafilm.runtime.params_schema import HalationParams, DirCouplersParams, GrainParams
from spektrafilm.utils.fast_gaussian_filter import fast_gaussian_filter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--budget-mib", type=int, default=2048)
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("at least one measured run is required")
    profile = load_profile("kodak_portra_400")
    halation, couplers, grain = HalationParams(), DirCouplersParams(), GrainParams(active=False)
    pitch, lens = 10.0, 8.0
    data = profile.data
    b = Builder()
    spatial = b.extend(prepare_spatial(halation, pitch, lens_blur_um=lens), 0)
    exposure = b.add(LOG10, (spatial,))
    negative = b.extend(prepare_development(data.log_exposure, data.density_curves, data.density_curves_layers,
                                           couplers, grain, pitch), exposure)
    program = b.finish(negative)
    compiled = program.compile()
    image = np.random.default_rng(725).uniform(.01, 4, (args.height, args.width, 3)).astype(np.float32)
    host_input = image.astype(np.float64)

    def cpu():
        raw = fast_gaussian_filter(host_input, lens/pitch)
        raw = apply_halation_um(raw, halation, pitch)
        log = np.log10(np.fmax(raw, 0) + 1e-10)
        return develop(log, pitch, data.log_exposure, data.density_curves, data.density_curves_layers,
                       couplers, grain, profile.info.type)

    cpu_times, native_times, native_c_times, runs = [], [], [], []
    with NativeExecutor(args.bundle, max_resident_bytes=args.budget_mib * 1024**2) as engine, \
            engine.prepare(program) as prepared, engine.upload(image) as source:
        # Warm both paths. Drop full outputs, not just their Python names in a cache.
        warm = cpu();del warm
        output, _ = engine.run(prepared, source)
        output.close()
        for index in range(args.runs):
            # Alternate order to reduce systematic first-in-pair bias.
            expected = actual = stats = None
            for path in (("cpu", "native") if index % 2 == 0 else ("native", "cpu")):
                start = perf_counter()
                if path == "cpu":
                    expected = cpu()
                    cpu_times.append(perf_counter()-start)
                else:
                    output, stats = engine.run(prepared, source)
                    with output:
                        actual = output.numpy()
                    native_times.append(perf_counter()-start)
                    native_c_times.append(stats.synchronized_seconds)
            np.testing.assert_allclose(actual, expected, atol=1e-6, rtol=1e-6)
            error = np.abs(actual-expected)
            runs.append({"max_abs": float(error.max()), "rms": float(np.sqrt(np.mean(error**2))),
                         "digest": hashlib.sha256(actual.tobytes()).hexdigest(), "native": asdict(stats)})
            del actual, expected, error
        assert len({run["digest"] for run in runs}) == 1
        occupied = asdict(engine.statistics)
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "unknown"
    report = {
        "scope": "post-upsampling lens/halation/log/DIR-development; grain off; not whole film/RAW pipeline",
        "sha": sha, "platform": platform.platform(), "shape": list(image.shape),
        "program": compiled.fingerprint, "slots": compiled.slots,
        "input_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "configuration": {"stock": "kodak_portra_400", "pixel_size_um": pitch, "lens_blur_um": lens,
                          "halation": asdict(halation), "couplers": asdict(couplers), "grain": asdict(grain)},
        "timing_boundary": "CPU float64 prepared input -> NumPy output; native already-uploaded float32 input -> NumPy output, including wait/readback; setup/upload excluded on both",
        "cpu_seconds": cpu_times, "native_seconds": native_times, "native_c_seconds": native_c_times,
        "cpu_median": median(cpu_times), "native_median": median(native_times),
        "buffer_accounting": occupied,
        "process_maxrss_raw": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "maxrss_unit": "bytes on macOS, KiB on Linux; not Metal buffer bytes",
        "runs": runs,
        "not_measured": ["RAW decode", "spectral upsampling", "print/scan/output", "legacy MLX equivalence", "50 MP unless explicitly requested"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps({"cpu_median": report["cpu_median"], "native_median": report["native_median"], "scope": report["scope"]}))


if __name__ == "__main__":
    main()
