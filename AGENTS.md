# Spektrafilm - Developer & Agent Guidelines

## Project Overview
Spectral simulation of analog film photography. Python 3.13+, Qt GUI, GPU backends (MLX/CuPy).

## Environment & Commands
- Dependencies: Install with `uv sync`
- Standard tests: Run `.venv/bin/python -m pytest --ignore=tests/gui -q` (GUI tests require display and QApplication, skipped in headless environments)

## Development Principles
- **Read Docs First**: Always refer to `docs/README.md` for the current documentation index and project architecture.
- **Scope Limits**: Do not modify files outside `src/`, `tests/`, `docs/`, `README.md`, and `pyproject.toml` unless explicitly requested.
- **SDR Parity**: Do not break or change default SDR output behaviors. Preserve existing behavior for working CPU/NumPy paths.
- **No Private Artifacts**: Avoid committing generated outputs, logs, debug scripts, or temporary test images.
- **Targeted Changes**: Keep changes minimal, clean, and targeted to the task.

## GPU Acceleration - Parity Constraint
**ZERO precision/quality loss.** GPU output must be numerically identical (or within float32 epsilon) to CPU/NumPy output. This means:
- No approximations, no "close enough", no lossy optimizations.
- Use `float32` throughout (no float16 unless explicitly opted in by user).
- Same algorithms and order of operations where possible.
- Every GPU kernel implementation must have a corresponding test asserting `np.allclose(gpu_result, cpu_result, atol=1e-6)`.
- If a GPU backend cannot match CPU precision, fall back to CPU for that operation.
- Results must be deterministic and bit-identical across backends.
