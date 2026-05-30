# Next Goals

## Not Yet Implemented (from HDR/Color Deep Review)

These are remaining findings from the code review that were not addressed in this audit pass:

### HDR-C-002: `gamut_map_oklch` binary search is a no-op

**Severity**: High

The binary search loop in `gamut_map_oklch` initializes `C_max` to `C` (the current chroma), not to `0`. This means `C_mid = (C_max + C) * 0.5` is always >= `C`, so the search never compresses chroma — the loop body is effectively a no-op for out-of-gamut pixels.

**Fix**: Change `C_max = np.where(needs_work, C, 0.0)` to `C_max = np.where(needs_work, 0.0, 0.0)` so the search starts from zero and bisects upward.

### HDR-C-003: `hdr_highlight_path_to_white` has no upper bound

**Severity**: High

The `path_to_white` strength parameter can exceed `1.0`, which pushes highlight colors past white and produces negative values in at least one channel. There is no clamp or validation on the strength parameter.

**Fix**: Clamp the strength parameter to `[0.0, 1.0]` or add validation in `HDRPhotoMapping.__post_init__`.

### MOD-001: `compute_lut_spectra` stores spectral LUT in `np.half` (float16)

**Severity**: Medium

The spectral LUT computation casts results to `float16`, violating the project's float32 precision constraint. This loses ~3 decimal digits of precision in spectral density values, which compounds through the simulation pipeline.

**Fix**: Remove the `astype(np.float16)` cast and keep the LUT in `float32`.

---

## Deferred P2 Items

These were identified during the review but deferred due to lower impact or larger scope:

### Performance Optimizations

- **PERF-001**: Numba JIT opportunities in hot loops (grain simulation, spectral integration)
- **PERF-003**: Redundant array copies in spectral pipeline intermediates
- **PERF-005**: Could batch multiple small images through GPU pipeline

### Gain Map Quality

- **HDR-C-003 (gain map variant)**: JPEG quality tradeoff for gain map encoding — currently uses default quality which may introduce banding in smooth gradients

### Format Interoperability

- **FMT-002**: MPF interoperability — second image index entries may not be recognized by all readers
- **FMT-012**: HEIF gain map metadata structure could be more complete for broader player support

### H3 Memory Optimization

- **H3**: Pipeline memory optimization — several intermediate arrays are allocated that could be reused. This is a larger refactor touching pipeline architecture.

---

## Recommended Next Steps

1. **Fix HDR-C-002** (binary search no-op) — highest priority remaining bug. This means out-of-gamut Oklch colors are never actually compressed, which can produce invalid output.
2. **Fix HDR-C-003** (path_to_white unbound) — unbounded strength can produce negative pixels, visible as color artifacts in HDR highlights.
3. **Fix MOD-001** (float16 LUT) — precision loss in spectral LUT violates the project's core quality contract (zero precision loss).
4. **Address deferred performance items** based on profiling data — focus on the spectral pipeline hot path first.
5. **Add GUI testing infrastructure** — several UI findings (M3, UI-001 through UI-005) cannot be validated on headless Linux and need a virtual display or screenshot-based test harness.
