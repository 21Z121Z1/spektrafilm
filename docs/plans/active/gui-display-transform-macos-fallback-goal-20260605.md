# macOS Display Transform Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Spektrafilm GUI Display Transform usable on macOS when Pillow `ImageCms.get_display_profile()` returns `None`, without adding PyObjC or changing non-macOS and default pytest missing-profile semantics.

**Architecture:** Keep the existing Pillow ImageCms display-transform pipeline intact. Add a private macOS-only resolver in `controller_runtime.py` that first uses Pillow, then falls back to ICC bytes from `CGMainDisplayID()` via `ctypes` CoreGraphics/CoreFoundation, and have both availability and details call the same resolver.

**Tech Stack:** Python 3.13 standard library `ctypes`, macOS CoreGraphics/CoreFoundation, Pillow ImageCms, NumPy, pytest, existing Spektrafilm GUI controller/runtime modules.

---

## Initial Findings Before Implementation

- `src/spektrafilm_gui/controller_runtime.py` still calls `imagecms_module.get_display_profile()` directly in `display_profile_details()` and `display_profile_available()`.
- `src/spektrafilm_gui/controller.py` still calls `runtime.display_profile_available(...)` from `sync_display_transform_availability()`, then unchecks Display Transform and reports `Display transform unavailable: no display profile detected, disabled` when availability is false.
- `src/spektrafilm_gui/app.py` still calls `controller.sync_display_transform_availability(report_status=False)` during initialization.
- `pyproject.toml` has Pillow but no PyObjC dependency. This plan does not add dependencies.
- On this macOS checkout, `.venv/bin/python -c "from PIL import ImageCms; print(ImageCms.get_display_profile())"` prints `None`, reproducing the disabling condition.
- Baseline command `.venv/bin/pytest tests/gui/test_controller_output.py` passes with `21 passed`, so new tests must preserve existing semantics.

## Execution Results

- Implemented the macOS fallback in `src/spektrafilm_gui/controller_runtime.py`.
- Updated Display Transform availability and details to share `_resolve_display_profile()`.
- Preserved the existing `apply_display_transform()` ImageCms conversion path.
- Updated the GUI tooltip that previously said Display Transform was Windows-only.
- Added implementation documentation at `studies/gui_display_transform_macos_fallback.md`.
- Updated the existing GUI color/HDR research notes in English and Chinese.
- Verified outside pytest on macOS:

  ```text
  Pillow get_display_profile(): None
  CoreGraphics ICC bytes: 4064
  display_profile_available(): True
  prepare_output_display_image status: Display transform: active (Display)
  ```

## Verification Results

- `.venv/bin/pytest tests/gui/test_controller_output.py`: `25 passed`
- `.venv/bin/pytest tests/gui`: `183 passed`
- `.venv/bin/pytest`: collection blocked by three untracked local HDR routemaster tests importing missing `spektrafilm.hdr`
- `.venv/bin/pytest $(git ls-files 'tests/*.py' 'tests/**/*.py')`: `1535 passed, 7 skipped, 6 failed`
- Clean HEAD worktree check of those same 6 failing tracked tests: same 6 failures, confirming they are baseline/environment failures unrelated to this Display Transform change.

## Final Self-Audit

1. Non-macOS does not load macOS frameworks because `_get_mac_display_profile_bytes()` returns `None` unless `sys.platform == "darwin"`.
2. Default pytest missing-profile semantics are preserved because `_mac_display_profile_fallback_enabled()` returns false under pytest.
3. macOS runtime fallback enables outside pytest; local probe showed Pillow `None`, CoreGraphics ICC bytes, and active Display Transform status.
4. ICC bytes are copied with `ctypes.string_at(...)` before `CFRelease`.
5. `ctypes` signatures use `c_void_p` for CoreFoundation/CoreGraphics object pointers and `c_uint32` for `CGDirectDisplayID`.
6. Fallback failures return `None` and keep existing no-display-profile UI messages.
7. Display Transform status strings are unchanged.
8. SDR rendering, HDR export, gain-map export, profile-aware HDR, film-scan-aware HDR, and save-output paths are not touched by this implementation.
9. Documentation states the `CGMainDisplayID()` main-display limitation.
10. Remaining full-suite failures are reproduced in clean HEAD and are not caused by this change.

## Files

- Modify: `src/spektrafilm_gui/controller_runtime.py`
  - Add `ctypes` and `sys` imports.
  - Add `_running_under_pytest()`, `_mac_display_profile_fallback_enabled()`, `_get_mac_display_profile_bytes()`, `_display_profile_from_fallback()`, and `_resolve_display_profile()`.
  - Change `display_profile_details()` and `display_profile_available()` to use `_resolve_display_profile()`.
  - Leave `apply_display_transform()` color conversion logic unchanged.
- Modify: `tests/gui/test_controller_output.py`
  - Add fallback success tests using monkeypatchable helpers.
  - Add fallback failure tests for missing bytes and bad ICC profile construction.
  - Preserve existing missing-profile tests under pytest default path.
- Modify: `tests/gui/test_controller_runtime_module.py`
  - Add low-level ctypes safety tests and a macOS-only smoke test that skips when no ICC bytes are available.
- Create: `studies/gui_display_transform_macos_fallback.md`
  - Explain cause, no-PyObjC rationale, CoreFoundation ownership, main-display limitation, tests, and manual validation.

## Task 1: Confirm Baseline Semantics

- [x] **Step 1: Read live code and docs**

  Inspect:
  - `src/spektrafilm_gui/controller_runtime.py`
  - `src/spektrafilm_gui/controller.py`
  - `src/spektrafilm_gui/app.py`
  - `tests/gui/test_controller_output.py`
  - `pyproject.toml`
  - `docs/dev/research-gui-color-hdr.md`

- [x] **Step 2: Run baseline targeted tests**

  Run:
  ```bash
  .venv/bin/pytest tests/gui/test_controller_output.py
  ```
  Expected: all current tests pass before source edits.

- [x] **Step 3: Probe local Pillow behavior**

  Run:
  ```bash
  .venv/bin/python -c "from PIL import ImageCms; p=ImageCms.get_display_profile(); print(type(p).__name__ if p is not None else None)"
  ```
  Expected on affected macOS: `None`.

## Task 2: Write Failing Tests First

- [ ] **Step 1: Add fallback success test for availability and details**

  In `tests/gui/test_controller_output.py`, add a test that:
  - monkeypatches `controller_runtime._mac_display_profile_fallback_enabled` to return `True`
  - monkeypatches `controller_runtime._get_mac_display_profile_bytes` to return valid sRGB ICC bytes from `ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()`
  - monkeypatches `controller_module.ImageCms.get_display_profile` to return `None`
  - asserts `controller_runtime.display_profile_available(imagecms_module=controller_module.ImageCms)` is `True`
  - asserts `controller_runtime.display_profile_details(imagecms_module=controller_module.ImageCms)` returns a non-`None` profile and a non-empty profile name

- [ ] **Step 2: Add fallback success test for output preview**

  In `tests/gui/test_controller_output.py`, add a test that:
  - uses the same fallback monkeypatch setup
  - runs `GuiController._prepare_output_display_image(... use_display_transform=True ...)`
  - asserts the status starts with `Display transform: active (`
  - asserts the preview is `uint8`
  - proves `profileToProfile` receives the fallback display profile rather than falling back to raw preview

- [ ] **Step 3: Add fallback missing-bytes test**

  In `tests/gui/test_controller_output.py`, add a test that:
  - enables fallback
  - makes `_get_mac_display_profile_bytes()` return `None`
  - makes `ImageCms.get_display_profile()` return `None`
  - asserts `display_profile_available(...)` is `False`
  - asserts display status remains `Display transform: no display profile, using raw preview`

- [ ] **Step 4: Add fallback bad-ICC test**

  In `tests/gui/test_controller_output.py`, add a test that:
  - enables fallback
  - makes `_get_mac_display_profile_bytes()` return invalid bytes
  - asserts details return `(None, None)` and availability is `False`

- [ ] **Step 5: Add ctypes failure and smoke tests**

  In `tests/gui/test_controller_runtime_module.py`, add:
  - a test that monkeypatches `runtime_module.ctypes.CDLL` to raise `OSError`, monkeypatches `runtime_module.sys.platform` to `darwin`, and asserts `_get_mac_display_profile_bytes()` returns `None`
  - a macOS-only smoke test that calls `_get_mac_display_profile_bytes()`, skips if it returns `None`, and otherwise parses bytes with `ImageCms.ImageCmsProfile(BytesIO(...))`

- [ ] **Step 6: Run new tests before implementation**

  Run:
  ```bash
  .venv/bin/pytest tests/gui/test_controller_output.py tests/gui/test_controller_runtime_module.py
  ```
  Expected before implementation: fallback tests fail because the helper functions do not exist or fallback does not run.

## Task 3: Implement Unified Display Profile Resolution

- [ ] **Step 1: Add imports**

  In `src/spektrafilm_gui/controller_runtime.py`, add:
  ```python
  import ctypes
  import sys
  ```

- [ ] **Step 2: Add pytest and fallback gates**

  Add:
  ```python
  def _running_under_pytest() -> bool:
      return "pytest" in sys.modules


  def _mac_display_profile_fallback_enabled() -> bool:
      return sys.platform == "darwin" and not _running_under_pytest()
  ```

- [ ] **Step 3: Add CoreGraphics/CoreFoundation ICC byte loader**

  Add `_get_mac_display_profile_bytes() -> bytes | None` that:
  - returns `None` immediately unless `sys.platform == "darwin"`
  - loads `/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation`
  - loads `/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics`
  - sets all `argtypes` and `restype` values needed to avoid pointer truncation
  - calls `CGMainDisplayID()`, `CGDisplayCopyColorSpace(display_id)`, `CGColorSpaceCopyICCData(color_space)`, `CFDataGetLength(icc_data)`, and `CFDataGetBytePtr(icc_data)`
  - copies the bytes using `ctypes.string_at(ptr, int(length))` before releasing objects
  - releases `icc_data` and `color_space` in `finally` when non-null and CoreFoundation loaded
  - returns `None` on invalid values or safe exceptions

- [ ] **Step 4: Add Pillow profile construction from fallback bytes**

  Add:
  ```python
  def _display_profile_from_fallback(*, imagecms_module: Any) -> object | None:
      if not _mac_display_profile_fallback_enabled():
          return None
      icc_bytes = _get_mac_display_profile_bytes()
      if not icc_bytes:
          return None
      pycms_error = getattr(imagecms_module, "PyCMSError", RuntimeError)
      try:
          return imagecms_module.ImageCmsProfile(BytesIO(icc_bytes))
      except (AttributeError, OSError, ValueError, TypeError, pycms_error):
          return None
  ```

- [ ] **Step 5: Add unified resolver**

  Add:
  ```python
  def _resolve_display_profile(*, imagecms_module: Any) -> object | None:
      pycms_error = getattr(imagecms_module, "PyCMSError", RuntimeError)
      try:
          display_profile = imagecms_module.get_display_profile()
      except (AttributeError, OSError, ValueError, TypeError, pycms_error):
          display_profile = None
      if display_profile is not None:
          return display_profile
      return _display_profile_from_fallback(imagecms_module=imagecms_module)
  ```

- [ ] **Step 6: Rewire public profile helpers**

  Change:
  - `display_profile_details()` to call `_resolve_display_profile()`, return `(None, None)` on missing profile, otherwise preserve existing `display_profile_name(...)`
  - `display_profile_available()` to return `_resolve_display_profile(...) is not None`

## Task 4: Documentation

- [ ] **Step 1: Write implementation note**

  Create `studies/gui_display_transform_macos_fallback.md` with:
  - cause: Pillow may return `None` on macOS, causing startup auto-disable
  - fix: `ctypes` CoreGraphics/CoreFoundation main-display ICC fallback
  - no PyObjC rationale: dependency set stays unchanged
  - ownership: `CGDisplayCopyColorSpace` and `CGColorSpaceCopyICCData` require `CFRelease`
  - limitation: uses `CGMainDisplayID()`, not current GUI window display
  - unit test strategy: pytest default gate plus explicit monkeypatch tests
  - manual validation steps and current local result

## Task 5: Verification And Self-Audit

- [ ] **Step 1: Run targeted tests**

  Run:
  ```bash
  .venv/bin/pytest tests/gui/test_controller_output.py
  ```
  Expected: pass.

- [ ] **Step 2: Run GUI tests**

  Run:
  ```bash
  .venv/bin/pytest tests/gui
  ```
  Expected: pass or report any environment-only blockers with exact evidence.

- [ ] **Step 3: Run feasible broader tests**

  Run:
  ```bash
  .venv/bin/pytest
  ```
  Expected: pass or classify pre-existing/environment failures without hiding them.

- [ ] **Step 4: Run final self-audit**

  Check:
  1. Non-macOS returns `None` from the ctypes byte loader and never tries macOS frameworks.
  2. Default pytest missing-profile tests still see no display profile.
  3. Real macOS runtime can enable fallback outside pytest.
  4. ICC bytes are copied before `CFRelease`.
  5. `ctypes` signatures use pointer-safe `c_void_p` returns.
  6. All fallback failures degrade to no display profile instead of raising.
  7. Status strings remain existing UI strings.
  8. SDR, HDR, save output, gain map, and film-scan-aware paths are not touched.
  9. Documentation states the main-display limitation.
  10. Remaining confidence gaps have either been fixed or explicitly bounded.
