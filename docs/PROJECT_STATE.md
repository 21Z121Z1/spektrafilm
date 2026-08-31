# Spektrafilm Project State

| Field | Value |
| --- | --- |
| Status | Current repository snapshot |
| Snapshot date | 2026-09-01 |
| Integration baseline | `develop` |
| Baseline SHA | `5d14af4e3b16b1fe282126943f03ac1d74d81c19` |
| Purpose | Fast orientation for branches, PRs, integration risk, and known evidence state |
| Update when | A workstream opens/closes/merges, a branch changes lifecycle, or `develop` materially changes the listed conclusions |

This is a **snapshot**, not timeless architecture. Always compare the target branch with current `develop` before acting if the baseline SHA above is no longer current.

## 1. Current baseline in one page

`develop` is the active integration branch.

The current baseline already contains the following recent integrations:

- PR #8 — selective integration of upstream spectral upsampling v2, keeping Hanatos 2025 as the default and preserving existing MLX/Mallett behavior;
- PR #9 — film-base tuning integrated on top of #8, with neutral defaults remaining identity;
- PR #11 — reflectance midgray exposure normalization correction plus stricter spectral differential/real-profile validation.

The current CI control surface includes:

- `SDR Upstream Conformance`: quick CPU checks on PRs, full CPU conformance for core changes, and explicit macOS 26 Apple/MLX validation when requested/labeled;
- `Spectral upstream differential`: path-scoped CPU tests, locked-upstream comparison, real-profile midgray enforcement, and macOS MLX fallback/Mallett checks.

Do not infer more than these gates prove; see `architecture/verification-contracts.md`.

## 2. Active workstreams

### PR #6 — HDR projection/route refinement

Branch: `hdr-review-implementation-20260727`

State at this snapshot: **open; diverged from current `develop` (ahead 3, behind 3)**.

Unique intent/evidence:

- dynamic tone-following chemical profiles;
- headroom-scaled path-to-white behavior;
- C1 highlight rolloff and stable extension spans;
- improved `scene_y_raw`/RouteMaster sidecar semantics;
- GUI HDR panel cleanup;
- detailed HDR film-simulation review and targeted tests.

Integration requirement:

- rebase/reconstruct the semantic delta on current `develop` after #8/#9/#11;
- resolve interactions with film-base and spectral changes explicitly;
- rerun HDR/RouteMaster/GUI tests and the relevant SDR/Apple gates;
- update canonical HDR docs only to describe behavior that actually lands.

Recommendation: **integrate this workstream before provenance/profile cache regeneration work**, because its dynamic profile-resampling design reduces coupling to stale pre-generated HDR curve data.

### PR #7 — profile provenance + MLX exactness work

Branch: `profile-provenance-mlx-exactness-20260727`

State at this snapshot: **open; diverged from current `develop` (ahead 3, behind 3)**.

This branch contains two mostly independent semantic workstreams:

1. profile provenance/evidence labeling, profile data updates, audit/digitization tooling and validation suites;
2. exactness-preserving MLX/Metal host/kernel-path optimizations and cache-budget work.

Known integration notes from the PR itself:

- `pypdf` was added to dev dependencies without refreshing `uv.lock`;
- bundled HDR curve-profile data may need regeneration after profile changes;
- the branch predates the August spectral/film-base/midgray integrations.

Recommendation: **split or reconstruct as two reviewable deltas** before landing. Provenance changes alter epistemic/data authority; MLX changes alter the compute plane. Keeping them separable improves rollback, verification selection, and future agent comprehension.

For the provenance half, preserve the branch’s strongest idea even if individual data edits change: field-level evidence must distinguish source origin from final runtime status and transformations.

For the MLX half, retain the branch report’s accepted/rejected optimization ledger so future audits do not repeat experiments whose premises have not changed.

### PR #5 — MLX performance re-audit / 50 MP capacity

Branch: `codex/mlx-performance-reaudit-20260710`

State at this snapshot: **open draft; diverged from current `develop` (ahead 1, behind 6)**.

Unique intent/evidence:

- reproducible MLX timing/memory instrumentation;
- a guarded grain fast path with exact-output evidence on the tested path;
- machine-readable benchmark results;
- explicit finding that the tested 50 MP / 16 GiB envelope still failed its safety guard.

Recommendation: keep this as an evidence-bearing draft until rebased after the newer MLX work. Do not treat the July performance numbers as the current performance baseline without rerunning the benchmark on current code and environment.

## 3. Branch lifecycle registry

The registry answers two separate questions: “is this branch mergeable?” and “does this branch still contain knowledge worth preserving?” Those are not the same.

| Branch | Relative to snapshot `develop` | Lifecycle | Meaning / next action |
| --- | --- | --- | --- |
| `develop` | baseline | **CANONICAL-INTEGRATION** | Source branch for new work; current executable truth. |
| `docs/agent-operable-system-20260901` | ahead 1 / behind 0 at initial control-plane commit | **ACTIVE-CONTROL-PLANE** | This documentation/architecture workstream. Merge only after review/CI; retire the branch after integration. |
| `hdr-review-implementation-20260727` | ahead 3 / behind 3 | **ACTIVE-REBASE** | PR #6. Reconstruct/rebase on current develop, verify, then integrate selectively. |
| `profile-provenance-mlx-exactness-20260727` | ahead 3 / behind 3 | **ACTIVE-REBASE-SPLIT** | PR #7. Preserve unique provenance/optimization evidence; split semantic workstreams before landing if practical. |
| `codex/mlx-performance-reaudit-20260710` | ahead 1 / behind 6 | **ACTIVE-DRAFT-EVIDENCE** | PR #5. Rebase/rerun before using results as current performance truth. |
| `feature/upstream-spectral-upsampling-v2` | ahead 24 / behind 3 | **INTEGRATED-RETIRED** | PR #8 was squash-merged. Historical experimental lineage; do not merge again. Safe to delete after confirming no unique evidence needs promotion. |
| `feature/upstream-film-base` | ahead 4 / behind 2 | **INTEGRATED-RETIRED** | PR #9 was squash-merged. Do not use as current implementation source. |
| `integration/upstream-film-base-final` | same head as `feature/upstream-film-base` | **DUPLICATE-RETIRED** | Duplicate branch pointer; highest-priority cleanup candidate once branch deletion is desired. |
| `fix/spectral-reflectance-midgray` | ahead 1 / behind 1 | **INTEGRATED-RETIRED** | PR #11 was squash-merged. Current behavior is on develop. |
| `ci/macos26-full-baseline` | ahead 2 / behind 3 | **TEMP-VALIDATION-RETIRED** | PR #10 closed without merge; existed to establish develop’s macOS/MLX baseline. Preserve PR/run reference, not branch as authority. |
| `audit/spectral-upstream-conformance` | ahead 26 / behind 1 | **HISTORICAL-AUDIT** | Exploratory lineage around the spectral correction/differential gate. Current merged implementation is #11/develop; preserve only unique audit rationale/tooling not already promoted. |
| `codex/mlx-float32-precision-staircase` | ahead 2 / behind 18 | **HISTORICAL-RESEARCH** | PR #3 closed without merge. Selected non-breaking ACES/OCIO changes were separately integrated via #4; stale implementation must not be ported wholesale. Mine reports/benchmarks only when relevant. |
| `runtime/mlx-memory-residency-governance-20260624` | ahead 9 / behind 20 | **SUPERSEDED-RESEARCH** | Early memory/residency design with an explicitly unverified report; later develop contains newer memory/residency work. Extract ideas only, never merge wholesale without reconstruction. |

No branches are deleted by the documentation/control-plane change that introduced this registry. Branch deletion is a separate destructive maintenance action.

## 4. Recommended integration sequence

This is a recommendation, not an immutable architecture rule.

### Step 1 — finish/rebase PR #6

Why first:

- it is a coherent HDR semantic workstream;
- it changes route authority/profile sampling behavior that affects how later profile updates should be consumed;
- dynamic resampling makes static HDR profile regeneration less central;
- landing it first reduces ambiguity for provenance/data work.

Acceptance focus:

- RouteMaster authority and crop/composition determinism;
- default SDR equivalence;
- persisted GUI compatibility;
- CPU/MLX projection contract;
- macOS/HEIC export gates where affected.

### Step 2 — decompose and rebase PR #7

Prefer two deltas:

A. provenance/profile evidence and data/tooling;

B. MLX exactness-preserving optimizations.

For A, refresh dependency lock state and regenerate/validate derived profile artifacts required by the target branch. For B, re-run exactness and M1-class memory/performance evidence on the post-#6/current baseline.

### Step 3 — re-run PR #5’s audit on the new compute baseline

The performance re-audit is most valuable after the accepted MLX implementation is stable. Then the 12 MP and 50 MP conclusions become current evidence instead of measurements of a superseded path.

### Step 4 — retire integrated/historical branch pointers

After durable knowledge has been promoted, remove duplicate/integrated branches in a dedicated maintenance action. The branch registry should then be updated in the same PR/commit.

## 5. Known baseline facts that should not be silently generalized

### macOS 26 / MLX full SDR gate

The current `SDR Upstream Conformance` workflow contains a normalized-report digest corresponding to a documented pre-existing full-MLX absolute-threshold state established by temporary PR #10. The workflow rejects any new metric drift while permitting that exact baseline.

Interpretation: **no-regression against the locked report**, not “absolute MLX conformance is universally perfect.” If the underlying absolute failures are fixed, retire/update the baseline logic.

### 50 MP / 16 GiB

PR #5 reported a failure of its 50 MP safety envelope on its July branch/environment. That is useful negative evidence, but not a permanent architecture limit. Re-measure after current memory/MLX changes before quoting it as the current capacity result.

### Profile provenance

The rich field-level provenance schema currently lives on PR #7, not snapshot `develop`. Its epistemic model is valuable, but agents must not assume its runtime schema/data edits have already landed.

## 6. Knowledge promotion checklist before retiring a branch

Before deleting or abandoning a branch, ask:

1. Did it discover a stable invariant or semantic boundary? Promote to canonical architecture/contract.
2. Did it establish a decision or reject an attractive alternative? Preserve the decision plus evidence/invalidation condition.
3. Did it add a reusable benchmark/conformance method? Land the tool/test if still valid, or preserve the report and exact reproduction instructions.
4. Did it produce only stale implementation code already represented by a merged PR? No promotion required.
5. Are its important results already captured in a merged PR discussion/run? Record the PR/run reference in this registry or a decision/report, then the branch can be disposable.

The objective is that deleting every retired branch would not erase any knowledge needed to make the next correct engineering decision.

## 7. Updating this file

When a lifecycle event occurs:

- update the baseline SHA/date;
- update only affected branch rows/workstream notes;
- remove recommendations that have become facts;
- move durable rationale to `docs/decisions/` instead of accumulating narrative here;
- avoid turning this file into a changelog.

The file should remain a compact control panel, not repository history.
