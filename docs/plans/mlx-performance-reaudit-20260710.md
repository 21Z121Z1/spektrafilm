# MLX Performance Reaudit 2026-07-10 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use focused parallel review for the four ownership domains below, then keep all implementation in the controlling session so benchmark baselines, candidate prototypes, and report claims share one source of truth.

**Goal:** Reassess the complete MLX execution and memory lifecycle on the latest `origin/develop`, produce reproducible profiling and a 50MP/16GiB verdict, rank only lossless opportunities, and conditionally land a minimal production optimization only if it clears the user's amended 100%-confidence gate.

**Architecture:** Work from one immutable baseline commit in an isolated branch. Four mutually exclusive review domains produce bounded findings under `/tmp/spektrafilm-mlx-audit/`; the controller reconciles them, implements standalone benchmark/profiling support and benchmark-local prototypes, runs every scenario in a fresh subprocess when peak memory matters, and promotes only a fully measured, exact-output prototype to a minimal production seam before writing one Markdown report plus one machine-readable JSON result.

**Tech stack:** Python 3.13, MLX 0.31.2/Metal, NumPy 2.4.4, rawpy 0.26.1, psutil 7.2.2, pytest 9.0.3, macOS `vm_stat`/`memory_pressure`/`ps`/`footprint` where available.

## Global Constraints

- Baseline is `origin/develop` at `bc9c4972f82712960f5dd27f74d705a52ca6f799`; all comparisons use this commit, the same input, and the same parameters.
- Preserve every SDR, HDR, film, paper, scan, ACES/OCIO, color-management, grain, gain-map, border, and random-distribution semantic.
- Do not use float16, lower resolution, fewer spectral samples, smaller LUTs, lower convolution/grain/gain-map quality, reduced computation, changed RNG semantics, or relaxed precision contracts.
- Default audit scope does not modify production algorithms or defaults. User amendment on 2026-07-11 conditionally permits a minimal production optimization when same-input simulation-to-output/encoder evidence proves a real win, every existing precision/effect/random/boundary contract passes, mixed/edge paths do not gain a device sync or material regression, memory does not regress, and an adversarial review leaves the controller at 100% confidence. The overall 50MP verdict remains an independent hard gate; if the current pipeline cannot reach a size-independent local seam at 50MP, a mathematically proven local optimization may still land, but it cannot be credited with a 50MP pass or called RAW end-to-end. Anything below that local gate remains benchmark-only.
- A performance sample is complete only after explicit MLX evaluation/synchronization and any required final host or encoder boundary.
- Report MLX active, peak, and cache memory separately from RSS and physical footprint; never add overlapping counters.
- Do not clear cache inside a timed production path or use cleanup to hide its real high-water mark. Record cleanup policy and cold/hot state.
- The 50MP target is 8160 × 6120 (49,939,200 pixels) when no legal real 50MP RAW exists. The repository’s 4032 × 3024 DNG is a real 12.2MP decode probe, not a 50MP RAW claim.
- PASS requires all required paths, no OOM/kill/exceptional fallback/quality reduction, physical footprint at or below 12GiB, no critical memory pressure or sustained swap thrashing, and existing equivalence contracts. CONDITIONAL is 12–13GiB or pressure/swap/manual budget dependence. FAIL is over 13GiB, OOM/kill/incompletion, or quality reduction.
- The original dirty `develop` worktree is out of scope and must remain untouched.

## File Structure

- Create `benchmarks/benchmark_mlx_performance_reaudit.py`: isolated scenario runner, deterministic input generator, raw-decode probe, memory sampler, cold/hot timing, boundary counters, parity digest, JSON emission, and benchmark-local candidate hooks.
- Create `tests/test_mlx_performance_reaudit_benchmark.py`: schema, deterministic input, memory-counter semantics, subprocess failure preservation, scenario matrix, and report-verdict tests.
- Create `docs/reports/mlx-performance-reaudit-20260710.json`: exact environment, commands, samples, findings, verdict, and limitations.
- Create `docs/reports/mlx-performance-reaudit-20260710.md`: human audit and prioritized recommendations.
- Do not edit any `src/` file unless a benchmark-local prototype crosses the 100%-confidence production gate. Conditional implementation ownership is limited to the proven candidate's exact production seam plus its focused regression tests: `src/spektrafilm/gpu/mlx_backend.py`/`tests/test_gpu_backend.py` for stable compile caching; `src/spektrafilm/runtime/stages/filming.py`/spatial parity tests for fused tiling; `src/spektrafilm/hdr/projection.py`/HDR projection tests for exact percentile selection; or `src/spektrafilm/gpu/kernels/grain.py`, `src/spektrafilm/model/grain.py`, and `tests/test_grain.py` for a caller-proven Poisson branch.

---

### Task 1: Freeze Baseline, Environment, and Coverage

**Files:**
- Create: `/tmp/spektrafilm-mlx-audit/shared-context.md`
- Create: `/tmp/spektrafilm-mlx-audit/coverage-manifest.md`
- Create: `docs/plans/mlx-performance-reaudit-20260710.md`

- [ ] Record branch, HEAD, remotes, dirty state, macOS/hardware/unified memory, Python/MLX/NumPy/rawpy/psutil versions, MLX memory APIs, and the real RAW inventory.
- [ ] Read all mandatory historical reports and record which ideas are already addressed, rejected, or conditional.
- [ ] Assign every file under `src/spektrafilm/gpu/`, `src/spektrafilm/runtime/`, and `src/spektrafilm/hdr/`, plus relevant input/color/export files, to exactly one reviewer.
- [ ] Verify the original worktree diff is unchanged and the audit worktree contains no unplanned file changes.

### Task 2: Run Four Bounded Reviews

**Files:**
- Create: `/tmp/spektrafilm-mlx-audit/runtime-memory.md`
- Create: `/tmp/spektrafilm-mlx-audit/spectral-color-hdr.md`
- Create: `/tmp/spektrafilm-mlx-audit/spatial-metal.md`
- Create: `/tmp/spektrafilm-mlx-audit/validation.md`

- [ ] Dispatch three isolated-context subagents for runtime/memory, spectral/color/HDR, and spatial/Metal; the controller occupies the fourth validation seat because the environment supports four active agents total and exposes no model-selection control.
- [ ] Enforce the shared finding row: `ID | 代码位置 | 当前成本 | 优化假设 | 收益证据 | 内存影响 | 等效性风险 | 验证方法 | 结论`.
- [ ] Limit each output to ten effective findings and about 1200 tokens, with conclusions restricted to `measured-win`, `promising`, `needs-evidence`, `already-addressed`, `not-worthwhile`, or `unsafe`.
- [ ] Validate the coverage manifest after review and directly inspect any unclaimed or conflicting path.

### Task 3: Specify the Reaudit Harness with Failing Tests

**Files:**
- Create: `tests/test_mlx_performance_reaudit_benchmark.py`
- Create: `benchmarks/benchmark_mlx_performance_reaudit.py`

- [ ] Write a failing import/schema test requiring an audit JSON envelope with `schema_version`, `head_sha`, `environment`, `input`, `scenarios`, `memory`, `parity`, `findings`, `verdict`, and `limitations`.
- [ ] Run `.venv/bin/python -m pytest tests/test_mlx_performance_reaudit_benchmark.py -q` and confirm failure is caused by the absent harness.
- [ ] Write failing tests for deterministic 8160 × 6120 input construction without upscaling, exact required scenario names, cold/hot sample separation, median/min/max aggregation, and explicit lazy-evaluation synchronization.
- [ ] Write failing tests proving MLX active/cache/RSS/physical-footprint fields remain separate, subprocess OOM/kill/error results are preserved, missing `footprint` is explicit, and swap/pressure snapshots are not fabricated.
- [ ] Write failing tests for RAW decode accounting: source dimensions, raw mosaic bytes, postprocess RGB bytes, decoder wall time/RSS delta, overlap assumptions, and an explicit `real_50mp_raw=false` marker for the 12.2MP sample.

### Task 4: Implement the Minimal Standalone Harness

**Files:**
- Create: `benchmarks/benchmark_mlx_performance_reaudit.py`
- Test: `tests/test_mlx_performance_reaudit_benchmark.py`

- [ ] Implement only enough pure helpers to satisfy the schema, deterministic-input, aggregation, and verdict tests.
- [ ] Add a parent/child CLI: the parent launches one scenario per process and samples RSS, physical footprint when available, swap, memory pressure, and exit status; the child records MLX active/peak/cache, residency operations, full-frame materializations, timings, and parity digests.
- [ ] Make the deterministic full-size image directly at 8160 × 6120 using reproducible row/chunk generation; never resize a smaller image and never persist the full array in the repository.
- [ ] Add scenarios for `scan-only`, `film-paper`, `film-paper-spatial-grain`, `hdr-light-table`, `hdr-paper`, `preprocess-resize`, `save-boundary`, and `hdr-export-boundary`, with unsupported boundaries reported rather than silently omitted.
- [ ] Add a separate real 12.2MP DNG decode probe and conservative 50MP decoder/demosaic overlap accounting; do not label this a real 50MP RAW execution.
- [ ] Add benchmark-local hooks only for candidates selected after review. They may call existing public/private functions but cannot patch or alter production defaults.
- [ ] Run the focused test and retain the red/green evidence in the final report.

### Task 5: Benchmark Baseline and Highest-Value Candidates

**Files:**
- Create: `docs/reports/mlx-performance-reaudit-20260710.json`

- [ ] First run small smoke scenarios to validate synchronization, counters, JSON integrity, and subprocess failure handling.
- [ ] Run current microbenchmarks for tile assembly, fused spectral paths, LUT/Metal kernels, residency, and runtime hot path only where they answer a live hypothesis.
- [ ] Select at most three candidate prototypes by expected end-to-end value, memory leverage, equivalence risk, and implementation complexity.
- [ ] Compare baseline and candidate with the same HEAD/input/parameters. Report cold start, hot median, min/max, explicit kernel/micro time, simulation-to-array time, export boundary time, input generation, child-process wall time, and RAW decode separately; never label a timer that excludes RAW/input as RAW end-to-end.
- [ ] Require exact or existing-contract parity, including grain seed/distribution semantics, border behavior, HDR/gain-map semantics, and float32 policy; otherwise classify the candidate `unsafe` or `needs-evidence`.
- [ ] Run required 50MP paths one per fresh subprocess. Preserve OOM, system kill, timeout, fallback, memory-pressure, and swap evidence exactly.

### Task 6: Reconcile Findings and Write Reports

**Files:**
- Create: `docs/reports/mlx-performance-reaudit-20260710.md`
- Create: `docs/reports/mlx-performance-reaudit-20260710.json`

- [ ] Merge duplicate findings, inspect code for disputed claims, and use benchmark evidence to resolve conflicts.
- [ ] Draw the current end-to-end MLX execution graph and list all covered files by owner.
- [ ] Report primary timings, memory counters, peak simultaneously-live objects, host materializations, decoder/encoder buffers, and cold/hot conditions.
- [ ] Assign an honest 50MP/16GiB PASS, CONDITIONAL, or FAIL. If the environment cannot execute a path, state that and use static lifecycle estimates without claiming a pass.
- [ ] Rank candidates P0/P1/P2/Reject and identify exactly three best next implementations. Every P0 must have code location, reproducible evidence, memory effect, precision/effect risk, complexity, and tests.
- [ ] Include commands, environment, HEAD, result paths, and actual orchestration: GPT-5.6 Sol requested by the user; runtime model identity not independently inspectable; three model-opaque subagents plus controller validation seat; no Luna model assignment API.

### Task 7: Verification and Adversarial Review

**Files:**
- Test: all tracked changes and required repository tests

- [ ] Run `.venv/bin/python -m pytest tests/test_mlx_tile_assembly_benchmark.py -q`.
- [ ] Run `.venv/bin/python -m pytest tests/test_preprocess_resize_backend_residency.py -q`.
- [ ] Run `.venv/bin/python -m pytest tests/test_spatial_tiling.py -q`.
- [ ] Run `.venv/bin/python -m pytest tests/test_gpu_pipeline.py -q`.
- [ ] Run `.venv/bin/python -m pytest tests/test_hdr_projection_backend.py -q`.
- [ ] Run `.venv/bin/python -m pytest --ignore=tests/gui -q`.
- [ ] Run `git diff --check` and verify that no `src/` production file changed except an explicitly gated seam with focused regression and benchmark evidence.
- [ ] Dispatch an independent reviewer against the plan, diff, reports, and raw JSON; fix every critical/important issue or document evidence-based rejection.
- [ ] Recheck every adversarial question in the user request, rerun any weak gate, and confirm each P0 is reproducible.
- [ ] For each candidate proposed for production, perform a second loophole hunt: same-input legacy/current simulation-to-output or encoder cold/hot medians, full-size evidence where the seam is reachable, exact output or contract-bound parity, mixed/edge/custom paths, dynamic-shape/cache behavior, failure/fallback paths, and full suite. Keep the overall 50MP peak/pressure verdict separate; if any local evidence is indirect or uncertain, keep the candidate benchmark-only.

### Task 8: Scoped Commit and Conditional GitHub Publication

**Files:**
- Stage only: plan, report/JSON, benchmark/profiling tool, benchmark results, validation tests, and any production/test change that independently crossed the 100%-confidence gate

- [ ] Inspect `git status`, `git diff --stat`, and `git diff --name-only`; reject any unrelated artifact and any production change without a complete evidence chain.
- [ ] Re-run the decisive focused test, full non-GUI test, and `git diff --check` immediately before commit.
- [ ] Commit locally with `audit: reassess lossless MLX performance and 50mp memory limits`.
- [ ] If no production candidate crosses the gate, keep the independent branch local as originally requested.
- [ ] If at least one production candidate crosses the gate, push the independent branch to `21Z121Z1/spektrafilm` and open a draft PR targeting the repository's appropriate integration branch; never push directly to `develop`/`main` without a separate explicit instruction.

## Plan Self-Review

- The plan covers every required output, path, counter, scenario, test command, orchestration disclosure, and final commit boundary.
- Production source/default changes are conditional on the explicit 2026-07-11 100%-confidence amendment and otherwise prohibited.
- No candidate is presumed valid; benchmark-local prototypes are gated by review and equivalence.
- No placeholder or unresolved design choice is required before execution.
