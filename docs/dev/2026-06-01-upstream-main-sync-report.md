# Upstream Main Sync Report - 2026-06-01

## Summary

- Current branch: `develop`
- Origin: `https://github.com/21Z121Z1/spektrafilm.git`
- Upstream: `https://github.com/andreavolpato/spektrafilm.git`
- Upstream target: `upstream/main` at `500bc429b7e93450ef228305c319dc03d8e185d1`
- Primary backup branch: `backup/before-upstream-sync-20260601-1804`
- Backup branch tip: `be287ac3039140a14bd25d18f78ae1cc2b67690c`
- Merge commit: `966e7c3cf7f1c0f8fead9945a306b94552e30443`
- Merge parents: `be287ac3039140a14bd25d18f78ae1cc2b67690c` and `500bc429b7e93450ef228305c319dc03d8e185d1`

No rebase, reset, force push, or broad file overwrite was used. The merge strategy was `git merge --no-ff upstream/main`.

## Ahead / Behind

- Initial audit before preserving dirty local work: `360 ahead / 31 behind` relative to `upstream/main`.
- Clean pre-merge state after preserving all local work as ordinary commits: `369 ahead / 31 behind` relative to `upstream/main`.
- Post-merge state after `966e7c3`: `370 ahead / 0 behind` relative to `upstream/main`.
- Post-merge state relative to `origin/develop`: `41 ahead / 0 behind`.

`upstream/main` and `backup/before-upstream-sync-20260601-1804` were both verified as ancestors of current `HEAD`.

## Conflict Files And Resolution Principles

- `README.md`: combined upstream package/LUT creator documentation with local HDR, GPU, and project documentation references; removed whitespace errors introduced by the upstream side.
- `pyproject.toml`: combined upstream package layout and LUT creator dependencies with local dev/OpenColorIO, Halide, MLX, CuPy, and GPU extras.
- `src/spektrafilm/model/develop.py`: kept local GPU density interpolation and development paths while adding upstream print density-curve morph support.
- `src/spektrafilm/model/diffusion.py`: kept local backend-aware blur/filter behavior and upstream-compatible function signatures.
- `src/spektrafilm/model/emulsion.py`: preserved backward-compatible imports as a shim to `model.develop` because local tests and scripts still import `model.emulsion`.
- `src/spektrafilm/runtime/params_schema.py`: kept local output clip flags and GPU/runtime settings while adding upstream input/output gamut compression specs and topology taps.
- `src/spektrafilm/runtime/pipeline.py`: preserved local SDR/default pipeline, metadata/HDR sidecars, and GPU backend selection; routed only explicit taps through upstream topology support.
- `src/spektrafilm/runtime/services/color_reference.py`: combined local backend-aware clipping/correction behavior with upstream color-science import changes.
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`: kept local backend LUT cache invalidation and added upstream input gamut compression cache keys.
- `src/spektrafilm/runtime/stages/filming.py`: preserved local HDR auto-exposure metadata and Hanatos bandpass support while using upstream `model.develop` imports.
- `src/spektrafilm/runtime/stages/printing.py`: preserved local GPU enlarger path and timing decorators while adding upstream print morph development.
- `src/spektrafilm/runtime/stages/scanning.py`: preserved local GPU XYZ->RGB, CCTF encoding, and output clip behavior; added upstream output gamut compression before final encoding/clip.
- `src/spektrafilm_gui/options.py`: kept local compute backend, GPU precision, and HDR mapping enums; added upstream input/output gamut compression enums.
- `src/spektrafilm_gui/state.py`: kept local color-management runtime/saving separation and HDR mapping fields; added upstream output gamut compression state.
- `src/spektrafilm_gui/widget_specs.py`: kept local HDR/GPU widgets; added upstream output gamut compression widgets.
- `tests/gui/test_params_mapper.py`: combined local ACES workflow imports/tests with upstream input gamut compression tests.
- `tests/test_filming_stage.py`: preserved local bandpass and input encoding tests; added upstream linear sensitivity test.
- Binary baseline conflicts under `tests/baselines/*.npz`: retained local pre-merge versions to avoid mechanically changing existing SDR/film/print regression behavior. Regeneration should only happen through an intentional baseline update after runtime tests pass.

## Validation

Successful checks:

- `/usr/bin/git status`: clean after merge commit.
- `/usr/bin/git diff --check`: pass.
- `/usr/bin/git diff --cached --check`: pass before merge commit.
- `/usr/bin/grep -R -n '^<<<<<<<' README.md pyproject.toml src tests`: no conflict markers.
- `/usr/bin/grep -R -n '^=======$' README.md pyproject.toml src tests`: no conflict separators.
- `/usr/bin/grep -R -n '^>>>>>>>' README.md pyproject.toml src tests`: no conflict markers.
- `/usr/bin/python3 -m py_compile ...`: passed for the hand-merged runtime, GUI mapper, model, and targeted test files.
- `/usr/bin/git merge-base --is-ancestor upstream/main HEAD`: pass.
- `/usr/bin/git merge-base --is-ancestor backup/before-upstream-sync-20260601-1804 HEAD`: pass.

Blocked checks:

- `.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests` was terminated after it hung with no output.
- `.venv/bin/python -m pytest -q tests/test_filming_stage.py ...` was terminated after it hung with no output.
- A single-process probe, `PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -c 'import numpy; print(numpy.__version__)'`, hung for more than 60 seconds and was terminated.

The pytest/compileall blockage is classified as a local Python/numpy dynamic library loading issue, not as a code regression. The system Python syntax pass was used as substitute static evidence, but it cannot replace the project pytest suite.

## Push Recommendation

Push is recommended after one successful project-environment pytest run on a machine/session where `.venv` can import numpy normally.

Use a normal non-force push only:

```bash
git push origin develop
```

Do not force push.
