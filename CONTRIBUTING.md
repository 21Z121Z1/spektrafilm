# Contributing to Spektrafilm

Thank you for your interest in contributing to Spektrafilm. This repository is a development fork of the upstream project [andreavolpato/spektrafilm](https://github.com/andreavolpato/spektrafilm).

Active development and features are integrated and tracked on the `develop` branch of this fork. This guide covers setup, testing, code style, and the numerical precision requirements that apply to all contributions.

## Development Setup

Spektrafilm requires **Python 3.13 or later**. Dependencies are managed with [uv](https://docs.astral.sh/uv/).

To set up your local workspace, clone the fork and sync dependencies:

```bash
git clone https://github.com/21Z121Z1/spektrafilm.git
cd spektrafilm
git checkout develop
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

GUI tests are excluded because they require a running Qt application and display server, which are typically not available in headless environments.

When adding validation or new functionality, include corresponding unit tests in the `tests/` directory.

## Code Style

Follow the patterns established in the codebase:

- **Imports**: use `from __future__ import annotations` at the top of every module.
- **Type hints**: annotate all function signatures and return types.
- **Docstrings**: document public functions and classes with docstrings.
- **Logging**: use the standard `logging` module, not `print` statements.
- **Minimal changes**: keep changes targeted and minimal. Do not refactor surrounding code unless necessary for the specific fix or feature.

## Pull Requests

1. **Branch from `develop`**. The `develop` branch is the active integration branch.
2. **Target `develop`** with your pull request.
3. **All tests must pass** (`.venv/bin/python -m pytest --ignore=tests/gui -q`).
4. Keep each PR focused on a single change. Unrelated changes should be sent in separate PRs.
5. Update documentation if you introduce user-visible behavior changes.

## GPU Precision Policy

We enforce a strict precision policy: GPU output must be **numerically identical** (or within float32 epsilon) to CPU/NumPy output.

The rules:

- **float32 throughout.** Do not use float16 unless explicitly opted in.
- **No approximations.** No lossy optimizations or shortcuts.
- **Algorithm parity.** Same algorithms and order of operations where possible between CPU and GPU paths.
- **Test coverage.** Every GPU kernel must have a matching unit test that asserts:
  ```python
  np.allclose(gpu_result, cpu_result, atol=1e-6)
  ```
- **Fallback.** Fall back to CPU if a GPU backend cannot match CPU precision for a given operation.

## Spectral Film Profiles

Film profile data lives in `src/spektrafilm/data/profiles/`. Each profile is a JSON file describing the spectral characteristics of a specific film stock (e.g. `kodak_portra_400.json`).

If you are adding a new film profile, follow the format and structure of the existing files in that directory.
