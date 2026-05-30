# Triaged Findings — Phase 3 Quality Audit

> Generated 2026-05-28 — All findings from 6 review files categorized into 3 buckets.

---

## Summary

| Bucket | Count | Description |
|--------|-------|-------------|
| **Accepted (P0/P1)** | 17 | Concrete evidence, narrow fix, correctness/safety impact |
| **Deferred (P2)** | 58 | Real issue but larger scope, performance-only, or needs design discussion |
| **Rejected** | 48 | Speculative, style-only, GUI-only, duplicate, or reviewer was wrong |
| **Total** | **123** | |

---

## Accepted Findings (P0/P1)

| ID | Original Sev | One-line reason |
|----|-------------|-----------------|
| HDR-C-001 | P0 | Gamut map feeds gamma-encoded sRGB to Oklab M1 (line 1136), corrupting all Oklch gamut mapping |
| HDR-C-002 | P1 | Gain map log2 floors SDR to 1e-8, producing ~20 stops of gain for near-black pixels (line 1270) |
| HDR-C-004 | P2 | `_apply_hdr_color_recovery` uses where=1e-6 but division uses _EPS32, creating discontinuity (line 598-603) |
| HDR-C-006 | P2 | `_graft_scene_luminance` scale = inf when look_y=0 and target_y>0, producing NaN (line 935) |
| FMT-001 | P1 | ISOBMFF inline patch inserts bytes without adjusting downstream box offsets (line 293) |
| FMT-003 | P1 | MPF gain map size is len(gm_data) but actual write includes +2 byte EOI (line 217 vs 222) |
| FMT-004 | P2 | HEIF save silently falls back to JPEG when pillow-heif unavailable (line 119) |
| FMT-005 | P2 | PIL save path uses _load_icc_profile without resolve_icc_profile_bytes fallback (line 690) |
| FMT-006 | P2 | _ICC_FILENAMES missing ("DCI-P3", False) linear entry (line 171-191) |
| FMT-008 | P2 | EXR bit_depth=16 casts to float16 without range check; values >65504 become inf (line 714) |
| PERF-002 | P1 | boost_highlights forces float64 then raises ValueError when out= is float32 (line 77,88) |
| PERF-016 | P2 | apply_grain_to_density mutates input array with += (line 95) |
| DOC-001 | P1 | README uses `create_params` but API exports `init_params` — breaks onboarding (line 66) |
| TEST-031 | P1 | test_color_management.py imports spektrafilm_gui at module level, entire file skipped on headless CI (line 14) |
| TEST-032 | P1 | Pipeline smoke tests have zero value-level assertions — could return random noise and pass |
| TEST-033 | P2 | LUT path comparison atol=0.02 is too loose for [0,1] data (line 200) |
| TEST-035 | P2 | JPEG gain map metadata test conditionally asserts — silently passes on failure (line 566-568) |

## Deferred Findings (P2)

| ID | Original Sev | One-line reason for deferral |
|----|-------------|------------------------------|
| HDR-C-003 | P1 | Gain map JPEG quality=90 too low for HDR precision — real but quality/size tradeoff, not a correctness bug |
| HDR-C-005 | P2 | Pre-clipping negative values before Oklch — only affects BT.2020; Display P3 default unaffected |
| HDR-C-007 | P3 | MPF flags use 0x02000000 instead of 0x00000000 — technically wrong per CIPA DC-007 but self-consistent |
| FMT-002 | P1 | MPF data offset computed from APP2 marker, not MP Entry — self-consistent round-trip but non-standard |
| FMT-009 | P3 | HEIF gain map metadata extraction returns None silently |
| FMT-012 | P3 | Duplicate of HDR-C-007 (MPF flags) |
| PERF-001 | P0 | Thread-unsafe np.random in Numba parallel — real risk but grain.py does save/restore state |
| PERF-003 | P1 | Per-channel ascontiguousarray copies 576MB per gaussian filter call — perf-only |
| PERF-004 | P1 | Diffusion PSF recomputed every frame — perf-only |
| PERF-005 | P1 | Per-channel FFT convolution — perf-only, ~2x slower than batched |
| PERF-006 | P1 | MLX clear_cache() after every convolution — perf-only (Metal-specific) |
| PERF-007 | P1 | Halide IIR blur falls back to sequential NumPy per channel — perf-only |
| MEM-001 | P1 | _gaussian_filter_2d_large allocates two full-image temporaries — perf-only |
| MEM-002 | P1 | _compute_gaussian_kernel_fft allocates 4 full-size arrays — perf-only |
| PERF-008-PERF-026 | P2-P3 | Various performance optimizations — all real but not correctness issues |
| MEM-003-MEM-007 | P2-P3 | Various memory optimizations — all real but not correctness issues |
| TEST-001-TEST-009 | P0-P1 | Missing test coverage for critical invariants (energy conservation, RNG state, tiling, EXR round-trip) |
| TEST-010-TEST-029 | P2-P3 | Missing edge-case tests, weak assertions, untested modules |
| TEST-034 | P2 | conftest.py fixture uses float64 instead of float32 |
| TEST-036-TEST-040 | P2 | Missing HDR/gain map edge-case tests |
| DOC-002-DOC-003 | P2 | Unused dependencies (lmfit, PyYAML) — needs owner confirmation before removal |
| DOC-005 | P2 | Dead code (LOG_EXPOSURE, STANDARD_OBSERVER_LMS constants) |
| DOC-010 | P2 | Malformed docstring in init_params |
| DOC-014 | P3 | Deprecated full_image property still present |

## Rejected Findings

| ID | Original Sev | One-line reason for rejection |
|----|-------------|-------------------------------|
| HDR-C-008 | P3 | GainMapMetadata default base_hdr_headroom=0.0 is correct for SDR-base workflow; no bug |
| HDR-C-009 | P3 | _float_to_unsigned_rational only used for values >= 0.000977; 10x bias on 0.00001 never triggers |
| FMT-007 | P2 | exiv2 handle cleanup — CPython refcounting handles this; exiv2 has no explicit close() |
| FMT-010 | P3 | Extension parsing edge case — no real-world paths end with a bare dot |
| FMT-011 | P3 | Same as FMT-007 — CPython refcounting handles exiv2 handles |
| UI-001-UI-012 | P1-P3 | All GUI-only findings — no GUI/display on headless Linux server |
| RUNTIME-001-003 | P3 | Thread safety notes for GUI — single-worker guard makes these safe; not applicable to headless |
| DOC-004 | P3 | PySide6 comment suggestion — style preference, no functional impact |
| DOC-006-DOC-009 | P3 | Type annotations, commented-out code — style/cleanup preferences |
| DOC-011-DOC-013 | P3 | Naming conventions, architecture index, debug validation — documentation preferences |
| PERF-009 | P2 | Unnecessary copy when radius=0 — edge case, negligible impact |
| PERF-010 | P2 | np.diff per line in LUT — ~50ms one-time cost at LUT preparation |
| PERF-022 | P3 | Small allocation (96 bytes) per call — negligible |
| PERF-023-PERF-026 | P3 | Minor perf items (closure references, debug intermediates, dict building, coverage check) |
| TEST-020 | P2 | Concurrent Simulator access — GUI/Metal-specific, not testable on headless Linux |
| TEST-021-TEST-030 | P3 | Minor test quality issues (silent skips, shallow assertions, redundant coverage) |
