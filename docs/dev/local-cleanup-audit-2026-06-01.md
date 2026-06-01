# Local Cleanup Audit - 2026-06-01

Scope: `/Users/retriedstormtrooper/Documents/spektrafilm-main`

This audit separates already-removed rebuildable caches from remaining items that
need a manual decision. It intentionally does not recommend deleting tracked
source files, tracked validation samples, or local IDE/agent state without an
explicit reason.

## Completed cleanup

The workspace size went from roughly `2.9G` to `2.3G` after removing ignored,
rebuildable cache/build outputs. `du` is rounded, so the practical recovery is
about `600M`.

Removed:

| Path | Why it was safe to remove |
| --- | --- |
| `build/` | Local Halide/test build output. |
| `android/.gradle/` | Gradle cache for this checkout. |
| `android/app/build/` | Android app build intermediates and merged assets. |
| `android/app/.cxx/` | Android external native/CMake intermediates. |
| `macos/SpektrafilmMac/DerivedData/` | Xcode derived data. |
| `macos/SpektrafilmMac/.build/` | SwiftPM build products. |
| `macos/SpektrafilmMac/dist/` | Local macOS distribution output. |
| `.pytest_cache/` | Pytest run cache. |
| `spektrafilm.egg-info/`, `src/spektrafilm.egg-info/` | Editable/install metadata. |
| `__pycache__/` directories | Python bytecode caches, including inside `.venv`. |
| `.DS_Store` files | Finder metadata. |
| `.matplotlib/fontlist-v390.json` from Git tracking | Machine-local Matplotlib font cache. The file is preserved locally when regenerated and `.matplotlib/` is now ignored. |

## Remaining manual cleanup candidates

| Priority | Path | Size | Current status | Recommendation |
| --- | ---: | ---: | --- | --- |
| High | `.venv/` | `2.1G` | Ignored local Python environment | Delete only when you are ready to recreate dependencies. Baseline command is `uv sync`; add optional extras such as `--extra dev`, `--extra halide`, or `--extra gpu-apple` as needed for the workflow. |
| Medium | `.venv/lib/python3.13/site-packages/colour/htmlcov/` | `75M` | Third-party package coverage HTML inside `.venv` | Safe space win if keeping `.venv`; it can come back on dependency reinstall. |
| Low | `docs/dev/autonomous-loop.log` | `32K` | Ignored local log | Delete if no longer needed for session history. |
| Low | `artifacts/`, `debug/` | `0B` | Ignored empty output dirs | Remove with `rmdir artifacts debug` if you want a quieter root. |
| Review | `.claude/`, `.codex/` | `48K`, `4K` | Ignored local agent state | Keep unless you are intentionally dropping local agent/session config. |
| Review | `android/local.properties` | `4K` | Ignored Android SDK path/config | Keep if Android builds still need local SDK configuration. |
| Review | `macos/SpektrafilmMac/Config/` | `4K` | Ignored local app config | Inspect before deleting; may be needed by the macOS app workspace. |
| Review | `macos/SpektrafilmMac/SpektrafilmMac.xcodeproj/` | `28K` | Ignored Xcode project metadata | Inspect before deleting; generated or local IDE project state may still be useful. |

Manual commands, if you choose to proceed:

```bash
# Largest reclaim, but requires dependency reinstall later.
rm -rf .venv
uv sync

# Smaller cleanup while keeping the virtualenv.
rm -rf .venv/lib/python3.13/site-packages/colour/htmlcov
rm -f docs/dev/autonomous-loop.log
rmdir artifacts debug 2>/dev/null
```

## Do not delete as local cleanup

These look cache-like or bulky, but are tracked or project-relevant:

| Path | Size | Reason to keep |
| --- | ---: | --- |
| `scratch/IMG_9121_converted.DNG` | `9.4M` | Tracked validation/sample artifact. |
| `output.heic` | `4K` | Tracked output/sample artifact. |
| `docs/dev/benchmark-artifacts/` | `476K` | Tracked benchmark evidence. |
| `android/app/src/main/assets/profiles/hanatos2025_lut.bin` | `11M` | Tracked Android runtime asset. |
| `src/spektrafilm/data/luts/spectral_upsampling/*` | `~10M` | Tracked simulation data. |
| `img/` | `18M` | Tracked README/test image assets. |
| `.git/` | `155M` | Repository history and object database. Do not delete; use Git maintenance only if needed. |

## Current ignored items after cleanup

The remaining ignored paths are expected local state:

```text
.claude/
.codex/
.matplotlib/
.venv/
android/local.properties
docs/dev/autonomous-loop.log
macos/SpektrafilmMac/Config/
macos/SpektrafilmMac/SpektrafilmMac.xcodeproj/
```

If those paths are no longer needed, remove them manually after confirming the
tradeoff above.
