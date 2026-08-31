# Spektrafilm Agent Operating Contract

Spektrafilm is a physically based reference implementation, not a collection of unrelated image effects. Work from the system model and contracts before working from file adjacency.

## Boot sequence

Read in this order, stopping when you have enough context for the task:

1. `docs/architecture/system-map.md` — stable architecture, authority boundaries, and abstraction tower.
2. `docs/PROJECT_STATE.md` — current integration snapshot, open workstreams, and branch lifecycle registry.
3. `docs/architecture/verification-contracts.md` — the exact meaning of parity, exactness, conformance, determinism, and performance claims.
4. The nearest subsystem README/design document, implementation, and tests for the change.
5. Dated reports, plans, archived audits, and non-`develop` branches only when they are relevant evidence.

Do not reconstruct the whole project from branch names, old reports, or a directory listing when the three control-plane documents above already answer the question.

## Source-of-truth precedence

When sources disagree, use this order:

1. Current executable code, tests, CI definitions, and locked data/contracts on the target commit.
2. Canonical architecture and verification-contract documents.
3. `docs/PROJECT_STATE.md` for repository/workstream state at its declared snapshot SHA.
4. Accepted architecture decisions.
5. Dated implementation reports and benchmark artifacts, valid only for the commit/environment they record.
6. Plans and research notes.
7. Archived audits and stale branches.

A report is evidence, not live configuration. A branch is an implementation carrier, not a knowledge authority.

## System model

Reason top-down through the abstraction tower defined in `docs/architecture/system-map.md`:

- purpose and product surfaces;
- semantic domains and ownership boundaries;
- named pipeline topology (`Tap`/`Node`);
- authority objects (`RuntimePhotoParams`, profiles, `RouteMaster`, backend/display policies);
- implementations and adapters;
- evidence and verification planes;
- historical decisions and experiments.

The core runtime contract remains linear-light RGB in named primaries -> film/print/scan physics -> linear-light RGB in named primaries. Transport encodings, display rendering, application UX, and LUT packaging must not leak into the physical core merely because a caller needs them.

Prefer explicit named state over hidden coupling. Named taps, sidecars, diagnostics, provenance, and policy objects are architectural assets because they make state and causality inspectable by both humans and agents.

## Before changing code

For any non-trivial change, identify four things before editing:

1. **Owner** — which architectural layer owns the behavior?
2. **Authority** — which object/file is the source of truth for the state or policy being changed?
3. **Contract** — which existing invariant may move, and which must not?
4. **Evidence** — what observation would prove the change correct at the required claim strength?

Then read the nearest implementation, adjacent tests, relevant CI gate, and any current decision/report named by those files. Do not copy a stale branch wholesale when a smaller semantic delta can be reconstructed against current `develop`.

## Change discipline

- Keep changes semantically focused, but do not preserve a bad boundary merely to minimize the diff.
- Maintain one-way package dependencies: higher-level GUI/LUT/export surfaces may depend on the runtime; the runtime must not depend upward.
- Do not introduce a second source of truth for a parameter, profile fact, route result, encoding, or backend policy.
- Do not materialize backend-resident arrays implicitly across host/device boundaries. Make residency changes explicit and test them.
- Preserve default SDR behavior unless the task explicitly changes that contract and the change is documented and validated.
- Never promote generated outputs, ad-hoc debug scripts, local logs, or temporary images into source unless they are intentional fixtures or reproducible evidence artifacts.
- Durable findings discovered on an experimental branch must be promoted to current code/tests/canonical docs or an accepted decision before that branch is considered disposable.

## Numerical and stochastic claims

There is no single repository-wide meaning of “parity.” Use the vocabulary in `docs/architecture/verification-contracts.md` and state the scope.

In particular:

- **bitwise-identical** is a strong local claim and requires bit/digest evidence for the stated path, dtype, backend, and environment;
- **numerically equivalent** requires a named metric and explicit tolerance;
- **deterministic** means repeated execution under the stated conditions is reproducible; it does not imply cross-backend bit identity;
- stochastic effects such as grain may have a deterministic same-path contract while using distribution/statistical parity across implementations;
- **upstream conformance** is relative to a locked upstream revision and harness, not a timeless equivalence claim;
- performance and memory results are valid only for the stated hardware, software versions, workload, and measurement method.

Float32 is the default GPU precision policy. Do not introduce lower precision or approximate algorithms into default paths without an explicit product decision and dedicated contract. Conversely, do not claim cross-backend bit identity where the tests only establish tolerance or statistical equivalence.

## Verification ladder

Run the cheapest evidence that can falsify the change first, then broaden in proportion to risk:

1. focused unit/contract tests;
2. subsystem integration tests;
3. relevant differential/conformance harness;
4. platform/backend gate when behavior depends on it;
5. broader pytest/full conformance for core changes;
6. benchmark/memory measurement only when making a performance or capacity claim.

Repository baseline setup:

```bash
uv sync --extra dev
uv run python -m pytest --ignore=tests/gui -q
```

Apple MLX work additionally uses:

```bash
uv sync --extra dev --extra gpu-apple
```

Use the CI workflows as executable evidence specifications. `SDR Upstream Conformance` and `Spectral upstream differential` contain stronger, path-specific gates than a generic test command.

## Repository and branch discipline

`develop` is the integration baseline. Before using another branch, consult `docs/PROJECT_STATE.md` and compare it with current `develop`.

Classify branch work as one of: active integration, active experiment, integrated/retired, historical evidence, or superseded. An old branch that is many commits ahead and behind can contain valuable evidence while still being unsafe to merge.

When a PR merges by squash or selective port, retire the source branch after any unique reports, rejected alternatives, benchmark methodology, or decision evidence worth preserving has been promoted. Do not leave branch topology to serve as the only record of what happened.

## Documentation discipline

Every durable document should make its authority obvious. Use these classes:

- **Canonical** — maintained description of the current system or contract.
- **Decision** — accepted architectural choice and rationale; supersede rather than silently rewrite history.
- **Plan** — intended future work; not evidence that the work exists.
- **Report** — observation tied to a commit/environment/date.
- **Generated** — reproducible derived material.
- **Archive** — historical context only.

Dated documents are snapshots by default unless they explicitly declare themselves canonical. Prefer updating the small canonical control plane over adding another broad “deep research” document that restates the whole repository.

## Completion standard

A change is complete when its intended contract is satisfied, the appropriate verification evidence exists, the final diff has been reread for cross-layer leakage and stale assumptions, and any durable new architectural knowledge has been promoted into the canonical map/contract/decision layer. Record skipped platform checks or unresolved risks explicitly; do not replace evidence with confidence language.
