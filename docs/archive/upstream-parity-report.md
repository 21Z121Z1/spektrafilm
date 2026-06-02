# Upstream Parity Report

Generated: 2026-05-31

This report supersedes the stale 2026-05-30 report. The older report claimed the fork was strictly ahead of `upstream/main` at `a227823b4163` and that core files/data were identical. After fetching current upstream, that claim is no longer true.

## Baseline

| Item | Value |
|---|---|
| Upstream remote | `https://github.com/andreavolpato/spektrafilm` |
| Upstream branch | `main` |
| Upstream SHA | `0a446004c78853ddac00e4df4276970ca76cd062` |
| Local branch | `develop` |
| Local HEAD | `e9022e68cfe62066d7654a69c0acc6967a3fdfa9` |
| Merge-base SHA | `a227823b4163eefc658fb5346ab1a8846a4bad25` |
| Upstream commits past merge-base | 27 |
| Current parity verdict | **Failing** |

## Verification Commands Run

```bash
bash scripts/check-upstream-parity.sh
.venv/bin/python -m pytest tests/test_upstream_parity.py -v
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m compileall src tests scripts
git diff --check
```

Results:

- `scripts/check-upstream-parity.sh`: failed, as expected for the current checkout.
- `tests/test_upstream_parity.py`: `13 passed`.
- Full non-GUI suite: `686 passed, 7 skipped, 1 warning`.
- `compileall`: passed.
- `git diff --check`: passed.

## Failing Core Path Checks

The current script treats declared core paths as a hard contract. Missing upstream paths are failures, not warnings.

Failing paths:

- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/params_builder.py`
- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- `src/spektrafilm/model/emulsion.py` (missing in current `upstream/main`)
- `src/spektrafilm/model/couplers.py`
- `src/spektrafilm/profiles/io.py`

Passing paths:

- `src/spektrafilm/runtime/process.py`
- `src/spektrafilm/model/density_curves.py`
- `src/spektrafilm/model/color_filters.py`
- `src/spektrafilm/profiles/__init__.py`
- `src/spektrafilm/config.py`

## Shared Data Hash Checks

The previous script missed the real upstream data root. The script now checks:

```text
src/spektrafilm/data/
data/
profiles/data/
```

Current result:

- 212 shared upstream data files found.
- 29 local working-tree files differ from current `upstream/main`.

Current differing shared data files:

- `src/spektrafilm/data/filters/neutral_print_filters.json`
- `src/spektrafilm/data/profiles/fujifilm_c200.json`
- `src/spektrafilm/data/profiles/fujifilm_crystal_archive_typeii.json`
- `src/spektrafilm/data/profiles/fujifilm_pro_400h.json`
- `src/spektrafilm/data/profiles/fujifilm_provia_100f.json`
- `src/spektrafilm/data/profiles/fujifilm_velvia_100.json`
- `src/spektrafilm/data/profiles/fujifilm_xtra_400.json`
- `src/spektrafilm/data/profiles/kodak_2383.json`
- `src/spektrafilm/data/profiles/kodak_2393.json`
- `src/spektrafilm/data/profiles/kodak_ektachrome_100.json`
- `src/spektrafilm/data/profiles/kodak_ektacolor_edge.json`
- `src/spektrafilm/data/profiles/kodak_ektar_100.json`
- `src/spektrafilm/data/profiles/kodak_endura_premier.json`
- `src/spektrafilm/data/profiles/kodak_gold_200.json`
- `src/spektrafilm/data/profiles/kodak_kodachrome_64.json`
- `src/spektrafilm/data/profiles/kodak_portra_160.json`
- `src/spektrafilm/data/profiles/kodak_portra_400.json`
- `src/spektrafilm/data/profiles/kodak_portra_800.json`
- `src/spektrafilm/data/profiles/kodak_portra_800_push1.json`
- `src/spektrafilm/data/profiles/kodak_portra_800_push2.json`
- `src/spektrafilm/data/profiles/kodak_portra_endura.json`
- `src/spektrafilm/data/profiles/kodak_supra_endura.json`
- `src/spektrafilm/data/profiles/kodak_ultra_endura.json`
- `src/spektrafilm/data/profiles/kodak_ultramax_400.json`
- `src/spektrafilm/data/profiles/kodak_verita_200d.json`
- `src/spektrafilm/data/profiles/kodak_vision3_200t.json`
- `src/spektrafilm/data/profiles/kodak_vision3_250d.json`
- `src/spektrafilm/data/profiles/kodak_vision3_500t.json`
- `src/spektrafilm/data/profiles/kodak_vision3_50d.json`

## Interpretation

Current state is not a clean upstream parity state. The fork contains local runtime/model/profile changes and upstream has advanced. The honest claim is:

- Local deterministic SDR regression coverage passes.
- Current upstream byte/path parity fails.
- Shared data drift is now detected instead of being silently skipped.

## Required Follow-Up To Claim Full Parity

Full current-upstream parity requires one of these decisions:

1. Merge/rebase current `upstream/main`, reconcile the core/data differences, then require `scripts/check-upstream-parity.sh` to pass.
2. Pin an older upstream baseline intentionally and document that the guarantee is against that fixed baseline, not current `upstream/main`.
3. Replace the byte-parity contract with a narrower numerical-compatibility contract and state that byte parity is no longer promised.

Until one of those is completed, do not describe this checkout as SDR byte-identical to current upstream.
