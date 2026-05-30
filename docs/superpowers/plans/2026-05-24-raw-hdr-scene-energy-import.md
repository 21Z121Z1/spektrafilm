# RAW HDR Scene-Energy Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a RAW import sidecar that records rawpy scale diagnostics and an automatic diffuse-white/headroom estimate without changing the current imported pixel image used by the film simulation.

**Architecture:** Keep `load_and_process_raw_file()` backward compatible by returning the existing NumPy image unless callers request diagnostics. When diagnostics are requested, return a `RawProcessingResult` containing the image plus a compact `RawImportDiagnostics` dataclass. The GUI RAW loader stores that diagnostics object on the controller and on the input preview layer metadata so later HDR export work can build a scene-energy/luminance graft from the same imported linear image and the estimated anchor. *(Update 2026-05-25: This HDR export work has been completed via the Dual-Layer HDR Mapping feature).*

**Tech Stack:** Python 3.13, rawpy/LibRaw, NumPy, colour-science, PySide/Qt GUI, pytest.

---

## Signal Decision

Current RAW import uses `rawpy.postprocess(output_bps=16, no_auto_bright=True, gamma=(1, 1), output_color=ACES)` and divides by `65535.0`. That is linear, but the numeric scale is rawpy/LibRaw render normalization, not a calibrated scene exposure convention. Real DNG samples under `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片` confirmed that rawpy RGB can hit `1.0` while upper percentiles and clip fractions vary widely.

This phase therefore does not rescale the imported image. It adds an honest sidecar:

- rawpy RGB min/max/p50/p99/p999 diagnostics after `65535` normalization;
- raw sensor black/white normalized max/p99/p999 diagnostics when rawpy exposes the needed fields;
- automatic diffuse-white estimate from imported linear RGB max-channel percentiles;
- low-key floor behavior so dark scenes are not brightened by a naive percentile;
- headroom estimate from a robust high percentile divided by the diffuse-white estimate;
- confidence/method labels so later UI/export code can distinguish estimate from calibration.

## Files

- Modify: `src/spektrafilm/utils/raw_file_processor.py`
  - Add `RawImportDiagnostics` and `RawProcessingResult`.
  - Add `estimate_raw_hdr_import_diagnostics()`.
  - Add optional `return_diagnostics: bool = False` to `load_and_process_raw_file()`.
- Modify: `src/spektrafilm_gui/controller.py`
  - Add `RAW_IMPORT_DIAGNOSTICS_KEY`.
  - Request diagnostics from RAW imports.
  - Store the diagnostics on the controller and input preview layer metadata.
- Modify: `tests/test_raw_file_processor.py`
  - Add diagnostics/unit coverage.
- Modify: `tests/gui/test_controller_flow.py`
  - Add GUI propagation coverage.
- Modify: `README.md`
  - Clarify that RAW import is linear rawpy-normalized and now records HDR anchor diagnostics.

## Task 1: Add RAW Import Diagnostics Tests

**Files:**
- Modify: `tests/test_raw_file_processor.py`

- [ ] **Step 1: Add imports and a diagnostics result test**

Add tests asserting that `return_diagnostics=True` returns a result object with the same image values as the legacy path and diagnostics based on percentiles:

```python
def test_process_raw_file_can_return_hdr_import_diagnostics(monkeypatch):
    raw_image = np.array(
        [[[6554, 6554, 6554], [32768, 32768, 32768], [65535, 65535, 65535]]],
        dtype=np.uint16,
    )
    _stub_raw_reader(monkeypatch, raw_image)

    result = raw_file_processor.load_and_process_raw_file(
        'example.dng',
        white_balance='daylight',
        return_diagnostics=True,
    )

    assert isinstance(result, raw_file_processor.RawProcessingResult)
    expected = raw_image.astype(np.float32) / 65535.0
    np.testing.assert_allclose(result.image, expected)
    assert result.diagnostics.rawpy_rgb_max == pytest.approx(1.0)
    assert result.diagnostics.rawpy_rgb_p99 > 0.5
    assert result.diagnostics.diffuse_white_estimate > 0.0
    assert result.diagnostics.headroom_estimate >= 1.0
    assert result.diagnostics.method in {'auto_percentile', 'auto_floor_low_key'}
```

- [ ] **Step 2: Add a low-key floor test**

```python
def test_estimate_raw_hdr_import_diagnostics_uses_low_key_floor() -> None:
    image = np.full((4, 4, 3), 0.01, dtype=np.float32)

    diagnostics = raw_file_processor.estimate_raw_hdr_import_diagnostics(image)

    assert diagnostics.diffuse_white_estimate == pytest.approx(0.10)
    assert diagnostics.method == 'auto_floor_low_key'
    assert diagnostics.confidence == 'low'
```

- [ ] **Step 3: Verify RED**

Run:

```bash
uv run --extra dev pytest -q tests/test_raw_file_processor.py::test_process_raw_file_can_return_hdr_import_diagnostics tests/test_raw_file_processor.py::test_estimate_raw_hdr_import_diagnostics_uses_low_key_floor
```

Expected: fail because `RawProcessingResult` and `estimate_raw_hdr_import_diagnostics()` do not exist yet.

## Task 2: Implement RAW Import Diagnostics

**Files:**
- Modify: `src/spektrafilm/utils/raw_file_processor.py`

- [ ] **Step 1: Add dataclasses**

```python
@dataclass(frozen=True, slots=True)
class RawImportDiagnostics:
    rawpy_rgb_min: float
    rawpy_rgb_max: float
    rawpy_rgb_p50: float
    rawpy_rgb_p99: float
    rawpy_rgb_p999: float
    rawpy_rgb_clip_fraction: float
    diffuse_white_estimate: float
    headroom_estimate: float
    method: str
    confidence: str
    raw_sensor_white_level: float | None = None
    raw_sensor_black_level: float | None = None
    raw_sensor_normalized_max: float | None = None
    raw_sensor_normalized_p99: float | None = None
    raw_sensor_normalized_p999: float | None = None


@dataclass(frozen=True, slots=True)
class RawProcessingResult:
    image: np.ndarray
    diagnostics: RawImportDiagnostics
```

- [ ] **Step 2: Add percentile estimator**

Use max-channel intensity for a first robust, color-space-independent anchor:

```python
def estimate_raw_hdr_import_diagnostics(
    rgb: np.ndarray,
    *,
    raw_sensor_stats: dict[str, float | None] | None = None,
    auto_percentile: float = 99.0,
    headroom_percentile: float = 99.9,
    min_auto_diffuse_white: float = 0.10,
    low_key_median_threshold: float = 0.03,
    max_headroom: float = 8.0,
) -> RawImportDiagnostics:
    ...
```

Requirements:

- require floating RGB shape `(H, W, 3+)`;
- require finite values;
- clamp diagnostic intensity to non-negative values;
- compute `p50`, `p99`, `p999`, `max`;
- if `p99 < 0.10` and `p50 < 0.03`, set diffuse white to `0.10`, method `auto_floor_low_key`, confidence `low`;
- otherwise set diffuse white to `clip(p99, 0.10, 1.0)`, method `auto_percentile`, confidence `medium`;
- set `headroom_estimate = min(max(p999 / diffuse_white, 1.0), max_headroom)`;
- set `rawpy_rgb_clip_fraction` to fraction of RGB channel samples at or above `1.0 - 0.5 / 65535.0`.

- [ ] **Step 3: Collect raw sensor diagnostics best-effort**

Inside the `rawpy.imread()` context, collect:

```python
raw_image_visible
white_level
black_level_per_channel
```

Normalize with the minimum black level and return `None` fields if any attribute is missing.

- [ ] **Step 4: Add `return_diagnostics` without breaking legacy callers**

If `return_diagnostics` is `False`, return the same NumPy image as before. If `True`, return:

```python
RawProcessingResult(image=image, diagnostics=diagnostics)
```

## Task 3: Store RAW Diagnostics In GUI

**Files:**
- Modify: `src/spektrafilm_gui/controller.py`
- Modify: `tests/gui/test_controller_flow.py`

- [ ] **Step 1: Add GUI test for result object propagation**

Add a test where the fake RAW loader returns `RawProcessingResult`; assert:

- loader receives `return_diagnostics=True`;
- `_current_input_image` remains the image;
- `_current_raw_import_diagnostics` stores diagnostics;
- preview layer metadata contains `RAW_IMPORT_DIAGNOSTICS_KEY`.

- [ ] **Step 2: Implement controller storage**

Add:

```python
RAW_IMPORT_DIAGNOSTICS_KEY = 'raw_import_diagnostics'
```

Initialize:

```python
self._current_raw_import_diagnostics = None
```

In `load_raw_image()`:

```python
raw_result = load_and_process_raw_file(..., return_diagnostics=True)
if hasattr(raw_result, 'image') and hasattr(raw_result, 'diagnostics'):
    image = raw_result.image
    self._current_raw_import_diagnostics = raw_result.diagnostics
else:
    image = raw_result
    self._current_raw_import_diagnostics = None
```

After `_set_or_add_input_stack(image)`, write diagnostics to the preview layer metadata if present.

## Task 4: Documentation And Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update RAW import docs**

Clarify:

- RAW import remains rawpy-normalized linear RGB;
- it records diagnostics/auto anchor estimates for later HDR scene-energy work;
- auto estimate is not physical calibration.

- [ ] **Step 2: Run targeted tests**

```bash
uv run --extra dev pytest -q tests/test_raw_file_processor.py tests/test_raw_smoke.py tests/gui/test_controller_flow.py::test_load_raw_image_uses_pipeline_input_settings_and_builds_preview_stack tests/gui/test_controller_flow.py::test_load_raw_image_aces_reference_outputs_acescg_and_updates_input_controls tests/gui/test_controller_flow.py::test_load_raw_image_stores_hdr_import_diagnostics
```

- [ ] **Step 3: Run real sample smoke**

Run against one local DNG:

```bash
uv run --extra dev python - <<'PY'
from pathlib import Path
from spektrafilm.utils.raw_file_processor import load_and_process_raw_file
sample = next(Path('/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片').rglob('*.DNG'))
result = load_and_process_raw_file(sample, return_diagnostics=True)
print(sample)
print(result.image.shape, result.image.dtype)
print(result.diagnostics)
PY
```

- [ ] **Step 4: Run static checks**

```bash
python3 -m compileall -q src/spektrafilm src/spektrafilm_gui tests
git diff --check
```

## Self-Audit Questions

- Does legacy `load_and_process_raw_file()` still return a NumPy image?
- Does the new result object preserve exactly the same image values?
- Are automatic anchor values clearly labeled estimates, not calibration?
- Does low-key input avoid forced brightening from a tiny percentile?
- Does GUI RAW loading preserve existing layer behavior while storing diagnostics?
- Does real local DNG loading produce finite diagnostics?
- Are existing unrelated GPU/HDR/ACES changes preserved?
