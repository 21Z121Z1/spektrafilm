# Spektrafilm System Map

| Field | Value |
| --- | --- |
| Status | Canonical architecture |
| Scope | Repository-wide |
| Authority | Stable system boundaries and vocabulary |
| Verified against | `develop` at `5d14af4e3b16b1fe282126943f03ac1d74d81c19` |
| Update when | Package direction, semantic domains, authority objects, route/tap semantics, or verification architecture changes |

This document is the shortest durable answer to “what system am I controlling?” It intentionally describes stable abstractions rather than every module. Implementation details belong in subsystem docs and code; current branch/workstream state belongs in `../PROJECT_STATE.md`.

## 1. Design thesis

Spektrafilm is a reference simulator whose central job is to preserve and expose the causal chain from scene-referred light through photographic materials to a rendered result.

The repository should therefore optimize for five properties:

1. **Semantic locality** — every transformation has one conceptual owner.
2. **Explicit authority** — parameters, physical data, route results, display policy, and compute policy each have a recognizable source of truth.
3. **Inspectable state transitions** — important boundaries are named rather than hidden inside call stacks.
4. **One-way dependencies** — higher-level products consume lower-level semantics without pushing application concerns into the physical core.
5. **Evidence-bearing evolution** — changes carry tests, differential evidence, or measurements appropriate to the claim being made.

For an agent, this means the correct unit of reasoning is not “a file” but **an authority crossing a semantic boundary under a contract**.

## 2. The abstraction tower

Read the project from top to bottom. Descend only as far as the task requires.

| Level | Question | Stable abstraction | Primary anchors |
| --- | --- | --- | --- |
| L0 Purpose | What must the project preserve? | Physically grounded film/print/scan reference behavior with inspectable evidence | root `README.md`, this document |
| L1 Product surfaces | Who consumes the system? | Runtime API, desktop GUI, LUT creator, export/integration tooling | `src/spektrafilm/`, `src/spektrafilm_gui/`, `src/spektrafilm_lut_creator/` |
| L2 Semantic domains | What kind of meaning is being transformed? | scene-linear RGB, spectral exposure, density, print/scan result, display/export representation | runtime stages, color/HDR modules |
| L3 Execution topology | In what order can state move? | named `Tap`s connected by `Node`s | `runtime/topology.py`, `runtime/pipeline.py` |
| L4 Authority objects | Which values govern or summarize a run? | `RuntimePhotoParams`, `Profile`/`ProfileData`, `RouteMaster`, explicit backend/materialization/display policies | `runtime/params_schema.py`, `profiles/io.py`, `runtime/route_master.py` |
| L5 Implementations | How is each transform executed? | model/stage/service code plus NumPy/MLX/CuPy/Halide and app adapters | `model/`, `runtime/stages/`, `runtime/services/`, `gpu/`, `halide/`, GUI/LUT packages |
| L6 Evidence | How do we know a claim is true? | unit contracts, conformance, differential tests, backend/platform gates, benchmark artifacts | `tests/`, `tools/`, `.github/workflows/`, `benchmarks/` |
| L7 Knowledge history | Why did the system become this way? | decisions, reports, plans, branch/PR history, archives | `docs/decisions/`, reports/plans, `PROJECT_STATE.md` |

The tower is deliberately asymmetric: lower levels may be complex, but higher levels must stay small. A new agent should be able to understand L0-L4 without loading L5-L7 in full.

## 3. Product and dependency layer

The repository exposes three main Python packages. The allowed high-level dependency graph is:

```text
spektrafilm_gui ───────────────> spektrafilm
       |
       | allowed when GUI needs LUT/export registries or helpers
       v
spektrafilm_lut_creator ───────> spektrafilm

spektrafilm ──X──> spektrafilm_gui
spektrafilm ──X──> spektrafilm_lut_creator
```

`spektrafilm` is the physical runtime core. It must not import from the GUI or LUT creator. The LUT creator is also above the runtime. The GUI may consume either lower-level package where that serves its application responsibilities; neither lower-level package may depend on the GUI.

The GUI owns interactive state/presentation. The LUT creator owns sampling, transport/shaper registries, bundle/formats, and integration packaging. A caller may add transport encoding or display behavior around the runtime; those concerns do not become runtime physics simply because they are needed for delivery.

The practical rule is:

> Put a concept at the lowest layer that fully owns its semantics, but no lower.

Examples:

- film exposure, density formation, couplers, grain, halation: runtime/model domain;
- UI widgets and persisted presentation choices: GUI domain;
- `.cube`/`.3dl`/Hald bundle structure and target/color-space registries: LUT-creator domain;
- PQ/HLG/gain-map/container policy: display/export domain unless a physical quantity is explicitly being produced by the runtime;
- backend scheduling/residency: compute plane, not film semantics.

Package-local contracts are documented in `src/spektrafilm/README.md`, `src/spektrafilm_gui/README.md`, and `src/spektrafilm_lut_creator/README.md`.

## 4. Physical data plane

The core runtime contract is:

```text
linear-light RGB in named primaries
        |
        v
   film / print / scan physics
        |
        v
linear-light RGB in named primaries
```

The named primaries tell the runtime how RGB relates to physical/colorimetric space. Transfer encodings are caller concerns except for the limited convenience flags already documented in `src/spektrafilm/README.md`.

The main semantic progression is:

```text
RGB scene light
  -> spectral reconstruction / film exposure
  -> log exposure at film
  -> developed film CMY density
  -> enlarger / print exposure
  -> print CMY density
  -> scan / colorimetric reconstruction
  -> linear RGB result
```

These domains are not interchangeable. A value that is correct as scene-linear luminance is not automatically a valid display-relative brightness; a CMY density is not an RGB color; a transport-coded value is not physical light.

### Named topology boundaries

`runtime/topology.py` makes the important runtime boundaries first-class:

```text
rgb_in
  -> rgb_pre
  -> log_e_film
  -> cmy_film
  -> log_e_print
  -> cmy_print
  -> rgb_out
```

A `Node` declares the taps it reads and writes. `run_topology` executes nodes whose dependencies are available and stops at the requested collection tap.

For agent reasoning, taps are semantic coordinates. Use them to ask “where did this value change?” before reading a large pipeline function. A feature that needs a new stable intermediate representation should prefer a named boundary or explicit sidecar over a hidden tuple element or duplicated recomputation.

## 5. Control and authority plane

The data plane describes what flows. The control plane describes what is allowed to govern that flow.

### 5.1 Runtime parameters

`RuntimePhotoParams` is the top-level runtime configuration authority. It groups:

- film and print `Profile`s;
- film/print rendering controls;
- camera, enlarger, scanner controls;
- I/O/color-space controls;
- debug/tap controls;
- settings for spectral reconstruction, compute backend, precision, materialization, sidecars, memory budgets, tiling, and validation.

Higher-level applications may map their state into this object, but they should not create a parallel hidden runtime policy.

### 5.2 Profiles

`Profile`/`ProfileData` are physical-model input authorities. They contain sensitometric/spectral model data and associated metadata. Treat profile values as model evidence, not arbitrary UI presets.

When provenance metadata exists, preserve the distinction between direct source evidence, reconstructed/generated values, and optimized/model-derived values. A citation is not by itself proof that a runtime array is a direct measurement.

### 5.3 RouteMaster

`RouteMaster` is an explicit authority bundle for route-aware HDR/display projection. It brings together the route’s linear result and the side information needed to derive display behavior without silently re-running or guessing physical stages.

Current fields distinguish, among other things:

- route kind and HDR mode;
- route-linear RGB/luminance (and optional XYZ/density);
- legacy SDR result;
- scene-side energy sidecars such as `scene_y_raw` and `post_halation_y`;
- optional derived look/detail state;
- diagnostics.

This pattern is important beyond HDR: when a higher layer needs both a rendered result and physically meaningful intermediate evidence, prefer an explicit authority object over reading implementation internals.

### 5.4 Policy objects and settings

Compute backend, precision, materialization, memory budget, tiling, resize fallback, color-management and display/export choices are policies. Policies should be:

- explicit;
- validated at construction/boundary time;
- observable through diagnostics where they affect execution;
- kept separate from physical parameters when they do not change the intended physical model.

## 6. Four interacting planes

Most cross-cutting bugs become easier to diagnose if the system is decomposed into four planes.

### A. Physical/data plane

What the image *means*: scene light, spectra, exposures, densities, scan/colorimetric values.

Owners: `runtime/stages/`, `model/`, spectral utilities/services, profiles.

### B. Control/authority plane

What configuration or state *governs* the run: runtime parameters, profiles, route authority, color/display/export policy.

Owners: parameter schema/builders, profile I/O, route/display/export contracts, GUI/LUT adapters at their boundaries.

### C. Compute/execution plane

*How* the same intended transform is scheduled or represented: CPU/NumPy, MLX/Metal, CuPy/CUDA, Halide, residency, tiling, caching, materialization.

Owners: `gpu/`, `halide/`, backend-facing services and policies.

A compute optimization must not silently become a new physical model. If it changes numerical semantics, its claim and contract must say so explicitly.

### D. Evidence/observability plane

How the system exposes causality and proves behavior: taps, diagnostics, timings, conformance reports, fixed fixtures, output digests, platform probes, memory/benchmark instrumentation.

Owners: `tests/`, `tools/`, `benchmarks/`, CI, plus diagnostics emitted by runtime components.

Observability is not disposable debugging code when it is the only way to verify a production contract.

## 7. SDR and HDR as views over one physical system

Default SDR behavior is a protected compatibility surface. The physical pipeline produces its route result; SDR encoding/display choices are applied according to the current caller/runtime boundary.

HDR must not be conceptualized as an unrelated second simulator. The existing architecture uses physically meaningful route/scene side information so that display projection can preserve a chosen photographic look while recovering or extending information from an appropriate authority.

The key separation is:

```text
physical pipeline
    |
    +--> route result / legacy SDR look
    |
    +--> explicit scene/material sidecars
               |
               v
          RouteMaster
               |
               v
        HDR/display projection
               |
               v
       delivery/export encoding
```

This keeps “what the material simulation produced” separate from “how a target display/container should present it.” Changes to open HDR workstreams may refine the projection semantics, but they should preserve this separation unless an explicit architecture decision supersedes it.

## 8. Compute backends are interchangeable only at declared contracts

NumPy, MLX, CuPy, and Halide are implementations of selected transforms, not globally interchangeable bit machines.

For each backend path, declare the required contract:

- exact bits/digest;
- numerical tolerance;
- deterministic same-path behavior;
- statistical/distribution equivalence for stochastic effects;
- explicit CPU fallback;
- or “not supported.”

The required vocabulary and evidence are defined in `verification-contracts.md`.

Host/device residency is part of the execution contract. An apparently harmless conversion can dominate memory or wall time at full resolution. Therefore materialization boundaries and cache/tiling policies are architecture-relevant even though they are not photographic physics.

## 9. Evidence architecture

Evidence should form a directed chain from a claim back to a reproducible observation.

```text
claim
  -> contract + scope
  -> test/harness/benchmark
  -> fixture + locked inputs
  -> commit + environment
  -> result/artifact
```

Different claims require different evidence. A unit test does not prove 50 MP memory capacity; a benchmark does not prove upstream semantic conformance; an output hash on MLX does not prove NumPy/MLX bit identity unless both outputs were actually compared under a stated contract.

The CI workflows are executable specifications:

- `SDR Upstream Conformance` supplies quick validation, core full CPU conformance, and opt-in/label-triggered macOS 26 Apple/MLX validation;
- `Spectral upstream differential` supplies path-scoped CPU contracts, comparison against a locked upstream revision, real-profile midgray checks, and Apple MLX/fallback validation.

Do not generalize beyond what a gate measures.

## 10. Knowledge architecture

The repository contains valuable long-form research, but agents should not need to reread it to recover current truth.

Use these information classes:

```text
Canonical architecture/contracts  -> mutable current truth
Project state                     -> mutable current repository snapshot
Decision records                  -> durable rationale, superseded explicitly
Reports                           -> immutable-ish evidence snapshots
Plans                             -> proposed future work
Generated material                -> reproducible derived evidence/docs
Archive / stale branches          -> historical context
```

The promotion rule is:

> When an experiment discovers durable knowledge, move the knowledge upward before the experiment disappears.

Examples of durable knowledge worth promoting:

- an invariant or new semantic boundary -> canonical architecture/contract;
- a rejected optimization and why it fails -> decision record or scoped report referenced by one;
- a new accepted workstream/lifecycle state -> `PROJECT_STATE.md`;
- a measured performance number -> dated report with commit/environment, not the system map;
- an implementation detail with no cross-task value -> code/test only.

## 11. Extension protocol

Any substantial new capability should be explainable with six fields before implementation:

1. **Layer** — which level/plane owns it?
2. **Authority** — where is its source of truth?
3. **Inputs/outputs** — which semantic domains cross the boundary?
4. **Invariant** — what existing behavior must remain stable?
5. **Evidence contract** — what proves correctness, compatibility, and (if claimed) performance?
6. **Lifecycle** — what docs/branch/decision state must be updated when it lands?

If those fields cannot be answered without describing many unrelated modules, the proposed boundary is probably too diffuse.

### Good extension shape

```text
one new semantic concept
  -> one clear authority
  -> one or a small number of explicit boundaries
  -> adapters at higher/lower layers
  -> focused tests + one integration proof
  -> optional platform/performance evidence
```

### Warning signs

- the same enum/threshold is independently copied into runtime, GUI, exporter, and tests;
- backend code decides photographic intent;
- GUI persistence becomes the only place a runtime behavior is defined;
- a report contains the only explanation of a production invariant;
- a branch contains the only copy of a useful benchmark method or rejected decision;
- a performance claim omits hardware/software/workload;
- “parity” appears without a metric/scope;
- a caller must know private stage internals to obtain a supported result.

## 12. Agent navigation by question

Use the smallest path that answers the task:

| Question | Start here | Then |
| --- | --- | --- |
| What is current/in flight? | `../PROJECT_STATE.md` | PR/branch diff, current tests |
| Where should a feature live? | this system map | nearest package README + imports |
| Why did a design choice exist? | `../decisions/README.md` | linked report/PR if needed |
| Can I claim parity/exactness? | `verification-contracts.md` | relevant test/CI implementation |
| Why did output change? | topology taps + authority object | stage/service/model tests |
| Why is MLX slow/large? | compute plane + residency policy | GPU modules + dated benchmark reports |
| Is an old branch useful? | `../PROJECT_STATE.md` | compare with `develop`, then branch reports/tests |
| Is a report still current? | its status/date/commit + source-of-truth precedence | current code/tests/contracts |

The goal is progressive disclosure: a well-oriented agent should read tens of lines before thousands, while still having a precise path to every deeper fact it needs.
