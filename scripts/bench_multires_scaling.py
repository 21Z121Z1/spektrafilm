#!/usr/bin/env python3
"""Multi-resolution scaling benchmark: CPU float64 vs MLX float32.

Loads a DNG, resizes to 4 target resolutions (3MP / 6MP / 9MP / 12MP),
runs the full Spektrafilm pipeline on each for both CPU and MLX backends,
and reports timing, precision, memory, and scaling analysis.
"""

from __future__ import annotations

import gc
import os
import resource
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator

DNG_PATH = "IMG20260530191638.dng"

# Target resolutions (width x height) — portrait orientation
TARGETS = [
    {"label": "3.15MP",  "width": 1536, "height": 2048,  "mp": 3.15},
    {"label": "6.23MP",  "width": 2163, "height": 2884,  "mp": 6.23},
    {"label": "9.35MP",  "width": 2649, "height": 3532,  "mp": 9.35},
    {"label": "12.58MP", "width": 3072, "height": 4096,  "mp": 12.58},
]

TIMEOUT_12MP = 300  # seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_dng(path: str) -> np.ndarray:
    """Load a DNG file via rawpy into float64 [0,1] RGB."""
    import rawpy
    print(f"  Loading DNG: {path}")
    t0 = time.perf_counter()
    raw = rawpy.imread(path)
    rgb16 = raw.postprocess(no_auto_bright=True, output_bps=16)
    img = rgb16.astype(np.float64) / 65535.0
    elapsed = time.perf_counter() - t0
    print(f"  Loaded in {elapsed:.1f}s  shape={img.shape}  dtype={img.dtype}")
    return img


def resize_image(img: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """Resize image to target dimensions using area averaging (for downscale) or bilinear."""
    from PIL import Image

    h, w = img.shape[:2]
    if w == target_w and h == target_h:
        return img

    # Use Pillow for resizing — convert to float32, resize, back to float64
    pil_img = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    pil_resized = pil_img.resize((target_w, target_h), Image.LANCZOS)
    return np.asarray(pil_resized).astype(np.float64) / 255.0


def get_rss_mb() -> float:
    """Get current resident set size in MB (macOS/Linux)."""
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # On macOS ru_maxrss is in bytes; on Linux it is in KB
    if sys.platform == "darwin":
        return usage.ru_maxrss / (1024 * 1024)
    else:
        return usage.ru_maxrss / 1024


def make_params(backend_name: str, precision: str):
    """Build digested params for the given backend."""
    params = init_params(film_profile='kodak_portra_400', print_profile='kodak_portra_endura')
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    params.film_render.halation.active = True
    params.film_render.halation.boost_ev = 1.0
    params.film_render.halation.scatter_amount = 1.0
    params.film_render.halation.halation_amount = 1.0
    params.film_render.grain.active = False
    params.settings.compute_backend = backend_name
    params.settings.gpu_precision = precision
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    params.settings.lut_resolution = 17
    params.debug.print_timings = False
    return digest_params(params)


def check_mlx() -> bool:
    """Check if MLX with Metal is available."""
    try:
        import mlx.core as mx
        probe = mx.array([1.0])
        mx.eval(probe)
        return True
    except Exception:
        return False


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    """Compute PSNR between two float64 images in [0, 1]."""
    mse = float(np.mean((a - b) ** 2))
    if mse <= 0:
        return float('inf')
    return 10.0 * np.log10(1.0 / mse)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------

def run_single(image: np.ndarray, label: str, backend_name: str, precision: str,
               num_warmup: int = 1, num_timed: int = 3,
               timeout: float | None = None) -> dict:
    """Run the pipeline on an image and collect timing + result."""
    gc.collect()
    rss_before = get_rss_mb()

    params = make_params(backend_name, precision)

    # Warmup
    print(f"    [{label}] warmup ({num_warmup} run)...")
    for _ in range(num_warmup):
        sim = Simulator(params)
        _ = sim.process(image.copy())

    # Timed runs
    times = []
    result = None
    print(f"    [{label}] timed runs ({num_timed}x)...")
    for i in range(num_timed):
        if timeout and sum(times) > timeout:
            print(f"    [{label}] timeout after {i} runs, skipping remaining")
            break
        gc.collect()
        time.sleep(0.3)
        sim = Simulator(params)
        t0 = time.perf_counter()
        result = sim.process(image.copy())
        elapsed = time.perf_counter() - t0
        times.append(elapsed)
        print(f"      run {i+1}: {elapsed:.2f}s")

    gc.collect()
    rss_after = get_rss_mb()

    if not times:
        return None

    best = min(times)
    avg = sum(times) / len(times)

    return {
        "result": result,
        "best": best,
        "avg": avg,
        "times": times,
        "rss_before_mb": rss_before,
        "rss_after_mb": rss_after,
        "rss_delta_mb": rss_after - rss_before,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("Spektrafilm Multi-Resolution Scaling Benchmark")
    print("=" * 80)
    print(f"Input: {DNG_PATH}")
    print()

    has_mlx = check_mlx()
    print(f"MLX available: {has_mlx}")
    print()

    # Load DNG at full resolution
    print("Step 1: Loading DNG at full resolution...")
    full_image = load_dng(DNG_PATH)
    src_h, src_w = full_image.shape[:2]
    src_mp = src_h * src_w / 1e6
    print(f"  Native resolution: {src_w}x{src_h} ({src_mp:.2f} MP)")
    print()

    # Step 2: Pre-resize all target images
    print("Step 2: Resizing to target resolutions...")
    resized_images = {}
    for t in TARGETS:
        print(f"  Resizing to {t['width']}x{t['height']} ({t['label']})...")
        resized_images[t['label']] = resize_image(full_image, t['width'], t['height'])
    print()

    # Release full-res image
    del full_image
    gc.collect()

    # Step 3: Run benchmarks
    print("Step 3: Running benchmarks...")
    results = {}

    for t in TARGETS:
        label = t['label']
        mp = t['mp']
        img = resized_images[label]
        h, w = img.shape[:2]
        pixel_count = h * w

        print(f"\n{'='*70}")
        print(f"  Resolution: {label}  ({w}x{h}, {pixel_count:,} pixels, {mp:.2f} MP)")
        print(f"{'='*70}")

        is_12mp = (label == "12.58MP")

        # CPU float64
        cpu_timeout = TIMEOUT_12MP if is_12mp else None
        cpu_num_timed = 1 if is_12mp else 3

        # Check if we should skip 12MP CPU
        # We'll estimate based on 9MP time later; for now try it

        print(f"  -> CPU float64:")
        cpu_res = run_single(img, "CPU float64", "cpu", "float64",
                             num_warmup=1, num_timed=cpu_num_timed,
                             timeout=cpu_timeout)

        if cpu_res is None:
            print(f"    CPU FAILED for {label}")
        else:
            print(f"    Best: {cpu_res['best']:.2f}s  Avg: {cpu_res['avg']:.2f}s  RSS delta: {cpu_res['rss_delta_mb']:.0f} MB")

        # MLX float32
        mlx_res = None
        if has_mlx:
            mlx_timeout = TIMEOUT_12MP if is_12mp else None
            mlx_num_timed = 1 if is_12mp else 3
            print(f"  -> MLX float32:")
            mlx_res = run_single(img, "MLX float32", "mlx", "float32",
                                 num_warmup=1, num_timed=mlx_num_timed,
                                 timeout=mlx_timeout)
            if mlx_res is None:
                print(f"    MLX FAILED for {label}")
            else:
                print(f"    Best: {mlx_res['best']:.2f}s  Avg: {mlx_res['avg']:.2f}s  RSS delta: {mlx_res['rss_delta_mb']:.0f} MB")

        # Precision comparison
        precision = None
        if cpu_res and mlx_res and cpu_res['result'] is not None and mlx_res['result'] is not None:
            cpu_out = np.asarray(cpu_res['result'], dtype=np.float64)
            mlx_out = np.asarray(mlx_res['result'], dtype=np.float64)
            diff = np.abs(cpu_out - mlx_out)
            precision = {
                "max_diff": float(np.max(diff)),
                "mean_diff": float(np.mean(diff)),
                "psnr": psnr(cpu_out, mlx_out),
            }
            print(f"  -> Precision:")
            print(f"    max_diff:  {precision['max_diff']:.4e}")
            print(f"    mean_diff: {precision['mean_diff']:.4e}")
            print(f"    PSNR:      {precision['psnr']:.1f} dB")

        results[label] = {
            "mp": mp,
            "pixels": pixel_count,
            "cpu": cpu_res,
            "mlx": mlx_res,
            "precision": precision,
        }

    # Free resized images
    del resized_images
    gc.collect()

    # Step 4: Analysis
    print(f"\n\n{'='*80}")
    print("RESULTS TABLE")
    print(f"{'='*80}")

    # Header
    hdr = f"{'Size(MP)':>10s} | {'CPU(s)':>8s} | {'MLX(s)':>8s} | {'Speedup':>8s} | {'CPU $/MP':>10s} | {'MLX $/MP':>10s} | {'Scaling':>10s} | {'max_diff':>10s} | {'PSNR':>8s}"
    print(hdr)
    print("-" * len(hdr))

    base_mp = TARGETS[0]['mp']
    base_cpu_time = None
    base_mlx_time = None

    for t in TARGETS:
        label = t['label']
        r = results[label]
        mp = r['mp']
        cpu = r['cpu']
        mlx = r['mlx']
        prec = r['precision']

        cpu_best = cpu['best'] if cpu else None
        mlx_best = mlx['best'] if mlx else None

        speedup = (cpu_best / mlx_best) if (cpu_best and mlx_best) else None
        cpu_per_mp = (cpu_best / mp) if cpu_best else None
        mlx_per_mp = (mlx_best / mp) if mlx_best else None

        # Scaling factor: time(this) / time(base) vs pixel_ratio
        if base_cpu_time is None and cpu_best is not None:
            base_cpu_time = cpu_best
        if base_mlx_time is None and mlx_best is not None:
            base_mlx_time = mlx_best

        scaling = None
        if cpu_best and base_cpu_time:
            pixel_ratio = mp / base_mp
            time_ratio = cpu_best / base_cpu_time
            scaling = time_ratio / pixel_ratio

        max_diff_str = f"{prec['max_diff']:.2e}" if prec else "N/A"
        psnr_str = f"{prec['psnr']:.1f}" if prec else "N/A"

        cpu_str = f"{cpu_best:.2f}" if cpu_best else "TIMEOUT"
        mlx_str = f"{mlx_best:.2f}" if mlx_best else ("N/A" if not has_mlx else "TIMEOUT")
        speedup_str = f"{speedup:.2f}x" if speedup else "N/A"
        cpu_per_mp_str = f"{cpu_per_mp:.2f}" if cpu_per_mp else "N/A"
        mlx_per_mp_str = f"{mlx_per_mp:.2f}" if mlx_per_mp else "N/A"
        scaling_str = f"{scaling:.3f}" if scaling else "N/A"

        print(f"{mp:>10.2f} | {cpu_str:>8s} | {mlx_str:>8s} | {speedup_str:>8s} | {cpu_per_mp_str:>10s} | {mlx_per_mp_str:>10s} | {scaling_str:>10s} | {max_diff_str:>10s} | {psnr_str:>8s}")

    # Step 5: Scaling analysis
    print(f"\n\n{'='*80}")
    print("SCALING ANALYSIS")
    print(f"{'='*80}")

    # Collect valid data points
    cpu_data = [(r['mp'], r['cpu']['best']) for r in results.values() if r['cpu']]
    mlx_data = [(r['mp'], r['mlx']['best']) for r in results.values() if r['mlx']]

    def analyze_scaling(data, label):
        if len(data) < 2:
            print(f"\n  {label}: insufficient data points for scaling analysis")
            return

        print(f"\n  {label} scaling:")
        print(f"    {'MP':>8s} | {'Time(s)':>8s} | {'Time/MP':>8s} | {'PixelRatio':>10s} | {'TimeRatio':>10s} | {'Scaling':>8s}")
        print(f"    {'-'*60}")

        base_mp, base_time = data[0]
        for mp, t in data:
            time_per_mp = t / mp
            pixel_ratio = mp / base_mp
            time_ratio = t / base_time
            scaling_factor = time_ratio / pixel_ratio if pixel_ratio > 0 else float('nan')
            print(f"    {mp:>8.2f} | {t:>8.2f} | {time_per_mp:>8.2f} | {pixel_ratio:>10.2f}x | {time_ratio:>10.2f}x | {scaling_factor:>8.3f}")

        # Linear fit: time = a * pixels + b
        mps = np.array([d[0] for d in data])
        times = np.array([d[1] for d in data])
        pixels = mps * 1e6

        # Compute R^2 for linear model
        coeffs = np.polyfit(pixels, times, 1)
        predicted = np.polyval(coeffs, pixels)
        ss_res = np.sum((times - predicted) ** 2)
        ss_tot = np.sum((times - np.mean(times)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        # Compute R^2 for quadratic model
        coeffs_q = np.polyfit(pixels, times, 2)
        predicted_q = np.polyval(coeffs_q, pixels)
        ss_res_q = np.sum((times - predicted_q) ** 2)
        r_squared_q = 1 - ss_res_q / ss_tot if ss_tot > 0 else 0

        print(f"\n    Linear fit (time = a*pixels + b):  R^2 = {r_squared:.4f}")
        print(f"      a = {coeffs[0]:.6e}  (time per pixel)")
        print(f"      b = {coeffs[1]:.2f}")

        print(f"    Quadratic fit (time = a*pixels^2 + b*pixels + c):  R^2 = {r_squared_q:.4f}")
        print(f"      a = {coeffs_q[0]:.6e}  (quadratic coefficient)")
        print(f"      b = {coeffs_q[1]:.6e}  (linear coefficient)")

        if r_squared > 0.99:
            print(f"    -> LINEAR scaling (R^2 > 0.99)")
        elif r_squared_q > r_squared + 0.01:
            print(f"    -> SUPER-LINEAR scaling (quadratic fit notably better)")
        else:
            print(f"    -> APPROXIMATELY LINEAR with overhead")

    analyze_scaling(cpu_data, "CPU float64")
    analyze_scaling(mlx_data, "MLX float32")

    # Step 6: Speedup trend
    if mlx_data:
        print(f"\n\n{'='*80}")
        print("SPEEDUP TREND")
        print(f"{'='*80}")

        cpu_dict = {mp: t for mp, t in cpu_data}
        mlx_dict = {mp: t for mp, t in mlx_data}
        common_mps = sorted(set(cpu_dict.keys()) & set(mlx_dict.keys()))

        print(f"  {'MP':>8s} | {'CPU(s)':>8s} | {'MLX(s)':>8s} | {'Speedup':>8s}")
        print(f"  {'-'*40}")
        for mp in common_mps:
            speedup = cpu_dict[mp] / mlx_dict[mp]
            print(f"  {mp:>8.2f} | {cpu_dict[mp]:>8.2f} | {mlx_dict[mp]:>8.2f} | {speedup:>7.2f}x")

    # Step 7: Memory
    print(f"\n\n{'='*80}")
    print("MEMORY (RSS delta during pipeline)")
    print(f"{'='*80}")
    print(f"  {'MP':>8s} | {'CPU RSS delta(MB)':>18s} | {'MLX RSS delta(MB)':>18s}")
    print(f"  {'-'*50}")
    for t in TARGETS:
        r = results[t['label']]
        cpu_rss = f"{r['cpu']['rss_delta_mb']:.0f}" if r['cpu'] else "N/A"
        mlx_rss = f"{r['mlx']['rss_delta_mb']:.0f}" if r['mlx'] else "N/A"
        print(f"  {r['mp']:>8.2f} | {cpu_rss:>18s} | {mlx_rss:>18s}")

    print(f"\n{'='*80}")
    print("BENCHMARK COMPLETE")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
