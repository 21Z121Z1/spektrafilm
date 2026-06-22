# Spektrafilm 公开暴露面整理报告 (Repository Public Surface Hygiene Report)

- **整理日期**: 2026-06-22
- **分支名称**: `chore/public-surface-hygiene`
- **主要目的**: 规范 Spektrafilm 开发 fork 的公开代码结构，抹除敏感的本地绝对路径与开发者用户名，归档和移除不必要的内部 Agent 执行历史文件与脚本，确保核心功能完整与测试全通。

---

## 1. 上游对照摘要

在此次整理前，当前 fork 相比于上游 `andreavolpato/spektrafilm` 的 `main` 分支存在以下公开面偏离：
- 根目录下存在许多本地 Agent 工具配置文件及自动修复循环脚本（`CLAUDE.md`、`CLAUDE-RESEARCH.md`、`autonomous-loop.sh` 等）。上游无类似文件。
- `docs/` 目录下包含了非常多仅作为智能体（Agent）开发、测试、和 Adversarial 审查的过程证据（如 `docs/agent_audit/`、`docs/superpowers/plans/`、`docs/archive/` 等），使公开代码库显得比较杂乱，且包含了过时信息。
- 部分性能脚本及 markdown 验证报告中泄漏了开发者的本地绝对路径。

---

## 2. 文件分类及处理方案表

本项任务对仓库文件进行了彻底的审计和分类，具体处理方案如下：

| 文件 / 目录路径 | 类别 (Category) | 实施动作 (Action Taken) | 理由 (Reason) |
| :--- | :--- | :--- | :--- |
| `CLAUDE.md`, `CLAUDE-RESEARCH.md` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 纯 Agent 提示与控制规则，对公开开发者无价值。 |
| `autonomous-loop.sh` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 本地自动运行及提交脚本，暴露内部自动化策略。 |
| `output.heic` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 本地测试生成样片，无明确授权和说明。 |
| `scratch/analyze_hdr_pipeline.py` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 一次性实验脚本，已失效。 |
| `docs/docs_inventory.txt` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 过时的文档快照索引，且含有大量绝对路径。 |
| `analysis/metal_float32_precision/` | C. 应移动到 private/internal 或不再跟踪 | **从 Git 中移除并物理删除** | 一次性临时精度分析，含大量用户本地绝对路径与图片。 |
| `AGENTS.md` | B. 可以公开但需要精简 | **修改为“公开安全版”** | 移除了 Scope 缺陷列表、优先级、跳过规则，仅保留项目概述和 GPU 精度基本策略。 |
| `CONTRIBUTING.md` | B. 可以公开但需要精简 | **精简与脱敏** | 明确为 fork 开发指南，指向 `develop` 分支和正确的 clone 链接。 |
| `docs/README.md`, `docs/README_zh.md` | B. 可以公开但需要精简 | **修改路由链接** | 移除了所有指向已移动/删除的历史 Agent 链路超链接。 |
| `docs/dev/` 下的稳定有价值设计文档 | A. 必须公开保留 | **移动至更稳定公开的目录** | 保留为公开架构参考（如 `docs/hdr/`、`docs/gpu/`、`docs/architecture/`、`docs/reports/`）。 |
| `docs/agent_audit/`, `docs/archive/`, `docs/plans/`, `docs/reviews/`, `docs/superpowers/plans/` | C. 应移动到 private/internal 或不再跟踪 | **备份至 `docs/internal/` 并从 Git 移除** | 纯 Agent 过程证据及临时基准测试报告。在本地物理备份，但不提交给公开仓库。 |
| `docs/reports/` 下的原始基准 JSON/MD 细节文件 | C. 应移动到 private/internal 或不再跟踪 | **备份至 `docs/internal/` 并从 Git 移除** | 纯特定时间的 benchmark 原始细节，本地备份以便查看，无需公开。 |

---

## 3. 敏感扫描结果

- **扫描命令**:
  ```bash
  git grep -n -I -E "api[_-]?key|secret|token|password|Authorization|Bearer|/Users/|/home/|<local-username>|<machine-user>" -- . || true
  ```
- **命中摘要**:
  经过扫描，发现：
  1. `docs/hdr_profile_aware_raw_validation.md` / `docs/hdr_profile_aware_raw_validation.en.md` / `docs/hdr_profile_aware_raw_validation.json` 包含本地绝对路径（包含 `<local-home>/<local-username>/...`）。
  2. `docs/heic-iso21496-compliance.md` 与 `docs/hdr-routemaster-rewrite-plan.md` 中包含本地标准文档绝对路径。
  3. `docs/profile-aware-hdr-audit-report.md` 包含本地 Python 绝对运行路径。
  4. `scripts/` 下的一系列 benchmark 和调试脚本硬编码了包含 `<local-home>/<local-username>/<local-sample-directory>/...` 的绝对路径。
- **已处理**:
  - `scripts/` 下的硬编码路径已全部重构为相对路径 `Path("IMG20260530191638.dng")`，可在本地运行时使用同名文件或参数传入。
  - 所有 markdown 报告及配套 json 里的绝对路径前缀均已被清除或修改为相对示范路径（例如 `RAW_DNG_JPEG_批量导出/`）。
- **需要人工决定项**:
  - 扫描中命中的 `/home/<third-party-user>/...` 等路径属于上游引用的第三方公共讨论和日志片段，不包含当前用户隐私，无泄露风险。
  - 过去提交历史中可能存在上述敏感绝对路径。如果不希望这些路径存在于 Git 历史记录中，建议由**人工决定**是否使用 `git-filter-repo` 重写历史（本任务为了低风险和可测试性，默认不重写 Git 历史）。

---

## 4. 实施改动列表

- **.gitignore 更新**:
  追加了对 Agent 配置文件、物理移动至本地的 `docs/internal/`、`docs/private/`、`docs/agent_runs/` 等目录以及临时 scratch、verify 文件和日志的过滤：
  ```gitignore
  # Public Surface Hygiene - Ignore Agent and temporary data
  /CLAUDE.md
  /CLAUDE-RESEARCH.md
  /AGENTS.private.md
  /AGENTS.local.md
  /autonomous-loop.sh
  /scratch_*.py
  /verify_*.py
  /output.*
  /docs/internal/
  /docs/private/
  /docs/agent_runs/
  /docs/dev/benchmark-artifacts/
  /scratch/
  *.log
  ```
- **文档整理与转正**:
  - 对 `docs/dev` 下的有价值的设计文件执行了移动和公开化。
  - 所有历史 Agent 过程报告和 plans 被物理归档到了 `docs/internal/`（由于 `.gitignore` 过滤，该文件夹不会被推送到 Git 仓库），保持了本地开发者参考价值的同时，净化了公开版本分支的表面。

---

## 5. 验证结果

1. **格式 and 规范验证**: `git diff --check` 执行全通，修正了 `CONTRIBUTING.md` 中遗留的尾随空格。
2. **测试验证**: 跑通非 GUI 的 1638 个测试：
   ```bash
   .venv/bin/python -m pytest --ignore=tests/gui -q
   ```
   测试结果: **1638 passed, 7 skipped, 4 xfailed**。表明没有对任何核心算法或编译/运行逻辑产生负面影响。
3. **最终摘要**:
   - 当前工作树已脱敏；
   - Git 历史是否重写仍为人工决策项。
