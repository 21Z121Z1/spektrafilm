> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 上游 Main 分支同步报告 - 2026-06-01

## 摘要

- 当前分支：`develop`
- 来源：`https://github.com/21Z121Z1/spektrafilm.git`
- 上游：`https://github.com/andreavolpato/spektrafilm.git`
- 上游目标：`upstream/main`，位于 `500bc429b7e93450ef228305c319dc03d8e185d1`
- 主备份分支：`backup/before-upstream-sync-20260601-1804`
- 备份分支顶端：`be287ac3039140a14bd25d18f78ae1cc2b67690c`
- 合并提交：`966e7c3cf7f1c0f8fead9945a306b94552e30443`
- 合并父提交：`be287ac3039140a14bd25d18f78ae1cc2b67690c` 和 `500bc429b7e93450ef228305c319dc03d8e185d1`

未使用 rebase、reset、force push 或批量文件覆盖。合并策略为 `git merge --no-ff upstream/main`。

## 领先/落后状态

- 保留本地未提交工作之前的初始审计：相对于 `upstream/main` 为 `360 ahead / 31 behind`。
- 将所有本地工作保留为普通提交后的合并前状态：相对于 `upstream/main` 为 `369 ahead / 31 behind`。
- 合并提交 `966e7c3` 之后的状态：相对于 `upstream/main` 为 `370 ahead / 0 behind`。
- 相对于 `origin/develop` 的合并后状态：`41 ahead / 0 behind`。

`upstream/main` 和 `backup/before-upstream-sync-20260601-1804` 均已验证为当前 `HEAD` 的祖先提交。

## 冲突文件及解决原则

- `README.md`：将上游的包/LUT 创建器文档与本地 HDR、GPU 及项目文档引用合并；移除了上游引入的空白字符错误。
- `pyproject.toml`：将上游的包布局和 LUT 创建器依赖与本地的 dev/OpenColorIO、Halide、MLX、CuPy 及 GPU 扩展合并。
- `src/spektrafilm/model/develop.py`：保留本地 GPU 密度插值和显影路径，同时添加上游的打印密度曲线变形支持。
- `src/spektrafilm/model/diffusion.py`：保留本地后端感知的模糊/滤波行为和上游兼容的函数签名。
- `src/spektrafilm/model/emulsion.py`：保留向后兼容的导入作为指向 `model.develop` 的垫片，因为本地测试和脚本仍在导入 `model.emulsion`。
- `src/spektrafilm/runtime/params_schema.py`：保留本地输出裁剪标志和 GPU/运行时设置，同时添加上游的输入/输出色域压缩规格和拓扑接入点。
- `src/spektrafilm/runtime/pipeline.py`：保留本地 SDR/默认管线、元数据/HDR 附带文件和 GPU 后端选择；仅将显式接入点路由到上游拓扑支持。
- `src/spektrafilm/runtime/services/color_reference.py`：将本地后端感知的裁剪/校正行为与上游 color-science 导入变更合并。
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`：保留本地后端 LUT 缓存失效机制，添加上游输入色域压缩缓存键。
- `src/spektrafilm/runtime/stages/filming.py`：保留本地 HDR 自动曝光元数据和 Hanatos 带通支持，同时使用上游的 `model.develop` 导入。
- `src/spektrafilm/runtime/stages/printing.py`：保留本地 GPU 放大器路径和计时装饰器，同时添加上游的打印变形显影。
- `src/spektrafilm/runtime/stages/scanning.py`：保留本地 GPU XYZ->RGB、CCTF 编码和输出裁剪行为；在最终编码/裁剪之前添加上游输出色域压缩。
- `src/spektrafilm_gui/options.py`：保留本地计算后端、GPU 精度和 HDR 映射枚举；添加上游输入/输出色域压缩枚举。
- `src/spektrafilm_gui/state.py`：保留本地色彩管理运行时/保存分离和 HDR 映射字段；添加上游输出色域压缩状态。
- `src/spektrafilm_gui/widget_specs.py`：保留本地 HDR/GPU 控件；添加上游输出色域压缩控件。
- `tests/gui/test_params_mapper.py`：将本地 ACES 工作流导入/测试与上游输入色域压缩测试合并。
- `tests/test_filming_stage.py`：保留本地带通和输入编码测试；添加上游线性灵敏度测试。
- `tests/baselines/*.npz` 下的二进制基线冲突：保留本地合并前版本，以避免机械性地更改现有的 SDR/胶片/打印回归行为。重新生成仅应在运行时测试通过后通过有意的基线更新进行。

## 验证

成功的检查项：

- `/usr/bin/git status`：合并提交后状态干净。
- `/usr/bin/git diff --check`：通过。
- `/usr/bin/git diff --cached --check`：合并提交前通过。
- `/usr/bin/grep -R -n '^<<<<<<<' README.md pyproject.toml src tests`：无冲突标记。
- `/usr/bin/grep -R -n '^=======$' README.md pyproject.toml src tests`：无冲突分隔符。
- `/usr/bin/grep -R -n '^>>>>>>>' README.md pyproject.toml src tests`：无冲突标记。
- `/usr/bin/python3 -m py_compile ...`：手动合并的运行时、GUI 映射器、模型和目标测试文件均通过。
- `/usr/bin/git merge-base --is-ancestor upstream/main HEAD`：通过。
- `/usr/bin/git merge-base --is-ancestor backup/before-upstream-sync-20260601-1804 HEAD`：通过。

受阻的检查项：

- `.venv/bin/python -m compileall -q src/spektrafilm src/spektrafilm_gui tests` 在无输出挂起后被终止。
- `.venv/bin/python -m pytest -q tests/test_filming_stage.py ...` 在无输出挂起后被终止。
- 单进程探针 `PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 .venv/bin/python -c 'import numpy; print(numpy.__version__)'` 挂起超过 60 秒后被终止。

pytest/compileall 阻塞被归类为本地 Python/numpy 动态库加载问题，而非代码回归。系统 Python 语法检查被用作替代的静态证据，但无法替代项目的 pytest 测试套件。

## 推送建议

建议在 `.venv` 能正常导入 numpy 的机器/会话上成功运行一次项目环境 pytest 后再推送。

仅使用常规非强制推送：

```bash
git push origin develop
```

不要使用 force push。
