# Spektrafilm Documentation Index

This directory contains all documentation for the Spektrafilm project: user guides, developer notes, code reviews, implementation plans, and research documents.

---

## User-Facing Documentation

| File | Description |
|------|-------------|
| `spectral_film_simulations.md` | English translation of the original pixls.us forum thread on spectral film simulation from scratch (source material for this project) |
| `spectral_film_simulations_zh.md` | Chinese translation of the same pixls.us spectral film simulation thread |

---

## Developer Documentation (`docs/dev/`)

### Current / Active

These documents describe the current state of the codebase or active development efforts.

| File | Description |
|------|-------------|
| `code-review-2026-05-26.md` | Full workspace code review with findings on SDR preservation, HDR export, color management, GPU paths, and test validity |
| `halide-backend-implementation.md` | Verified state of the Halide backend -- 67/67 Halide tests passing, documents all implemented kernels and AOT foundation |
| `halide-android-port-plan.md` | Plan for porting the Halide backend to Android ARM via JNI; Android app/JNI foundation exists, no full renderer shipped yet |
| `research-android-app-architecture.md` | Research document for designing an Android photo editing / film simulation app architecture |
| `research-android-port.md` | Research and strategy for porting the spectral film simulation engine to Android with zero-precision-loss GPU requirements |
| `research-android-porting-strategies.md` | Deep evaluation of six porting dimensions for bringing spektrafilm to Android |
| `research-gpu-color-management.md` | Research on GPU acceleration and color management with zero-precision-loss constraint |
| `research-gui-aesthetics.md` | GUI aesthetics and UX research for the spektrafilm Qt interface |
| `research-gui-color-hdr.md` | GUI color management and HDR preview research |
| `research-gui-product-logic.md` | Product logic review and UX flow audit of all GUI source files |
| `research-halide-port.md` | Halide rewrite feasibility research for spektrafilm |
| `research-memory-management.md` | Deep research on memory management strategies for spektrafilm |
| `research-memory-optimization-patterns.md` | Memory optimization patterns evaluated against zero-precision-loss constraint |
| `deep-research-implementation-patterns.md` | Exhaustive research to drive the spektrafilm implementation roadmap |
| `gain-map-HDR分析报告.md` | Gain map HDR image generation -- ISO 21496-1 standard analysis and spektrafilm integration plan |
| `modern_recovery_peak_budget_plan.md` | Plan for a profile-preserving HDR mode that recovers shoulder-compressed highlights with a fixed peak budget |
| `autonomous-loop.log` | Log output from the autonomous agent development loop |
| `xdremux-ref/` | Reference Python modules (container, edr, gainmap, heif_io, iso21496, isobmff_patch) from the xdremux project for HEIF/gain-map I/O |

### Completed Plans

These implementation plans have been executed and their goals achieved.

| File | Description |
|------|-------------|
| `accepted-p0-p1-implementation-plan-2026-05-28.md` | P0/P1 fix implementation plan -- all findings fixed during adversarial review pass (COMPLETED) |
| `2026-05-26-develop-upstream-branch-integration-plan.md` | Plan for merging upstream/main into develop -- merge completed 2026-05-29 (COMPLETED) |
| `2026-05-28-adversarial-review-goal-plan.md` | Adversarial review goal plan with task-by-task execution steps (COMPLETED) |
| `android-port-implementation-plan-20260528.md` | Android port implementation plan -- foundation exists under android/ (COMPLETED) |
| `halide-impl-plan.md` | Original Halide backend implementation plan -- all 8 planned kernels plus 4 additional implemented (COMPLETED) |
| `test-system-hardening-2026-05-27.md` | Test system hardening completion notes -- test count grown from ~295 to 814+ |
| `gui-research-hardening-implementation.md` | Implementation notes for GUI research hardening |
| `memory-management-implementation-2026-05-27.md` | Memory management implementation notes from 2026-05-27 |

### Archived Reviews

Older review rounds and reports that have been superseded by later work.

| File | Description |
|------|-------------|
| `2026-05-26-full-workspace-code-review.md` | Archived verbose duplicate of code-review-2026-05-26.md; findings addressed in adversarial-review-report.md |
| `2026-05-28-adversarial-review-report.md` | Results of the adversarial review pass executed on 2026-05-28 |
| `code-quality-review-round-1.md` | Code quality review round 1 -- findings addressed in subsequent rounds (ARCHIVED) |
| `code-quality-review-round-2.md` | Code quality review round 2 -- findings addressed in subsequent rounds (ARCHIVED) |
| `code-quality-review-round-3.md` | Code quality review round 3 -- type hints, error handling, dead code, API consistency (ARCHIVED) |
| `code-quality-review-round-4.md` | Code quality review round 4 -- comprehensive review of code quality (ARCHIVED) |
| `code-quality-review-round-5.md` | Code quality review round 5 (ARCHIVED) |
| `code-quality-review-round-6.md` | Code quality review round 6 (ARCHIVED) |
| `review-round-7.md` | Autonomous code review round 7 |
| `review-round-8.md` | Autonomous code review round 8 |
| `research-implementation-round-1.md` | Research implementation round 1 based on GPU color management and code review findings |
| `research-implementation-round-2.md` | Research implementation round 2 |
| `research-implementation-round-3.md` | Research implementation round 3 |
| `research-implementation-round-4.md` | Research implementation round 4 -- GPU acceleration and color management |
| `research-implementation-round-5.md` | Research implementation round 5 -- Oklch gamut mapping and ISO 21496-1 validation |
| `test-improvement-plan.md` | Original test improvement plan -- test count grown from ~295 to 814+ (ARCHIVED) |
| `项目状态报告-20260527.md` | Project status report from 2026-05-27 -- version now 0.3.2, 814+ tests (ARCHIVED) |

---

## Top-Level Review Documents (`docs/`)

These are standalone review and plan documents at the docs root.

| File | Description |
|------|-------------|
| `CODE_REVIEW.md` | SpektraFilm v0.3.1 full code review (Chinese) |
| `GPU_CODE_REVIEW.md` | Metal GPU acceleration system comprehensive code review report (Chinese) |
| `color_management_code_review.md` | Color management system comprehensive code review report (Chinese) |
| `color_management_report.md` | Color management system analysis and best practices report (Chinese) |
| `color-management-hdr-deep-review.md` | Color management and HDR engineering code review and remediation verification report |
| `color-management-system-review.md` | Color management system code review covering runtime pipeline, RAW import, GUI preview, and output saving |
| `gpu_hardware_acceleration_evaluation.md` | Metal hardware acceleration evaluation on Apple M1 Pro with MLX 0.31.2 |
| `gpu_hardware_acceleration_plan.md` | GPU hardware acceleration implementation plan based on profiling and vendor documentation |
| `hdr_exr_output_plan.md` | HDR EXR output implementation plan for scene-linear `.exr` export with unclipped highlights |
| `hdr_profile_aware_raw_validation.md` | Profile-aware HDR ProRAW validation results across 365 DNG samples |
| `hdr_profile_aware_raw_validation.json` | Machine-readable JSON data for the profile-aware HDR raw validation |
| `implementation_plan.md` | Color management and HDR EXR fusion refactoring plan |
| `ISSUE_color_space_metadata.md` | Bug report: saved images do not embed the selected color space (ICC profile / chromaticities) |
| `issue_positive_film_print_exposure.md` | Bug report: print exposure has no effect after selecting a print profile for positive film stocks |
| `memory_management_review.md` | Memory management system review report (Chinese) |
| `upstream_migration.md` | Upstream merge migration document for syncing develop with upstream/main |

---

## Agent Audit (`docs/agent_audit/`)

Automated quality audit documents generated by agent-driven review passes on 2026-05-28.

| File | Description |
|------|-------------|
| `accepted_p0_p1.md` | 17 findings accepted for fix with priority order and dependencies |
| `architecture_index.md` | Package structure and module dependency map |
| `critical_paths.md` | Critical execution paths through the codebase |
| `deferred_p2.md` | Real but non-urgent P2 findings deferred due to larger scope or design discussion needed |
| `final_validation_report.md` | Final validation report summarizing audit outcomes |
| `module_contracts.md` | Module-level contracts and invariants for each package |
| `next_goals.md` | Remaining findings from the HDR/color deep review not yet addressed |
| `rejected_findings.md` | Findings that did not meet acceptance criteria, with rejection reasons |
| `review_docs_ci.md` | Docs and API consistency findings from the audit |
| `review_format_metadata.md` | Format, metadata, and I/O safety review findings |
| `review_hdr_color.md` | HDR and color correctness review findings across hdr_photo, gain_map, spectral_upsampling, and color_management |
| `review_performance.md` | Performance and memory risk review (review-only, no source modifications) |
| `review_test_gaps.md` | Test coverage gap and quality review across 608 tests in 42 test files |
| `review_ui_runtime.md` | UI, runtime, and threading risk review (review-only) |
| `test_inventory.md` | Inventory of 608 non-GUI tests across 42 test files |
| `triaged_findings.md` | All findings from 6 review files categorized into 3 priority buckets |
| `validation_matrix.md` | Maps each module contract/invariant to the tests that validate it |
| `upstream_baseline/public_api_contracts.md` | Auto-generated audit of every public function, class, and CLI entry point in spektrafilm v0.3.1 |

---

## Superpowers Plans (`docs/superpowers/plans/`)

Implementation plans written for agentic workers using the superpowers subagent-driven-development pattern. Each plan contains checkbox-tracked task steps.

| File | Description |
|------|-------------|
| `2026-05-23-aces-color-management.md` | Add an explicit ACES reference color-management workflow using ACEScg as the scene-linear working space |
| `2026-05-23-hdr-diffuse-white-calibration.md` | Proposal for establishing a diffuse-white anchor for HDR still export |
| `2026-05-23-hdr-photo-mapping-execution.md` | Execution plan for implementing correct HDR still-photo export mapping |
| `2026-05-23-hdr-photo-mapping.md` | Implementation plan for HDR photo export with explicit diffuse/paper-white anchor and gain-map rendition |
| `2026-05-23-metal-processing-acceleration.md` | Complete the Apple Silicon Metal acceleration path across all hot-path kernels |
| `2026-05-24-auto-exposure-scene-linear.md` | Improve automatic exposure system for scene-linear / ACES / HDR inputs |
| `2026-05-24-film-simulation-lossless-speed.md` | Speed up film simulation without reducing quality or loosening numerical precision |
| `2026-05-24-gui-release-hardening.md` | Harden GUI for shipping -- preview correctness, output saving, metadata, background workers |
| `2026-05-24-hdr-scene-linear-exr.md` | Make HDR EXR export an explicit scene-linear output archive preserving unclipped linear values |
| `2026-05-24-raw-hdr-scene-energy-import.md` | Add RAW import sidecar with rawpy scale diagnostics and automatic diffuse-white/headroom estimate |
| `2026-05-24-scene-energy-hdr-gainmap-autoexposure.md` | Add scene-energy sidecar to simulation output for natural HEIC/HEIF HDR gain-map export |
| `2026-05-25-profile-aware-hdr-photo-export.md` | Implement profile-aware paired SDR/HDR tone-curve mapping for HDR photo export |
| `2026-05-27-gpu-color-management-audit-fixes.md` | Reconcile GPU color management research with current codebase and fix real defects |
| `2026-05-27-gui-research-hardening.md` | Convert verified GUI research findings into concrete low-risk improvements |
| `2026-05-27-halide-android-port-foundation.md` | Add a verified Halide/Android port foundation without overclaiming completeness |
| `2026-05-27-halide-backend.md` | Add a strict optional Halide backend, wire into backend selection, migrate first LUT kernel to Halide JIT |
| `2026-05-27-memory-management-fixes.md` | Remove real memory pressure bugs in runtime/GUI/GPU paths |
| `2026-05-27-test-system-hardening.md` | Bring pytest system into a truthful, maintainable state by fixing stale assumptions and real behaviors |
| `2026-05-28-halide-android-aot-contract.md` | Turn Halide/Android foundation into a verified AOT pre-JNI contract with reliable CMake builds |
| `2026-05-28-halide-continuation.md` | Continue Halide backend from 8615e6e by fixing JIT CCTF defect and AOT CMake skeleton |

---

## Curve Analysis (`docs/curve_analysis/`)

Comprehensive analysis of film stock and print paper curve combinations for HDR mapping. Contains per-combination markdown reports across 16 film stocks and 8 print papers (128 combinations total), plus the analysis tooling.

| File | Description |
|------|-------------|
| `film_print_hdr_analysis.md` | Summary report: HDR mapping curves must be dynamically adjusted based on the joint film+paper combination, not either alone |
| `curve_analysis.json` | Machine-readable JSON data for all curve analysis results |
| `analyze_curves.py` | Python script that runs all film/paper combinations through the simulator and fits curves |
| `generate_all_md.py` | Python script that generates the per-combination markdown reports from curve_analysis.json |
| `<film>_on_<paper>.md` | Individual curve analysis report for a specific film stock on a specific print paper (128 files) |

Film stocks analyzed: fujifilm_c200, fujifilm_pro_400h, fujifilm_provia_100f, fujifilm_velvia_100, fujifilm_xtra_400, kodak_ektachrome_100, kodak_ektar_100, kodak_gold_200, kodak_kodachrome_64, kodak_portra_160, kodak_portra_400, kodak_portra_800 (plus push1/push2 variants), kodak_ultramax_400, kodak_verita_200d, kodak_vision3_200t, kodak_vision3_250d, kodak_vision3_500t, kodak_vision3_50d.

Print papers analyzed: fujifilm_crystal_archive_typeii, kodak_2383, kodak_2393, kodak_ektacolor_edge, kodak_endura_premier, kodak_portra_endura, kodak_supra_endura, kodak_ultra_endura.
