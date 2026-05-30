# Contributing to Spektrafilm

Thank you for your interest in contributing to Spektrafilm. This guide covers setup, testing, code style, and the precision requirements that apply to all contributions.

## Development Setup

Spektrafilm requires **Python 3.13 or later**. Dependencies are managed with [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/spektrafilm/spektrafilm.git
cd spektrafilm
uv sync
```

This installs all runtime and development dependencies into `.venv`. Optional backend groups are available:

| Group | Command | Purpose |
|---|---|---|
| `gpu-apple` | `uv sync --extra gpu-apple` | Apple MLX backend |
| `gpu-cuda12` | `uv sync --extra gpu-cuda12` | CUDA 12 via CuPy |
| `halide` | `uv sync --extra halide` | Halide AOT generators |

## Running Tests

All non-GUI tests must pass before submitting a pull request. Use the project virtualenv directly:

```bash
.venv/bin/python -m pytest --ignore=tests/gui -q
```

GUI tests are excluded because they require a running Qt application and display server, which are not available in CI or headless environments.

When adding validation or new functionality, include corresponding tests in the `tests/` directory. Run the full test suite after each change to catch regressions early.

## Code Style

Follow the patterns already established in the codebase:

- **Imports**: use `from __future__ import annotations` at the top of every module.
- **Type hints**: annotate all function signatures and return types.
- **Docstrings**: document public functions and classes with docstrings.
- **Logging**: use the standard `logging` module, not `print` statements.
- **Minimal changes**: fix the specific issue at hand. Do not refactor surrounding code unless it is directly necessary for the fix.

## Pull Requests

1. **Branch from `develop`**. The `develop` branch is the active integration branch; `main` tracks releases.
2. **Target `develop`** with your pull request.
3. **All tests must pass** (`pytest --ignore=tests/gui -q`).
4. Keep each PR focused on a single change or fix. Unrelated changes belong in separate PRs.
5. Update documentation if the user-visible behavior changes.

## GPU Precision Policy

This is a hard constraint, not a guideline. GPU output must be **numerically identical** (or within float32 epsilon) to CPU/NumPy output.

The rules:

- **float32 throughout.** Do not use float16 unless the user has explicitly opted in.
- **No approximations.** No "close enough", no lossy optimizations, no shortcuts.
- **Same algorithms, same order of operations** wherever possible between CPU and GPU paths.
- **Every GPU kernel must have a matching test** that asserts:
  ```python
  np.allclose(gpu_result, cpu_result, atol=1e-6)
  ```
- **Fall back to CPU** if a GPU backend cannot match CPU precision for a given operation.

Results must be deterministic and reproducible across all backends.

## Spectral Film Profiles

Film profile data lives in `src/spektrafilm/data/profiles/`. Each profile is a JSON file describing the spectral characteristics of a specific film stock (e.g. `kodak_portra_400.json`, `fujifilm_velvia_100.json`).

If you are adding a new film profile, follow the format and structure of the existing files in that directory.

## Opening Issues for Large Changes

If your planned contribution involves architectural changes, new backends, pipeline restructuring, or other large-scale work, **open an issue first** to discuss the approach. This avoids investing significant effort in a direction that may not be accepted.
