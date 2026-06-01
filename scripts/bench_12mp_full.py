"""12MP Full-Resolution Benchmark: CPU float64 vs MLX float32

Loads a DNG at full 4096x3072 resolution and runs the complete
Spektrafilm pipeline on both CPU float64 and MLX float32 backends.
Reports per-stage timing and precision comparison.
"""

import gc
import sys
import os
import time
import copy

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
from spektrafilm.runtime.params_builder import init_params, digest_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.gpu.backend import select_backend

DNG_PATH = "/Users/retriedstormtrooper/Documents/OPPO 互联/IMG20260530191638.dng"

# Baseline numbers (pre-optimization)
BASELINE = {
    "cpu_time": 213.4,
    "mlx_time": 51.2,
    "speedup": 4.16,
    "max_diff": 4.66e-2,
    "mean_diff": 1.25e-3,
    "psnr": 53.5,
}


def load_image():
    """Load DNG at full resolution as ProPhoto RGB linear."""
    print(f"Loading DNG: {DNG_PATH}")
    t0 = time.perf_counter()
    image = load_and_process_raw_file(
        DNG_PATH,
        white_balance='as_shot',
        output_colorspace='ProPhoto RGB',
        output_cctf_encoding=False,
    )
    elapsed = time.perf_counter() - t0
    print(f"  Loaded in {elapsed:.1f}s  shape={image.shape}  dtype={image.dtype}")
    print(f"  Range: [{image.min():.6f}, {image.max():.6f}]")
    return image


def build_params(backend_name, precision):
    """Build digested params for the given backend."""
    params = init_params(film_profile='kodak_portra_400', print_profile='kodak_portra_endura')
    # Input is linear ProPhoto RGB (raw output from rawpy)
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    # Halation ON with boost_ev=1.0, scatter=1.0, halation=1.0
    params.film_render.halation.active = True
    params.film_render.halation.boost_ev = 1.0
    params.film_render.halation.scatter_amount = 1.0
    params.film_render.halation.halation_amount = 1.0
    # Grain OFF
    params.film_render.grain.active = False
    # Backend
    params.settings.compute_backend = backend_name
    params.settings.gpu_precision = precision
    # LUT enabled for performance
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    params.settings.lut_resolution = 17
    params.debug.print_timings = True
    return digest_params(params)


def run_benchmark(image, label, backend_name, precision, num_runs=1):
    """Run the pipeline and collect timings."""
    print(f"\n{'='*70}")
    print(f"BENCHMARK: {label}")
    print(f"{'='*70}")

    params = build_params(backend_name, precision)

    # Warmup run
    print("  Warmup run...")
    gc.collect()
    img_copy = image.copy()
    sim = Simulator(params)
    _ = sim.process(img_copy)
    warmup_time = sim.get_total_elapsed_time()
    print(f"  Warmup: {warmup_time:.1f}s")

    # Timed runs
    times = []
    all_timings = []
    for i in range(num_runs):
        gc.collect()
        time.sleep(0.5)
        img_copy = image.copy()
        sim = Simulator(params)
        result = sim.process(img_copy)
        elapsed = sim.get_total_elapsed_time()
        timings = sim.get_timings()
        times.append(elapsed)
        all_timings.append(timings)
        print(f"  Run {i+1}: {elapsed:.1f}s")
        # Print formatted timings
        sim.print_timings()

    best_time = min(times)
    avg_time = sum(times) / len(times)

    # Use the timings from the best run
    best_idx = times.index(best_time)
    best_timings = all_timings[best_idx]

    print(f"\n  Best time: {best_time:.1f}s  Avg: {avg_time:.1f}s")
    return result, best_time, avg_time, best_timings


def compute_precision(cpu_result, mlx_result):
    """Compare MLX result against CPU reference."""
    cpu = np.asarray(cpu_result, dtype=np.float64)
    mlx = np.asarray(mlx_result, dtype=np.float64)

    diff = np.abs(cpu - mlx)
    max_diff = float(np.max(diff))
    mean_diff = float(np.mean(diff))
    median_diff = float(np.median(diff))

    # PSNR
    mse = float(np.mean((cpu - mlx) ** 2))
    if mse > 0:
        psnr = 10.0 * np.log10(1.0 / mse)
    else:
        psnr = float('inf')

    # Per-channel stats
    ch_max = [float(np.max(diff[:, :, c])) for c in range(3)]
    ch_mean = [float(np.mean(diff[:, :, c])) for c in range(3)]

    return {
        "max_diff": max_diff,
        "mean_diff": mean_diff,
        "median_diff": median_diff,
        "mse": mse,
        "psnr": psnr,
        "ch_max": ch_max,
        "ch_mean": ch_mean,
    }


def format_stage_comparison(cpu_timings, mlx_timings):
    """Format a per-stage timing comparison table."""
    all_keys = sorted(set(list(cpu_timings.keys()) + list(mlx_timings.keys())))
    lines = []
    lines.append(f"  {'Stage':<50s} {'CPU (s)':>10s} {'MLX (s)':>10s} {'Speedup':>10s}")
    lines.append(f"  {'-'*50} {'-'*10} {'-'*10} {'-'*10}")
    for key in all_keys:
        cpu_t = cpu_timings.get(key, 0.0)
        mlx_t = mlx_timings.get(key, 0.0)
        if cpu_t > 0 and mlx_t > 0:
            speedup = cpu_t / mlx_t
            lines.append(f"  {key:<50s} {cpu_t:>10.2f} {mlx_t:>10.2f} {speedup:>9.2f}x")
        elif cpu_t > 0:
            lines.append(f"  {key:<50s} {cpu_t:>10.2f} {'N/A':>10s} {'':>10s}")
        elif mlx_t > 0:
            lines.append(f"  {'':50s} {'N/A':>10s} {mlx_t:>10.2f} {'':>10s}")
    return "\n".join(lines)


def main():
    print("="*70)
    print("Spektrafilm 12MP Full-Resolution Benchmark")
    print("="*70)
    print(f"Input: {DNG_PATH}")
    print(f"Resolution: 4096x3072 (12.6 MP)")
    print(f"Film: kodak_portra_400  Print: kodak_portra_endura")
    print(f"Grain: OFF  Halation: ON (boost_ev=1.0, scatter=1.0, halation=1.0)")
    print()

    # Check backends
    cpu_backend = select_backend("cpu")
    print(f"CPU backend: {cpu_backend.name}")

    mlx_backend = None
    try:
        mlx_backend = select_backend("mlx", precision="float32")
        print(f"MLX backend: {mlx_backend.name}")
    except Exception as e:
        print(f"MLX backend: UNAVAILABLE ({e})")

    # Load image
    image = load_image()

    # Run CPU float64
    cpu_result, cpu_time, cpu_avg, cpu_timings = run_benchmark(
        image, "CPU float64", "cpu", "float64", num_runs=1
    )

    # Run MLX float32
    mlx_result = None
    mlx_time = None
    mlx_timings = None
    if mlx_backend is not None:
        mlx_result, mlx_time, mlx_avg, mlx_timings = run_benchmark(
            image, "MLX float32", "mlx", "float32", num_runs=1
        )

    # Precision comparison
    print(f"\n{'='*70}")
    print("PRECISION COMPARISON (MLX float32 vs CPU float64)")
    print(f"{'='*70}")
    if mlx_result is not None:
        precision = compute_precision(cpu_result, mlx_result)
        print(f"  max_diff:    {precision['max_diff']:.4e}")
        print(f"  mean_diff:   {precision['mean_diff']:.4e}")
        print(f"  median_diff: {precision['median_diff']:.4e}")
        print(f"  MSE:         {precision['mse']:.4e}")
        print(f"  PSNR:        {precision['psnr']:.1f} dB")
        print(f"  Per-channel max_diff:  R={precision['ch_max'][0]:.4e}  G={precision['ch_max'][1]:.4e}  B={precision['ch_max'][2]:.4e}")
        print(f"  Per-channel mean_diff: R={precision['ch_mean'][0]:.4e}  G={precision['ch_mean'][1]:.4e}  B={precision['ch_mean'][2]:.4e}")
    else:
        print("  MLX not available, skipping precision comparison.")

    # Speedup
    speedup = None
    if mlx_time is not None:
        speedup = cpu_time / mlx_time

    # Summary comparison
    print(f"\n{'='*70}")
    print("SUMMARY COMPARISON (Baseline vs Current)")
    print(f"{'='*70}")
    print(f"  {'Metric':<30s} {'Baseline':>15s} {'Current':>15s} {'Delta':>15s}")
    print(f"  {'-'*30} {'-'*15} {'-'*15} {'-'*15}")
    print(f"  {'CPU float64 (s)':<30s} {BASELINE['cpu_time']:>15.1f} {cpu_time:>15.1f} {cpu_time - BASELINE['cpu_time']:>+15.1f}")
    if mlx_time is not None:
        print(f"  {'MLX float32 (s)':<30s} {BASELINE['mlx_time']:>15.1f} {mlx_time:>15.1f} {mlx_time - BASELINE['mlx_time']:>+15.1f}")
        print(f"  {'Speedup':<30s} {BASELINE['speedup']:>14.2f}x {speedup:>14.2f}x {speedup - BASELINE['speedup']:>+14.2f}x")
    if mlx_result is not None:
        print(f"  {'max_diff':<30s} {BASELINE['max_diff']:>15.4e} {precision['max_diff']:>15.4e} {precision['max_diff'] - BASELINE['max_diff']:>+15.4e}")
        print(f"  {'mean_diff':<30s} {BASELINE['mean_diff']:>15.4e} {precision['mean_diff']:>15.4e} {precision['mean_diff'] - BASELINE['mean_diff']:>+15.4e}")
        print(f"  {'PSNR (dB)':<30s} {BASELINE['psnr']:>15.1f} {precision['psnr']:>15.1f} {precision['psnr'] - BASELINE['psnr']:>+15.1f}")

    # Per-stage timing comparison
    if mlx_timings is not None:
        print(f"\n{'='*70}")
        print("PER-STAGE TIMING COMPARISON")
        print(f"{'='*70}")
        print(format_stage_comparison(cpu_timings, mlx_timings))

    # Verdict
    print(f"\n{'='*70}")
    print("VERDICT")
    print(f"{'='*70}")
    if speedup is not None:
        if mlx_time < BASELINE['mlx_time'] * 0.95:
            verdict = "IMPROVED"
        elif mlx_time > BASELINE['mlx_time'] * 1.05:
            verdict = "REGRESSED"
        else:
            verdict = "NO SIGNIFICANT CHANGE"
        print(f"  MLX speed: {verdict}")
        print(f"  MLX time: {BASELINE['mlx_time']:.1f}s -> {mlx_time:.1f}s ({mlx_time - BASELINE['mlx_time']:+.1f}s)")
        print(f"  Speedup:  {BASELINE['speedup']:.2f}x -> {speedup:.2f}x")
    if mlx_result is not None:
        if precision['psnr'] > BASELINE['psnr'] - 1.0:
            prec_verdict = "STABLE"
        else:
            prec_verdict = "DEGRADED"
        print(f"  Precision: {prec_verdict}")
        print(f"  PSNR: {BASELINE['psnr']:.1f} dB -> {precision['psnr']:.1f} dB")


if __name__ == "__main__":
    main()
