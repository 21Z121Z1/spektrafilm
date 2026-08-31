# Contributing to Spektrafilm

Spektrafilm is a development fork of [andreavolpato/spektrafilm](https://github.com/andreavolpato/spektrafilm). Active integration happens on `develop`.

The repository is a physically based reference implementation. Contributions should preserve clear semantic ownership and carry evidence appropriate to the claim being made, not just pass a generic test command.

## Orient before editing

For non-trivial work, read:

1. [`docs/architecture/system-map.md`](docs/architecture/system-map.md) for the stable architecture and ownership model;
2. [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) for the current integration/branch state;
3. [`docs/architecture/verification-contracts.md`](docs/architecture/verification-contracts.md) for correctness and performance claim vocabulary;
4. the nearest implementation, tests, and subsystem documentation.

If you are using an old branch or dated report as input, first compare it with current `develop`. Branch names and report dates do not establish authority.

## Development setup

Spektrafilm requires Python 3.13. Dependencies are managed with `uv`.

```bash
git clone https://github.com/21Z121Z1/spektrafilm.git
cd spektrafilm
git checkout develop
uv sync --extra dev
```

Optional backend groups:

| Group | Command | Purpose |
| --- | --- | --- |
| `gpu-apple` | `uv sync --extra dev --extra gpu-apple` | Apple MLX/Metal backend |
| `gpu-cuda12` | `uv sync --extra dev --extra gpu-cuda12` | CUDA 12 via CuPy |
| `halide` | `uv sync --extra dev --extra halide` | Halide AOT generators/runtime support |

## Architecture discipline

Before adding a substantial feature, be able to state:

- which architectural layer owns it;
- which object/file is its source of truth;
- which semantic domains enter and leave the boundary;
- which existing invariant must remain stable;
- which test/conformance/platform/benchmark evidence will prove the intended result.

Core rules:

- `spektrafilm_gui` and `spektrafilm_lut_creator` may depend on `spektrafilm`; the runtime must not depend upward;
- keep transport/display/application concerns out of physical runtime stages unless they represent an explicitly owned runtime contract;
- avoid duplicate policy/state across GUI, runtime, exporter, and tests;
- make backend materialization/fallback/residency behavior explicit;
- prefer named taps, sidecars, diagnostics, and validated policy objects to hidden cross-module coupling;
- keep default SDR behavior stable unless the PR explicitly changes that compatibility contract.

Small diffs are desirable when they preserve a good boundary. They are not a reason to leave a new semantic concept split across multiple sources of truth.

## Tests and verification

Start with focused tests, then broaden according to the affected contract.

Baseline non-GUI suite:

```bash
uv run python -m pytest --ignore=tests/gui -q
```

GUI tests require an appropriate Qt/display environment; CI may run them under an offscreen configuration on supported lanes.

For core runtime/model/profile/spectral work, consult `.github/workflows/sdr-upstream-conformance.yml`. It defines quick and full CPU upstream-conformance behavior and the explicit Apple/MLX lane.

For spectral reconstruction/core changes, consult `.github/workflows/spectral-upstream-differential.yml`; it includes locked-upstream differential and real-profile contracts that a generic pytest run does not replace.

If a PR claims a platform-specific result, run or request the corresponding platform gate. If it claims speed or memory improvement, provide benchmark evidence in addition to correctness evidence.

## Numerical and GPU policy

Float32 is the default GPU precision policy. Do not introduce float16/lower precision or approximate default algorithms as a routine optimization.

However, the repository does **not** use one universal “GPU parity” rule. Follow [`docs/architecture/verification-contracts.md`](docs/architecture/verification-contracts.md):

- claim **bitwise identity** only when exact bit/digest comparison proves it for the named path;
- claim **numerical equivalence** with an explicit metric and tolerance;
- distinguish deterministic same-path execution from cross-backend equality;
- use statistical/distribution contracts for stochastic effects where pixel identity is not the intended cross-backend contract;
- identify CPU fallback explicitly;
- scope upstream conformance to the locked upstream revision/harness;
- attach hardware/software/workload/methodology to performance and memory claims.

Do not make a test pass by weakening the tolerance, refreshing a baseline, disabling a gate, or changing the reference until the semantic reason is understood and documented.

## Profiles and evidence

Film/paper profiles live under `src/spektrafilm/data/profiles/` and are consumed through the profile I/O/model layer.

A source citation does not imply that every final array is a direct measurement. When working on a branch that includes field-level provenance, preserve the separation between source origin, reconstructed/generated/optimized status, donor relationships, transformations, and independent validation evidence.

Until a provenance schema is integrated into the target branch, do not assume branch-only metadata is part of the current public/runtime contract.

## Pull requests

1. Branch from the current `develop` unless reconstructing a documented active workstream.
2. Target `develop`.
3. Keep one PR centered on one semantic change or one tightly coupled integration unit.
4. Describe the affected layer/authority and the protected invariant.
5. State verification results using the vocabulary in `verification-contracts.md`.
6. For performance/memory claims, include the measured environment and correctness gate.
7. Update user-facing/canonical documentation when behavior or architecture changes.
8. Update `docs/PROJECT_STATE.md` only when branch/PR lifecycle or repository-level integration state materially changes; ordinary local bug fixes do not need state-log churn.
9. Add/supersede an ADR when a durable architectural boundary or contract changes.

When porting work from a stale branch, prefer reconstructing the smallest current semantic delta over merging/cherry-picking a long divergent history blindly.

## Branch lifecycle and research artifacts

Experimental branches are temporary implementation/evidence carriers. Before retiring one, make sure durable knowledge has somewhere safer to live:

- accepted behavior -> current code/tests/canonical docs;
- durable rationale/rejected alternative -> ADR or a report referenced by an ADR;
- reusable harness -> `tests/`, `tools/`, or `benchmarks/` as appropriate;
- environment-specific measurement -> dated report/artifact;
- obsolete implementation already represented by a merged PR -> no extra preservation required.

Do not commit ad-hoc outputs, debug logs, scratch images, or one-off generated files unless they are intentional fixtures or reproducible evidence assets.

## Code style

Follow the surrounding code rather than introducing a parallel style:

- use `from __future__ import annotations` where the package already requires it;
- type public/new interfaces consistently with neighboring modules;
- document public semantics and non-obvious invariants;
- use `logging` rather than permanent `print` debugging;
- keep error/fallback behavior explicit;
- add regression tests for fixed bugs when practical.

## Completion checklist

Before requesting review:

- reread the final diff from the system boundary outward, not only file-by-file;
- confirm the intended authority has one source of truth;
- run the relevant verification ladder;
- distinguish verified, partially verified, and unverified platform claims;
- make sure docs/PR text does not overstate the evidence;
- preserve any durable new knowledge that should outlive the working branch.
