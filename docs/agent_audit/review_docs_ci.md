# Docs & API Consistency Findings

> Generated 2026-05-28 — Review-only audit (no code changes)

---

## Finding: DOC-001
- **Severity**: P1
- **Evidence**: README.md:66-72
- **Issue**: README code sample uses `create_params` but the actual public API exports `init_params`. `from spektrafilm import create_params` will raise `ImportError`. The function was renamed at some point and the README was not updated.
- **Fix**: Change the code sample to `from spektrafilm import init_params, simulate` and rename `create_params(` to `init_params(`.

---

## Finding: DOC-002
- **Severity**: P2
- **Evidence**: pyproject.toml:24 (`lmfit~=1.3.2`)
- **Issue**: `lmfit` is declared as a dependency but has zero imports anywhere in `src/`, `src/spektrafilm_gui/`, or `tests/`. It appears to be a leftover from an earlier version of the codebase.
- **Fix**: Remove `lmfit~=1.3.2` from `dependencies` if confirmed unused by the project owner.

---

## Finding: DOC-003
- **Severity**: P2
- **Evidence**: pyproject.toml:33 (`PyYAML~=6.0`)
- **Issue**: `PyYAML` is declared as a dependency but has zero `import yaml` or `from yaml` statements anywhere in the source tree. It may have been used for profile serialization before the JSON-based approach in `profiles/io.py`.
- **Fix**: Remove `PyYAML~=6.0` from `dependencies` if confirmed unused by the project owner.

---

## Finding: DOC-004
- **Severity**: P3
- **Evidence**: pyproject.toml:25 (`pyside6~=6.9`)
- **Issue**: `PySide6` is never directly imported — the codebase uses `qtpy` as the abstraction layer. However, `qtpy` requires a Qt binding at runtime, so `PySide6` is an indirect runtime dependency. This is architecturally correct but could benefit from a comment explaining why both `qtpy` and `PySide6` are listed (e.g. `# Qt binding for qtpy`).
- **Fix**: Add a comment next to `PySide6` in `pyproject.toml` explaining it's the runtime Qt backend for `qtpy`. Low priority.

---

## Finding: DOC-005
- **Severity**: P2
- **Evidence**: `src/spektrafilm/config.py:5` and `src/spektrafilm/config.py:13-15`
- **Issue**: Two public constants are defined but never imported anywhere in the codebase:
  - `LOG_EXPOSURE` — a `np.linspace(-3,4,256)` array, zero references outside `config.py`.
  - `STANDARD_OBSERVER_LMS` — Stockman & Sharpe 2° cone fundamentals, zero references outside `config.py`.
  
  These are dead code that adds import-time cost (colour-science alignment).
- **Fix**: Remove both constants, or move them to the modules that would use them if they are planned for future use.

---

## Finding: DOC-006
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_builder.py:51`
- **Issue**: `digest_params` parameter `apply_stocks_specifics` is missing a type annotation. It defaults to `True` (implying `bool`) but the bare signature `apply_stocks_specifics=True` lacks an explicit `bool` type hint, inconsistent with the other typed parameters on the same function.
- **Fix**: Change to `apply_stocks_specifics: bool = True`.

---

## Finding: DOC-007
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_builder.py:22`
- **Issue**: `apply_database_neutral_print_filters` parameter `database` has no type annotation. Its default is `None` and it receives a `dict` or `None` at runtime, but the signature is bare `database=None`.
- **Fix**: Add annotation `database: dict | None = None`.

---

## Finding: DOC-008
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_builder.py:131-150`
- **Issue**: Large block of commented-out optimization matrices (lines 131-150) inside `_apply_film_specifics`. These are scratch notes from tuning coupler gamma values — raw matrix dumps with loss/alpha annotations. They are not documentation and clutter the function body.
- **Fix**: Move to a separate notes file or remove. If they need to stay for reference, wrap in a clear `# Historical tuning notes:` header or use a dev-notes file.

---

## Finding: DOC-009
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_builder.py:167-168`
- **Issue**: Commented-out stock override for `kodak_portra_400` halation scatter. This is dead code left behind after experimentation.
- **Fix**: Remove the two commented-out lines.

---

## Finding: DOC-010
- **Severity**: P2
- **Evidence**: `src/spektrafilm/runtime/params_builder.py:100-106`
- **Issue**: `init_params` has a malformed docstring — it reads as two concatenated docstrings: the first says "Simple helper to build a RuntimePhotoParams with just film and print profiles specified." and the second says "Build a runtime parameter object. It needs to be digested with digest_params before being used in the runtime pipeline." The second sentence appears to be a stale leftover from a previous version of the function.
- **Fix**: Consolidate into a single clear docstring, e.g.: `"""Build a RuntimePhotoParams with default film/print profiles. Must be digested via digest_params before use in the pipeline."""`

---

## Finding: DOC-011
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_schema.py:162-175` (IOParams)
- **Issue**: Inconsistent unit-suffix naming in `IOParams`: `crop_center` and `crop_size` are fractions (0.0-1.0) but have no suffix indicating their unit, while other params in sibling dataclasses use `_um`, `_mm`, `_ev` suffixes. The field `upscale_factor` is a multiplier with no suffix. This is not a bug, but the naming convention is inconsistent across the schema.
- **Fix**: Low priority — consider documenting the expected ranges/units in field comments or docstrings.

---

## Finding: DOC-012
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_schema.py:11` and `src/spektrafilm/runtime/params_schema.py:44`
- **Issue**: `DiffusionFilterParams` and `CameraParams` are public dataclasses but not listed in the architecture index's public API for `runtime/params_schema.py`. The index lists `RuntimePhotoParams`, `CameraParams`, `EnlargerParams`, etc. but the nested `DiffusionFilterParams` is omitted despite being part of the public interface (used as a field type in `CameraParams` and `EnlargerParams`).
- **Fix**: Add `DiffusionFilterParams` to the architecture index's public API list for `params_schema.py`.

---

## Finding: DOC-013
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_schema.py:200`
- **Issue**: `DebugParams.debug_mode` has a comment listing allowed values (`'output', 'inject', 'off'`) but these are not enforced by validation. A user can set any string. The allowed values are also discoverable only by reading the source — they are not documented in the README or any user-facing doc.
- **Fix**: Low priority. Consider adding an `__post_init__` validation or documenting the allowed values in the README's debug section.

---

## Finding: DOC-014
- **Severity**: P3
- **Evidence**: `src/spektrafilm/runtime/params_schema.py:176-192`
- **Issue**: `IOParams.full_image` is a deprecated property that always returns `True` and whose setter is a no-op. It emits `DeprecationWarning` on every access. The comment says "Temporary compatibility shim while the GUI still carries compute_full_image." This is dead code if the GUI no longer references it.
- **Fix**: `spektrafilm_gui` no longer references `full_image` or `compute_full_image`. However, `scripts/compare_simulation_revisions.py:51` and `tools/validate_profile_aware_hdr_raw_samples.py:206` still set it, and `tests/test_runtime_api.py:421-448` tests the deprecation behavior. Before removing, update those three files to stop using the property, then remove it and the now-unused `warnings` import from `params_schema.py`.
