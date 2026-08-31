# 0001 — Agent-operable repository architecture

Status: Accepted
Date: 2026-09-01
Scope: repository architecture, documentation authority, branch knowledge, verification language
Supersedes: none
Superseded by: none

## Context

Spektrafilm has accumulated several forms of high-value engineering knowledge at the same time:

- a mature physical runtime with explicit topology and route authority objects;
- multiple compute backends and platform-specific validation;
- long-form architecture/research reports;
- generated audits and benchmark artifacts;
- experimental branches that contain both implementation and unique evidence;
- squash/selective integrations that make a merged branch look divergent even after its useful behavior is on `develop`.

The result is an information problem rather than a lack of technical detail. A new agent can spend substantial context reconstructing which document is current, whether a branch is still active, what “parity” meant in a report, and which object actually owns a behavior.

The previous root `AGENTS.md` also compressed several distinct numerical contracts into a universal GPU “bit-identical” expectation, while other current documentation correctly describes statistical rather than pixel-identical parity for stochastic grain. That ambiguity makes optimization and review less reliable.

## Decision

Spektrafilm will use a small repository control plane that sits above detailed implementation/research material:

1. `docs/architecture/system-map.md` defines the stable abstraction tower, semantic ownership, authority objects, and dependency/data/control/evidence planes.
2. `docs/architecture/verification-contracts.md` defines scoped evidence language instead of a single overloaded notion of parity.
3. `docs/PROJECT_STATE.md` is a high-churn snapshot of current integration state and branch lifecycle.
4. `AGENTS.md` is a short boot/operating protocol that routes agents through those documents before deep repository archaeology.
5. ADRs preserve durable rationale when a system boundary or contract changes.

Non-`develop` branches and dated reports remain valuable evidence, but they are not sources of current truth merely because they contain more detail.

Durable knowledge discovered in an experiment must be promoted into current code/tests/canonical docs or an ADR before the experiment is treated as disposable.

## Invariants

- Current executable code/tests/CI on the target commit outrank prose when they conflict.
- Stable architecture and verification vocabulary stay small enough for progressive disclosure.
- Branch lifecycle and knowledge value are tracked separately: a branch can be unsafe to merge yet still contain useful evidence.
- “Bitwise identical,” “numerically equivalent,” “deterministic,” “statistically equivalent,” “upstream conformant,” and performance/capacity claims remain distinct.
- Historical reports keep their original evidence value; they are not rewritten to masquerade as current architecture.
- One-way runtime/GUI/LUT dependency direction and explicit semantic authorities remain visible at the control-plane level.

## Consequences

Benefits:

- agents can orient from a few compact files before loading large reports/code;
- stale branch names stop functioning as an implicit knowledge database;
- rejected experiments can be retained without re-running them every session;
- verification language becomes precise enough to choose the correct test/benchmark gate;
- current state can change rapidly without rewriting stable architectural reasoning.

Costs:

- `PROJECT_STATE.md` must be updated when branch/PR lifecycle materially changes;
- architecture-affecting work may need a short ADR in addition to an implementation report;
- old documents may remain detailed but become explicitly lower authority, requiring contributors to follow the router rather than treating the longest document as the newest truth.

## Alternatives considered

### Keep using the documentation index plus Git history

Rejected as the primary control model. A flat subject index answers “where is a document?” but not “is this current?”, “what owns this behavior?”, or “what evidence class supports this claim?” Git history also cannot distinguish durable knowledge from implementation residue without re-analysis.

### Generate a complete module/file graph for every agent session

Rejected as the primary abstraction. Generated inventories are useful diagnostics, but file-level completeness consumes context while hiding semantic ownership. They remain appropriate as generated evidence, not as the first-level system model.

### Consolidate all historical reports into one giant living architecture document

Rejected. It would mix current truth, evidence, plans, and superseded rationale, create merge pressure, and make every agent pay the full historical context cost.

### Treat branches as permanent research notebooks

Rejected. Squash merges and selective ports make branch divergence misleading, branches are easy to delete, and implementation code is a poor durable index for rejected reasoning. Research can stay on branches while active, but durable findings must be promoted.

## Evidence

This decision was informed by the current `develop` runtime topology/README, runtime parameter and RouteMaster authority objects, current CI workflows, all twelve repository branches and their comparisons to `develop`, open/merged PR histories, and representative HDR/profile/MLX branch reports.

The implementation of this ADR is documentation/control-plane only; it does not change runtime behavior.

## Revisit when

Revisit if any of these premises materially change:

- the repository adopts a machine-generated architecture/branch manifest that is demonstrably more reliable and cheaper to consume than the current compact control plane;
- runtime/package boundaries are replaced by a different execution architecture;
- branch/PR state becomes automatically synchronized into canonical docs without losing semantic annotations;
- verification contracts become centrally machine-readable and the Markdown contract becomes redundant.
