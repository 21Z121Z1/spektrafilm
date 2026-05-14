"""Benchmark GPU (MLX/Metal) vs CPU (Numba) performance for SpektraFilm."""
import sys, os, time, gc
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from spektrafilm.utils.numba_warmup import warmup
from spektrafilm.utils.io import load_image_oiio
from spektrafilm.runtime import init_params, simulate
from spektrafilm.gpu.backend import select_backend
from spektrafilm.model.density_curves import interpolate_exposure_to_density
from spektrafilm.utils.fast_gaussian_filter import (
    fast_gaussian_filter, fast_gaussian_filter_small,
    fast_exponential_filter,
)

try:
    import mlx.core as mx
    HAS_MLX = mx.metal.is_available()
except Exception:
    HAS_MLX = False

FLOAT32_IMG = 'img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif'
WARM_IMG = None  # small image for warmup

def get_params():
    p = init_params(print_profile='kodak_portra_endura')
    p.io.input_cctf_decoding = False
    p.print_render.glare.active = True
    p.debug.deactivate_stochastic_effects = False
    p.camera.auto_exposure = True
    p.io.upscale_factor = 1.0
    p.io.scan_film = False
    p.film_render.grain.agx_particle_area_um2 = 1
    p.enlarger.preflash_exposure = 0.0
    p.enlarger.print_exposure_compensation = True
    p.enlarger.print_exposure = 1.0
    p.film_render.grain.active = True
    p.settings.use_fast_stats = True
    p.settings.use_enlarger_lut = True
    p.settings.use_scanner_lut = True
    p.settings.lut_resolution = 17
    p.debug.output_film_density_cmy = False
    p.debug.output_print_density_cmy = False
    return p


def bench_pipeline(label, backend_name):
    try:
        p = get_params()
        p.settings.compute_backend = backend_name
        p.debug.print_timings = False

        img = load_image_oiio(FLOAT32_IMG)

        # warmup run (not timed)
        _ = simulate(img.copy(), p, print_timings=False)

        # timed runs
        times = []
        for i in range(3):
            gc.collect()
            time.sleep(0.5)
            t0 = time.perf_counter()
            result = simulate(img.copy(), p, print_timings=False)
            t1 = time.perf_counter()
            elapsed = t1 - t0
            times.append(elapsed)
            print(f"  {label} run {i+1}: {elapsed:.3f}s")

        t_min = min(times)
        t_avg = sum(times) / len(times)
        print(f"  {label} best: {t_min:.3f}s  avg: {t_avg:.3f}s")
        return t_min, t_avg, times
    except Exception as e:
        print(f"  {label} FAILED: {e}")
        return None, None, None


def bench_gaussian_filter(label, backend, image_sizes, sigmas, num_runs=10):
    print(f"\n--- Gaussian Filter: {label} ---")
    for size in image_sizes:
        h, w = size, size
        for sigma in sigmas:
            img_cpu = np.random.rand(h, w, 3).astype(np.float32)
            img_backend = backend.asarray(img_cpu) if backend else img_cpu

            # warmup
            if backend and backend.supports_gpu:
                from spektrafilm.gpu.kernels.filters import gaussian_filter_backend
                _ = gaussian_filter_backend(img_backend, sigma, backend)
            else:
                _ = fast_gaussian_filter(img_cpu, sigma)

            times = []
            for _ in range(num_runs):
                if backend and backend.supports_gpu:
                    from spektrafilm.gpu.kernels.filters import gaussian_filter_backend
                    t0 = time.perf_counter()
                    _ = gaussian_filter_backend(img_backend, sigma, backend)
                    backend.eval(_)
                    t1 = time.perf_counter()
                else:
                    t0 = time.perf_counter()
                    _ = fast_gaussian_filter(img_cpu, sigma)
                    t1 = time.perf_counter()
                times.append(t1 - t0)

            t_avg = sum(times) / len(times)
            print(f"  {h}x{w} σ={sigma}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def bench_density_interp(label, backend, sizes, num_runs=10):
    print(f"\n--- Density Interpolation: {label} ---")
    from spektrafilm.gpu.kernels.density import interpolate_exposure_to_density_backend

    K = 40  # typical number of wavelength samples
    log_exposure = np.linspace(-3, 1, K).astype(np.float32)
    density_curves = np.random.rand(K, 3).astype(np.float32)

    for size in sizes:
        h, w = size, size
        log_exp_rgb = np.random.rand(h, w, 3).astype(np.float32) * 2 - 1

        if backend and backend.supports_gpu:
            be = backend.asarray(log_exp_rgb)
            warmup = interpolate_exposure_to_density_backend(be, log_exposure, density_curves, 1.0, backend)
            backend.eval(warmup)

            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                out = interpolate_exposure_to_density_backend(
                    backend.asarray(log_exp_rgb), log_exposure, density_curves, 1.0, backend)
                backend.eval(out)
                t1 = time.perf_counter()
                times.append(t1 - t0)
        else:
            warmup = interpolate_exposure_to_density(log_exp_rgb, density_curves, log_exposure, 1.0)
            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                _ = interpolate_exposure_to_density(log_exp_rgb, density_curves, log_exposure, 1.0)
                t1 = time.perf_counter()
                times.append(t1 - t0)

        t_avg = sum(times) / len(times)
        print(f"  {h}x{w}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def bench_boost_hlight(label, backend, sizes, num_runs=10):
    print(f"\n--- Highlight Boost: {label} ---")
    from spektrafilm.gpu.kernels.color import boost_highlights_backend
    from spektrafilm.utils.numba_boost_hightlights import boost_highlights

    for size in sizes:
        h, w = size, size
        x = np.random.rand(h, w, 3).astype(np.float32) * 2

        if backend and backend.supports_gpu:
            be = backend.asarray(x)
            _ = boost_highlights_backend(be, 2.0, 0.5, 0.5, backend)
            backend.synchronize()

            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                out = boost_highlights_backend(backend.asarray(x), 2.0, 0.5, 0.5, backend)
                backend.eval(out)
                t1 = time.perf_counter()
                times.append(t1 - t0)
        else:
            _ = boost_highlights(x, 2.0, 0.5, 0.5)
            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                _ = boost_highlights(x, 2.0, 0.5, 0.5)
                t1 = time.perf_counter()
                times.append(t1 - t0)

        t_avg = sum(times) / len(times)
        print(f"  {h}x{w}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def bench_cmy_to_log_xyz(label, backend, sizes, num_runs=10):
    print(f"\n--- CMY -> log_XYZ: {label} ---")
    from spektrafilm.gpu.kernels.density import cmy_to_log_xyz_backend

    K = 40
    channel_density = np.random.rand(K, 3).astype(np.float32)
    base_density = np.random.rand(K).astype(np.float32) * 0.02
    scan_illuminant = np.random.rand(K).astype(np.float32)
    cmfs = np.random.rand(K, 3).astype(np.float32)

    for size in sizes:
        h, w = size, size
        density_cmy = np.random.rand(h, w, 3).astype(np.float32) * 0.5

        if backend and backend.supports_gpu:
            be_cmy = backend.asarray(density_cmy)
            _ = cmy_to_log_xyz_backend(be_cmy, channel_density, base_density, scan_illuminant, cmfs, 1.0, backend)
            backend.synchronize()

            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                out = cmy_to_log_xyz_backend(
                    backend.asarray(density_cmy), channel_density, base_density,
                    scan_illuminant, cmfs, 1.0, backend)
                backend.eval(out)
                t1 = time.perf_counter()
                times.append(t1 - t0)
        else:
            def cmy_to_log_xyz_cpu(density_cmy, channel_density, base_density, scan_illuminant, cmfs, normalization):
                K = channel_density.shape[0]
                density_spectral = density_cmy @ channel_density.T
                if base_density is not None:
                    density_spectral = density_spectral + base_density
                transmitted = 10.0 ** (-density_spectral)
                light = transmitted * scan_illuminant
                light = np.nan_to_num(light, nan=0.0)
                xyz = light @ cmfs / normalization
                xyz_safe = np.fmax(xyz, 0.0) + 1e-10
                return np.log10(xyz_safe)

            _ = cmy_to_log_xyz_cpu(density_cmy, channel_density, base_density, scan_illuminant, cmfs, 1.0)
            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                _ = cmy_to_log_xyz_cpu(density_cmy, channel_density, base_density, scan_illuminant, cmfs, 1.0)
                t1 = time.perf_counter()
                times.append(t1 - t0)

        t_avg = sum(times) / len(times)
        print(f"  {h}x{w}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def bench_lut_3d(label, backend, sizes, num_runs=10):
    print(f"\n--- 3D LUT Trilinear: {label} ---")
    from spektrafilm.gpu.kernels.lut import apply_lut_trilinear_3d_mlx, apply_lut_trilinear_3d_numpy

    lut_size = 17
    lut = np.random.rand(lut_size, lut_size, lut_size, 3).astype(np.float32)

    for size in sizes:
        h, w = size, size
        image = np.random.rand(h, w, 3).astype(np.float32)

        if backend and backend.supports_gpu:
            mx_be = backend.mx
            _ = apply_lut_trilinear_3d_mlx(lut, image, mx=mx_be)
            mx.eval(mx_be)

            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                out = apply_lut_trilinear_3d_mlx(lut, image, mx=mx_be)
                mx.eval(out)
                t1 = time.perf_counter()
                times.append(t1 - t0)
        else:
            _ = apply_lut_trilinear_3d_numpy(lut, image)
            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                _ = apply_lut_trilinear_3d_numpy(lut, image)
                t1 = time.perf_counter()
                times.append(t1 - t0)

        t_avg = sum(times) / len(times)
        print(f"  {h}x{w}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def bench_fft_convolve(label, backend, sizes, num_runs=10):
    print(f"\n--- FFT Convolve (same): {label} ---")
    from spektrafilm.gpu.kernels.filters import fft_convolve_same_backend

    kernel_h, kernel_w = 15, 15

    for size in sizes:
        h, w = size, size
        image = np.random.rand(h, w, 3).astype(np.float32)
        kernel = np.random.rand(kernel_h, kernel_w, 3).astype(np.float32)

        if backend and backend.supports_gpu:
            _ = fft_convolve_same_backend(image, kernel, backend)
            backend.synchronize()

            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                out = fft_convolve_same_backend(image, kernel, backend)
                backend.eval(out)
                t1 = time.perf_counter()
                times.append(t1 - t0)
        else:
            from scipy.signal import fftconvolve
            _ = fftconvolve(image[:,:,0], kernel[:,:,0], mode='same')
            times = []
            for _ in range(num_runs):
                t0 = time.perf_counter()
                for c in range(3):
                    _ = fftconvolve(image[:,:,c], kernel[:,:,c], mode='same')
                t1 = time.perf_counter()
                times.append(t1 - t0)

        t_avg = sum(times) / len(times)
        print(f"  {h}x{w} kernel={kernel_h}x{kernel_w}: {t_avg*1000:.1f}ms (best {min(times)*1000:.1f}ms)")


def main():
    print("=" * 70)
    print("SpektraFilm GPU vs CPU Performance Benchmark")
    print("=" * 70)
    print(f"Hardware: Apple M1 Pro, 16GB")
    print(f"MLX available: {HAS_MLX}")
    print()

    # Warmup Numba
    print("Warming up Numba JIT...")
    warmup()
    print("Done.")

    SIZES = [256, 512, 1000, 2048]
    SIZES_SMALL = [256, 512]  # larger sizes would take too long on CPU

    # ---- End-to-end pipeline ----
    print("\n" + "=" * 70)
    print("END-TO-END PIPELINE (1000x667 image)")
    print("=" * 70)
    cpu_best, cpu_avg, _ = bench_pipeline("CPU (Numba)", "cpu")
    gpu_best, gpu_avg, _ = bench_pipeline("GPU (MLX/Metal)", "mlx")

    if cpu_best and gpu_best:
        speedup = cpu_best / gpu_best
        print(f"\n  >>> End-to-end speedup (GPU/CPU): {speedup:.2f}x")

    # ---- Micro-benchmarks ----
    print("\n" + "=" * 70)
    print("MICRO-BENCHMARKS")
    print("=" * 70)

    # Gaussian filter
    cpu_backend = select_backend("cpu")
    gpu_backend = select_backend("mlx")

    SIZES_MICRO = [256, 512, 1000, 2000]

    bench_gaussian_filter("CPU (Numba)", cpu_backend, SIZES_MICRO, [1.0, 5.0], num_runs=10)

    if HAS_MLX:
        bench_gaussian_filter("GPU (Metal)", gpu_backend, SIZES_MICRO, [1.0, 5.0], num_runs=10)

    # Density interpolation
    SIZES_DENSE = [256, 512, 1000, 2000]
    bench_density_interp("CPU (Numba)", cpu_backend, SIZES_DENSE, num_runs=10)
    if HAS_MLX:
        bench_density_interp("GPU (Metal)", gpu_backend, SIZES_DENSE, num_runs=10)

    # Highlight boost
    bench_boost_hlight("CPU (Numba)", cpu_backend, SIZES_DENSE, num_runs=10)
    if HAS_MLX:
        bench_boost_hlight("GPU (Metal)", gpu_backend, SIZES_DENSE, num_runs=10)

    # CMY -> log_XYZ
    bench_cmy_to_log_xyz("CPU (Numba)", cpu_backend, SIZES_DENSE, num_runs=10)
    if HAS_MLX:
        bench_cmy_to_log_xyz("GPU (Metal)", gpu_backend, SIZES_DENSE, num_runs=10)

    # 3D LUT
    bench_lut_3d("CPU (NumPy)", cpu_backend, SIZES_DENSE, num_runs=10)
    if HAS_MLX:
        bench_lut_3d("GPU (Metal)", gpu_backend, SIZES_DENSE, num_runs=10)

    # FFT convolve
    bench_fft_convolve("CPU (SciPy)", cpu_backend, [256, 512, 1000], num_runs=5)
    if HAS_MLX:
        bench_fft_convolve("GPU (MLX)", gpu_backend, [256, 512, 1000], num_runs=5)

    print("\n" + "=" * 70)
    print("BENCHMARK COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
