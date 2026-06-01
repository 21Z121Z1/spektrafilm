#!/usr/bin/env python3
"""Unified timing benchmark: MLX on 12 MP image, three timing modes + CPU reference.

Each mode uses a SEPARATE pipeline invocation (no LUT cache reuse between modes).
"""

from __future__ import annotations

import time
import numpy as np

# ---------------------------------------------------------------------------
# Load input image (once)
# ---------------------------------------------------------------------------
INPUT_PATH = "/Users/retriedstormtrooper/Documents/OPPO 互联/IMG20260530191638.dng"

from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

print("Loading RAW image...")
raw_img = load_and_process_raw_file(
    INPUT_PATH,
    white_balance="as_shot",
    output_colorspace="ProPhoto RGB",
    output_cctf_encoding=False,
)
mp = raw_img.shape[0] * raw_img.shape[1] / 1e6
print(f"  Shape: {raw_img.shape}  ({mp:.1f} MP), dtype={raw_img.dtype}")

# ---------------------------------------------------------------------------
# Params builders
# ---------------------------------------------------------------------------
from spektrafilm.runtime.params_builder import init_params, digest_params
from spektrafilm.runtime.pipeline import SimulationPipeline
import mlx.core as mx


def _build_params(backend_name: str):
    params = init_params("kodak_portra_400", "kodak_portra_endura")
    params.film_render.grain.active = False          # grain OFF
    params.film_render.halation.active = True         # halation ON
    params.camera.auto_exposure = False               # auto_exposure OFF
    params.io.output_cctf_encoding = True             # CCTF ON
    params.settings.compute_backend = backend_name
    if backend_name == "mlx":
        params.settings.gpu_precision = "float32"
    return digest_params(params)


# ---------------------------------------------------------------------------
# Warmup runs (JIT compile, LUT cache population)
# ---------------------------------------------------------------------------
print("\n--- Warmup: MLX ---")
p_w = _build_params("mlx")
sim_w = SimulationPipeline(p_w)
_ = sim_w.process(raw_img)
print("  done.")
del sim_w, p_w

print("--- Warmup: CPU ---")
p_wc = _build_params("cpu")
sim_wc = SimulationPipeline(p_wc)
_ = sim_wc.process(raw_img)
print("  done.")
del sim_wc, p_wc


def _sync(backend):
    """Force all pending GPU work to complete."""
    backend.synchronize()


# ===================================================================
# MODE 1 — Wall-clock (user experience)
# Each backend gets its own fresh pipeline. No manual sync.
# ===================================================================
print("\n" + "=" * 72)
print("MODE 1: Wall-clock (end-to-end, no manual sync)")
print("=" * 72)

# MLX
p1m = _build_params("mlx")
sim1m = SimulationPipeline(p1m)
t0 = time.perf_counter()
result_mlx = sim1m.process(raw_img)
t_wall_mlx = time.perf_counter() - t0
print(f"  MLX wall-clock: {t_wall_mlx:.4f} s")

# CPU
p1c = _build_params("cpu")
sim1c = SimulationPipeline(p1c)
t0 = time.perf_counter()
result_cpu = sim1c.process(raw_img)
t_wall_cpu = time.perf_counter() - t0
print(f"  CPU wall-clock: {t_wall_cpu:.4f} s")

# ===================================================================
# MODE 2 — Synced-stage (true per-stage cost)
# Manually drive each stage, then force mx.synchronize() after each.
# Fresh pipeline (no LUT reuse).
# ===================================================================
print("\n" + "=" * 72)
print("MODE 2: Synced-stage (mx.synchronize after each stage)")
print("=" * 72)

p2 = _build_params("mlx")
sim2 = SimulationPipeline(p2)
be = sim2._backend

stage_times: dict[str, float] = {}

def _timed_synced(name: str, fn, *args, backend=be):
    """Call fn(*args), then sync the GPU, and return the result + elapsed."""
    t0 = time.perf_counter()
    result = fn(*args)
    _sync(backend)
    elapsed = time.perf_counter() - t0
    stage_times[name] = elapsed
    return result

# preprocess
img = np.double(np.array(raw_img)[:, :, 0:3])
img = _timed_synced("preprocess.auto_exposure", sim2._filming_stage.auto_exposure, img)
img = _timed_synced("preprocess.crop_rescale", sim2._resize_service.crop_and_rescale, img)

# filming
log_raw_film = _timed_synced("filming.expose", sim2._filming_stage.expose, img)
cmy_film     = _timed_synced("filming.develop", sim2._filming_stage.develop, log_raw_film)

# printing
log_raw_print = _timed_synced("printing.expose", sim2._printing_stage.expose, cmy_film)
cmy_print     = _timed_synced("printing.develop", sim2._printing_stage.develop, log_raw_print)

# scanning
rgb_scan = _timed_synced("scanning.scan", sim2._scanning_stage.scan, cmy_print)

# final conversion
t0 = time.perf_counter()
final = np.asarray(rgb_scan, dtype=np.float64)
stage_times["np.asarray(final)"] = time.perf_counter() - t0

synced_total = sum(stage_times.values())

print(f"\n  {'Stage':<32s} {'Time (s)':>10s}  {'%':>6s}")
print(f"  {'-' * 32} {'-' * 10}  {'-' * 6}")
for name, t in stage_times.items():
    pct = t / synced_total * 100
    print(f"  {name:<32s} {t:>10.4f}  {pct:>5.1f}%")
print(f"  {'-' * 32} {'-' * 10}  {'-' * 6}")
print(f"  {'TOTAL (synced)':<32s} {synced_total:>10.4f}  {100.0:>5.1f}%")

# Also show the decorator-based internal timings
print(f"\n  Internal @timeit timings (from pipeline):")
for k, v in sorted(sim2.get_timings().items()):
    print(f"    {k}: {v:.4f} s")

# ===================================================================
# MODE 3 — Final materialize (MLX array → numpy)
# Fresh pipeline, intercept before the final np.asarray.
# ===================================================================
print("\n" + "=" * 72)
print("MODE 3: Final materialize (MLX → numpy)")
print("=" * 72)

p3 = _build_params("mlx")
sim3 = SimulationPipeline(p3)
be3 = sim3._backend

# Run full pipeline manually up to scan (no final np.asarray)
img3 = np.double(np.array(raw_img)[:, :, 0:3])
img3 = sim3._filming_stage.auto_exposure(img3)
img3 = sim3._resize_service.crop_and_rescale(img3)
log_raw_film3 = sim3._filming_stage.expose(img3)
cmy_film3 = sim3._filming_stage.develop(log_raw_film3)
log_raw_print3 = sim3._printing_stage.expose(cmy_film3)
cmy_print3 = sim3._printing_stage.develop(log_raw_print3)
rgb_scan3 = sim3._scanning_stage.scan(cmy_print3)

arr_type = type(rgb_scan3).__module__ + "." + type(rgb_scan3).__qualname__
print(f"  Pipeline output type: {arr_type}")
is_mlx_arr = type(rgb_scan3).__module__.startswith("mlx.")

if is_mlx_arr:
    # 3a: eval then asarray (two-step)
    _sync(be3)  # ensure scan is computed
    t0 = time.perf_counter()
    mx.eval(rgb_scan3)
    t_eval_only = time.perf_counter() - t0

    t0 = time.perf_counter()
    _ = np.asarray(rgb_scan3, dtype=np.float64)
    t_copy_only = time.perf_counter() - t0

    print(f"\n  3a) Two-step materialize:")
    print(f"      mx.eval()     = {t_eval_only:.4f} s")
    print(f"      np.asarray()  = {t_copy_only:.4f} s")
    print(f"      Total         = {t_eval_only + t_copy_only:.4f} s")

    # 3b: just np.asarray (eval is implicit) — need fresh data
    img3b = np.double(np.array(raw_img)[:, :, 0:3])
    img3b = sim3._filming_stage.auto_exposure(img3b)
    img3b = sim3._resize_service.crop_and_rescale(img3b)
    lrf3b = sim3._filming_stage.expose(img3b)
    cmf3b = sim3._filming_stage.develop(lrf3b)
    lrp3b = sim3._printing_stage.expose(cmf3b)
    cmp3b = sim3._printing_stage.develop(lrp3b)
    rs3b = sim3._scanning_stage.scan(cmp3b)
    _sync(be3)  # scan done, but result is still lazy in rs3b

    t0 = time.perf_counter()
    _ = np.asarray(rs3b, dtype=np.float64)
    t_just_asarray = time.perf_counter() - t0
    print(f"\n  3b) np.asarray() only (eval implicit) = {t_just_asarray:.4f} s")
else:
    print("  Output is already numpy — materialize cost negligible.")
    t0 = time.perf_counter()
    _ = np.asarray(rgb_scan3, dtype=np.float64)
    print(f"  np.asarray() = {time.perf_counter() - t0:.6f} s")

# ===================================================================
# CPU reference timings (per-stage, from pipeline decorators)
# ===================================================================
print("\n" + "=" * 72)
print("CPU REFERENCE: per-stage timings (decorator-based)")
print("=" * 72)

for k, v in sorted(sim1c.get_timings().items()):
    print(f"  {k:<40s} {v:>10.4f} s")
print(f"  {'Total elapsed':<40s} {sim1c.get_total_elapsed_time():>10.4f} s")

# ===================================================================
# UNIFIED COMPARISON TABLE
# ===================================================================
print("\n" + "=" * 72)
print(f"UNIFIED COMPARISON TABLE  ({mp:.1f} MP, grain OFF, halation ON)")
print("=" * 72)

# Per-stage comparison (from @timeit)
mlx_stage_times = dict(sorted(sim1m.get_timings().items()))
cpu_stage_times = dict(sorted(sim1c.get_timings().items()))

all_stages = sorted(set(list(mlx_stage_times.keys()) + list(cpu_stage_times.keys())))

print(f"\n  {'Stage':<35s} {'MLX (s)':>10s} {'CPU (s)':>10s} {'Speedup':>10s}")
print(f"  {'-' * 35} {'-' * 10} {'-' * 10} {'-' * 10}")
for s in all_stages:
    mt = mlx_stage_times.get(s)
    ct = cpu_stage_times.get(s)
    ms = f"{mt:.4f}" if mt is not None else "—"
    cs = f"{ct:.4f}" if ct is not None else "—"
    sp = f"{ct / mt:.2f}x" if (mt is not None and ct is not None and mt > 0) else "—"
    print(f"  {s:<35s} {ms:>10s} {cs:>10s} {sp:>10s}")

print(f"\n  {'Summary':<35s} {'MLX (s)':>10s} {'CPU (s)':>10s} {'Speedup':>10s}")
print(f"  {'-' * 35} {'-' * 10} {'-' * 10} {'-' * 10}")
print(f"  {'Mode 1: Wall-clock (no sync)':<35s} {t_wall_mlx:>10.4f} {t_wall_cpu:>10.4f} {t_wall_cpu / t_wall_mlx:>9.2f}x")
print(f"  {'Mode 2: Synced total':<35s} {synced_total:>10.4f} {'—':>10s} {'—':>10s}")
if is_mlx_arr:
    print(f"  {'Mode 3a: eval + asarray':<35s} {t_eval_only + t_copy_only:>10.4f} {'—':>10s} {'—':>10s}")
    print(f"  {'Mode 3b: asarray only':<35s} {t_just_asarray:>10.4f} {'—':>10s} {'—':>10s}")

# Pipeline internal totals
print(f"\n  {'Pipeline internal elapsed':<35s} {'MLX (s)':>10s} {'CPU (s)':>10s}")
print(f"  {'-' * 35} {'-' * 10} {'-' * 10}")
print(f"  {'Total (from @timeit)':<35s} {sim1m.get_total_elapsed_time():>10.4f} {sim1c.get_total_elapsed_time():>10.4f}")

print("\nDone.")
