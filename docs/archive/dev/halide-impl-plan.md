> **STATUS: COMPLETED**. All 8 planned kernels plus 4 additional implemented. See halide-backend-implementation.md.

# Halide Backend Implementation Plan

## Goal
Implement all 8 Halide kernels in Python JIT (`halide_backend.py`) + write C++ Generator source files + tests.

## Rules
- Every kernel MUST match NumPy output within `atol=1e-6`
- float32 only
- Each kernel is a cached JIT pipeline (build once, reuse with ImageParam.set)
- Use `hl.ImageParam` for inputs, `hl.Func` for output
- Schedule: `output.vectorize(x, 8).parallel(y)` as baseline

## Kernel Inventory

### Group A: Spectral (spectral_generator)
1. **density_to_light** — `10^(-density) * illuminant`
   - Input: density [3, H, W], illuminant [81, 3]
   - Output: light [3, H, 81]
   - Halide: element-wise exp + multiply

2. **light_to_raw** — `einsum('ijk,kl->ijl', light, sensitivity)`
   - Input: light [3, H, 81], sensitivity [81, 3]
   - Output: raw [3, H, 3]
   - Halide: reduction over K=81

3. **compute_density_spectral** — `einsum('ijk,lk->ijl', density_cmy, channel_density)`
   - Input: density_cmy [3, H, W], channel_density [3, 81]
   - Output: result [3, H, 81]
   - Halide: reduction over last dim of channel_density

### Group B: Filters (filter_generator)
4. **gaussian_blur_fir** — separable 2D convolution
   - Input: image [C, H, W], kernel_1d [radius*2+1]
   - Output: blurred [C, H, W]
   - Halide: two-pass separable (horizontal + vertical)
   - Use `BoundaryConditions::mirror_interior`

5. **gaussian_blur_iir** — Young-van Vliet 4-tap IIR
   - Input: image [C, H, W], sigma (float)
   - Output: blurred [C, H, W]
   - Halide: forward scan + backward scan per row

### Group C: Color/LUT (color_generator + lut_generator)
6. **cctf_encode** — sRGB/ProPhoto/BT.2020 transfer function
   - Input: linear [C, H, W], gamma (float), coefficients (float3)
   - Output: encoded [C, H, W]
   - Halide: `select(x <= threshold, a*x + b, pow(c*x + d, gamma))`

7. **cctf_decode** — inverse transfer function
   - Same structure as encode but inverted

8. **highlight_boost** — piecewise exponential curve
   - Input: image [C, H, W], params (threshold, scale, pivot)
   - Output: boosted [C, H, W]
   - Halide: `select(x < threshold, x * scale, ...)`

9. **interp_1d** — linear interpolation
   - Input: values [N], positions [M], query [H, W]
   - Output: interpolated [H, W]
   - Halide: clamp + linear blend

10. **lut_2d_cubic** — Mitchell-Netravali 2D LUT
    - Input: lut [size, size, C], image [H, W, 2]
    - Output: result [H, W, C]
    - Halide: 4-point cubic interpolation

### Group D: RNG (no Halide kernel — pre-generated buffer)
11. **grain_glare_rng** — C++ std::mt19937 → numpy buffer
    - This is NOT a Halide kernel. Generate random buffer in Python/C++, pass as ImageParam to Halide blur pipeline.

## Files to Create/Modify

### Modify
- `src/spektrafilm/gpu/halide_backend.py` — add all kernel methods

### Create
- `src/spektrafilm/generators/spectral_generator.cpp`
- `src/spektrafilm/generators/filter_generator.cpp`
- `src/spektrafilm/generators/color_generator.cpp`
- `src/spektrafilm/generators/lut_generator.cpp`
- `tests/test_halide_spectral.py`
- `tests/test_halide_filters.py`
- `tests/test_halide_color.py`
- `tests/test_halide_lut.py`

## Execution Order
1. Group A + B in parallel (no dependencies)
2. Group C + D in parallel (no dependencies)
3. Tests after all kernels implemented
4. C++ generators after Python JIT verified
