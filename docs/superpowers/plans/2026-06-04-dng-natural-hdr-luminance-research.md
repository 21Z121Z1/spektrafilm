# DNG Natural HDR Luminance Research Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development before changing implementation code. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Define and validate a DNG/RAW Natural HDR luminance system that separates measured/estimated diffuse white from sensor white, display white, paper white, and authored HDR controls.

**Architecture:** Keep production HDR rendering unchanged in this pass. Add a research-only estimator in `tools/` with explicit dataclasses, synthetic fixtures, optional real-DNG scanning, JSON/CSV output, and tests that prove the estimator downgrades uncertain or authored cases instead of calling them Natural HDR.

**Tech Stack:** Python 3.13, NumPy, optional rawpy for real DNG scanning, pytest with plugin autoload disabled for fast targeted runs, current Spektrafilm HDR docs and source.

---

## Scope Decision

This is not a production rewrite of `HDRPhotoMapping`, GUI save dispatch, EXR export, or gain-map encoding. The supplied prompt and `/Users/retriedstormtrooper/Downloads/deep-research-report.md` ask for a DNG Natural HDR brightness definition architecture plus minimal experiments. The correct implementation scope is:

- Create a durable plan before code edits.
- Add `tools/research_dng_diffuse_white_estimation.py`.
- Add focused tests for the estimator and classification policy.
- Write `docs/dev/2026-06-04-dng-natural-hdr-luminance-research.md`.
- Run targeted HDR, RAW, GUI-output, compile, and diff checks where the environment allows.

## Current Evidence To Preserve

- `docs/dev/2026-06-03-hdr-naturalness-audit.md` already classifies current `profile_aware`, `film_scan_aware`, and `modern_recovery_peak_budget` as authored/profile/budgeted HDR rather than pure natural HDR.
- `docs/hdr_profile_aware_raw_validation.md` validates four real DNG samples, but its diffuse-white estimate is still `postprocess_percentile`; it is useful evidence, not a complete Natural HDR eligibility system.
- `src/spektrafilm/runtime/pipeline.py::HDRSceneEnergyMetadata` currently stores `scene_luminance` after preprocessing/auto-exposure; it does not store RAW/DNG diffuse-white provenance.
- `src/spektrafilm/utils/raw_file_processor.py::load_and_process_raw_file()` demosaics RAW into linear ACES RGB, but does not return sensor black/white/clipping diagnostics.
- `src/spektrafilm/utils/hdr_photo.py::HDRPhotoMapping` exposes authored controls such as `profile_hdr_peak_ev`, `profile_hdr_target_peak_ev`, `profile_hdr_recovery_ratio`, `profile_hdr_min_gain`, and path-to-white controls. These must be disallowed as Natural HDR evidence.

## Files

- Create: `tools/research_dng_diffuse_white_estimation.py`
  - Holds research dataclasses, synthetic fixture generation, scene luminance calculation, RAW diagnostics helpers, diffuse-white estimation, eligibility classification, JSON/CSV serialization, and CLI.
- Create: `tests/test_dng_diffuse_white_estimation.py`
  - Imports the research tool as a module and tests synthetic scenes without requiring rawpy or real files.
- Create: `docs/dev/2026-06-04-dng-natural-hdr-luminance-research.md`
  - Final research architecture, code audit table, experiment results, commands, answers to the prompt questions, and remaining uncertainties.
- Modify if needed: `docs/dev/README.md` and `docs/dev/README_zh.md`
  - Add links to the new research document only after the document exists.

## Task 1: Write The Failing Tests

- [x] **Step 1: Add tests for measured white-card eligibility**

Create `tests/test_dng_diffuse_white_estimation.py` with a test that builds a scene-linear RGB image containing a known diffuse white patch and a brighter specular patch. Call `estimate_diffuse_white_from_scene()` with a measured mask. Expected behavior:

```python
assert estimate.method == "measured_gray_or_white_card"
assert estimate.confidence == "high"
assert estimate.can_claim_natural_hdr is True
assert estimate.recommended_mode == "natural_scene_hdr"
assert estimate.natural_hdr_class == "natural_scene_hdr_verified"
```

- [x] **Step 2: Add tests for low-key downgrade**

Use a mostly dark scene with a tiny bright highlight. Expected behavior:

```python
assert estimate.confidence == "low"
assert estimate.can_claim_natural_hdr is False
assert estimate.recommended_mode in {"scene_derived_heuristic_hdr", "authored_hdr"}
assert "low-key" in " ".join(estimate.warnings)
assert estimate.highlight_headroom_estimate <= 8.0
```

- [x] **Step 3: Add tests for snow/white-wall diffuse scenes**

Use a large high-luminance neutral region plus modest highlights. Expected behavior:

```python
assert estimate.confidence in {"medium", "high"}
assert estimate.recommended_mode in {"natural_scene_hdr", "scene_derived_heuristic_hdr"}
assert estimate.value >= 0.8
assert "large diffuse" in " ".join(estimate.assumptions + estimate.warnings)
```

- [x] **Step 4: Add tests for neon/emissive small highlights**

Use a dark scene with tiny saturated red/blue lights. Expected behavior:

```python
assert estimate.confidence == "low"
assert estimate.can_claim_natural_hdr is False
assert estimate.recommended_mode == "scene_derived_heuristic_hdr"
assert "emissive" in " ".join(estimate.warnings)
```

- [x] **Step 5: Add tests for clipped RAW downgrade**

Build `RawCaptureDiagnostics(clipping_fraction=0.04, ...)` and pass it with a bright scene. Expected behavior:

```python
assert estimate.confidence in {"low", "invalid"}
assert estimate.can_claim_natural_hdr is False
assert estimate.recommended_mode in {"scene_derived_heuristic_hdr", "sdr_only"}
assert "clipped" in " ".join(estimate.warnings)
```

- [x] **Step 6: Add tests for authored-control exclusion**

Call `classify_dng_natural_hdr_eligibility()` with a good measured estimate but active controls such as `profile_hdr_target_peak_ev`, `modern_recovery_peak_budget`, and `path_to_white`. Expected behavior:

```python
assert provenance.natural_hdr_class == "authored_hdr_from_raw"
assert provenance.can_claim_natural_hdr is False
assert "profile_hdr_target_peak_ev" in provenance.disallowed_creative_controls
```

- [x] **Step 7: Add tests for WhiteLevel separation**

Create raw diagnostics with `white_level=4095` and a scene whose diffuse white estimate is around `0.6`. Expected behavior:

```python
assert estimate.value != raw_diagnostics.white_level
assert estimate.raw_metadata_summary["white_level"] == 4095
assert "WhiteLevel" in " ".join(estimate.assumptions + estimate.warnings)
```

- [x] **Step 8: Run red tests**

Run:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_dng_diffuse_white_estimation.py -q
```

Expected: fail because `tools/research_dng_diffuse_white_estimation.py` does not exist yet.

## Task 2: Implement The Research Estimator

- [x] **Step 1: Add dataclasses**

Implement these dataclasses in `tools/research_dng_diffuse_white_estimation.py`:

```python
@dataclass(slots=True)
class RawCaptureDiagnostics:
    black_level: float | None
    white_level: float | None
    channel_white_levels: tuple[float, ...]
    clipping_fraction: float
    channel_clipping_fraction: tuple[float, ...]
    raw_p50: float
    raw_p95: float
    raw_p99: float
    raw_p999: float
    warnings: tuple[str, ...] = ()

@dataclass(slots=True)
class DiffuseWhiteEstimate:
    value: float
    method: str
    confidence: str
    provenance: str
    assumptions: tuple[str, ...]
    warnings: tuple[str, ...]
    clipping_fraction: float
    highlight_headroom_estimate: float
    is_user_override: bool
    is_measured: bool
    is_heuristic: bool
    can_claim_natural_hdr: bool
    recommended_mode: str
    natural_hdr_class: str
    raw_metadata_summary: dict[str, object]
```

Also add `SceneLuminanceState` and `NaturalHDRProvenance` with the fields requested in the prompt.

- [x] **Step 2: Implement `compute_scene_luminance_y()`**

The function must accept scene-linear RGB, record/return coefficients, and refuse gamma/display-derived assumptions in documentation. Tests should use Rec.709 coefficients for simple synthetic scenes.

- [x] **Step 3: Implement measured/user-assisted paths**

Measured masks and user-confirmed calibration regions may return high confidence. User overrides without a measured flag must remain heuristic and cannot claim verified Natural HDR.

- [x] **Step 4: Implement robust statistics with safeguards**

Use scene-linear luminance percentiles and content flags, not display RGB. The estimator must detect low-key scenes, large diffuse high-key scenes, small saturated/emissive highlights, and clipping. It must output confidence and downgrade reasons rather than a bare percentile.

- [x] **Step 5: Implement creative-control exclusion**

`classify_dng_natural_hdr_eligibility()` must make active target EV, budget recovery, profile peak, min gain, source/bounded chroma, and path-to-white controls override an otherwise good estimate into `authored_hdr_from_raw`.

- [x] **Step 6: Implement CLI**

Support:

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --synthetic --json-output /tmp/dng-natural-hdr-synthetic.json --csv-output /tmp/dng-natural-hdr-synthetic.csv
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_历史批量归档" --max-samples 3 --json-output /tmp/dng-natural-hdr-real.json
```

The real-DNG path may import rawpy lazily. If rawpy or a DNG decode fails, record the file-level error and continue.

## Task 3: Green Tests And Experiments

- [x] **Step 1: Run focused estimator tests**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_dng_diffuse_white_estimation.py -q
```

Expected: all tests pass.

- [x] **Step 2: Run synthetic CLI**

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --synthetic --json-output /tmp/spektrafilm-dng-natural-hdr-synthetic.json --csv-output /tmp/spektrafilm-dng-natural-hdr-synthetic.csv
```

Expected: outputs include measured white-card, normal, low-key, snow, neon, clipped, and authored-control cases with explicit classes.

- [x] **Step 3: Run bounded real-DNG CLI if feasible**

```bash
.venv/bin/python tools/research_dng_diffuse_white_estimation.py --sample-dir "/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/RAW_DNG_历史批量归档" --max-samples 3 --json-output /tmp/spektrafilm-dng-natural-hdr-real.json
```

Expected: either real diagnostics are produced, or file/dependency failures are classified as environment/input issues.

## Task 4: Write The Final Research Document

- [x] **Step 1: Create `docs/dev/2026-06-04-dng-natural-hdr-luminance-research.md`**

The document must include:

- Executive summary.
- How deep-research conclusions become DNG rules.
- DNG/RAW brightness terminology.
- Strict separation of diffuse white, WhiteLevel, sensor saturation, display reference white, and paper white.
- No-chart diffuse white estimation strategy.
- Confidence and downgrade system.
- Natural HDR eligibility classes.
- DNG to Scene-Film Master State data flow.
- Current code audit table.
- Conflicts with `profile_aware` and `modern_recovery_peak_budget`.
- Recommended API/dataclasses.
- Recommended GUI/UX grouping.
- Minimal experiment results.
- Test commands and results.
- Follow-up implementation issues.
- Remaining uncertainty.

- [x] **Step 2: Update dev README links if appropriate**

Add a concise link to `docs/dev/README.md` and `docs/dev/README_zh.md` only after the research document exists.

## Task 5: Final Validation And Confidence Loop

- [x] **Step 1: Run requested targeted tests where feasible**

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_dng_diffuse_white_estimation.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_hdr_photo.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_hdr_curve_profiles.py -q
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/test_image_io_color_metadata.py -q
QT_QPA_PLATFORM=offscreen PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest tests/gui/test_controller_output.py -q
.venv/bin/python -m compileall -q src tests tools scripts
git diff --check
```

If `uv run --extra dev pytest ...` is stable, run the prompt's `uv` commands too. If it hangs, classify the issue and use the `.venv` commands above as the bounded verifier, matching prior workspace practice.

- [x] **Step 2: Ask the 100% confidence questions**

Before completion, answer in the final document and final reply:

- Did the implementation separate measured diffuse white, estimated diffuse white, sensor white, display white, and paper white?
- Did it prevent target EV, budget recovery, profile peak, min gain, and path-to-white from becoming Natural HDR evidence?
- Did it avoid a single percentile hack by using confidence, clipping, chroma/emissive warnings, and downgrade classes?
- Are the only remaining uncertainties real limitations such as no white card, no device display validation, no actual scene measurement, or DNG decode environment limits?

If any answer is no, add the missing test, estimator guard, or document correction before closing.
