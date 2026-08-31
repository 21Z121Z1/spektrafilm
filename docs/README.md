# Spektrafilm Documentation Map

This is the canonical router for repository documentation. It is organized by **authority and lifecycle first**, then by subject. The goal is to let a contributor or agent determine what is current before loading detailed research.

## Start here

| Path | Authority | Use |
| --- | --- | --- |
| [`../README.md`](../README.md) | Product overview | User-facing purpose, installation, package layout, and public entry points. |
| [`architecture/system-map.md`](architecture/system-map.md) | **Canonical architecture** | Stable abstraction tower, semantic domains, authority objects, dependency direction, and extension protocol. |
| [`PROJECT_STATE.md`](PROJECT_STATE.md) | **Current snapshot** | `develop` baseline, open workstreams, all branch lifecycle states, integration order, and known state-specific caveats. |
| [`architecture/verification-contracts.md`](architecture/verification-contracts.md) | **Canonical contract** | Exact meanings of bitwise identity, numerical equivalence, determinism, statistical parity, upstream conformance, baselines, performance, and memory claims. |
| [`decisions/README.md`](decisions/README.md) | **Decision index** | Durable architectural rationale and supersession rules. |
| [`../src/spektrafilm/README.md`](../src/spektrafilm/README.md) | Runtime contract | Physical core philosophy: linear-light RGB in named primaries -> film/print/scan physics -> linear-light RGB. |

For engineering work, read the control-plane documents above before dated reports or stale branches. They are deliberately small and route you to deeper evidence only when needed.

## Documentation authority model

Documents in this repository have different jobs. Do not infer authority from length or recency alone.

| Class | Meaning | Mutation policy |
| --- | --- | --- |
| **Canonical** | Maintained statement of current architecture or contract. | Update when the system changes. |
| **Current snapshot** | Repository/workstream state at a declared commit/date. | Update on lifecycle/integration changes. |
| **Decision** | Accepted/rejected durable rationale. | Supersede explicitly; preserve historical context. |
| **Plan** | Intended future work. | Does not prove implementation exists. |
| **Report** | Evidence/analysis tied to a date, commit, environment, or experiment. | Preserve as a snapshot; correct factual errors explicitly rather than silently converting it into current truth. |
| **Generated** | Reproducible derived material. | Regenerate from its source/tool. |
| **Archive** | Historical context only. | Never use as current truth without re-verification. |

Dated documents are **reports/plans by default** unless they explicitly declare canonical status. A non-`develop` branch is also lower authority than current code/tests/contracts; consult `PROJECT_STATE.md` before using one.

## Canonical runtime, SDR, HDR, color, and export contracts

These documents describe active subsystem semantics or executable validation contracts. When they conflict with current code/tests/CI, treat the executable target commit as authoritative and fix the documentation.

| Path | Use |
| --- | --- |
| [`sdr-upstream-conformance.md`](sdr-upstream-conformance.md) | Locked-upstream SDR conformance harness, thresholds, allowlist, and refresh process. |
| [`film-scan-aware-hdr.md`](film-scan-aware-hdr.md) | `film_scan_aware` positive film-scan HDR semantics and raw/positive route split. |
| [`hdr-export-pipeline.md`](hdr-export-pipeline.md) | RouteMaster SDR/HDR pair export boundary and HEIC validation contract. |
| [`hdr-modes.md`](hdr-modes.md) | Current HDR mode semantics. |
| [`heic-iso21496-compliance.md`](heic-iso21496-compliance.md) | ISO 21496-1 / HEIC `tmap` validation, repair, fail-closed behavior, and Mac openability gates. |
| [`hdr-routemaster-rewrite-implementation-report.md`](hdr-routemaster-rewrite-implementation-report.md) | Implementation evidence for the RouteMaster rewrite. Treat measurements/status as report evidence; RouteMaster’s current executable contract lives in code/tests. |
| [`../src/spektrafilm/data/hdr_curve_profiles/README.md`](../src/spektrafilm/data/hdr_curve_profiles/README.md) | Runtime HDR curve-profile data contract. |
| [`../src/spektrafilm/data/icc/README.md`](../src/spektrafilm/data/icc/README.md) | Bundled ICC profile notes. |

Open HDR work on PR #6 is not canonical until integrated. Its review/report is indexed through `PROJECT_STATE.md` rather than silently folded into current HDR semantics.

## Active plans and proposals

Plans are useful design input, not implementation status. Check `PROJECT_STATE.md` and current code before acting on them.

| Path | Scope |
| --- | --- |
| [`halide-mlx-parity-plan-20260531.md`](halide-mlx-parity-plan-20260531.md) | Historical/currently useful Halide/MLX parity planning and benchmark contract. [中文](halide-mlx-parity-plan-20260531_zh.md) |
| [`upstream-sync-plan-20260602.md`](upstream-sync-plan-20260602.md) | Upstream synchronization plan snapshot. [中文](upstream-sync-plan-20260602_zh.md) |
| [`film-scan-aware-negative-positive-plan.md`](film-scan-aware-negative-positive-plan.md) | Negative-film raw-vs-positive film-scan HDR route separation plan. |
| [`hdr_exr_output_plan.md`](hdr_exr_output_plan.md) | Scene-linear EXR export proposal. [English](hdr_exr_output_plan.en.md) |
| [`issue_positive_film_print_exposure.md`](issue_positive_film_print_exposure.md) | Historical issue/implementation proposal; re-check the referenced code before assuming the stated bug still exists. [中文](issue_positive_film_print_exposure_zh.md) |

Do not label an old plan “current” merely because no newer plan has the same title.

## Reports and research evidence

The following are evidence snapshots or research. Their strongest claims remain scoped to the code/environment/method they describe.

### Color and HDR

| Path | Scope |
| --- | --- |
| [`color-management-hdr-review-2026-05-31.md`](color-management-hdr-review-2026-05-31.md) | Color-management/HDR review snapshot. [English](color-management-hdr-review-2026-05-31.en.md) |
| [`hdr_profile_aware_raw_validation.md`](hdr_profile_aware_raw_validation.md) | Real ProRAW profile-aware HDR export validation; companion JSON holds machine-readable evidence. [English](hdr_profile_aware_raw_validation.en.md) |
| [`hdr/gain-map-HDR分析报告.md`](hdr/gain-map-HDR分析报告.md) | ISO 21496-1 gain-map HDR integration analysis. [English](hdr/gain-map-HDR-analysis-report.en.md) |
| [`hdr/research-gui-color-hdr.md`](hdr/research-gui-color-hdr.md) | GUI color/HDR rendering research. |

### GPU, Halide, and memory

| Path | Scope |
| --- | --- |
| [`gpu/research-gpu-color-management.md`](gpu/research-gpu-color-management.md) | GPU acceleration/color-management research. [中文](gpu/research-gpu-color-management_zh.md) |
| [`gpu/mlx-optimization-report-20260530.md`](gpu/mlx-optimization-report-20260530.md) | MLX optimization measurements at the report’s environment. [English](gpu/mlx-optimization-report-20260530.en.md) |
| [`gpu/halide-backend-implementation.md`](gpu/halide-backend-implementation.md) | Halide backend implementation/verification snapshot. [中文](gpu/halide-backend-implementation_zh.md) |
| [`gpu/halide-deep-research.md`](gpu/halide-deep-research.md) | Halide Android-port research. [中文](gpu/halide-deep-research_zh.md) |
| [`architecture/research-memory-management.md`](architecture/research-memory-management.md) | Memory-management/leak-detection research. [中文](architecture/research-memory-management_zh.md) |

### Android

| Path | Scope |
| --- | --- |
| [`architecture/research-android-app-architecture.md`](architecture/research-android-app-architecture.md) | Android app architecture research. [中文](architecture/research-android-app-architecture_zh.md) |
| [`architecture/research-android-port.md`](architecture/research-android-port.md) | Android port research snapshot. [中文](architecture/research-android-port_zh.md) |
| [`architecture/research-android-porting-strategies.md`](architecture/research-android-porting-strategies.md) | Android porting strategies. [中文](architecture/research-android-porting-strategies_zh.md) |
| [`reports/android-port-status-20260528.md`](reports/android-port-status-20260528.md) | Android port status at its report date. [中文](reports/android-port-status-20260528_zh.md) |

### Repository/process reports

| Path | Scope |
| --- | --- |
| [`reports/public-surface-hygiene-report-20260622.md`](reports/public-surface-hygiene-report-20260622.md) | Public-surface hygiene report at its audit date. |
| [`architecture/full-pipeline-color-management-audit-20260608.md`](architecture/full-pipeline-color-management-audit-20260608.md) | Full-pipeline color-management audit snapshot. |

Open-branch reports (HDR review, profile provenance, MLX exactness/performance) are intentionally not duplicated into this canonical index as if they were landed. `PROJECT_STATE.md` identifies the branch/PR and explains how to consume those reports safely.

## Research source material

| Path | Use |
| --- | --- |
| [`spectral_film_simulations.md`](spectral_film_simulations.md) | English source-material writeup from the spectral film simulation thread. [中文](spectral_film_simulations_zh.md) |
| [`spectral_film_simulations_zh.md`](spectral_film_simulations_zh.md) | Chinese translation of the same source material. [English](spectral_film_simulations.md) |

## Generated and data-adjacent documentation

| Path | Use |
| --- | --- |
| [`curve_analysis/`](curve_analysis/) | Generated curve-analysis corpus, including per film/paper combinations. Start with [`curve_analysis/README.md`](curve_analysis/README.md). |

Generated corpora are evidence products, not the architecture router. Prefer their summary/index before opening individual generated files.

## Root-level project documents

| Path | Use |
| --- | --- |
| [`../AGENTS.md`](../AGENTS.md) | Agent boot/operating protocol. |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Contributor workflow and evidence expectations. |
| [`../CHANGELOG.md`](../CHANGELOG.md) | Release/change history. |

## Bilingual policy

Translations are navigation/accessibility aids, not a second independent source of truth. Where a pair is listed, the document itself or this index should make the primary source clear. Do not assume every active document has a translation, and do not block an architecture/contract correction merely to keep two files textually synchronized in the same commit.

When translating a canonical document, preserve its semantics and link the translation to the canonical source so agents know which file to update first.

## Maintenance rule

When adding documentation, decide its class first. Prefer:

- updating a canonical control document when the system itself changed;
- adding an ADR when durable rationale changed;
- adding a dated report for experimental evidence;
- adding a plan only for future work;
- avoiding another repository-wide report that duplicates the system map and immediately begins to go stale.
