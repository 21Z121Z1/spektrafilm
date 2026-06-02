> 这是英文原文的中文翻译。权威版本请参考英文原文。

# Markdown 文档审计 - 2026-05-31

## 范围

本审计覆盖 `/Users/retriedstormtrooper/Documents/spektrafilm-main` 中的 Markdown 文档，排除 `.git`、`.venv`、`.pytest_cache` 和 `__pycache__`。

目标是使文档表面可导航，同时不删除历史记录，也不涉及并行的源代码/测试/GPU 实现工作。

## 清点发现

- 最终验证时观察到的 Markdown 清点：314+ 个文件。在并行基准测试任务于 `docs/dev/benchmark-artifacts/` 下生成 Markdown 期间，确切数量可能会增加。
- 主要集群：
  - 根项目文档：`README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`CLAUDE.md`、`CLAUDE-RESEARCH.md`。
  - 规范文档树：`docs/`。
  - 活跃开发报告：`docs/dev/`。
  - 审计快照：`docs/agent_audit/`。
  - 生成的曲线分析语料库：`docs/curve_analysis/`。
  - 智能体实施计划：`docs/superpowers/plans/`。
  - 运行时数据说明：`src/spektrafilm/data/hdr_curve_profiles/README.md` 和 `src/spektrafilm/data/icc/README.md`。
  - 历史重复树：原顶层 `docs 2/`，现已归档至 `docs/archive/docs-2-legacy-20260531/`。

## 分类结论

1. `docs/README.md` 应作为规范的文档路由。根目录 `README.md` 应保持面向产品，仅指向该路由。
2. `docs/dev/` 是一个混合工作区。它需要一个本地索引，因为它包含活跃的协调文档、当前 GPU/MLX/Halide 报告、Android 研究、GUI/内存/测试工作以及较旧的审查轮次。
3. `docs/agent_audit/` 是一个连贯的审计快照，应拥有自己的索引，而不是被扁平化到顶层路由中。
4. `docs/curve_analysis/` 是生成的语料库文档。摘要报告是入口点；160 个按组合生成的文件不应被独立手动维护。
5. `docs/superpowers/plans/` 包含实施计划，而非完成证明。它需要一个索引，提醒读者验证当前状态。
6. 原 `docs 2/` 树是一个真实的被跟踪的重复项，包含 26 个 Markdown 文件。它应作为归档证据保留，而不应作为第二个文档根。
7. `.gitignore` 使用了 `archive/`，这隐藏了 `docs/archive/README.md`。该规则已缩小为 `/archive/`，以便文档归档可以被 git 跟踪。

## 已执行的变更

- 创建了计划优先的实施工件：`docs/superpowers/plans/2026-05-31-markdown-documentation-consolidation.md`。
- 将 `docs/README.md` 重写为规范的文档地图。
- 添加了目录索引：
  - `docs/dev/README.md`
  - `docs/agent_audit/README.md`
  - `docs/curve_analysis/README.md`
  - `docs/superpowers/plans/README.md`
- 添加了归档文档：
  - `docs/archive/README.md`
  - `docs/archive/docs-2-legacy-20260531/README.md`
- 将原 `docs 2/dev/*.md` 文件移至 `docs/archive/docs-2-legacy-20260531/dev/`。
- 将 Markdown 引用从旧的 `docs 2/dev/...` 路径重写为归档路径（当它们引用实际文件时）。
- 在根目录 `README.md` 中添加了指向 `docs/README.md` 的指针。
- 更新了 `CLAUDE.md`，使智能体在使用较旧的审查文件之前从文档地图开始。
- 将 `.gitignore` 从 `archive/` 更新为 `/archive/`，以便 `docs/archive/` 对 git 可见。

## 验证证据

- Markdown 本地相对链接扫描：最终观察到的 Markdown 集中 `broken=0`；在基准测试工件生成活跃期间，已检查的数量可能会增长。
- 文档范围空白检查通过：

```bash
git diff --check -- .gitignore docs README.md CLAUDE.md 'docs 2'
```

- 全工作树空白检查也通过：

```bash
git diff --check
```

- 顶层 `docs 2/` 移除检查通过：

```bash
test ! -e "docs 2"
```

- `docs/dev/README.md` 覆盖了 `docs/dev/` 下的所有直接 Markdown 文件，并按目录覆盖了生成的基准测试工件，因为这些文件正在被活跃生成。
- `docs/superpowers/plans/README.md` 覆盖了 `docs/superpowers/plans/` 下的所有直接计划文件，其自身的 README 除外。

## 剩余边界

工作空间仍然包含来自并行实施工作的广泛源代码、测试、脚本、锁文件和生成工件的变更。本审计仅负责上述文档组织变更。
