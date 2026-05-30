# Deferred Findings — P2

> Real issues but not urgent. Deferred due to larger scope, performance-only impact, or need for design discussion.

---

## HDR & Color

### HDR-C-003: Gain map JPEG quality=90 too low for HDR precision [P1 → Deferred]
- **Evidence**: `gain_map_io.py:47` — `gain_map_quality: int = 90`. Each uint8 step ≈ 12 millistops for 3-stop headroom. JPEG DCT adds additional error.
- **Why deferred**: Quality vs file size tradeoff. Quality=100 (lossless JPEG) or PNG would be more correct but significantly larger. Needs product decision on acceptable quality level.
- **To accept**: If the project decides HDR precision is more important than gain map file size, change default to 100 or use PNG.

### HDR-C-005: Pre-clipping negatives before Oklch conversion [P2 → Deferred]
- **Evidence**: `hdr_photo.py:1133` — `srgb = np.clip(np.einsum(...), 0.0, None)` clips negative values from color space conversion before Oklch.
- **Why deferred**: Only affects BT.2020 → sRGB with highly saturated colors. Display P3 (the default) rarely produces negatives. Removing the clip could introduce other issues if negative values aren't handled downstream.
- **To accept**: If BT.2020 HDR workflow becomes a primary use case, remove pre-clipping and ensure gamut mapping handles negatives correctly.

### HDR-C-007 / FMT-012: MPF entry flags use wrong value [P3 → Deferred]
- **Evidence**: `gain_map_io.py:252` — `0x02000000` (Large Thumbnail) instead of `0x00000000` (Individual Image).
- **Why deferred**: Self-consistent round-trip works. Only affects interoperability with strict CIPA DC-007 parsers.
- **To accept**: If external MPF parser compatibility becomes a requirement.

---

## Format & Metadata

### FMT-002: MPF data offset computed from APP2 marker, not MP Entry [P1 → Deferred]
- **Evidence**: `gain_map_io.py:216,444` — Writer stores offset from APP2 marker position; reader uses same reference. Self-consistent but 8 bytes off from CIPA DC-007 spec.
- **Why deferred**: Self-consistent round-trip — our reader and writer agree. Only matters for interoperability with external MPF readers.
- **To accept**: If external MPF reader compatibility is needed, adjust offset by -8 in writer and +8 in reader.

### FMT-009: HEIF gain map metadata extraction not implemented [P3 → Deferred]
- **Evidence**: `gain_map_io.py:500-505` — Returns `metadata: None` with comment "Would need ISOBMFF parsing."
- **Why deferred**: Requires implementing ISOBMFF metadata parsing. JPEG path works correctly.
- **To accept**: When HEIF gain map workflow becomes primary.

---

## Performance (all deferred — perf-only, no correctness impact)

### PERF-001: Thread-unsafe global RNG in Numba parallel [P0 → Deferred]
- **Evidence**: `fast_stats.py:49` — `np.random.rand()` inside `@njit(parallel=True)`. `grain.py:43` — `np.random.seed()` global mutation.
- **Why deferred**: `grain.py` does save/restore global state (lines 40-47). Numba's `np.random` in njit may use per-thread state. Single-threaded pipeline means no concurrent access. Risk is theoretical unless multithreaded grain is added.
- **To accept**: If grain is ever called from multiple threads concurrently, or if Numba's parallel RNG is confirmed unsafe.

### PERF-003: Per-channel ascontiguousarray copies [P1 → Deferred]
- **Evidence**: `fast_gaussian_filter.py:258` — `np.ascontiguousarray(image[:, :, ch])` copies each channel. 576MB per gaussian filter call for 6000x4000 float64.
- **Why deferred**: Performance-only. Correctness is not affected. Fix requires restructuring channel extraction.
- **To accept**: When profiling shows gaussian filter is a bottleneck.

### PERF-004: Diffusion PSF recomputed every frame [P1 → Deferred]
- **Evidence**: `diffusion.py:585-592` — PSF computation depends only on constant params. ~10ms + 24MB per frame.
- **Why deferred**: Performance-only. Fix requires adding caching infrastructure.
- **To accept**: When batch processing performance is critical.

### PERF-005: Per-channel FFT convolution [P1 → Deferred]
- **Evidence**: `diffusion.py:602-607` — 3 separate FFT convolve calls instead of batched.
- **Why deferred**: Performance-only. ~2x slower than necessary.
- **To accept**: When diffusion filter is a bottleneck.

### PERF-006: MLX clear_cache() after every convolution [P1 → Deferred]
- **Evidence**: `gpu/kernels/filters.py:634` — Forces Metal to discard cached shaders.
- **Why deferred**: Metal-specific. Performance-only.
- **To accept**: When MLX diffusion throughput is critical.

### PERF-007: Halide IIR blur sequential per channel [P1 → Deferred]
- **Evidence**: `gpu/halide_backend.py:474-478` — Falls back to Numba per channel, no prange.
- **Why deferred**: Performance-only. ~3x slower than parallel.
- **To accept**: When Halide IIR blur is a bottleneck.

### MEM-001: _gaussian_filter_2d_large two full-image temporaries [P1 → Deferred]
- **Evidence**: `fast_gaussian_filter.py:216-217` — Allocates `tmp` and `output`. Vertical pass could write in-place.
- **Why deferred**: Performance/memory-only. 384MB for 6000x4000 float64.
- **To accept**: When memory is a constraint for large images.

### MEM-002: _compute_gaussian_kernel_fft 4 full-size arrays [P1 → Deferred]
- **Evidence**: `fft_gaussian_filter.py:87-98` — Creates fx, fy, FX, FY, freq2, kernel_fft. ~1GB for padded 6700x4700.
- **Why deferred**: Performance/memory-only. Could be cached.
- **To accept**: When FFT gaussian filter memory is a constraint.

### PERF-008 through PERF-026, MEM-003 through MEM-007 [P2-P3 → Deferred]
- Various performance and memory optimizations. All real but not correctness issues. See individual review files for details.

---

## Test Coverage Gaps

### TEST-001 through TEST-009: Missing critical invariant tests [P0-P1 → Deferred]
- Diffusion energy conservation, pipeline cleanup after exceptions, GPU tiling overlap, grain RNG state, digest_params idempotency, PSF normalization, HDR EXR round-trip, soft_update invalidation, large image GPU tiling.
- **Why deferred**: Adding tests is important but doesn't fix existing bugs. These should be added alongside the accepted fixes.
- **To accept**: Prioritize TEST-001 (energy conservation) and TEST-004 (RNG state) alongside HDR-C-001 fix.

### TEST-010 through TEST-029: Missing edge-case tests [P2-P3 → Deferred]
- Various coverage gaps for crop, RAW, grain, parametric, profile I/O, Halide, diffusion, I/O clipping, HDR validation, micro-structure, concurrent access.
- **Why deferred**: Quality improvements. No existing bugs identified.
- **To accept**: As test infrastructure improvements are prioritized.

### TEST-034: conftest.py fixture uses float64 [P2 → Deferred]
- **Evidence**: `conftest.py:32` — `dtype=np.float64` while pipeline defaults to float32.
- **Why deferred**: Tests may exercise different code paths than production. Not a bug in the code.
- **To accept**: Change fixture to float32 or add f32 variant.

### TEST-036 through TEST-040: Missing HDR/gain map edge-case tests [P2 → Deferred]
- Non-finite inputs, empty/single-pixel images, all-zero SDR, gain map statistics, HEIC on Linux.
- **Why deferred**: Edge-case coverage improvements.
- **To accept**: As HDR workflow matures.

---

## Documentation

### DOC-002, DOC-003: Unused dependencies (lmfit, PyYAML) [P2 → Deferred]
- **Evidence**: Zero imports of `lmfit` or `yaml` in source tree.
- **Why deferred**: Needs project owner confirmation before removal. May be used by external tools.
- **To accept**: After confirming no external consumers depend on these.

### DOC-005: Dead code constants [P2 → Deferred]
- **Evidence**: `config.py:5,13-15` — `LOG_EXPOSURE` and `STANDARD_OBSERVER_LMS` never imported.
- **Why deferred**: May be planned for future use. Removal is safe but needs owner confirmation.
- **To accept**: After confirming these are truly unused.

### DOC-010: Malformed docstring in init_params [P2 → Deferred]
- **Evidence**: `params_builder.py:100-106` — Two concatenated docstrings.
- **Why deferred**: Documentation quality issue, not a bug.
- **To accept**: Anytime — trivial fix.

### DOC-014: Deprecated full_image property [P3 → Deferred]
- **Evidence**: `params_schema.py:176-192` — Always returns True, setter is no-op, emits DeprecationWarning.
- **Why deferred**: Still referenced by scripts and tests. Requires updating 3 files before removal.
- **To accept**: After updating `scripts/compare_simulation_revisions.py`, `tools/validate_profile_aware_hdr_raw_samples.py`, and `tests/test_runtime_api.py`.
