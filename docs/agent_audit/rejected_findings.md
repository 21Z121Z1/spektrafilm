# Rejected Findings

> Findings that don't meet the acceptance criteria. Each rejection includes the specific reason.

---

## HDR & Color

### HDR-C-008: GainMapMetadata default base_hdr_headroom=0.0 [P3]
- **Claim**: If caller creates HDR-base gain map with default `base_hdr_headroom=0.0`, XMP reports `BaseRenditionIsHDR=False`.
- **Rejection**: This is correct behavior, not a bug. `base_hdr_headroom=0.0` means SDR base (headroom=0 = SDR). The default is designed for the common SDR-base workflow. The `__post_init__` validation correctly handles this. The reviewer's scenario (HDR-base with default headroom=0.0) is a caller error, not a code bug.

### HDR-C-009: _float_to_unsigned_rational biases small values [P3]
- **Claim**: `max(1, int(round(value * 10000)))` biases values < 0.00005 upward to 0.0001.
- **Rejection**: The function is only called for `base_offset` and `alternate_offset` fields, which default to `1/1023 ≈ 0.000977`. The 10x bias on 0.00001 never triggers in practice. The `max(1, ...)` prevents encoding 0/10000 which would be interpreted as 0.0 (a different value than 0.00001). This is a deliberate design choice for the actual use case.

---

## Format & Metadata

### FMT-007: exiv2 handle not wrapped in try/finally [P2]
- **Claim**: `io.py:128` — `exiv2.ImageFactory.open` result not in try/finally.
- **Rejection**: CPython's reference counting releases the handle immediately when the variable goes out of scope or is reassigned. The exiv2 Python bindings don't expose an explicit `close()` method. Wrapping in try/finally with `destination = None` provides no additional cleanup over CPython's deterministic refcounting. The target platform (Linux/CPython) handles this correctly.

### FMT-010: Extension parsing via split('.') [P3]
- **Claim**: `io.py:615` — `filename.split('.')[-1].lower()` fails for paths ending with a dot.
- **Rejection**: No real-world file paths end with a bare dot. The `Path(filename).suffix` approach is more robust but the current code works for all practical inputs. Style preference, not a bug.

### FMT-011: exiv2 handle in raw_file_processor.py [P3]
- **Claim**: `raw_file_processor.py:284-296` — Same pattern as FMT-007.
- **Rejection**: Same reasoning as FMT-007. CPython refcounting handles cleanup.

---

## UI & Runtime (all GUI-only)

### UI-001 through UI-012: GUI findings [P1-P3]
- **Claim**: Various GUI issues (window close crash, blocking I/O, error dialogs, warmup exceptions, stale references, memory leaks, animation cycles, stale results, save state, hidden layers, editor failures, signal connections).
- **Rejection**: All GUI-only. This project runs on a headless Linux server with no display. The GUI code (`spektrafilm_gui/`) is not testable or relevant in this environment. These findings should be revisited if/when GUI testing infrastructure is added.

### RUNTIME-001 through RUNTIME-003: Thread safety notes [P3]
- **Claim**: `_runtime_simulator`, `SimulationPipeline.process()`, and `soft_update` lack thread-safety for non-Metal backends.
- **Rejection**: The single-worker guard in `_start_simulation` (line 1024) ensures only one simulation runs at a time. No concurrent access is possible in the current architecture. These are hypothetical risks for a hypothetical future change.

---

## Documentation

### DOC-004: PySide6 comment in pyproject.toml [P3]
- **Claim**: Add comment explaining why PySide6 is listed alongside qtpy.
- **Rejection**: Style preference. No functional impact.

### DOC-006: Missing type annotation on apply_stocks_specifics [P3]
- **Claim**: `params_builder.py:51` — `apply_stocks_specifics=True` lacks `bool` type hint.
- **Rejection**: Style preference. The default value clearly implies `bool`. No functional impact.

### DOC-007: Missing type annotation on database parameter [P3]
- **Claim**: `params_builder.py:22` — `database=None` lacks type hint.
- **Rejection**: Style preference. No functional impact.

### DOC-008: Commented-out optimization matrices [P3]
- **Claim**: `params_builder.py:131-150` — Scratch notes cluttering the function.
- **Rejection**: Code style/cleanup preference. No functional impact. Can be removed in a cleanup pass.

### DOC-009: Commented-out stock override [P3]
- **Claim**: `params_builder.py:167-168` — Dead code from experimentation.
- **Rejection**: Code style/cleanup preference. No functional impact.

### DOC-011: Inconsistent unit-suffix naming [P3]
- **Claim**: `params_schema.py:162-175` — `crop_center` and `crop_size` lack unit suffixes.
- **Rejection**: Naming convention preference. No functional impact.

### DOC-012: DiffusionFilterParams not in architecture index [P3]
- **Claim**: `params_schema.py:11` — Missing from public API list in architecture index.
- **Rejection**: Documentation accuracy issue. No functional impact on code.

### DOC-013: DebugParams.debug_mode values not validated [P3]
- **Claim**: `params_schema.py:200` — Allowed values not enforced by validation.
- **Rejection**: Debug mode is an internal development tool. Hard validation would be overly restrictive. The allowed values are documented in the source comment.

---

## Performance

### PERF-009: Unnecessary data.copy() when radius=0 [P2]
- **Claim**: `diffusion.py:122` — `result = data.copy()` when `radius <= 0`.
- **Rejection**: Edge case. When `radius <= 0` and `diffusion_fraction <= 0`, the function is a no-op. The copy is defensive (prevents accidental mutation of input). Negligible impact.

### PERF-010: np.diff per line in LUT monotonicity check [P2]
- **Claim**: `fast_interp_lut.py:343` — 324K small array allocations for 33^3 LUT.
- **Rejection**: ~50ms one-time cost at LUT preparation time. Not per-frame. Not a bottleneck.

### PERF-022: _halo_channel_weights allocates per call [P3]
- **Claim**: `diffusion.py:374` — 96-byte allocation per call.
- **Rejection**: Negligible. 96 bytes is not worth optimizing.

### PERF-023: ScanningStage holds backend array references [P3]
- **Claim**: `scanning.py:152-171` — GPU arrays held in closure.
- **Rejection**: Arrays are 81x3 (tiny). Negligible memory impact. No action needed.

### PERF-024: _pipeline_debug doesn't free intermediates [P3]
- **Claim**: `pipeline.py:659-692` — Debug pipeline keeps intermediates alive.
- **Rejection**: Debug-only code path. Extra memory during debug runs is expected and acceptable.

### PERF-025: _overrides_from_params builds dict unnecessarily [P3]
- **Claim**: `diffusion.py:438-451` — Dict allocated even when all defaults.
- **Rejection**: ~100ns per call. Negligible.

### PERF-026: tiled_processing allocates has_coverage array [P3]
- **Claim**: `backend.py:173` — 24MB boolean array.
- **Rejection**: Used for correctness checking. Removing it would remove a safety check.

---

## Test Quality

### TEST-020: Concurrent Simulator access untested [P2]
- **Claim**: Multiple threads calling `Simulator.process()` simultaneously.
- **Rejection**: GUI/Metal-specific concern. On headless Linux with CPU backend, the single-worker guard prevents concurrent access. Not testable in this environment.

### TEST-021: GPU backend tests silently pass when unavailable [P3]
- **Claim**: `except BackendUnavailableError: return` silently passes.
- **Rejection**: This is the correct behavior for headless Linux. The tests verify that GPU backends are correctly unavailable. Using `pytest.skip()` would be more visible but doesn't change behavior.

### TEST-022 through TEST-030: Minor test quality issues [P3]
- Various claims about limited regression baselines, loose tolerances, minimal fixtures, zero-coverage modules, single-test files, monkeypatched tests, shallow assertions, redundant coverage.
- **Rejection**: These are quality-of-life improvements for the test suite, not bugs. They should be addressed in a dedicated test improvement pass, not as part of a bug-fix triage.
