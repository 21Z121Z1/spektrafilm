# Documentation Archive

This directory preserves historical Markdown that should not be deleted, but should not be treated as the active source of truth without revalidation.

Use archived documents for provenance, old reasoning, and comparison against current files. For current navigation, start at [`../README.md`](../README.md).

## Contents

| Path | Meaning |
| --- | --- |
| [`dev/`](dev/) | Archived development reports, review rounds, and completed plans from `docs/dev/`, moved here on 2026-06-02. Includes 2 files from the former `docs-2-legacy-20260531/` directory. |
| Root-level files | Archived root-level reviews, plans, and issue drafts from `docs/`, moved here on 2026-06-02. |

## 2026-06-02 Archive Sweep

42 files were archived after cross-referencing against current code and tests. The full audit report is in the main docs/README.md archive policy section.

### Root-Level Files Archived (14 files)

| File | Superseded By |
| --- | --- |
| `color_management_report.md` | `color-management-hdr-review-2026-05-31.md` |
| `color_management_code_review.md` | `color-management-hdr-review-2026-05-31.md` |
| `color-management-system-review.md` | `color-management-hdr-review-2026-05-31.md` |
| `color-management-hdr-deep-review.md` | `color-management-hdr-review-2026-05-31.md` |
| `ISSUE_color_space_metadata.md` | Bug fixed (commit 54e947c) |
| `CODE_REVIEW.md` | `dev/2026-05-30-adversarial-code-review-v5.md` + agent_audit |
| `GPU_CODE_REVIEW.md` | `dev/mlx-optimization-report-20260530.md` + `dev/2026-05-31-mlx-backend-review.md` |
| `gpu_hardware_acceleration_evaluation.md` | `dev/mlx-optimization-report-20260530.md` (6.11x vs 1.15x) |
| `gpu_hardware_acceleration_plan.md` | `dev/2026-05-31-mlx-postprocessing-effects.md` + `halide-mlx-parity-plan-20260531.md` |
| `implementation_plan.md` | `color-management-hdr-review-2026-05-31.md` + CLAUDE.md |
| `upstream_migration.md` | `dev/2026-06-01-upstream-main-sync-report.md` |
| `upstream-parity-report.md` | `dev/2026-06-01-upstream-main-sync-report.md` |
| `sdr-parity-guarantee.md` | `upstream-sync-plan-20260602.md` + `dev/2026-06-01-upstream-main-sync-report.md` |
| `memory_management_review.md` | `dev/memory-management-implementation-2026-05-27.md` |

### dev/ Files Archived (28 files)

| File | Superseded By |
| --- | --- |
| `code-quality-review-round-1.md` through `round-6.md` | Later review rounds |
| `review-round-7.md`, `review-round-8.md` | Later adversarial reviews |
| `research-implementation-round-1.md` through `round-5.md` | Completed |
| `deep-research-implementation-patterns.md` | P0/P1 implementation plan |
| `2026-05-28-adversarial-review-goal-plan.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-28-adversarial-review-report.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-30-adversarial-code-review.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-31-adversarial-review-remediation-report.md` | Historical record |
| `2026-05-31-codex-plugin-adversarial-review-report.md` | Historical record |
| `2026-05-26-full-workspace-code-review.md` | `code-review-2026-05-26.md` |
| `halide-impl-plan.md` | `halide-backend-implementation.md` |
| `accepted-p0-p1-implementation-plan-2026-05-28.md` | Completed (17/17 findings) |
| `2026-05-26-develop-upstream-branch-integration-plan.md` | Completed |
| `test-improvement-plan.md` | `test-system-hardening-2026-05-27.md` |
| `gpu-cpu-parity-audit-20260530.md` | `2026-05-31-gpu-backend-100-percent-completion-report.md` |
| `2026-05-31-gpu-backend-100-percent-completion-report.md` | Historical record |
| `2026-05-31-gpu-backend-full-code-review.md` | Historical record |
| `2026-05-31-mlx-backend-review.md` | Historical record |
