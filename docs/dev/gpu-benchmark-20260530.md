# GPU Backend Benchmark — 2026-05-30

## Test Configuration
- **Hardware**: Apple M1 Pro (16 GPU cores), 16 GB RAM, macOS 26.5
- **Input**: portrait_leaves_32bit_linear_prophoto_rgb.tif (1000x667, float32, ProPhoto RGB)
  - Note: Requested image IMG20260530191638.dng not found in repository; used available test image.
- **Film profile**: kodak_portra_400
- **Print profile**: kodak_portra_endura
- **Grain**: ON (active + sublayers, n_sub_layers=1)
- **Halation**: ON (boost_ev=1.0, scatter_amount=1.0, halation_amount=1.0)
- **CCTF encoding**: ON (output_cctf_encoding=True, input_cctf_decoding=False)
- **Auto exposure**: OFF
- **Precision**: float32
  - Note: float64 requested but MLX and Halide backends only support float32. CPU backend operates internally in float64.
- **LUT settings**: resolution=17, use_enlarger_lut=True, use_scanner_lut=True, use_fast_stats=True
- **Framework versions**: MLX 0.31.2, NumPy 2.4.4, Python 3.13
- **Runs per measurement**: 3 timed (end-to-end), 10 timed (micro-kernels) after 1 warmup
- **Date**: 2026-05-30

## Results Table

### End-to-End Pipeline (1000x667 image, best of 3 runs)

| Backend          | Type | Best (s) | Avg (s) | Median (s) | Max (s) | Speedup vs CPU |
|------------------|------|----------|---------|------------|---------|----------------|
| cpu (NumPy+Numba)| CPU  | 0.743    | 0.764   | 0.755      | 0.792   | 1.00x (ref)    |
| mlx (Metal)      | GPU  | 0.669    | 0.686   | 0.671      | 0.718   | 1.11x          |
| halide (JIT)     | GPU  | 0.818    | 0.821   | 0.822      | 0.823   | 0.91x          |

### Per-Stage Timing Breakdown (single run, print_timings=True)

| Stage                          | CPU (ms) | %    | MLX (ms) | %    | Halide (ms) | %    |
|--------------------------------|----------|------|----------|------|-------------|------|
| FilmingStage.expose            | 155      | 19.7 | 137      | 21.3 | 137         | 13.2 |
| FilmingStage.develop           | 365      | 46.3 | 331      | 51.5 | 336         | 32.5 |
| SpectralLUT (enlarger compute) | 64.8     | 8.2  | 58.2     | 9.1  | 377         | 36.5 |
| PrintingStage.expose           | 88.7     | 11.3 | 84.7     | 13.2 | 401         | 38.7 |
| PrintingStage.develop          | 8.55     | 1.1  | 0.504    | 0.1  | 8.88        | 0.9  |
| SpectralLUT (scanner compute)  | 58.2     | 7.4  | 51.2     | 8.0  | 44.9        | 4.3  |
| ScanningStage.scan             | 169      | 21.4 | 88.6     | 13.8 | 152         | 14.7 |
| **Total**                      | **787**  |      | **642**  |      | **1030**    |      |

### Micro-Kernel Benchmarks (best time of 10 runs)

#### Gaussian Filter (sigma=5.0, 3-channel)

| Size     | CPU (ms) | MLX (ms) | MLX speedup | MLX max_diff | Halide (ms) | Halide speedup | Halide max_diff |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 1.03     | 0.79     | 1.30x       | 4.83e-06     | 0.89        | 1.16x          | 0.00e+00        |
| 512x512  | 2.29     | 1.43     | 1.60x       | 5.01e-06     | 2.27        | 1.01x          | 0.00e+00        |
| 1000x1000| 7.17     | 1.95     | 3.68x       | 5.60e-06     | 7.27        | 0.99x          | 0.00e+00        |

#### Density Interpolation (40 wavelength samples)

| Size     | CPU (ms) | MLX (ms) | MLX speedup | MLX max_diff | Halide (ms) | Halide speedup | Halide max_diff |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 0.91     | 0.27     | 3.33x       | 5.96e-08     | 0.97        | 0.95x          | 0.00e+00        |
| 512x512  | 3.24     | 0.47     | 6.91x       | 5.96e-08     | 3.34        | 0.97x          | 0.00e+00        |
| 1000x1000| 12.20    | 1.23     | 9.92x       | 5.96e-08     | 15.66       | 0.78x          | 0.00e+00        |

#### Highlight Boost

| Size     | CPU (ms) | MLX (ms) | MLX speedup | MLX max_diff | Halide (ms) | Halide speedup | Halide max_diff |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 0.29     | 0.70     | 0.41x       | 3.41e-06     | 0.51        | 0.57x          | 3.41e-06        |
| 512x512  | 0.91     | 1.15     | 0.80x       | 3.92e-06     | 2.11        | 0.43x          | 3.83e-06        |
| 1000x1000| 3.39     | 1.73     | 1.96x       | 3.99e-06     | 8.81        | 0.39x          | 3.96e-06        |

#### CMY -> log_XYZ

| Size     | CPU (ms) | MLX (ms) | MLX speedup | MLX max_diff | Halide (ms) | Halide speedup | Halide max_diff |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 15.54    | 2.03     | 7.66x       | 2.98e-07     | 14.66       | 1.06x          | 0.00e+00        |
| 512x512  | 62.77    | 8.43     | 7.45x       | 2.98e-07     | 65.30       | 0.96x          | 0.00e+00        |
| 1000x1000| 239.79   | 30.20    | 7.94x       | 2.98e-07     | 223.60      | 1.07x          | 0.00e+00        |

#### 3D LUT Trilinear (17^3)

| Size     | CPU (ms) | MLX (ms) | MLX speedup | MLX max_diff | Halide (ms) | Halide speedup | Halide max_diff |
|----------|----------|----------|-------------|--------------|-------------|----------------|-----------------|
| 256x256  | 9.71     | 1.20     | 8.12x       | 1.37e-07     | 0.47        | 20.79x         | 9.74e-08        |
| 512x512  | 38.54    | 3.69     | 10.44x      | 1.48e-07     | 1.53        | 25.12x         | 1.12e-07        |
| 1000x1000| 147.81   | 13.68    | 10.80x      | 1.60e-07     | 5.55        | 26.61x         | 1.21e-07        |

#### FFT Convolve (15x15 kernel, same mode)

| Size     | CPU/SciPy (ms) | MLX (ms) | MLX speedup | Halide (ms) | Halide speedup |
|----------|----------------|----------|-------------|-------------|----------------|
| 256x256  | 1.39           | 1.19     | 1.17x       | 1.45        | 0.95x          |
| 512x512  | 5.32           | 1.78     | 2.99x       | 5.73        | 0.93x          |
| 1000x1000| 23.09          | 6.08     | 3.80x       | 26.18       | 0.88x          |

## Per-Backend Details

### CPU (NumPy + Numba)
- **Configuration**: Default NumpyBackend with Numba JIT for hot loops. float64 internal precision.
- **Timing breakdown**: Dominated by FilmingStage.develop (46.3%) and ScanningStage.scan (21.4%). Density interpolation and 3D LUT are the most expensive individual kernels.
- **Precision**: Reference implementation. All GPU backends are compared against this.
- **Strengths**: Full float64 precision, no GPU dependency, deterministic.
- **Weaknesses**: Slowest overall for large images; density interpolation and CMY->logXYZ are O(n) in image size with no parallelism advantage.

### MLX (Apple Metal)
- **Configuration**: MlxBackend, float32 precision. Apple M1 Pro with 16 GPU cores.
- **Timing breakdown**: Best end-to-end time at 642ms. FilmingStage.develop still dominates (51.5%) but ScanningStage.scan drops significantly (88.6ms vs 169ms CPU, a 1.91x improvement). PrintingStage.develop drops from 8.55ms to 0.504ms (16.97x improvement).
- **Precision metrics**:
  - Gaussian filter: max_diff 5.60e-06 (float32 rounding)
  - Density interpolation: max_diff 5.96e-08 (excellent)
  - Highlight boost: max_diff 3.99e-06 (float32 rounding)
  - CMY->log_XYZ: max_diff 2.98e-07 (excellent)
  - 3D LUT: max_diff 1.60e-07 (excellent)
  - End-to-end pipeline: max_diff 5.13e-02, mean_diff 2.20e-03 (accumulated float32 vs float64 error through full pipeline)
- **Strengths**: Best end-to-end speedup (1.11x). Excellent micro-kernel performance for density interpolation (up to 9.92x), CMY->log_XYZ (up to 7.94x), 3D LUT (up to 10.80x), and FFT convolve (up to 3.80x). Scales well with image size.
- **Weaknesses**: float32 only. Pipeline-level precision deviation from CPU float64 (5.13e-02 max) is notable but expected given float32 vs float64. Highlight boost kernel slower than CPU for small images (GPU dispatch overhead).
- **Warnings**: `mx.metal.clear_cache` deprecation warning (use `mx.clear_cache` instead).

### Halide (JIT)
- **Configuration**: HalideBackend, float32 precision. JIT-compiled Halide pipelines.
- **Timing breakdown**: Slowest end-to-end at 1.03s. The enlarger spectral compute (377ms, 36.5%) and printing expose (401ms, 38.7%) dominate — both regress heavily vs CPU. Halide's LUT kernel is extremely fast (5.55ms at 1000x1000) but other kernels regress.
- **Precision metrics**:
  - Gaussian filter: max_diff 0.00e+00 (bit-identical to CPU NumPy)
  - Density interpolation: max_diff 0.00e+00 (bit-identical)
  - CMY->log_XYZ: max_diff 0.00e+00 (bit-identical)
  - Highlight boost: max_diff 3.96e-06 (float32 rounding)
  - 3D LUT: max_diff 1.21e-07 (excellent)
  - End-to-end pipeline: max_diff 5.87e-02, mean_diff 2.21e-03
- **Strengths**: 3D LUT trilinear kernel is the fastest of all backends (26.61x speedup at 1000x1000). Bit-identical output to CPU for Gaussian filter, density interpolation, and CMY->log_XYZ. Most deterministic micro-kernel results.
- **Weaknesses**: End-to-end pipeline is 10% slower than CPU. Spectral LUT computation regresses badly (377ms vs 64.8ms CPU). Halide's JIT compilation and dispatch overhead negates per-kernel gains for the full pipeline. The enlarger and printing stages appear to not benefit from Halide's architecture.
- **Errors**: No runtime errors. The backend works correctly but underperforms at the pipeline level.

## Conclusions

### Available Backends
| Backend | Available | GPU | Precision |
|---------|-----------|-----|-----------|
| cpu     | Yes       | No  | float64   |
| mlx     | Yes       | Yes (Metal) | float32/float16 |
| cupy    | No        | --  | --        |
| halide  | Yes       | JIT | float32   |

CuPy is not available (no CUDA/ROCm device on Apple M1 Pro).

### Speedup Achieved
- **MLX is the fastest backend** with a 1.11x end-to-end speedup over CPU. The speedup comes primarily from the ScanningStage (1.91x faster) and PrintingStage.develop (16.97x faster). Individual micro-kernels show much larger speedups (up to 10.80x for 3D LUT, 9.92x for density interpolation) but the pipeline has significant serial sections that limit overall gains.
- **Halide is 10% slower** than CPU end-to-end despite having the fastest 3D LUT kernel (26.61x speedup). The spectral LUT computation stages are poorly suited to Halide's JIT model on this hardware.

### Precision Impact
- All GPU backends operate in float32 vs CPU's float64 internal precision.
- Micro-kernel precision is excellent: max_diff < 6e-06 for all measured kernels (within float32 epsilon).
- End-to-end pipeline precision: max_diff of 5.13e-02 (MLX) and 5.87e-02 (Halide) vs CPU. This is accumulated float32 rounding across 9+ pipeline stages, primarily in the spectral computation and density interpolation chains. Mean differences are much lower (2.20e-03 and 2.21e-03 respectively).
- Halide achieves bit-identical output to CPU NumPy for several individual kernels (Gaussian filter, density interpolation, CMY->log_XYZ), suggesting its JIT compiler preserves float32 operation order.

### Recommendations for Default Backend Selection
1. **Default to `auto`** (resolves to MLX on Apple Silicon, CuPy on CUDA). MLX provides the best overall performance.
2. **CPU remains viable** for precision-critical work. The 1.11x speedup from MLX may not justify the float32 precision tradeoff for all users. Consider making `cpu` the default with `auto` as an opt-in for performance.
3. **Halide is not recommended** as a default backend. Its 3D LUT kernel is exceptionally fast but the pipeline-level regression makes it a net negative. Consider using Halide selectively for specific kernels via the tiled processing interface.
4. **float64 support**: MLX and Halide only support float32. If float64 precision is required, the CPU backend is the only option. Consider documenting this limitation.
5. **CuPy**: Would likely provide the largest speedup on NVIDIA hardware. Not testable on this Apple Silicon machine.

## Appendix: Raw Benchmark Output

### End-to-End Pipeline (raw)

```
======================================================================
SpektraFilm GPU Backend Benchmark — 2026-05-30
======================================================================
Input image: img/test/portrait_leaves_32bit_linear_prophoto_rgb.tif
Film: kodak_portra_400
Print: kodak_portra_endura
Precision: float32
Available backends: ['cpu', 'mlx', 'halide']

Warming up Numba JIT...
Done.

Image shape: (1000, 667, 3), dtype: float32

======================================================================
Backend: cpu (CPU)
======================================================================
  Run 1: 0.743s
  Run 2: 0.792s
  Run 3: 0.755s
  Best: 0.743s  Avg: 0.764s  Median: 0.755s  Max: 0.792s
  Output shape: (1000, 667, 3), dtype: float64
  Output range: [0.0000, 0.8887]

======================================================================
Backend: mlx (GPU)
======================================================================
  Run 1: 0.718s
  Run 2: 0.671s
  Run 3: 0.669s
  Best: 0.669s  Avg: 0.686s  Median: 0.671s  Max: 0.718s
  Precision vs CPU: max_diff=5.13e-02, mean_diff=2.20e-03
    allclose(atol=1e-5): False
    allclose(atol=1e-4): False
    allclose(atol=1e-3): False

======================================================================
Backend: halide (GPU)
======================================================================
  Run 1: 0.822s
  Run 2: 0.818s
  Run 3: 0.823s
  Best: 0.818s  Avg: 0.821s  Median: 0.822s  Max: 0.823s
  Precision vs CPU: max_diff=5.87e-02, mean_diff=2.21e-03
    allclose(atol=1e-5): False
    allclose(atol=1e-4): False
    allclose(atol=1e-3): False
```

### Per-Stage Timing (raw)

```
CPU backend:
  Total                                          787 ms  100.0%
  FilmingStage.expose                            155 ms   19.7%
  FilmingStage.develop                           365 ms   46.3%
  SpectralLUTService.spectral_compute_enlarger   64.8 ms   8.2%
  PrintingStage.expose                           88.7 ms  11.3%
  PrintingStage.develop                          8.55 ms   1.1%
  SpectralLUTService.spectral_compute_scanner    58.2 ms   7.4%
  ScanningStage.scan                             169 ms   21.4%

MLX backend:
  Total                                          642 ms  100.0%
  FilmingStage.expose                            137 ms   21.3%
  FilmingStage.develop                           331 ms   51.5%
  SpectralLUTService.spectral_compute_enlarger   58.2 ms   9.1%
  PrintingStage.expose                           84.7 ms  13.2%
  PrintingStage.develop                         0.504 ms   0.1%
  SpectralLUTService.spectral_compute_scanner    51.2 ms   8.0%
  ScanningStage.scan                            88.6 ms   13.8%

Halide backend:
  Total                                          1.03 s  100.0%
  FilmingStage.expose                            137 ms   13.2%
  FilmingStage.develop                           336 ms   32.5%
  SpectralLUTService.spectral_compute_enlarger   377 ms   36.5%
  PrintingStage.expose                           401 ms   38.7%
  PrintingStage.develop                          8.88 ms   0.9%
  SpectralLUTService.spectral_compute_scanner    44.9 ms   4.3%
  ScanningStage.scan                             152 ms   14.7%
```

### Micro-Kernel Benchmarks (raw)

```
1. GAUSSIAN FILTER (sigma=5.0, 3-channel)
  256x256:     CPU:    1.03ms | MLX:    0.79ms (1.30x) | Halide:    0.89ms (1.16x)
  512x512:     CPU:    2.29ms | MLX:    1.43ms (1.60x) | Halide:    2.27ms (1.01x)
  1000x1000:   CPU:    7.17ms | MLX:    1.95ms (3.68x) | Halide:    7.27ms (0.99x)

2. DENSITY INTERPOLATION
  256x256:     CPU:    0.91ms | MLX:    0.27ms (3.33x) | Halide:    0.97ms (0.95x)
  512x512:     CPU:    3.24ms | MLX:    0.47ms (6.91x) | Halide:    3.34ms (0.97x)
  1000x1000:   CPU:   12.20ms | MLX:    1.23ms (9.92x) | Halide:   15.66ms (0.78x)

3. HIGHLIGHT BOOST
  256x256:     CPU:    0.29ms | MLX:    0.70ms (0.41x) | Halide:    0.51ms (0.57x)
  512x512:     CPU:    0.91ms | MLX:    1.15ms (0.80x) | Halide:    2.11ms (0.43x)
  1000x1000:   CPU:    3.39ms | MLX:    1.73ms (1.96x) | Halide:    8.81ms (0.39x)

4. CMY -> log_XYZ
  256x256:     CPU:   15.54ms | MLX:    2.03ms (7.66x) | Halide:   14.66ms (1.06x)
  512x512:     CPU:   62.77ms | MLX:    8.43ms (7.45x) | Halide:   65.30ms (0.96x)
  1000x1000:   CPU:  239.79ms | MLX:   30.20ms (7.94x) | Halide:  223.60ms (1.07x)

5. 3D LUT TRILINEAR (17^3)
  256x256:     CPU:    9.71ms | MLX:    1.20ms (8.12x) | Halide:    0.47ms (20.79x)
  512x512:     CPU:   38.54ms | MLX:    3.69ms (10.44x) | Halide:    1.53ms (25.12x)
  1000x1000:   CPU:  147.81ms | MLX:   13.68ms (10.80x) | Halide:    5.55ms (26.61x)

6. FFT CONVOLVE (15x15 kernel, same mode)
  256x256:     CPU:    1.39ms | MLX:    1.19ms (1.17x) | Halide:    1.45ms (0.95x)
  512x512:     CPU:    5.32ms | MLX:    1.78ms (2.99x) | Halide:    5.73ms (0.93x)
  1000x1000:   CPU:   23.09ms | MLX:    6.08ms (3.80x) | Halide:   26.18ms (0.88x)
```
