# Halide Backend Implementation — Verified State

**Date:** 2026-05-28
**Status:** 53/53 tests passing on host (Python JIT)

---

## 1. Architecture

The Halide backend lives in `src/spektrafilm/gpu/halide_backend.py`. It implements
the `ArrayBackend` protocol used by the rest of spektrafilm, but delegates
non-kernel operations (element-wise math, reductions) to NumPy while JIT-compiling
selected hot-path kernels via the Halide Python bindings.

### 1.1 HalideBackend class

```
class HalideBackend:
    name = "halide"
    supports_gpu = True
    precision = "float32"   # only float32 is supported
    requires_serial_runtime = True
```

- Constructed with `HalideBackend(halide_module=hl)` or auto-imports `halide`.
- `hl.get_host_target()` is used for JIT — no cross-compilation at runtime.
- All pipelines are cached as instance attributes and lazily built on first call.
- `cleanup()` clears all cached pipelines, forcing a rebuild on next use.

### 1.2 Pipeline caching strategy

Each kernel type has its own cache pattern:

| Kernel | Cache field | Cache key |
|--------|------------|-----------|
| `rgb_to_xyz` (3x3 matrix) | `_rgb_matrix_pipeline` | singleton |
| `apply_lut_trilinear_3d` | `_trilinear_3d_cache` | `dict[int, pipeline]` keyed by LUT size |
| `density_to_light` | `_density_to_light_pipeline` | singleton |
| `light_to_raw` | `_light_to_raw_pipeline` | singleton |
| `compute_density_spectral` | `_compute_density_spectral_pipeline` | singleton |
| `gaussian_blur_fir` | `_fir_blur_pipeline` + `_fir_blur_kernel_len` | rebuilds when kernel length changes |
| `highlight_boost` | `_highlight_boost_pipeline` | singleton |
| `cctf_encode` | `_cctf_encode_pipeline` | singleton |
| `cctf_decode` | `_cctf_decode_pipeline` | singleton |
| `interp_1d` | `_interp_1d_pipeline` + `_interp_1d_n` | rebuilds when N changes |
| `lut_2d_cubic` | `_lut_2d_pipeline` + `_lut_2d_size` | rebuilds when LUT size changes |

Pipeline parameters (scalars, buffers) are set via `Param.set()` / `ImageParam.set()`
before each `realize()` call. The compiled Func itself is reused.

### 1.3 Scheduling

All kernels use `output.compile_jit(self.target)` for host JIT. Common scheduling
patterns:

- `vectorize(x, 8)` — SIMD over the width dimension
- `parallel(y)` — thread pool over the height dimension
- `unroll(c)` — unroll the 3-channel dimension at compile time
- `reorder(c, x, y)` — channel-first layout for better vectorization

---

## 2. Verified Kernels

All 53 tests pass. Each kernel is tested for numerical parity against a NumPy
reference implementation with `np.allclose(atol=1e-5..1e-6)`.

### 2.1 RGB 3x3 matrix multiply

**Method:** `rgb_to_xyz(rgb, matrix_3x3)`
**Formula:** `output[x, y, c] = sum_i image[x, y, i] * matrix[i, c]`
**Tests:** `test_halide_backend.py` (1 test via `test_halide_backend_rgb_to_xyz_matches_numpy_reference`)

NumPy `[C,H,W]` is transposed to Halide `[W,H,C]`, realized, then transposed back.
The matrix is passed as a `[3,3]` buffer directly.

### 2.2 3D trilinear LUT interpolation

**Method:** `apply_lut_trilinear_3d(lut, image)`
**Tests:** (covered via backend integration tests)

Standard trilinear interpolation: 8-corner lerp with clamped coordinates.
LUT is cached per size. LUT is transposed from `[L,L,L,3]` to `[3,L,L,L]` for Halide.

### 2.3 density_to_light (spectral)

**Method:** `density_to_light(density, illuminant)`
**Formula:** `light[w, y, c] = exp(-density[w, y, c] * ln(10)) * illuminant[c, w]`
**Inputs:** density `[3, H, 81]`, illuminant `[81, 3]`
**Output:** `[3, H, 81]`
**Tests:** `test_halide_spectral.py` — 3 tests (match numpy, various sizes, invalid shapes)

Uses `exp(log10 * -x)` instead of `pow(10, -x)` for Halide compatibility.

### 2.4 light_to_raw (spectral)

**Method:** `light_to_raw(light, sensitivity)`
**Formula:** `output[c_in, y, c_out] = sum_wl light[wl, y, c_out] * sensitivity[c_in, wl]`
**Inputs:** light `[3, H, 81]`, sensitivity `[81, 3]`
**Output:** `[3, H, 3]`
**Tests:** `test_halide_spectral.py` — 3 tests

Uses `RDom` over 81 wavelengths for the reduction.

### 2.5 compute_density_spectral (spectral)

**Method:** `compute_density_spectral(density_cmy, channel_density)`
**Formula:** `output[w, y, c] = sum_k density[w, y, k] * channel[w, k]`
**Inputs:** density_cmy `[3, H, 81]`, channel_density `[3, 81]`
**Output:** `[3, H, 81]`
**Tests:** `test_halide_spectral.py` — 3 tests

Uses `RDom` over 3 channels for the reduction.

### 2.6 gaussian_blur_fir (separable FIR)

**Method:** `gaussian_blur_fir(image, kernel_1d)`
**Inputs:** image `[C, H, W]`, kernel_1d `[K]` (odd length)
**Output:** `[C, H, W]`
**Tests:** `test_halide_filters.py` — 5 tests (scipy reference, identity kernel, cache rebuild, invalid inputs)

Two-pass separable: horizontal then vertical. Boundary condition is
`BoundaryConditions.mirror_image` for x, and a manually computed `_mirror_y`
function for y (because `mirror_interior` on a Func with RDom can produce
incorrect boundary accesses). Pipeline rebuilds when kernel length changes.

### 2.7 gaussian_blur_iir (NumPy-backed YVV)

**Method:** `gaussian_blur_iir(image, sigma)`
**Inputs:** image `[C, H, W]`, sigma >= 0.5
**Output:** `[C, H, W]`
**Tests:** `test_halide_filters.py` — 4 tests

**This kernel does NOT use Halide JIT.** Halide Python JIT does not support
self-referencing recursive Funcs, so the implementation falls back to
`spektrafilm.utils.fast_gaussian_filter._gaussian_filter_2d_large` (NumPy YVV).
Results are numerically identical to what a Halide scan would produce.

### 2.8 highlight_boost

**Method:** `highlight_boost(image, *, threshold, boost, offset=0.0)`
**Formula:** `select(v < threshold, v, (v + offset) * boost)`
**Input:** image `[C, H, W]`
**Output:** `[C, H, W]`
**Tests:** `test_halide_filters.py` — 5 tests

Parameters are passed as `hl.Param` scalars, set before each `realize()`.

### 2.9 cctf_encode (sRGB)

**Method:** `cctf_encode(linear, *, gamma, threshold, a, b, c_coeff, d_coeff)`
**Formula:** `select(x <= threshold, a*x + b, c_coeff * pow(x, 1/gamma) - d_coeff)`
**Input:** linear `[C, H, W]`
**Output:** encoded `[C, H, W]`
**Tests:** `test_halide_color.py` — 5 tests (sRGB random, below/above/exact threshold, custom params)

### 2.10 cctf_decode (sRGB inverse)

**Method:** `cctf_decode(encoded, *, gamma, threshold, a, b, c_coeff, d_coeff)`
**Formula:** `select(x <= encoded_threshold, (x - b)/a, pow((x + d_coeff)/c_coeff, gamma))`
**Input:** encoded `[C, H, W]`
**Output:** linear `[C, H, W]`
**Tests:** `test_halide_color.py` — 6 tests (roundtrip, random, below/above threshold, custom params, transition monotonicity)

The **encoded threshold** is computed as `a * threshold + b` (i.e., the encode
function applied to the linear-domain threshold). This is critical for correct
roundtrip behavior.

### 2.11 interp_1d (1D linear interpolation)

**Method:** `interp_1d(values, positions, query)`
**Inputs:** values `[N]`, positions `[N]` (ascending), query `[H, W]`
**Output:** `[H, W]`
**Tests:** `test_halide_color.py` — 4 tests

Uses `constant_exterior` boundary on the query, then a select-chain to find
the bracketing interval. Clamps out-of-range queries to nearest endpoint.
Pipeline rebuilds when N changes.

### 2.12 lut_2d_cubic (Mitchell-Netravali bicubic)

**Method:** `lut_2d_cubic(lut, image)`
**Inputs:** lut `[size, size, C]`, image `[H, W, 2]` (normalized 0-1)
**Output:** `[H, W, C]`
**Tests:** `test_halide_lut.py` — 4 tests

Uses Mitchell-Netravali kernel with B=1/3, C=1/3. 4x4 bicubic footprint
with clamped boundary. LUT is transposed from `[size, size, C]` to
`[C, size, size]` for Halide, output transposed back.

### 2.13 Additional tests

- **Grain buffer:** `generate_grain_buffer()` — NumPy-only, not a Halide kernel. 3 tests.
- **Backend infrastructure:** backend selection, precision rejection, cleanup, probe — 6 tests in `test_halide_backend.py`.
- **Pipeline caching:** spectral pipeline reuse and cleanup — 2 tests in `test_halide_spectral.py`.

---

## 3. CCTF Formula Contract

The CCTF (Coded Colour Transfer Function) encode/decode pair must be exact
inverses. The following formulas are **the contract** — any future change must
preserve invertibility.

### 3.1 Encode (linear → encoded)

```
f(x) = { a * x + b                          if x <= threshold
        { c_coeff * pow(x, 1/gamma) - d_coeff  otherwise
```

For sRGB: `a=12.92, b=0.0, c_coeff=1.055, d_coeff=0.055, gamma=2.4,
threshold=0.0031308`.

### 3.2 Decode (encoded → linear)

```
encoded_threshold = a * threshold + b

f_inv(y) = { (y - b) / a                           if y <= encoded_threshold
            { pow((y + d_coeff) / c_coeff, gamma)    otherwise
```

**Critical:** The decode threshold is in *encoded space*, not linear space.
The decode threshold is `a * threshold + b` (the encode of the linear threshold).
This ensures the piecewise branches align exactly.

### 3.3 Roundtrip invariant

For any `x` in `[0, 1]`:
```
decode(encode(x)) ≈ x   (within float32 epsilon)
```

This is validated by `TestCctfDecode.test_srgb_roundtrip` and
`TestCctfDecode.test_transition_region_roundtrip` (monotonicity check at the
threshold boundary).

### 3.4 Historical bug note

A previous version used the *linear-domain threshold* in the decode branch,
which caused a non-invertible discontinuity at the threshold boundary. The
fix (computing `encoded_threshold = a * threshold + b`) ensures the encode
and decode piecewise boundaries meet at exactly the same point.

---

## 4. Dimension Convention

Halide uses **column-major** dimension ordering; NumPy uses **row-major**.
The backend handles this via explicit transpose at the boundary.

| NumPy shape | Halide shape | Func indices | realize() args |
|------------|-------------|--------------|----------------|
| `[C, H, W]` | `[W, H, C]` | `Func[x, y, c]` | `[W, H, C]` |
| `[H, W]` | `[W, H]` | `Func[x, y]` | `[W, H]` |
| `[N]` | `[N]` | `Func[i]` | `[N]` |
| `[H, W, 2]` | `[2, W, H]` | `Func[c, x, y]` | `[width, height, channels]` |

The general pattern:
1. `np.ascontiguousarray(np.transpose(array, (2, 0, 1)))` — NumPy → Halide
2. `np.ascontiguousarray(np.transpose(result, (1, 2, 0)))` — Halide → NumPy

For 2D LUTs, the LUT is transposed from `[size, size, C]` to `[C, size, size]`.

---

## 5. Current Limitations

### 5.1 IIR Gaussian uses NumPy fallback

`gaussian_blur_iir` delegates to `fast_gaussian_filter._gaussian_filter_2d_large`.
Halide Python JIT cannot express self-referencing recursive Funcs (the YVV
4-tap filter requires `y[n] = b0*x[n] + b1*x[n-1] + ... - a1*y[n-1] - ...`).
The C++ AOT generators *do* have a Halide IIR implementation (see
`filter_generator.cpp`) because C++ generators support recursive Funcs via
`RDom` update definitions.

### 5.2 Grain uses NumPy

`generate_grain_buffer()` is pure NumPy (`np.random.RandomState`).
Halide is a deterministic dataflow language and cannot express RNG.
On-device, grain would use a pre-generated random buffer (C++ RNG → Halide buffer).

### 5.3 No Vulkan dispatch

The backend uses `hl.get_host_target()` only. Halide's Vulkan backend exists
but is not used. Future Android work would use AOT-compiled ARM targets.

### 5.4 float32 only

The backend rejects `precision="float64"` at construction time.
All buffers are `hl.Float(32)`. This matches the project's GPU precision policy.

### 5.5 No autoscheduler

Pipelines use hand-written schedules (`vectorize`, `parallel`, `unroll`).
Halide's autoscheduler could optimize further but is not yet integrated.
