> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 文档归档

本目录保存了不应删除的历史 Markdown 文档，但在重新验证之前，不应将其视为当前有效的权威来源。

归档文档可用于追溯来源、查阅旧有推理论证，以及与当前文件进行对比。如需当前导航，请从 [`../README.md`](../README.md) 开始。

## 目录内容

| 路径 | 说明 |
| --- | --- |
| [`dev/`](dev/) | 归档的开发报告、审查轮次和已完成的计划，原位于 `docs/dev/`，于 2026-06-02 迁移至此。包括原 `docs-2-legacy-20260531/` 目录中的 2 个文件。 |
| 根级文件 | 归档的根级审查、计划和问题草案，原位于 `docs/`，于 2026-06-02 迁移至此。 |

## 2026-06-02 归档清理

在与当前代码和测试进行交叉比对后，共归档了 42 个文件。完整的审计报告位于主文档 docs/README.md 的归档策略部分。

### 根级归档文件（14 个文件）

| 文件 | 已被以下文件取代 |
| --- | --- |
| `color_management_report.md` | `color-management-hdr-review-2026-05-31.md` |
| `color_management_code_review.md` | `color-management-hdr-review-2026-05-31.md` |
| `color-management-system-review.md` | `color-management-hdr-review-2026-05-31.md` |
| `color-management-hdr-deep-review.md` | `color-management-hdr-review-2026-05-31.md` |
| `ISSUE_color_space_metadata.md` | Bug 已修复（提交 54e947c） |
| `CODE_REVIEW.md` | `dev/2026-05-30-adversarial-code-review-v5.md` + agent_audit |
| `GPU_CODE_REVIEW.md` | `dev/mlx-optimization-report-20260530.md` + `dev/2026-05-31-mlx-backend-review.md` |
| `gpu_hardware_acceleration_evaluation.md` | `dev/mlx-optimization-report-20260530.md`（6.11x 对比 1.15x） |
| `gpu_hardware_acceleration_plan.md` | `dev/2026-05-31-mlx-postprocessing-effects.md` + `halide-mlx-parity-plan-20260531.md` |
| `implementation_plan.md` | `color-management-hdr-review-2026-05-31.md` + CLAUDE.md |
| `upstream_migration.md` | `dev/2026-06-01-upstream-main-sync-report.md` |
| `upstream-parity-report.md` | `dev/2026-06-01-upstream-main-sync-report.md` |
| `sdr-parity-guarantee.md` | `upstream-sync-plan-20260602.md` + `dev/2026-06-01-upstream-main-sync-report.md` |
| `memory_management_review.md` | `dev/memory-management-implementation-2026-05-27.md` |

### dev/ 目录归档文件（28 个文件）

| 文件 | 已被以下文件取代 |
| --- | --- |
| `code-quality-review-round-1.md` 至 `round-6.md` | 后续审查轮次 |
| `review-round-7.md`、`review-round-8.md` | 后续对抗性审查 |
| `research-implementation-round-1.md` 至 `round-5.md` | 已完成 |
| `deep-research-implementation-patterns.md` | P0/P1 实施计划 |
| `2026-05-28-adversarial-review-goal-plan.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-28-adversarial-review-report.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-30-adversarial-code-review.md` | `2026-05-30-adversarial-code-review-v5.md` |
| `2026-05-31-adversarial-review-remediation-report.md` | 历史记录 |
| `2026-05-31-codex-plugin-adversarial-review-report.md` | 历史记录 |
| `2026-05-26-full-workspace-code-review.md` | `code-review-2026-05-26.md` |
| `halide-impl-plan.md` | `halide-backend-implementation.md` |
| `accepted-p0-p1-implementation-plan-2026-05-28.md` | 已完成（17/17 项发现） |
| `2026-05-26-develop-upstream-branch-integration-plan.md` | 已完成 |
| `test-improvement-plan.md` | `test-system-hardening-2026-05-27.md` |
| `gpu-cpu-parity-audit-20260530.md` | `2026-05-31-gpu-backend-100-percent-completion-report.md` |
| `2026-05-31-gpu-backend-100-percent-completion-report.md` | 历史记录 |
| `2026-05-31-gpu-backend-full-code-review.md` | 历史记录 |
| `2026-05-31-mlx-backend-review.md` | 历史记录 |
