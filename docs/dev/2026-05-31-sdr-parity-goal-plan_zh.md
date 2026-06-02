> 这是英文原文的中文翻译。权威版本请参考英文原文。

# SDR 对等性现实核查实施计划

> **致自动化工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 来逐任务实施本计划。步骤使用复选框（`- [ ]`）语法进行跟踪。

**目标：** 用可验证的当前状态检查替换过时的 SDR 对等性保证，修复上游对等性脚本以捕获真正的共享数据漂移，并更新文档使其不再声称当前检出版本无法满足的保证。

**架构：** 保持运行时行为不变。工作仅限于测试、对等性 shell 检查和文档。shell 检查仍作为命令行强制执行层；pytest 使用隔离的临时 Git 仓库覆盖脚本行为；`tests/test_upstream_parity.py` 仍作为本地数值回归测试套件。

**技术栈：** Bash、Git、pytest、NumPy、项目 `.venv/bin/python`。

---

## 当前证据

当前检出版本不满足原始 `docs/sdr-parity-guarantee.md` 文本的要求。

- `bash scripts/check-upstream-parity.sh` 针对当前 `upstream/main` 运行失败。
- `upstream/main` 已在此分支 merge-base 之上推进了 27 个提交。
- 被列为逐字节一致的核心文件中有多个在当前工作树中存在差异：`pipeline.py`、`params_builder.py`、`params_schema.py`、`filming.py`、`printing.py`、`scanning.py`、`spectral_lut_compute.py`、`couplers.py` 和 `profiles/io.py`。
- 脚本当前报告 `(no shared data files found in upstream/main)`，尽管上游在 `src/spektrafilm/data/` 下跟踪共享数据。
- 当前本地数值测试套件仍然通过：`.venv/bin/python -m pytest tests/test_upstream_parity.py -v` 报告 `13 passed`。
- 文档中的计数已过时：当前本地计数为 `src/spektrafilm/data/hdr_curve_profiles` 下 162 个文件和 `src/spektrafilm/data/icc` 下 173 个 ICC/ICM 文件。

## 外部最佳实践输入

- NumPy 推荐使用 `numpy.testing.assert_allclose` 进行数组容差检查，因为它会检查形状并使用显式的 `atol + rtol * abs(desired)` 语义进行值比较。
- Pytest 推荐注册自定义标记，以便标记用法出现在 `pytest --markers` 中，避免因意外行为而产生警告。
- Git 自身的 `git diff` 文档区分工作树、暂存区、提交和 merge-base 比较；对等性脚本必须明确说明正在比较哪个 Git 对象。

## 需要修复的实际问题

1. 保证文档过度声称了当前的上游对等性。
2. 对等性报告已过时，仍声称 fork 严格领先于上游 SHA `a227823...`，在获取当前 `upstream/main` 后这已不再成立。
3. shell 脚本未对真正的上游数据根目录 `src/spektrafilm/data/` 进行哈希检查，因此共享的 profile/filter/LUT 漂移可能静默通过。
4. 当声明的核心文件在上游缺失时，shell 脚本仅发出警告而非失败，这使得损坏的文件契约看起来是非致命的。
5. 文档混淆了两种不同的保证：本地 SDR 数值稳定性和针对移动上游分支的字节/路径对等性。

## 任务 1：为脚本缺陷添加失败测试

**文件：**
- 创建：`tests/test_upstream_parity_script.py`

- [ ] 创建一个 pytest fixture，构建一个在 `src/spektrafilm/data/profiles/example.json` 处有一个跟踪共享数据文件的临时上游 Git 仓库。
- [ ] 将该仓库克隆到一个工作仓库，复制 `scripts/check-upstream-parity.sh`，在本地修改共享数据文件，并使用 `UPSTREAM_REMOTE=origin UPSTREAM_BRANCH=main` 运行脚本。
- [ ] 断言脚本以非零退出码退出，并将 `src/spektrafilm/data/profiles/example.json` 命名为哈希比较失败项。
- [ ] 创建第二个临时仓库场景，其中上游缺少一个声明的核心文件路径，断言脚本以非零退出码退出而非仅发出警告。
- [ ] 运行：`.venv/bin/python -m pytest tests/test_upstream_parity_script.py -v`
- [ ] 实现前预期：至少共享数据测试失败，因为当前脚本不扫描 `src/spektrafilm/data/`。

## 任务 2：修复 `scripts/check-upstream-parity.sh`

**文件：**
- 修改：`scripts/check-upstream-parity.sh`

- [ ] 添加包含 `src/spektrafilm/data/` 的 `DATA_ROOT_PATTERNS`，仅将旧根目录保留为兼容性。
- [ ] 当路径明确属于契约的一部分时，缺失的核心路径应失败而非仅警告。
- [ ] 通过将 `git cat-file blob "$UPSTREAM_REF:$path"` 管道传输到 `shasum -a 256` 来保持二进制安全的上游哈希计算。
- [ ] 打印清晰的摘要，包含比较的上游 ref、merge-base 和数据文件计数。
- [ ] 保留 `UPSTREAM_REMOTE` 和 `UPSTREAM_BRANCH` 覆盖。
- [ ] 运行：`.venv/bin/python -m pytest tests/test_upstream_parity_script.py -v`
- [ ] 实现后预期：新的脚本测试通过。

## 任务 3：修正 SDR 对等性文档

**文件：**
- 修改：`docs/sdr-parity-guarantee.md`
- 修改：`docs/upstream-parity-report.md`

- [ ] 将保证重写为当前状态契约，而非错误地断言所有核心文件当前完全一致。
- [ ] 将"针对上游的字节/路径对等性"与"本地数值 SDR 回归稳定性"分开。
- [ ] 记录当前失败的 `scripts/check-upstream-parity.sh` 证据和通过的本地 `tests/test_upstream_parity.py` 证据。
- [ ] 将真正的数据根目录更正为 `src/spektrafilm/data/`。
- [ ] 更正当前 HDR 曲线 profile 文件和 ICC/ICM 文件的本地计数。
- [ ] 说明当前上游对等性已损坏，直到上游分歧和核心文件差异被有意调和或通过新的记录基线被接受。

## 任务 4：验证循环

**文件：**
- 只读，除非失败需要针对性的测试/文档修复。

- [ ] 运行：`.venv/bin/python -m pytest tests/test_upstream_parity_script.py tests/test_upstream_parity.py -v`
- [ ] 运行：`bash scripts/check-upstream-parity.sh`
- [ ] 运行：`.venv/bin/python -m pytest --ignore=tests/gui -q`
- [ ] 运行：`.venv/bin/python -m compileall src tests scripts`
- [ ] 运行：`git diff --check`
- [ ] 自我审查：检查实现是否会错误地声称 100% 对等性。如果是，修订文档或检查，直到剩余的失败状态是明确的且不会被误认为成功。

## 非目标

- 不要回退或重写现有的运行时、模型、GPU 或 GUI 更改。
- 不要将当前 `upstream/main` 合并到此脏工作树中。
- 不要通过降低上游对等性标准来使 `scripts/check-upstream-parity.sh` 通过。
- 在当前上游分歧和核心文件差异尚未解决时，不要声称完全的 SDR 上游对等性。
