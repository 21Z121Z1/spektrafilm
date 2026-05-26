# Spektrafilm - Claude Code Instructions

## Project Overview
Spectral simulation of analog film photography. Python 3.13+, Qt GUI, GPU backends (MLX/CuPy).

## Environment
- Linux server (no macOS, no Metal, no GUI display)
- Test command: `.venv/bin/python -m pytest --ignore=tests/gui -q`
- GUI tests are skipped (no QApplication/display available)
- Python: `.venv/bin/python`
- Dependencies: `uv sync`

## Code Review Document
Read `docs/dev/code-review-2026-05-26.md` for the full review findings.

## Scope for Fixes
Fix all Critical, High, and Medium findings EXCEPT:
- **Skip M3** (GUI HEIC tests abort without QApplication) — this is a GUI-only test harness issue, skip on Linux
- **Skip Metal/macOS-specific paths** — no Metal or macOS conditions available
- **Skip H3 memory optimization** for now — that's a larger refactor, note it but don't change pipeline architecture

## Priorities (in order)
1. **C1**: HDR Rendition EXR mode — extend save_image_oiio or add save_hdr_rendition_exr helper
2. **H1**: ACEScg ICC mapping — add to _ICC_FILENAMES and _ICC_PROFILES
3. **H2**: GUI path-to-white toggle — fix profile_hdr_path_to_white_strength passthrough
4. **M1**: HDR SDR-base test expectations — reconcile tests with preserve_sdr_base=True default
5. **M2**: HDRPhotoMapping validation — extend __post_init__ for all profile-HDR fields
6. **M4**: save_image_oiio API boundary — clarify ownership, update tests
7. **L1**: README tree — remove stale spektrafilm_profile_creator reference

## Rules
- Every change MUST pass all non-GUI tests: `.venv/bin/python -m pytest --ignore=tests/gui -q`
- Do NOT modify files outside src/, tests/, docs/, README.md, pyproject.toml
- When adding validation, add corresponding tests
- Keep changes minimal and targeted — fix the specific issue, don't refactor surrounding code
- Preserve existing behavior for working code paths
- Run tests after EACH fix to ensure no regressions

## GPU Acceleration - CRITICAL CONSTRAINT
**ZERO precision/quality loss.** GPU output must be numerically identical (or within float32 epsilon) to CPU/NumPy output. This means:
- No approximations, no "close enough", no lossy optimizations
- float32 throughout (no float16 unless explicitly opted in by user)
- Same algorithms, same order of operations where possible
- Every GPU kernel MUST have a corresponding test that asserts `np.allclose(gpu_result, cpu_result, atol=1e-6)`
- If a GPU backend can't match CPU precision, fall back to CPU for that operation
- Architecture can be creative, but results must be deterministic and bit-identical across backends
