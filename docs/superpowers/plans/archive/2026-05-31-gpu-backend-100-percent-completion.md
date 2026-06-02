# GPU Backend 100 Percent Completion Plan

日期：2026-05-31

## Goal

把当前 GPU 后端从“主要路径已接入但仍有验证和边界缺口”的状态推进到可验证完成：

- MLX/Metal 是 Apple Silicon 上的 production GPU backend，默认模拟路径、LUT 路径、光谱直算路径、扫描后处理和 GUI 处理流程都必须真实接入。
- CuPy 保持 CUDA/ROCm hardware-gated backend：本机无法运行 CUDA 时不能假装完成，但代码路径、prepared LUT、内存池和 benchmark 规则必须正确。
- Halide 保持 explicit experimental backend，除非 target feature 和 schedule 都证明使用 GPU；host JIT/CPU schedule 不能在文档或 GUI 中被描述为完整 GPU。
- `gpu_validate` 不能只写 `status: ok`，必须在启用时执行 CPU reference 对比并输出误差指标。
- 最终报告必须说明完成度、验证证据、仍可继续加速和提高精度的空间，以及无法在本机验证的硬件条件。

## Current Evidence

已阅读并纳入这些本地文档：

- `docs/dev/2026-05-31-gpu-backend-full-code-review.md`
- `docs/superpowers/plans/2026-05-31-gpu-backend-full-review-remediation.md`
- `docs/dev/gpu-cpu-parity-audit-20260530.md`
- `docs/dev/mlx-optimization-report-20260530.md`
- `docs/halide-mlx-parity-results-20260531.md`
- `docs/dev/2026-05-31-autonomous-session-coordination-plan.md`

当前确认的关键事实：

- `SimulationPipeline` 已按 `settings.compute_backend/gpu_precision` 选择 backend，并传入 filming/printing/scanning stage。
- GUI state/mapper 已包含 `compute_backend` 和 `gpu_precision`。
- 最近文档记录过 `686 passed, 7 skipped` 的广测试结果，但当前本机 `.venv/bin/python -c "import numpy"` 会卡在 NumPy dynamic module 加载；因此必须重新建立当前可复现验证证据，不能只引用旧结果。
- `gpu_validate` 当前只是占位实现：非 debug 模式直接写 `{"status": "ok"}`，没有 CPU/GPU 数值对比。
- `_preprocess_base()` 仍把输入固定转换为 NumPy float64，这是输入/autoexposure/crop 边界，不是当前 GPU 热路径的最大缺口，但会影响峰值内存和端到端 GPU 驻留，需要在报告中明确。
- Halide 最新性能文档显示 direct spectral path 很快，但仍有 Python JIT、Buffer 和 NumPy crossing；除非引入 GPU target/schedule/AOT，否则应继续标注 experimental。

## External Best-Practice Basis

只采用官方/主源文档作为依据：

- MLX lazy evaluation: <https://ml-explore.github.io/mlx/build/html/usage/lazy_evaluation.html>
- MLX compilation: <https://ml-explore.github.io/mlx/build/html/usage/compile.html>
- MLX custom Metal kernels: <https://ml-explore.github.io/mlx/build/html/dev/custom_metal_kernels.html>
- CuPy performance best practices: <https://docs.cupy.dev/en/stable/user_guide/performance.html>
- CuPy memory management: <https://docs.cupy.dev/en/stable/user_guide/memory.html>
- Halide GPU scheduling: <https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html>

Derived rules for this repo:

- MLX arrays should stay lazy/backend-resident until an intentional scalar sync, validation, or final output boundary.
- `mx.compile()` belongs on pure tensor chains with stable shapes and tested cache behavior; random/stateful code and shape-dependent graphs need explicit guards.
- Custom Metal kernels should be cached and reused, not rebuilt per invocation.
- CuPy benchmark evidence must use warm-up and CUDA event-aware timing, not naive wall-clock only.
- Halide should be called GPU only when target features and schedule actually use GPU tiling/blocking.

## Implementation Tasks

### Task 1: Make validation real

- Add a failing test for `settings.gpu_validate=True` proving `SimulationPipeline.validation_report` contains real CPU/GPU metrics, not a placeholder.
- Implement validation by re-running a CPU reference pipeline with `gpu_validate=False`, comparing shapes, finiteness, max/mean absolute difference, tolerance, and pass/fail status.
- Keep debug mode skip behavior.
- Avoid recursive validation and preserve original params.
- Make tolerance backend-aware:
  - MLX/CuPy float32 default: absolute tolerance around `2e-4` for LUT paths and stricter `1e-5` for direct small-path tests when applicable.
  - Halide experimental: document/report tolerance from existing parity data instead of forcing production pass gates without a real GPU schedule.

### Task 2: Lock GUI/runtime validation plumbing

- Confirm GUI/macOS bridge can carry `gpu_validate` only if schema and UI already expose it.
- If no UI exposure exists, keep it as a runtime/dev flag and document the exact programmatic usage.
- Ensure worker failures from validation propagate as normal failure signals instead of silent worker death.

### Task 3: Close remaining backend-residency holes that are safe to fix

- Re-scan GPU hot paths for `np.asarray`, `np.array`, `np.clip`, `backend.to_numpy`, and eager scalar sync inside backend branches.
- Fix only issues that have a focused regression test and do not require unrelated refactors.
- Candidate hot-path checks:
  - scanner `SpectralLUTService`
  - layered grain density interpolation
  - glare and scanner correction
  - LUT prepared arrays
  - color matrix/CCTF helpers
  - filter helpers that may intentionally sync for memory control

### Task 4: Resolve verification environment

- Diagnose the current NumPy import hang in `.venv`.
- Prefer the repo-supported runner (`uv run --extra dev ...` or `.venv/bin/python`) after repair.
- If the existing `.venv` remains blocked, create a clean throwaway verification environment with the same Python/package constraints and record the exact commands.
- Do not claim completion until at least targeted GPU tests and static gates run in a current working environment.

### Task 5: Run verification gates

Minimum gates before completion:

- `git diff --check`
- Python syntax/compile check for touched files
- Targeted tests:
  - `tests/test_gpu_pipeline.py`
  - `tests/test_spectral_lut_service.py`
  - `tests/test_grain.py`
  - `tests/test_glare.py`
  - `tests/test_color_reference.py`
  - relevant GUI worker/runtime tests
- MLX availability smoke:
  - `select_backend("mlx")`
  - `mlx.core.metal.is_available()`
  - one small pipeline run with `compute_backend="mlx"`
- If environment allows, wider non-GUI pytest and sample smoke from the existing GPU/HDR docs.

Hardware-gated gates:

- CuPy tests may skip on Apple Silicon without CUDA/ROCm, but skip reason must be explicit.
- Halide may pass its JIT parity tests, but final docs must not count it as production GPU unless GPU scheduling is proven.

### Task 6: Update documentation and confidence loop

- Update `docs/dev/2026-05-31-gpu-backend-full-code-review.md` or write a new final report documenting:
  - what changed in this pass,
  - exact validation results,
  - current completion status by backend,
  - remaining acceleration opportunities,
  - remaining precision opportunities,
  - explicit non-goals/hardware-gated gaps.
- Before completing the goal, run a self-review:
  - Is there any GPU setting that silently falls back to CPU without being documented?
  - Does `gpu_validate` prove real parity when enabled?
  - Does the GUI path pass settings into runtime?
  - Are Halide/CuPy limitations truthfully represented?
  - Is every new production change backed by a test or documented verification?

## Acceptance Criteria

- A new plan document exists before production edits: this file.
- `gpu_validate=True` produces real validation metrics or an explicit skip/fail reason.
- MLX production path has current, local verification evidence.
- CuPy and Halide are accurately bounded rather than overclaimed.
- Final docs are updated with evidence and no known unreported GPU backend hole remains.

## Completion Addendum

完成时间：2026-05-31

- `gpu_validate=True` 已实现真实 CPU reference 对比，并在 MLX smoke 中验证：`max_abs_diff=2.088169911984572e-07`，低于 `1e-5`。
- 已修复 glare backend array conversion、CCTF midgray reference、profile save monkeypatch path，并更新当前确定性 golden baselines。
- 最终报告已写入 `docs/dev/2026-05-31-gpu-backend-100-percent-completion-report.md`。
- 当前验证：
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest --ignore=tests/gui -q` -> `722 passed, 7 skipped, 1 warning`
  - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/gui -q` -> `152 passed`
  - `.venv/bin/python -m compileall -q src tests` -> pass
  - `git diff --check` -> pass
