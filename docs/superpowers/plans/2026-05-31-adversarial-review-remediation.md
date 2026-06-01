# Adversarial Review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate the real, currently reproducible defects from `docs/dev/2026-05-30-adversarial-code-review.md` and `docs/dev/2026-05-30-adversarial-code-review-v5.md` without regressing SDR behavior or overwriting existing dirty-worktree changes.

**Execution Status:** Completed on 2026-05-31. See `docs/dev/2026-05-31-adversarial-review-remediation-report.md` for the implemented fixes, final disposition, and verification evidence.

**Architecture:** Treat the current worktree as authoritative. Keep the fixes narrow: add public-input validation at package-resource boundaries, turn silent NaN/Inf propagation into explicit sanitation or errors, tighten weak tests, and document any architectural item that is real but too broad for a safe one-pass code rewrite. Existing GPU/backend work remains in place and is validated by CPU-reference comparisons rather than replaced.

**Tech Stack:** Python 3.13, NumPy/SciPy/colour-science, pytest, optional MLX/CuPy/Halide backends.

---

## External References Used

- Python `importlib.resources` documents resource path names as package-relative path components. This supports validating profile names before joining them to package resources.
- SciPy `Akima1DInterpolator` documents `extrapolate=None` as returning NaNs for out-of-bounds query points. This supports explicit `np.nan_to_num(..., nan=0.0)` after filter interpolation.
- Git `gitcli` documents `--end-of-options` for stopping option parsing. This supports adding an end-of-options separator before untrusted revision strings.
- NumPy documents `nan_to_num` as replacing NaN and infinities, and `numpy.random.seed` as a legacy singleton-state API. This supports backend parity for `nan_to_num` and avoiding global RNG mutation when feasible.

## Finding Disposition

### Accepted for Code Change

- H1 original review: `profiles/io.py` still constructs resource names from unvalidated `stock`; fix both `load_profile` and `save_profile`.
- H2 original review: `utils/io.py` still leaves Akima out-of-range NaNs in dichroic/filter data; replace out-of-range NaNs with zero transmittance.
- M4 original review: `ProfileData` constructor still lacks shape and finite-value validation for public construction; add construction-time checks aligned with `_validate_profile`.
- M5 original review: `model/emulsion.py` needs explicit all-NaN density curve column rejection.
- M3 original review: `fast_gaussian_filter` should return an empty copy before IIR/FIR kernels index into empty arrays.
- M1 original review: `scripts/compare_simulation_revisions.py` needs `--end-of-options` before revision input.
- M9/M10/M11 original review: tighten gain-map JPEG roundtrip, unknown diffusion family, and nonexistent file exception tests.
- v4 findings M1, M2, M4-M12 and L1-L3/L6-L11: retain and verify already-present fixes; patch gaps found by targeted tests.
- v5 M1/M3/M5 and L5/L7/L8/L18: retain current fixes where correct, and patch any remaining weak assertions or duplicate/wasteful code.

### Rejected or Documentation-Only

- Original C1/H3 GPU abstraction removal/refactor: current worktree has active backend integration across pipeline stages and CPU-reference GPU tests. Removing the backend or doing a full protocol rewrite would conflict with the current architecture and exceed a safe remediation pass.
- Original M6 stage constructor grouping: real architecture concern, but broad refactor across all runtime stages is not required to close concrete defects and would create high regression risk.
- Original M7 central constant registry and M8 logging standardization everywhere: valid maintainability issues, but only directly affected warning paths are in scope for this pass.
- v4 M3 "No unsafe deserialization found": this is a negative finding, not a code defect.
- v5 low-priority import-time I/O/dead-code coverage items: record as follow-up unless directly touched by accepted fixes.

## Task 1: Profile Resource Boundary Hardening

**Files:**
- Modify: `src/spektrafilm/profiles/io.py`
- Test: `tests/test_profiles.py`

- [ ] **Step 1: Add failing tests**

```python
def test_load_profile_rejects_path_traversal_stock_name():
    with pytest.raises(ValueError, match="Invalid profile stock"):
        load_profile("../kodak_portra_400")

def test_save_profile_rejects_path_traversal_stock_name(portra_400_profile):
    profile = portra_400_profile.clone()
    profile.info.stock = "../evil"
    with pytest.raises(ValueError, match="Invalid profile stock"):
        save_profile(profile)
```

- [ ] **Step 2: Implement validation**

Add `_SAFE_PROFILE_STOCK_RE = re.compile(r"^[A-Za-z0-9_-]+$")`, `_validate_profile_stock()`, and call it before constructing filenames in `load_profile()` and `save_profile()`.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_profiles.py -q
```

Expected: profile tests pass.

## Task 2: Filter Interpolation NaN Sanitization

**Files:**
- Modify: `src/spektrafilm/utils/io.py`
- Test: `tests/test_edge_cases.py` or `tests/test_profiles.py`

- [ ] **Step 1: Add failing tests**

Use a monkeypatched Akima interpolator or temporary data fixture to show out-of-range interpolation returns NaN before sanitation and zero after sanitation for `load_filter()` and `load_dichroic_filters()`.

- [ ] **Step 2: Implement sanitation**

After Akima interpolation, call:

```python
np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
```

Keep valid in-range values unchanged.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_edge_cases.py -q
```

Expected: no NaN propagation from filter loaders.

## Task 3: Public ProfileData Validation

**Files:**
- Modify: `src/spektrafilm/profiles/io.py`
- Test: `tests/test_profiles.py`

- [ ] **Step 1: Add failing tests**

Construct `ProfileData` directly with invalid `density_curves`, `log_sensitivity`, nonmatching `wavelengths`, and non-finite arrays. Each should raise `ValueError` with the field name.

- [ ] **Step 2: Implement validation**

Add small helper checks in `ProfileData.__post_init__` after array conversion. Preserve empty defaults, but validate non-empty arrays:

- `density_curves`: 2D, 3 columns, finite.
- `log_sensitivity`: 2D, 3 columns, finite.
- `channel_density`: 2D, 3 columns, finite, wavelength length when both present.
- `base_density` and `midscale_neutral_density`: 1D, finite, wavelength length when both present.
- `log_exposure`: 1D finite and same length as `density_curves` when both present.
- `bandpass_hanatos2025`: empty or same shape as `log_sensitivity`, finite.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_profiles.py tests/test_color_reference.py tests/test_emulsion.py -q
```

Expected: profile construction remains compatible with existing tests while invalid public payloads fail early.

## Task 4: Numeric Edge-Case Guards

**Files:**
- Modify: `src/spektrafilm/model/emulsion.py`
- Modify: `src/spektrafilm/utils/fast_gaussian_filter.py`
- Test: `tests/test_emulsion.py`
- Test: `tests/test_edge_cases.py`

- [ ] **Step 1: Add failing tests**

Add a `develop()` test where one density-curve channel is all NaN and assert `ValueError` naming the channel. Add fast Gaussian tests for `(0, n)`, `(n, 0)`, and `(0, n, 3)` inputs with large sigma.

- [ ] **Step 2: Implement guards**

In `develop()`, reject all-NaN density curve columns before subtracting `np.nanmin`. In `_apply_per_channel()`, return `image.copy()` when `image.size == 0`.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_emulsion.py tests/test_edge_cases.py -q
```

Expected: no NaN-only profile data reaches the simulation; empty images do not crash the Gaussian dispatch.

## Task 5: Script and Test Quality Fixes

**Files:**
- Modify: `scripts/compare_simulation_revisions.py`
- Modify: `tests/test_gain_map.py`
- Modify: `tests/test_edge_cases.py`
- Modify: `tests/test_color_reference.py`
- Test: affected test files

- [ ] **Step 1: Add or tighten tests**

Check that the worktree command inserts `--end-of-options`; tighten CCTF expected values; assert exact unknown-family scatter from the table; assert `FileNotFoundError`/`OSError` for missing gain-map files.

- [ ] **Step 2: Implement script separator**

Use `["git", "worktree", "add", "--detach", str(worktree_path), "--end-of-options", revision]` if supported by the command path, otherwise `--` before `revision`.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_gain_map.py tests/test_edge_cases.py tests/test_color_reference.py -q
```

Expected: stricter tests pass.

## Task 6: Verify Current GPU and Runtime Fixes

**Files:**
- Inspect: `src/spektrafilm/gpu/mlx_backend.py`
- Inspect: `src/spektrafilm/gpu/halide_backend.py`
- Inspect: `src/spektrafilm/runtime/stages/scanning.py`
- Inspect: `src/spektrafilm/runtime/services/color_reference.py`
- Test: `tests/test_gpu_backend.py`
- Test: `tests/test_gpu_pipeline.py`
- Test: `tests/test_photo_params.py`
- Test: `tests/test_grain.py`

- [ ] **Step 1: Verify source state**

Confirm current code already:

- Handles MLX infinities in `nan_to_num`.
- Uses `hl.pow` instead of `hl.fast_pow`.
- Honors `output_clip_min/output_clip_max`.
- Raises clear errors for missing color-reference callbacks.
- Raises for invalid `RuntimePhotoParams` and `GrainParams.n_sub_layers`.
- Tests GPU pipeline output against CPU references.

- [ ] **Step 2: Patch only proven gaps**

Do not widen the GPU refactor unless tests show a current behavioral defect.

- [ ] **Step 3: Verify**

Run:

```bash
uv run pytest tests/test_gpu_backend.py tests/test_gpu_pipeline.py tests/test_photo_params.py tests/test_grain.py -q
```

Expected: CPU-backed tests pass; optional GPU tests skip or pass depending on installed backends.

## Task 7: Documentation and Final Gates

**Files:**
- Create or modify: `docs/dev/2026-05-31-adversarial-review-remediation-report.md`
- Existing plan: `docs/superpowers/plans/2026-05-31-adversarial-review-remediation.md`

- [ ] **Step 1: Write remediation report**

Record accepted/rejected findings, exact files changed, sources used, and verification commands.

- [ ] **Step 2: Run verification gates**

Run targeted tests first, then broader checks:

```bash
uv run pytest tests/test_profiles.py tests/test_edge_cases.py tests/test_emulsion.py tests/test_color_reference.py tests/test_gain_map.py tests/test_photo_params.py tests/test_grain.py tests/test_gpu_backend.py tests/test_gpu_pipeline.py -q
uv run pytest -q
uv run python -m compileall src tests
git diff --check
```

- [ ] **Step 3: Completion audit**

Re-read both adversarial review docs and this plan. Confirm each accepted finding has source-code evidence and tests; each rejected/deferred finding has a written rationale; no new test failures or whitespace errors remain.
