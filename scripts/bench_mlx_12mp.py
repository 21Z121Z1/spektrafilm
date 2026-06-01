#!/usr/bin/env python3
"""Unified timing benchmark — three modes for MLX on a 12 MP image.

Mode 1: wall-clock (user experience)
  Full pipeline call; no manual syncs. This is what the user actually waits.

Mode 2: synced-stage (true per-stage cost)
  Each stage method is called individually, then mx.eval() is forced on its
  output before the next stage.  Isolates GPU compute cost from lazy eval
  deferral.

Mode 3: final-materialize (MLX -> numpy + output)
  After the pipeline completes, measures:
    mx.eval(result) + np.asarray(result, dtype=float64)

Each mode uses a SEPARATE SimulationPipeline invocation so cached LUTs do
not distort timing.
"""

from __future__ import annotations

import time
import numpy as np

INPUT_IMAGE = "/Users/retriedstormtrooper/Documents/OPPO 互联/IMG20260530191638.dng"
FILM_PROFILE = "kodak_portra_400"
PRINT_PROFILE = "kodak_portra_endura"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def make_params():
    from spektrafilm.runtime.params_builder import digest_params, init_params
    params = init_params(film_profile=FILM_PROFILE, print_profile=PRINT_PROFILE)
    params.film_render.grain.active = False
    params.camera.auto_exposure = False
    params.io.output_cctf_encoding = True
    params.debug.deactivate_stochastic_effects = True
    return digest_params(params)


def is_mlx_array(val) -> bool:
    return type(val).__module__.startswith("mlx.")


def mlx_eval(val):
    """mx.eval no-op for non-MLX arrays."""
    if is_mlx_array(val):
        import mlx.core as mx
        mx.eval(val)


def fmt_time(seconds: float) -> str:
    if seconds >= 1.0:
        return f"{seconds:.3f} s"
    if seconds >= 1e-3:
        return f"{seconds * 1e3:.2f} ms"
    return f"{seconds * 1e6:.1f} us"


def pct(part: float, total: float) -> str:
    if total <= 0:
        return "  -  "
    return f"{part / total * 100:5.1f}%"


# ---------------------------------------------------------------------------
# Mode 1: wall-clock
# ---------------------------------------------------------------------------

def run_mode1_wallclock(raw_img, params):
    from spektrafilm.runtime.pipeline import SimulationPipeline

    sim = SimulationPipeline(params)
    t0 = time.perf_counter()
    result = sim.process(raw_img)
    t_wall = time.perf_counter() - t0
    return result, t_wall, sim.timings


# ---------------------------------------------------------------------------
# Mode 2: synced-stage
# ---------------------------------------------------------------------------

def run_mode2_synced(raw_img, params):
    from spektrafilm.runtime.pipeline import SimulationPipeline

    sim = SimulationPipeline(params)
    timings = {}
    total_start = time.perf_counter()

    # --- preprocess ---
    t0 = time.perf_counter()
    image = np.double(np.array(raw_img)[:, :, 0:3])
    image = sim._filming_stage.auto_exposure(image)
    image = sim._resize_service.crop_and_rescale(image)
    timings["preprocess"] = time.perf_counter() - t0

    # --- film expose ---
    t0 = time.perf_counter()
    log_raw_film = sim._filming_stage.expose(image)
    mlx_eval(log_raw_film)
    timings["film.expose"] = time.perf_counter() - t0

    # --- film develop ---
    t0 = time.perf_counter()
    cmy_film = sim._filming_stage.develop(log_raw_film)
    mlx_eval(cmy_film)
    timings["film.develop"] = time.perf_counter() - t0

    # --- print expose ---
    t0 = time.perf_counter()
    log_raw_print = sim._printing_stage.expose(cmy_film)
    mlx_eval(log_raw_print)
    timings["print.expose"] = time.perf_counter() - t0

    # --- print develop ---
    t0 = time.perf_counter()
    cmy_print = sim._printing_stage.develop(log_raw_print)
    mlx_eval(cmy_print)
    timings["print.develop"] = time.perf_counter() - t0

    # --- scan ---
    t0 = time.perf_counter()
    rgb_scan = sim._scanning_stage.scan(cmy_print)
    mlx_eval(rgb_scan)
    timings["scan"] = time.perf_counter() - t0

    t_total = time.perf_counter() - total_start

    # --- materialize (Mode 3 measurement, piggy-backed) ---
    t0 = time.perf_counter()
    result_np = np.asarray(rgb_scan, dtype=np.float64)
    t_materialize = time.perf_counter() - t0

    return result_np, timings, t_total, t_materialize


# ---------------------------------------------------------------------------
# Mode 3: standalone materialize (separate pipeline invocation)
# ---------------------------------------------------------------------------

def run_mode3_materialize(raw_img, params):
    from spektrafilm.runtime.pipeline import SimulationPipeline

    sim = SimulationPipeline(params)
    # Run the full pipeline but do NOT call np.asarray at the end.
    # Replicate _pipeline without the final np.asarray to get a raw result.
    image = np.double(np.array(raw_img)[:, :, 0:3])
    image = sim._filming_stage.auto_exposure(image)
    image = sim._resize_service.crop_and_rescale(image)

    log_raw_film = sim._filming_stage.expose(image)
    cmy_film = sim._filming_stage.develop(log_raw_film)
    log_raw_print = sim._printing_stage.expose(cmy_film)
    cmy_print = sim._printing_stage.develop(log_raw_print)
    rgb_scan = sim._scanning_stage.scan(cmy_print)

    # Now time the materialize step: eval + to numpy
    t0 = time.perf_counter()
    mlx_eval(rgb_scan)
    result_np = np.asarray(rgb_scan, dtype=np.float64)
    t_materialize = time.perf_counter() - t0

    return t_materialize


# ---------------------------------------------------------------------------
# CPU float64 reference
# ---------------------------------------------------------------------------

def run_cpu_reference(raw_img, params):
    from spektrafilm.runtime.pipeline import SimulationPipeline

    cpu_params = make_params()
    cpu_params.settings.compute_backend = "cpu"
    cpu_params.settings.gpu_precision = "float64"

    sim = SimulationPipeline(cpu_params)
    t0 = time.perf_counter()
    result = sim.process(raw_img)
    t_wall = time.perf_counter() - t0
    return result, t_wall


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def load_dng(path: str) -> np.ndarray:
    """Load a DNG file via rawpy into float64 [0,1] RGB."""
    import rawpy
    raw = rawpy.imread(path)
    rgb16 = raw.postprocess(no_auto_bright=True, output_bps=16)
    return rgb16.astype(np.float64) / 65535.0


def main():
    import sys
    sys.path.insert(0, "src")

    print("Loading image ...")
    raw_img = load_dng(INPUT_IMAGE)
    print(f"  Image shape: {raw_img.shape}  (~{raw_img.shape[0]*raw_img.shape[1]/1e6:.1f} MP)")

    try:
        import mlx.core as mx
        # quick probe to confirm Metal is available
        probe = mx.array([1.0])
        mx.eval(probe)
        HAS_MLX = True
        print(f"  MLX backend: available")
    except Exception as e:
        HAS_MLX = False
        print(f"  MLX backend: NOT available ({e})")
        print("  Running CPU-only benchmark.\n")

    params = make_params()
    if HAS_MLX:
        params.settings.compute_backend = "mlx"
        params.settings.gpu_precision = "float32"

    # ---- Warmup: first invocation primes JIT caches for CPU path ----
    print("\n>>> CPU warmup ...")
    warmup_cpu_params = make_params()
    warmup_cpu_params.settings.compute_backend = "cpu"
    warmup_cpu_params.settings.gpu_precision = "float64"
    from spektrafilm.runtime.pipeline import SimulationPipeline
    sim_warm_cpu = SimulationPipeline(warmup_cpu_params)
    _ = sim_warm_cpu.process(raw_img)
    print("  Warmup done.")

    print("\n>>> CPU float64 reference ...")
    _, t_cpu = run_cpu_reference(raw_img, params)
    print(f"  CPU wall-clock: {fmt_time(t_cpu)}")

    if not HAS_MLX:
        print("\nNo MLX available. CPU-only results above.")
        return

    # ---- Warmup: first MLX invocation primes LUT caches ----
    print("\n>>> MLX warmup (builds LUT caches) ...")
    warmup_params = make_params()
    warmup_params.settings.compute_backend = "mlx"
    warmup_params.settings.gpu_precision = "float32"
    from spektrafilm.runtime.pipeline import SimulationPipeline
    sim_warm = SimulationPipeline(warmup_params)
    _ = sim_warm.process(raw_img)
    print("  Warmup done.\n")

    # ---- Mode 1: wall-clock ----
    print(">>> Mode 1: wall-clock (user experience) ...")
    params1 = make_params()
    params1.settings.compute_backend = "mlx"
    params1.settings.gpu_precision = "float32"
    result1, t_wall, internal_timings = run_mode1_wallclock(raw_img, params1)
    print(f"  Wall-clock: {fmt_time(t_wall)}")
    for k, v in internal_timings.items():
        print(f"    {k}: {fmt_time(v)}  ({pct(v, t_wall)})")

    # ---- Mode 2: synced-stage ----
    print("\n>>> Mode 2: synced-stage (true per-stage cost) ...")
    params2 = make_params()
    params2.settings.compute_backend = "mlx"
    params2.settings.gpu_precision = "float32"
    result2, stage_timings, t_synced, t_mat_from_mode2 = run_mode2_synced(raw_img, params2)
    print(f"  Synced total: {fmt_time(t_synced)}")
    for k, v in stage_timings.items():
        print(f"    {k}: {fmt_time(v)}  ({pct(v, t_synced)})")

    # ---- Mode 3: final-materialize (separate invocation) ----
    print("\n>>> Mode 3: final-materialize (MLX -> numpy) ...")
    params3 = make_params()
    params3.settings.compute_backend = "mlx"
    params3.settings.gpu_precision = "float32"
    t_materialize = run_mode3_materialize(raw_img, params3)
    print(f"  mx.eval + np.asarray: {fmt_time(t_materialize)}")

    # ---- Comparison table ----
    print("\n" + "=" * 90)
    print("UNIFIED TIMING COMPARISON")
    print(f"  Input:  {INPUT_IMAGE}")
    print(f"  Image:  {raw_img.shape[1]}x{raw_img.shape[0]} ({raw_img.shape[0]*raw_img.shape[1]/1e6:.1f} MP)")
    print(f"  Config: {FILM_PROFILE} / {PRINT_PROFILE}, grain OFF, halation ON, AE OFF, CCTF ON")
    print(f"  MLX:    float32")
    print("=" * 90)

    # Stage names for the table
    stage_order = [
        "preprocess",
        "film.expose",
        "film.develop",
        "print.expose",
        "print.develop",
        "scan",
    ]

    # Header
    print(f"\n{'Stage':<20} {'wall-clock':>14} {'synced':>14} {'synced %':>10} {'materialize':>14}")
    print("-" * 76)

    # Rows per stage
    wall_total = t_wall
    synced_total = t_synced

    # Map stage abbreviations to @timeit keys
    stage_to_wall_key = {
        "preprocess": None,  # no @timeit for preprocess
        "film.expose": "FilmingStage.expose",
        "film.develop": "FilmingStage.develop",
        "print.expose": "PrintingStage.expose",
        "print.develop": "PrintingStage.develop",
        "scan": "ScanningStage.scan",
    }

    for stage in stage_order:
        synced = stage_timings.get(stage, None)
        wall_key = stage_to_wall_key.get(stage)
        wall_val = internal_timings.get(wall_key) if wall_key else None

        w_str = fmt_time(wall_val) if wall_val is not None else "  (merged)  "
        s_str = fmt_time(synced) if synced is not None else "-"
        s_pct = pct(synced, synced_total) if synced is not None else "-"
        m_str = "-"

        print(f"  {stage:<18} {w_str:>14} {s_str:>14} {s_pct:>10} {m_str:>14}")

    print("-" * 76)

    # Totals row
    print(f"  {'TOTAL':<18} {fmt_time(t_wall):>14} {fmt_time(t_synced):>14} {'100.0%':>10} {'':>14}")
    print(f"  {'materialize':<18} {'(incl.)':>14} {fmt_time(t_mat_from_mode2):>14} {pct(t_mat_from_mode2, synced_total):>10} {fmt_time(t_materialize):>14}")
    print(f"  {'CPU float64':<18} {fmt_time(t_cpu):>14} {'':>14} {'':>10} {'':>14}")

    # Summary
    speedup = t_cpu / t_wall if t_wall > 0 else float('inf')
    print(f"\n  MLX wall-clock speedup vs CPU:  {speedup:.2f}x")
    print(f"  MLX synced total:              {fmt_time(t_synced)}")
    print(f"  MLX materialize (standalone):  {fmt_time(t_materialize)}")
    print(f"  MLX materialize (in-pipeline): {fmt_time(t_mat_from_mode2)}")
    print(f"  CPU float64 wall-clock:        {fmt_time(t_cpu)}")


if __name__ == "__main__":
    main()
