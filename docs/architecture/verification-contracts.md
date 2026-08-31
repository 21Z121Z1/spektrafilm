# Spektrafilm Verification Contracts

| Field | Value |
| --- | --- |
| Status | Canonical contract |
| Scope | Repository-wide correctness, compatibility, conformance, and performance claims |
| Verified against | `develop` at `5d14af4e3b16b1fe282126943f03ac1d74d81c19` |
| Update when | A claim class, baseline policy, backend contract, or CI evidence level changes |

This document defines what evidence is required before words such as “identical,” “parity,” “deterministic,” “conformant,” or “faster” may be used. It exists because different parts of Spektrafilm intentionally have different equivalence contracts.

## 1. Principle: every claim has a scope

A correctness statement without a scope is incomplete. At minimum identify:

- operation/path;
- input/fixture class;
- backend and dtype;
- comparison target;
- metric/tolerance or exactness rule;
- relevant environment when platform behavior matters.

Do not upgrade a narrow result into a global property. For example, a bit-identical MLX optimization on one path does not imply CPU/MLX bit identity for all stages.

## 2. Claim vocabulary

Use these terms consistently.

| Claim | Meaning | Required evidence |
| --- | --- | --- |
| **bitwise-identical** | The compared values have the same bit representation under the stated conditions. | Bit-array equality or canonical digest over both compared outputs; same dtype and clearly stated path/environment. |
| **value-identical** | Values compare exactly in the chosen representation, while irrelevant representation details may be normalized. | Exact equality after explicitly documented normalization. |
| **numerically equivalent** | Differences are bounded by a declared numeric error contract. | Named metric plus `atol`/`rtol`, ULP/error bound, or other explicit threshold over representative/contract fixtures. |
| **behavior-compatible** | Public/default observable behavior satisfies the same contract even if internals differ. | Contract/integration tests covering the observable surface and identified edge cases. |
| **deterministic** | Repeated runs under stated conditions produce the same result. | Repeated-run equality/digests with seed/environment stated as applicable. |
| **statistically equivalent** | Stochastic implementations agree on declared distribution/statistical properties, not necessarily pixel values. | Distribution/summary metrics, sample size, thresholds, and deterministic seed policy where used. |
| **upstream-conformant** | Local behavior satisfies a harness relative to a specific upstream revision and allowlist/threshold contract. | Locked upstream revision + conformance/differential harness result. |
| **no regression vs baseline** | Result matches or improves an explicitly captured baseline according to a named comparison rule. | Baseline identity (commit/artifact/digest) + current result + comparison rule. |
| **performance improvement** | A workload is measurably faster under a specified environment/methodology. | Hardware, OS/runtime/backend versions, workload, warmup/repetition/order, timing statistic, and output-correctness gate. |
| **memory/capacity result** | A workload fits/fails an explicit memory envelope. | Hardware memory, workload dimensions/path, allocator/cache policy, peak measurement method and safety threshold. |

Avoid the bare word **parity** in durable docs and PR summaries. Prefer one of the scoped terms above.

## 3. Core invariants

### 3.1 Semantic-domain invariant

The physical runtime consumes and produces linear-light RGB in named primaries around the film/print/scan model. Transport encoding and display referencing must not be silently conflated with physical light.

Evidence: runtime contract tests, stage/topology tests, color-management tests as relevant.

### 3.2 Dependency invariant

`spektrafilm` must not depend on `spektrafilm_gui` or `spektrafilm_lut_creator`. Higher layers adapt to the runtime, not vice versa.

Evidence: import/package structure review and tests/builds. A dependency-direction change is architectural and requires an explicit decision.

### 3.3 Default SDR compatibility invariant

Unless a change explicitly targets the default SDR contract, default SDR output is a protected compatibility surface.

Evidence should scale with the change:

- focused regression tests for local behavior;
- quick upstream compatibility for ordinary core work;
- full CPU upstream conformance for changes touching core model/runtime/profile/spectral paths;
- Apple/MLX no-regression when the change affects those paths or claims Apple behavior.

The exact current CI selection logic lives in `.github/workflows/sdr-upstream-conformance.yml` and is executable authority for that gate.

### 3.4 Explicit fallback invariant

If a backend does not implement a semantic operation natively, fallback behavior must be explicit, observable where useful, and tested. “GPU selected” must not imply every operation ran on GPU.

Evidence: backend/fallback tests plus relevant integration path.

### 3.5 Explicit materialization invariant

Host/device materialization that can affect memory, performance, dtype, or lifecycle must occur at deliberate boundaries rather than hidden utility conversions.

Evidence: backend-residency/materialization tests and memory instrumentation when a capacity/performance claim depends on it.

## 4. Numerical contracts are local, not universal

### 4.1 Deterministic mathematical transforms

For deterministic kernels/transforms, choose the strongest contract justified by the algorithm and actual implementation:

- use bitwise identity when preserving exact MLX graph values is a deliberate gate and both sides are proven bitwise equal;
- use numerical equivalence when backend libraries or operation ordering legitimately change rounding;
- document any exact fallback path separately.

Do not use `np.allclose(..., atol=1e-6)` as a universal substitute for thinking about the operation. The correct tolerance depends on scale, dtype, accumulated operations, and the downstream contract.

### 4.2 Float32 GPU policy

Float32 is the default GPU precision policy. A lower-precision or approximate default path is a product/architecture change, not an ordinary optimization.

A performance optimization advertised as **exactness-preserving** must not change the values covered by its declared exactness gate. Pure host scheduling/overhead changes may instead prove that the computation graph and evaluation semantics are unchanged.

### 4.3 Stochastic effects

Stochastic effects require two separate questions:

1. Is each implementation deterministic for a fixed seed and stated environment/path?
2. What is the cross-implementation equivalence contract?

For grain, current documentation already distinguishes fixed-seed deterministic execution from CPU pixel-identical parity. Therefore cross-backend validation may be statistical/distribution based unless a specific implementation/path establishes a stronger contract.

Never rewrite this into “all backends are bit-identical.”

## 5. Upstream conformance contracts

Upstream comparison is revision-relative.

A valid claim names:

- the locked upstream commit/ref;
- local commit;
- suite/mode;
- backend;
- thresholds/allowlist or exact differential rule;
- any known baseline exceptions.

The spectral differential workflow currently compares the merged spectral core against upstream revision `28bf883e1672e884307edc75852549376e13644e` and separately checks runtime midgray behavior. That is stronger and more precise than saying the entire fork “matches upstream.”

When intentionally correcting an upstream defect, preserve both facts:

- where local code matches upstream;
- where local code intentionally differs and which independent contract proves the correction.

## 6. Baselines and known failures

A baseline is an explicit comparison object, not permission to ignore a red test.

If an absolute gate has a known pre-existing failure, a no-regression mechanism may compare the current normalized report to a captured baseline. Such a mechanism must state:

- where the baseline came from;
- what normalization is allowed;
- what digest/metrics are locked;
- what event should retire the baseline.

The current macOS 26 MLX full-SDR CI follows this pattern: it allows the established normalized report digest only when absolute conformance remains in its documented pre-existing state. Any metric drift remains a regression until reviewed.

When the absolute failures are fixed, update/remove the baseline rather than preserving the old failure forever.

## 7. Evidence ladder

Use the lowest rung that can falsify the hypothesis, then climb only as required by risk and claim strength.

### E0 — Static/local contract

Examples: schema validation, pure helper behavior, serialization rules, dependency direction.

Use for: narrow changes with no runtime numerical effect.

### E1 — Focused unit tests

Examples: one model, kernel, profile validator, or parameter contract.

Use for: implementation correctness of a local semantic unit.

### E2 — Subsystem integration

Examples: filming stage end-to-end, RouteMaster projection, GUI state round trip, LUT bundle generation.

Use for: boundaries between a small number of owners.

### E3 — Differential/conformance

Examples: locked-upstream SDR suite, spectral upstream differential, CPU/backend reference comparison.

Use for: compatibility or equivalence claims.

### E4 — Platform/backend validation

Examples: macOS 26 Apple Silicon + MLX Metal smoke/full suite, container/HEIC openability validation.

Use for: claims dependent on actual platform APIs, GPU implementation, or delivery behavior.

### E5 — Full regression suite

Use for: broad core changes, refactors crossing multiple semantic domains, or final integration confidence.

### E6 — Performance/memory experiment

Use only when making a performance/capacity claim. It supplements correctness evidence; it never replaces it.

## 8. Performance evidence contract

A useful benchmark report records:

- commit/branch;
- exact hardware model and memory;
- OS, Python, MLX/CuPy/Halide versions as relevant;
- image dimensions/pixel count and route/settings;
- warm/cold state, warmup count, repetitions and statistic;
- synchronization points;
- cache/tiling/materialization policy;
- correctness digest/metric for compared variants;
- peak-memory measurement source;
- environmental caveats such as active swap or hosted-runner memory limits.

A 12 MP hot-path speedup on M1 Pro is not evidence that a 50 MP workload fits 16 GiB. An isolated FFT microbenchmark is not an end-to-end speedup until the pipeline measurement confirms it.

Rejected optimizations with strong negative evidence are worth retaining because they reduce future agent search cost. Record the reason and invalidation condition so the idea can be reconsidered only when the relevant premise changes (for example a new MLX version or larger memory envelope).

## 9. Profile/data evidence contract

Profile data are model inputs and must not be described more strongly than their evidence chain supports.

When provenance metadata is available, distinguish at least:

- original source type;
- whether the runtime field is direct/source-derived/reconstructed/inherited/generated/optimized;
- donor/derivation information;
- transformations applied;
- validation evidence that did not itself generate the field.

A manufacturer graph citation does not automatically make a processed runtime array an instrument measurement. Independent validation evidence must not be relabeled as the source that generated the array.

Until provenance work is integrated on `develop`, treat provenance-rich branches as evidence/proposals rather than silently assuming their schema is current runtime truth.

## 10. Documentation and PR claim template

For any non-trivial numerical/performance statement, write it in this form:

```text
Claim: <precise statement>
Scope: <path/backend/dtype/workload>
Reference: <CPU/upstream/baseline/previous commit>
Contract: <bitwise | metric+tolerance | statistical | behavior>
Evidence: <test/harness/run/artifact>
Environment: <only when relevant>
Known limits: <what this does not prove>
```

This format is intentionally compact. It prevents agents from spending tokens reverse-engineering what “same,” “exact,” or “faster” meant in an old report.

## 11. Changing a contract

A contract change is allowed, but it must be explicit.

When changing one:

1. state the old and new semantics;
2. identify affected product surfaces and stored states/files;
3. add migration/compatibility behavior where needed;
4. update the canonical contract/system map if the boundary changes;
5. update tests so they prove the new contract rather than weakening the old assertion until it passes;
6. record an architecture decision when the change alters a durable system invariant.

Do not hide a semantic change inside a tolerance increase, a disabled test, a baseline refresh, or a performance optimization.
