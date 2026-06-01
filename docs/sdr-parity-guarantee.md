# SDR Parity Contract And Current Status

Last verified: 2026-05-31

This document replaces the previous unconditional "SDR Parity Guarantee" wording. The current checkout can still prove local SDR numerical stability, but it cannot honestly claim byte/path parity with current `upstream/main`.

## Current Verdict

**Current upstream byte parity is broken.**

Fresh command:

```bash
bash scripts/check-upstream-parity.sh
```

Current result:

- Compared local `HEAD` `e9022e68cfe6` against `upstream/main` `0a446004c788`.
- Merge-base is `a227823b4163`.
- `upstream/main` has 27 commits past the merge-base.
- 10 of the 15 declared core paths fail the core path check.
- 212 shared upstream data files are now inspected under the real root `src/spektrafilm/data/`.
- 29 shared data files differ locally from current `upstream/main`.

Fresh local numerical regression command:

```bash
.venv/bin/python -m pytest tests/test_upstream_parity.py -v
```

Current result:

- `13 passed`

Fresh broader validation after the parity tooling/documentation repair:

- `.venv/bin/python -m pytest --ignore=tests/gui -q`: `686 passed, 7 skipped, 1 warning`
- `.venv/bin/python -m compileall src tests scripts`: passed
- `git diff --check`: passed

This means local deterministic SDR regression checks pass, but that is not the same as parity with current upstream.

## What The Contract Means

The project now tracks two separate claims:

| Claim | Evidence | Current Status |
|---|---|---|
| Current upstream byte/path parity | `bash scripts/check-upstream-parity.sh` | **Failing** |
| Local SDR numerical stability | `.venv/bin/python -m pytest tests/test_upstream_parity.py -v` | Passing |

These claims must not be conflated. Passing the pytest suite does not prove current upstream parity. Failing the upstream parity script does not by itself prove the local runtime is numerically unstable.

## Core Path Check

The strict core path check compares the local working tree against current `upstream/main` for these paths:

| File | Current Status Against `upstream/main` |
|---|---|
| `src/spektrafilm/runtime/pipeline.py` | Differs |
| `src/spektrafilm/runtime/process.py` | Matches |
| `src/spektrafilm/runtime/params_builder.py` | Differs |
| `src/spektrafilm/runtime/params_schema.py` | Differs |
| `src/spektrafilm/runtime/stages/filming.py` | Differs |
| `src/spektrafilm/runtime/stages/printing.py` | Differs |
| `src/spektrafilm/runtime/stages/scanning.py` | Differs |
| `src/spektrafilm/runtime/services/spectral_lut_compute.py` | Differs |
| `src/spektrafilm/model/emulsion.py` | Missing in current `upstream/main` |
| `src/spektrafilm/model/density_curves.py` | Matches |
| `src/spektrafilm/model/couplers.py` | Differs |
| `src/spektrafilm/model/color_filters.py` | Matches |
| `src/spektrafilm/profiles/io.py` | Differs |
| `src/spektrafilm/profiles/__init__.py` | Matches |
| `src/spektrafilm/config.py` | Matches |

Any future claim of current upstream parity must make this table pass or must replace the baseline with an explicitly documented accepted baseline.

## Shared Data Check

The authoritative shared data root is:

```text
src/spektrafilm/data/
```

The parity script also keeps historical compatibility roots:

```text
data/
profiles/data/
```

Current script behavior:

- Discovers shared upstream data files from the upstream tree.
- Hashes each upstream blob directly from Git.
- Hashes the corresponding local working-tree file.
- Fails if a local shared data file is missing or has a different SHA-256 hash.

Current mismatches:

- `src/spektrafilm/data/filters/neutral_print_filters.json`
- All 28 current profile JSON files under `src/spektrafilm/data/profiles/`

These data mismatches are real relative to current `upstream/main`. They may be intentional local profile changes, but they are not upstream parity.

## Local SDR Numerical Regression Scope

`tests/test_upstream_parity.py` verifies local properties only:

- Deterministic output for repeated runs with stochastic/spatial effects disabled.
- Float32 and float64 input arrays remain within the documented tolerance.
- The spectral LUT produced by `SpectralLUTService` is finite, non-negative, 3-D, and `float64`.
- A local midgray golden reference remains stable within `1e-10`.
- Pipeline output dtype remains `float64` for float32 and float64 inputs.

The test is useful for local drift detection, but it is not a byte-for-byte comparison with current upstream.

## Current Additive Data Counts

Current local tree counts:

- `src/spektrafilm/data/hdr_curve_profiles/`: 162 files.
- `src/spektrafilm/data/icc/`: 173 ICC/ICM files.

These counts are descriptive only. New local files do not break upstream parity by themselves because the parity script checks shared upstream-tracked paths.

## Enforcement Commands

Use these commands before claiming SDR parity status:

```bash
bash scripts/check-upstream-parity.sh
.venv/bin/python -m pytest tests/test_upstream_parity.py -v
```

For broader release validation, also run:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m compileall src tests scripts
git diff --check
```

## Restoring A True Upstream Parity Claim

To restore a true current-upstream parity guarantee, do not weaken the checks. Instead:

1. Decide whether this branch should merge/rebase current `upstream/main` or intentionally pin an older upstream baseline.
2. Reconcile or explicitly accept each core path difference.
3. Reconcile or explicitly accept the 29 shared data hash differences.
4. Re-run `bash scripts/check-upstream-parity.sh` and require a zero exit code.
5. Re-run the local numerical regression suite.

Until those steps are complete, the honest status is: **local SDR regression checks pass, current upstream byte/path parity fails**.
