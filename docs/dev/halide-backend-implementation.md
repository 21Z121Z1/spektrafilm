# Halide Backend Implementation Notes

Date: 2026-05-27

## What Landed

Spektrafilm now has an explicit optional `compute_backend="halide"` path.

- Install with `spektrafilm[halide]` or by installing the official `halide` Python wheel.
- Missing Halide raises `BackendUnavailableError` for explicit `halide`.
- `auto` still chooses MLX, then CuPy, then CPU. It does not silently choose Halide.
- The backend is float32-only for now.
- `pyproject.toml` is the source of truth for the optional dependency. `uv lock`
  was run after adding the extra; with the current `uv`/lock format it resolved
  `halide v21.0.0` but did not persist a separate optional-extra entry in
  `uv.lock`.
- The current real Halide JIT kernels are:
  - 3x3 RGB/XYZ matrix conversion through the color kernel dispatch.
  - 3D trilinear LUT sampling through `apply_lut_trilinear_3d_backend()`.
- Generic eager array operations still delegate to NumPy because Halide is a staged DSL, not an eager ndarray replacement.

## Research Conclusion

Official Halide docs support the chosen incremental path:

- The Python bindings expose `Func`, `ImageParam`, `Buffer`, `realize()`, Generator APIs, and zero-copy-compatible Buffer protocol semantics.
- Halide's CMake package supports JIT and AOT via `add_halide_library()` and Python extension helpers.
- The GPU tutorial uses explicit target probing and per-`Func` schedules; this argues against hiding Halide behind `auto`.
- Autoscheduler use needs estimates and is best kept for a later AOT/generator phase.

References:

- [Halide Python bindings](https://halide-lang.org/docs/md_doc_2_python.html)
- [Halide CMake package](https://halide-lang.org/docs/md_doc_2_halide_c_make_package.html)
- [Halide GPU tutorial](https://halide-lang.org/tutorials/tutorial_lesson_12_using_the_gpu.html)
- [Halide autoscheduler tutorial](https://halide-lang.org/tutorials/tutorial_lesson_21_auto_scheduler_generate.html)
- [halide 21.0.0 on PyPI](https://pypi.org/project/halide/21.0.0/)

## Implementation Boundary

This is not a full pipeline rewrite. The safe boundary is:

1. Keep `NumpyBackend` as the numerical reference.
2. Keep MLX/CuPy paths unchanged.
3. Use Halide only where a focused parity test proves the kernel is active and correct.
4. Preserve float32 parity at `rtol/atol` around `1e-6`.
5. Treat Android AOT as a generator/CMake integration path, not as a Python runtime JIT path.

## Files

- `src/spektrafilm/gpu/halide_backend.py`: optional Halide backend and cached JIT kernels.
- `src/spektrafilm/gpu/backend.py`: backend selection accepts strict `halide`.
- `src/spektrafilm/gpu/kernels/color.py`: uses the Halide RGB matrix specialization when present.
- `src/spektrafilm/gpu/kernels/lut.py`: dispatches 3D trilinear LUT sampling to the Halide helper when present.
- `src/spektrafilm/halide/availability.py`: lightweight optional dependency probe.
- `src/spektrafilm/halide/android.py`: tested Android ABI to Halide target/CMake contract helpers.

## Verification

Targeted checks:

```bash
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_android.py -q
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_lut.py -q
.venv/bin/python -m pytest tests/test_runtime_api.py::TestRuntimeApi::test_float64_runtime_precision_rejects_explicit_gpu_backend -q
```

Final gate should still include:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m compileall src/spektrafilm tests
git diff --check
```

## Next Work

- Port separable Gaussian FIR to Halide with reflect boundary parity tests.
- Move 1D density interpolation to Halide after LUT parity stays stable.
- Add Generator/AOT outputs for the two shipped kernels before attempting Android JNI.
- Benchmark first-run JIT latency separately from warmed steady-state execution.
