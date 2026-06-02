> 中文摘要。权威完整记录见 `docs/upstream-sync-plan-20260602.md`。

# 上游同步计划与报告摘要 - 2026-06-02

## 新 /goal

安全完成 `develop` 对 `upstream/main` 的最终同步确认：证明上游最新历史已经包含在当前分支中，完整保留本地 HDR/HEIC/Apple Adaptive HDR、profile-aware HDR、export-only HDR、MLX/GPU、色彩管理、胶片模拟、RAW/EXR/HEIC 导出、测试和文档工作；不做 rebase/reset/force push；验证后只允许推送到 `origin/develop`，绝不推送到 `upstream`。

## 分支与远程状态

- 当前分支：`develop`
- `origin`：`https://github.com/21Z121Z1/spektrafilm.git`
- `upstream`：`https://github.com/andreavolpato/spektrafilm.git`
- `HEAD`：`949cf43ad0e8af8cf14dfc51eba02489441cacc1`
- `origin/develop`：`949cf43ad0e8af8cf14dfc51eba02489441cacc1`
- `upstream/main`：`906351eca5f677e4c7d991b929e2dcbdac53827a`
- `HEAD...upstream/main`：`380 0`
- `upstream/main` 已经是 `HEAD` 的祖先。

## 策略结论

本轮没有再次执行 merge，因为实时状态不是旧计划中的落后状态；当前 `develop` 已经包含 `upstream/main`。安全策略是：

- 创建备份分支：`backup/before-upstream-sync-20260602-2303`
- 保留既有 380 个本地 ahead commits。
- 不执行 rebase、reset、force push、大范围 ours/theirs checkout。
- 不推送到 `upstream`。
- 将当前工作区里的本地文档整理、HDR GUI、MLX runtime hot path、film-scan-aware HDR 等工作作为普通提交保留下来。
- 提交 `40e387b` 后，分支相对 `upstream/main` 仍然是 `behind = 0`；增加的 ahead 只来自本地 fork/report 工作。
- 推送前再次确认 remote、分支、ahead/behind 和验证结果。

## 冲突情况

本轮没有新增冲突文件，因为没有新的 merge。既有历史中已经有 `0d3aeda Merge upstream/main into develop` 处理上游 GUI refactor；本轮没有重开或覆盖那次解决结果。

## 保护的本地功能

- HDR / HEIC / Apple Adaptive HDR / gain-map 导出。
- profile-aware HDR 与 film-scan-aware HDR。
- export-only HDR rendition path；不改变 SDR preview、SDR output 或 film/print/scan runtime look。
- RAW / EXR / HEIC / ICC / EXIF / 色彩 metadata 导出。
- MLX / GPU / Halide / CuPy 后端与相关验证。
- GUI HDR export 设置、持久化、state bridge、layout、controller save path、widget manifest。

## 验证结果

通过的检查：

- `git diff --check`
- `git diff --cached --check`（先发现两个文档末尾空行，清理后通过）
- GUI 关键切片：`102 passed`
- HDR/photo/GPU/runtime 切片：`189 passed, 2 skipped`
- HDR/color/export/MLX/runtime 切片：`219 passed, 2 skipped`

完整非 GUI 入口：

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

结果：`1298 passed, 7 skipped, 6 failed, 1 warning`。

6 个失败都是 SDR baseline/golden-reference 数值不匹配：

- `tests/test_pipeline_smoke.py::test_midgray_input_produces_expected_output_values`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_portra_endura_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[negative_density_portra_endura_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_fuji_crystal_gray_ramp16]`
- `tests/test_regression_baselines.py::TestRegressionBaselines::test_pipeline_snapshot[print_rgb_portra_endura_green_patch8]`
- `tests/test_upstream_parity.py::TestGoldenReference::test_midgray_output_golden_reference`

为区分失败来源，我从当前 `HEAD` 创建了临时干净 worktree `/tmp/spektrafilm-head-VUcgYc`，并用 `PYTHONPATH=/tmp/spektrafilm-head-VUcgYc/src` 运行同一组 SDR baseline/golden 测试。结果同样失败且数值一致。因此这些是当前 `HEAD/origin/develop` 已存在的 SDR baseline 债务，不是本轮同步 finalization 引入的新回归。本轮没有通过改 baseline 或改 SDR 行为来掩盖这些失败。

## 已知限制和后续建议

- 需要单独做一次 SDR baseline reconciliation，明确当前 SDR 行为是否应成为新基线。
- 本轮不会为通过测试而修改 SDR runtime behavior。
- `40e387b` 之后如有额外报告/文档提交，推送前仍必须确认相对 `upstream/main` 的 `behind = 0`。
- 推送只能使用 `git push origin develop`。
- 禁止 `git push upstream ...`、`git push --force upstream ...`、`git push --mirror ...`。
