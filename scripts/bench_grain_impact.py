"""Benchmark: grain ON vs grain OFF, CPU vs MLX."""
import sys, os, time, gc
import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
sys.path.insert(0, ROOT)

from spektrafilm.utils.numba_warmup import warmup
from spektrafilm.utils.io import load_image_oiio
from spektrafilm.runtime.params_builder import init_params, digest_params
from spektrafilm.runtime.process import Simulator

DNG_PATH = 'IMG20260530191638.dng'
TARGET_SIZE = (1536, 2048)  # H, W

def load_and_resize_dng(path, target_hw):
    """Load DNG via rawpy, resize to target (H, W)."""
    import rawpy
    with rawpy.imread(path) as raw:
        rgb = raw.postprocess(
            use_camera_wb=True,
            output_color=rawpy.ColorSpace.raw,
            output_bps=16,
            no_auto_bright=True,
            gamma=(1, 1),  # linear
        )
    img = rgb.astype(np.float64) / 65535.0
    # resize: target_hw is (H, W), img shape is (H, W, C)
    from scipy.ndimage import zoom
    zoom_h = target_hw[0] / img.shape[0]
    zoom_w = target_hw[1] / img.shape[1]
    return zoom(img, (zoom_h, zoom_w, 1), order=1)


def get_params(backend_name, grain_active=True, grain_sublayers=True, halation=True):
    p = init_params(film_profile='kodak_portra_400', print_profile='kodak_portra_endura')
    p.settings.compute_backend = backend_name
    p.settings.gpu_precision = 'float32'
    p.camera.auto_exposure = True
    p.io.scan_film = False
    p.io.upscale_factor = 1.0
    p.film_render.grain.active = grain_active
    p.film_render.grain.sublayers_active = grain_sublayers
    p.film_render.grain.use_fast_stats = True
    p.settings.use_fast_stats = True
    if not halation:
        p.film_render.halation.scatter_core_um = (0.0, 0.0, 0.0)
        p.film_render.halation.scatter_tail_um = (0.0, 0.0, 0.0)
        p.film_render.halation.halation_first_sigma_um = (0.0, 0.0, 0.0)
        p.film_render.halation.halation_strength = (0.0, 0.0, 0.0)
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    p.settings.lut_resolution = 17
    p.debug.deactivate_stochastic_effects = False
    return digest_params(p)


def run_bench(label, img, params, num_runs=3, num_warmup=1):
    print(f"\n  [{label}] warming up ({num_warmup} run(s))...")
    sim = Simulator(params)
    for _ in range(num_warmup):
        _ = sim.process(img.copy())
    sim.print_timings()

    times = []
    for i in range(num_runs):
        gc.collect()
        time.sleep(0.3)
        sim2 = Simulator(params)
        t0 = time.perf_counter()
        result = sim2.process(img.copy())
        t1 = time.perf_counter()
        elapsed = t1 - t0
        times.append(elapsed)
        print(f"  [{label}] run {i+1}: {elapsed:.3f}s")
        timings = sim2.get_timings()
        # print grain-related timing if present
        for k, v in timings.items():
            if 'grain' in k.lower() or 'develop' in k.lower():
                print(f"      {k}: {v:.4f}s")

    t_min = min(times)
    t_avg = sum(times) / len(times)
    print(f"  [{label}] best: {t_min:.3f}s  avg: {t_avg:.3f}s")
    return t_min, t_avg, result


def check_grain_array_types():
    """Instrument apply_grain to see what array types it receives/returns."""
    import spektrafilm.model.grain as grain_mod
    import spektrafilm.model.emulsion as emulsion_mod

    orig_grain = grain_mod.apply_grain
    grain_info = {}

    def instrumented_grain(density_cmy, *args, **kwargs):
        input_type = type(density_cmy).__name__
        input_module = type(density_cmy).__module__
        result = orig_grain(density_cmy, *args, **kwargs)
        output_type = type(result).__name__
        output_module = type(result).__module__
        grain_info['input'] = f"{input_module}.{input_type}"
        grain_info['output'] = f"{output_module}.{output_type}"
        return result

    grain_mod.apply_grain = instrumented_grain

    orig_develop = emulsion_mod.develop

    def instrumented_develop(log_raw, *args, **kwargs):
        input_type = type(log_raw).__name__
        input_module = type(log_raw).__module__
        grain_info['develop_input'] = f"{input_module}.{input_type}"
        result = orig_develop(log_raw, *args, **kwargs)
        grain_info['develop_output'] = f"{type(result).__module__}.{type(result).__name__}"
        return result

    emulsion_mod.develop = instrumented_develop
    return grain_mod, emulsion_mod, grain_info


def main():
    print("=" * 70)
    print("GRAIN IMPACT BENCHMARK")
    print("=" * 70)

    # Warmup Numba
    print("Warming up Numba JIT...")
    warmup()
    print("Done.")

    # Load image
    print(f"Loading DNG: {DNG_PATH}")
    img = load_and_resize_dng(DNG_PATH, TARGET_SIZE)
    print(f"Image shape: {img.shape}, dtype: {img.dtype}, range: [{img.min():.4f}, {img.max():.4f}]")

    # First: check array types at grain boundary
    print("\n" + "=" * 70)
    print("ARRAY TYPE ANALYSIS (grain boundary)")
    print("=" * 70)

    # Test with MLX backend, grain ON
    grain_mod, emulsion_mod, grain_info = check_grain_array_types()
    p_mlx = get_params('mlx', grain_active=True, grain_sublayers=True)
    print("\nMLX backend + grain ON:")
    sim = Simulator(p_mlx)
    _ = sim.process(img.copy())
    print(f"  develop() receives: {grain_info.get('develop_input', 'N/A')}")
    print(f"  apply_grain() receives: {grain_info.get('input', 'N/A')}")
    print(f"  apply_grain() returns: {grain_info.get('output', 'N/A')}")
    print(f"  develop() returns: {grain_info.get('develop_output', 'N/A')}")

    # Restore
    grain_mod.apply_grain = grain_mod.__dict__.get('_orig_apply_grain', grain_mod.apply_grain)
    emulsion_mod.develop = emulsion_mod.__dict__.get('_orig_develop', emulsion_mod.develop)
    # Actually just reimport
    import importlib
    importlib.reload(grain_mod)
    importlib.reload(emulsion_mod)

    print("\n  ==> Grain is CPU-only: apply_grain receives numpy arrays")
    print("  ==> GPU data is converted to numpy before grain, and must be re-uploaded after")

    # ---- BENCHMARKS ----
    print("\n" + "=" * 70)
    print("BENCHMARK: A. CPU float64, grain ON")
    print("=" * 70)
    p_cpu_on = get_params('cpu', grain_active=True, grain_sublayers=True)
    cpu_on_best, cpu_on_avg, cpu_on_result = run_bench("CPU grain ON", img, p_cpu_on, num_runs=3)

    print("\n" + "=" * 70)
    print("BENCHMARK: B. MLX float32, grain ON")
    print("=" * 70)
    p_mlx_on = get_params('mlx', grain_active=True, grain_sublayers=True)
    mlx_on_best, mlx_on_avg, mlx_on_result = run_bench("MLX grain ON", img, p_mlx_on, num_runs=3)

    print("\n" + "=" * 70)
    print("BENCHMARK: C. MLX float32, grain OFF")
    print("=" * 70)
    p_mlx_off = get_params('mlx', grain_active=False, grain_sublayers=False)
    mlx_off_best, mlx_off_avg, mlx_off_result = run_bench("MLX grain OFF", img, p_mlx_off, num_runs=3)

    # ---- SUMMARY ----
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"  A. CPU  float64, grain ON:  best={cpu_on_best:.3f}s  avg={cpu_on_avg:.3f}s")
    print(f"  B. MLX  float32, grain ON:  best={mlx_on_best:.3f}s  avg={mlx_on_avg:.3f}s")
    print(f"  C. MLX  float32, grain OFF: best={mlx_off_best:.3f}s  avg={mlx_off_avg:.3f}s")
    print()
    print(f"  Grain overhead (CPU):  {cpu_on_best - cpu_on_best:.3f}s (self)")
    print(f"  Grain overhead (MLX):  best={mlx_on_best - mlx_off_best:.3f}s  avg={mlx_on_avg - mlx_off_avg:.3f}s")
    print(f"  MLX speedup with grain ON:  {cpu_on_best / mlx_on_best:.2f}x")
    print(f"  MLX speedup with grain OFF: {cpu_on_best / mlx_off_best:.2f}x  (hypothetical CPU grain OFF)")
    print()

    # Precision check: MLX grain ON vs CPU grain ON
    # Since grain is stochastic, results will differ
    if cpu_on_result is not None and mlx_on_result is not None:
        cpu_out = np.asarray(cpu_on_result, dtype=np.float64)
        mlx_out = np.asarray(mlx_on_result, dtype=np.float64)
        if cpu_out.shape == mlx_out.shape:
            diff = np.abs(cpu_out - mlx_out)
            print(f"  Precision: MLX grain ON vs CPU grain ON")
            print(f"    max_diff = {diff.max():.6f}")
            print(f"    mean_diff = {diff.mean():.6f}")
            print(f"    (NOTE: grain is stochastic, large diffs are expected)")
        else:
            print(f"  Cannot compare: CPU shape {cpu_out.shape} vs MLX shape {mlx_out.shape}")

    print("\n" + "=" * 70)
    print("GRAIN ARCHITECTURE ANALYSIS")
    print("=" * 70)
    print("""
  Grain implementation (model/grain.py):
    - 100% CPU/NumPy: uses np.random, scipy.stats, numba (fast_stats)
    - No MLX/GPU code path exists for grain

  Pipeline data flow when GPU + grain ON:
    1. expose() -> GPU arrays (log_raw)
    2. develop():
       a. develop_simple() -> GPU array (density_cmy) via Metal kernel
       b. backend.to_numpy(density_cmy)  <-- GPU->CPU transfer
       c. backend.to_numpy(log_raw)      <-- GPU->CPU transfer
       d. apply_density_correction_dir_couplers() -> numpy
       e. apply_grain() -> numpy (CPU-only, stochastic)
       f. returns numpy array
    3. printing.expose():
       a. _spectral_compute_enlarger_gpu(cmy_film_density)
       b. backend.asarray(cmy_film_density)  <-- CPU->GPU transfer
       c. ... GPU operations ...
    4. printing.develop() -> GPU array via Metal kernel
    5. scanning.scan() -> final result

  Conclusion: grain forces GPU->CPU->GPU round-trip at the develop() boundary.
  Two extra array transfers per pipeline run (GPU->CPU + CPU->GPU).
""")


if __name__ == "__main__":
    main()
