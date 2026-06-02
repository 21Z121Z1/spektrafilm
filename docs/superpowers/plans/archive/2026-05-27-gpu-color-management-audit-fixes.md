# GPU Color Management Audit Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Reconcile `docs/archive/docs-2-legacy-20260531/dev/research-gpu-color-management.md` with the current codebase, then fix the real GPU/color-management defects that still exist.

**Architecture:** Keep the current `ArrayBackend` + colour-science + OpenImageIO design. Apply only narrow fixes that preserve float32/float64 numerical parity, color metadata contracts, and existing GUI/runtime APIs. Treat Taichi, OCIO, and cross-platform HDR gain-map encoding as future architecture work unless a current failing behavior proves they are required.

**Tech Stack:** Python 3.13, NumPy, colour-science, OpenImageIO, pytest, existing Spektrafilm GPU backends.

---

## Evidence And Scope

The entrance research document is partially stale. Current code already contains:

- ACEScg ICC mapping in `src/spektrafilm/utils/io.py`.
- Display P3 linear ICC mapping and `src/spektrafilm/data/icc/DisplayP3-linear.icc`.
- `save_hdr_rendition_exr()` and `exr_mode="hdr_rendition"`.
- Generic backend tiling helper in `src/spektrafilm/gpu/backend.py`.

The current targeted suite passes before new changes:

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_image_io_color_metadata.py tests/test_gpu_color_chain.py tests/test_gpu_backend.py tests/test_hdr_photo.py -q
# Expected current baseline: 189 passed
```

Authority checks used for the implementation choices:

- Python Array API standard: keep a focused backend protocol because the standard explicitly targets common array construction/operation interop, while Spektrafilm needs a smaller custom kernel surface.
- OpenImageIO metadata conventions: continue tagging `oiio:ColorSpace`, EXR chromaticities, and ICC profile data through `ImageSpec`.
- ACEScg documentation: keep ACEScg as a linear AP1 working space and ACES2065-1 as interchange/archive.
- ICC RGB registry for DCI P3: DCI-P3 has a 2.6 gamma transfer, so backend CCTF encode should be `pow(rgb, 1/2.6)` to match colour-science.
- Apple HDR gain-map documentation: keep current macOS CoreImage HEIC path as the production HEIC writer; cross-platform gain-map writing remains future work.

## Real Issues To Fix

### Issue 1: GPU CCTF Encoding Fails For DCI-P3

`RGBColorSpaces` exposes `DCI-P3`, and `cctf_decoding_backend()` already supports it, but `cctf_encoding_backend()` omits it. A GPU-backed scan/output path with `output_color_space="DCI-P3"` and CCTF encoding raises:

```text
NotImplementedError: Backend CCTF encoding is not implemented for color space 'DCI-P3'
```

This is a real runtime bug, not a future enhancement.

### Issue 2: HDR Rendition EXR Drops Mapping Diagnostics

`prepare_hdr_photo_renditions()` can return diagnostics such as source-chroma fallback warnings. `save_hdr_photo_heic()` returns those diagnostics, but `save_image_oiio(..., exr_mode="hdr_rendition")` and `save_hdr_rendition_exr()` currently discard them and return `()`. The GUI already captures `hdr_diagnostics`, so the IO boundary should preserve diagnostics consistently for HEIC and HDR rendition EXR.

### Issue 3: API Documentation Is Stale Around HDR EXR Parameters And Return Semantics

`save_image_oiio()` accepts `scene_luminance`, `scene_rgb`, `hdr_mapping_kwargs`, and `exr_mode`, but its docstring does not fully document those parameters or the diagnostics return contract. The research doc also still lists already-fixed gaps as active recommendations. This is a real maintenance problem because future callers can misuse archive EXR vs HDR rendition EXR.

## Non-Issues / Future Work

These recommendations from the entrance research doc are not one-shot bug fixes:

- Taichi backend: would require a new backend implementation and optional dependency; current `ArrayBackend` methods assume NumPy-like array semantics, which Taichi does not provide as a drop-in replacement.
- Optional OCIO: valid future work for ACES output transforms, but not required to fix current ICC/OIIO metadata or GPU CCTF parity.
- Cross-platform HDR gain-map HEIC/JPEG encoding: significant encoder work. Current Apple/CoreImage path is intentional and documented.
- DCI-P3 linear ICC: current code explicitly treats it as unavailable; DCI-P3 CCTF output is the active user-facing path.

## File Structure

- Modify `tests/test_gpu_color_chain.py`: add DCI-P3 to the GPU CCTF encoding parity test.
- Modify `tests/test_image_io_color_metadata.py`: add HDR rendition EXR diagnostics tests for `save_image_oiio()` and `save_hdr_rendition_exr()`.
- Modify `src/spektrafilm/gpu/kernels/color.py`: add backend DCI-P3 CCTF encoding.
- Modify `src/spektrafilm/utils/io.py`: preserve HDR rendition diagnostics and update docstring.
- Modify `src/spektrafilm_gui/controller.py`: show HDR rendition EXR diagnostics when available.
- Modify `docs/dev/research-gpu-color-management.md` and `docs/archive/docs-2-legacy-20260531/dev/research-gpu-color-management.md`: add current audit notes so the stale recommendations are not re-applied blindly.

## Task 1: Add Failing GPU DCI-P3 Encoding Test

**Files:**
- Modify: `tests/test_gpu_color_chain.py`

- [x] **Step 1: Write the failing test**

Add `"DCI-P3"` to the `test_backend_cctf_encoding_matches_colour_reference` parameter list:

```python
@pytest.mark.parametrize(
    "color_space",
    ["sRGB", "Display P3", "ProPhoto RGB", "ITU-R BT.2020", "Adobe RGB (1998)", "DCI-P3", "ACES2065-1", "ACEScg"],
)
def test_backend_cctf_encoding_matches_colour_reference(color_space: str) -> None:
    ...
```

- [x] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_color_chain.py::test_backend_cctf_encoding_matches_colour_reference -q
```

Expected before implementation: DCI-P3 case fails with `NotImplementedError`.

## Task 2: Implement DCI-P3 GPU CCTF Encoding

**Files:**
- Modify: `src/spektrafilm/gpu/kernels/color.py`

- [x] **Step 1: Add the transfer helper**

Add:

```python
def _cctf_encoding_dci_p3(rgb: Any, backend) -> Any:
    return backend.pow(rgb, 1.0 / 2.6)
```

- [x] **Step 2: Wire it into dispatch**

Add before ACES passthrough:

```python
if color_space == "DCI-P3":
    return _cctf_encoding_dci_p3(rgb, backend)
```

- [x] **Step 3: Verify targeted pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_gpu_color_chain.py::test_backend_cctf_encoding_matches_colour_reference -q
```

Expected after implementation: all parameter cases pass, with expected RuntimeWarnings for negative gamma powers if present.

## Task 3: Add Failing HDR Rendition EXR Diagnostics Tests

**Files:**
- Modify: `tests/test_image_io_color_metadata.py`

- [x] **Step 1: Add a helper-free failing test for the wrapper**

Add a test that forces source-chroma fallback diagnostics:

```python
def test_save_hdr_rendition_exr_returns_mapping_diagnostics(tmp_path) -> None:
    path = tmp_path / "rendition-diagnostics.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    scene_rgb = np.zeros((1, 2, 3), dtype=np.float32)

    diagnostics = save_hdr_rendition_exr(
        str(path),
        image,
        color_space="Display P3",
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "profile_aware",
            "film": "kodak_portra_400",
            "paper": "kodak_ultra_endura",
            "hdr_highlight_color_mode": "source_chroma",
        },
    )

    assert any("degrading to off" in item for item in diagnostics)
```

- [x] **Step 2: Add a failing test for the generic IO path**

Add:

```python
def test_save_image_oiio_hdr_rendition_returns_mapping_diagnostics(tmp_path) -> None:
    path = tmp_path / "rendition-diagnostics-api.exr"
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    scene_rgb = np.zeros((1, 2, 3), dtype=np.float32)

    diagnostics = save_image_oiio(
        str(path),
        image,
        encoding=ColorEncoding(
            color_space="Display P3",
            transfer="linear",
            role="scene",
            clip_highlights=False,
        ),
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb,
        hdr_mapping_kwargs={
            "hdr_mapping_mode": "profile_aware",
            "film": "kodak_portra_400",
            "paper": "kodak_ultra_endura",
            "hdr_highlight_color_mode": "source_chroma",
        },
        exr_mode="hdr_rendition",
    )

    assert any("degrading to off" in item for item in diagnostics)
```

- [x] **Step 3: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/test_image_io_color_metadata.py::test_save_hdr_rendition_exr_returns_mapping_diagnostics tests/test_image_io_color_metadata.py::test_save_image_oiio_hdr_rendition_returns_mapping_diagnostics -q
```

Expected before implementation: both fail because diagnostics are `()`.

## Task 4: Preserve HDR Rendition Diagnostics

**Files:**
- Modify: `src/spektrafilm/utils/io.py`
- Modify: `src/spektrafilm_gui/controller.py`

- [x] **Step 1: Preserve diagnostics in IO**

Inside `save_image_oiio()`, initialize:

```python
hdr_diagnostics: tuple[str, ...] = ()
```

When `exr_mode == "hdr_rendition"`, after `prepare_hdr_photo_renditions(...)`, set:

```python
hdr_diagnostics = renditions.diagnostics
```

At the final successful non-PNG/JPEG write return, return `hdr_diagnostics` instead of `()`.

- [x] **Step 2: Show EXR diagnostics in controller status**

For `elif exr_save and hdr_exr_mode == 'hdr_rendition':`, append diagnostics when present:

```python
base_msg = f"Saved output image to {filepath} (EXR saved as HDR rendition)"
if hdr_diagnostics:
    diag_msg = " | ".join(hdr_diagnostics)
    set_status(self._viewer, f"{base_msg} - {diag_msg}")
else:
    set_status(self._viewer, base_msg)
```

- [x] **Step 3: Verify targeted pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_image_io_color_metadata.py::test_save_hdr_rendition_exr_returns_mapping_diagnostics tests/test_image_io_color_metadata.py::test_save_image_oiio_hdr_rendition_returns_mapping_diagnostics -q
```

Expected: both pass.

## Task 5: Update API And Research Documentation

**Files:**
- Modify: `src/spektrafilm/utils/io.py`
- Modify: `docs/dev/research-gpu-color-management.md`
- Modify: `docs/archive/docs-2-legacy-20260531/dev/research-gpu-color-management.md`

- [x] **Step 1: Update `save_image_oiio()` docstring**

Document:

- `scene_luminance`
- `scene_rgb`
- `hdr_mapping_kwargs`
- `exr_mode`
- return diagnostics for HEIC and HDR rendition EXR

- [x] **Step 2: Add audit addendum to both research docs**

Add a dated section stating:

- Already implemented: ACEScg ICC, Display P3 linear ICC, HDR rendition EXR, backend tiling.
- Fixed in this pass: DCI-P3 GPU CCTF encoding, HDR rendition EXR diagnostic propagation, API docs.
- Deferred: Taichi, OCIO, cross-platform HDR gain-map encoding.

## Task 6: Verification And Self-Audit Loop

**Files:**
- No new files unless verification uncovers another bug.

- [x] **Step 1: Run focused tests**

```bash
.venv/bin/python -m pytest tests/test_gpu_color_chain.py tests/test_image_io_color_metadata.py tests/test_hdr_photo.py -q
```

- [x] **Step 2: Run broader relevant tests**

```bash
.venv/bin/python -m pytest tests/test_color_management.py tests/test_gpu_backend.py tests/test_runtime_api.py tests/test_pipeline_smoke.py -q
```

- [x] **Step 3: Run full non-GUI suite**

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

- [x] **Step 4: Run static sanity checks**

```bash
.venv/bin/python -m compileall -q src tests
git diff --check
```

- [x] **Step 5: 100% confidence self-question**

Ask:

- Did every code change have a failing test before implementation where behavior changed?
- Did DCI-P3 GPU output match colour-science numerically, including negative-value `NaN` parity?
- Did EXR archive mode remain untouched and avoid HDR mapping?
- Did HEIC diagnostics remain unchanged?
- Did docs now distinguish real current fixes from future architecture work?

If any answer is "no", add the missing test/fix and rerun the relevant checks.

## Verification-Discovered Fixes

The broader focused test run surfaced additional existing tests that were already present in the working tree and failing. These are now part of the goal because they are real behavior defects in the same HDR/color-management surface.

### Issue 4: `load_image_oiio(Path)` Fails With `TypeError` In Error Path

**Files:**
- Modify: `src/spektrafilm/utils/io.py`

- [x] Convert `filename` to a string before passing it to OpenImageIO and before composing `OSError` messages.
- [x] Re-run `tests/test_image_io_color_metadata.py::test_load_image_oiio_path_open_failure_raises_oserror`.

### Issue 5: HEIC HDR Export Does Not Validate Output Path Before Encoder

**Files:**
- Modify: `src/spektrafilm/utils/hdr_photo.py`

- [x] Reject output paths containing ASCII control characters before creating encoder payloads.
- [x] Reject output paths whose parent directory does not exist before invoking the Swift/CoreImage encoder.
- [x] Re-run the two HEIC path-validation tests in `tests/test_hdr_photo.py`.

### Issue 6: Scene-Luminance Graft Uses Max Channel Instead Of Perceptual Look Luminance

**Files:**
- Modify: `src/spektrafilm/utils/hdr_photo.py`

- [x] Replace max-channel look luminance in `_graft_scene_luminance()` with the existing Rec.709/sRGB `luminance_y()` helper.
- [x] Re-run `tests/test_hdr_photo.py::test_scene_luminance_graft_uses_perceptual_look_luminance_for_saturated_color` plus the surrounding HDR photo tests.

### Issue 7: Halide Backend Is Exposed In Tests/GUI But Not Fully Wired Through Selection And Precision Rules

**Files:**
- Modify: `src/spektrafilm/gpu/backend.py`
- Modify: `src/spektrafilm/gpu/halide_backend.py`
- Modify: `src/spektrafilm/runtime/pipeline.py`
- Modify: `src/spektrafilm_gui/options.py`
- Modify: `pyproject.toml`

- [x] Include `halide` in the strict backend-name validator and reject unknown names with an error that lists the full supported set.
- [x] Keep `auto` limited to MLX, CuPy, then CPU; do not silently select Halide unless requested.
- [x] Make `select_backend("halide")` strict: return a Halide backend when the optional dependency exists and raise `BackendUnavailableError` when it does not.
- [x] Keep Halide float32-only and reject explicit Halide with runtime `float64` before pipeline initialization.
- [x] Implement Halide `cleanup()` so it satisfies the `ArrayBackend` protocol and clears cached JIT pipelines during runtime cache cleanup.
- [x] Re-run the Halide/backend selector tests plus the runtime float64 precision test.

### Issue 8: `Simulator.process_with_metadata()` Breaks Older Pipeline-Like Objects

**Files:**
- Modify: `src/spektrafilm/runtime/process.py`

- [x] Only pass `include_scene_rgb=True` when the caller requests scene RGB metadata. Preserve the legacy no-keyword call shape for `include_scene_rgb=False`.
- [x] Re-run `tests/test_runtime_api.py::TestRuntimeApi::test_simulator_process_with_metadata_preserves_process_array_api`.
