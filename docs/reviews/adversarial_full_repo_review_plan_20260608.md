# Adversarial Full-Repository Review Plan - 2026-06-08

## Objective

Run a full-current-state adversarial review of the Spektrafilm workspace at `/Users/retriedstormtrooper/Documents/Projects/Active/spektrafilm-main`. The review is evidence-driven and covers correctness, HDR/color/image semantics, performance, memory, platform compatibility, security/robustness, test coverage, documentation drift, and maintainability. This is a review-only task: no production code, tests, configuration, or existing documentation may be modified.

## Allowed Writes

Only the following review artifacts may be created or updated:

- `docs/reviews/adversarial_full_repo_review_plan_20260608.md`
- `docs/reviews/adversarial_full_repo_review_20260608.md`
- `docs/reviews/adversarial_full_repo_findings_20260608.json`

No commits, pushes, cleanups, baseline regeneration, formatting rewrites, code fixes, or project restructuring are allowed.

## Initial Repository State To Record

- Branch: `develop`
- HEAD at planning time: `48655e1 feat: implement MLX backend-resident float32 P1 foundation and initiate HDR routemaster rewrite`
- Branch relation: `develop...origin/develop [ahead 3]`
- Remotes: `origin` and `upstream`
- Dirty worktree at planning time: 36 modified tracked files and 25 untracked files
- Tracked files: 1247
- Non-excluded filesystem files: approximately 1312
- Program source/test/script/platform files: approximately 266 files, about 69k lines
- Test collection: `.venv/bin/python -m pytest --ignore=tests/gui --collect-only -q` collected 1435 tests

The review target is the current dirty workspace, not only `HEAD` and not only a recent diff. Findings may therefore apply to uncommitted local work.

## Scope

Include by default:

- Python runtime, model, HDR, color, image I/O, RAW/DNG, GPU, Halide, GUI, and LUT creator code under `src/`
- Python tests under `tests/`
- Scripts and tools under `scripts/` and `tools/`
- Android Kotlin/C++/JNI/build/test surfaces under `android/`
- macOS Swift/Python-bridge/build/test surfaces under `macos/`
- Project configuration: `pyproject.toml`, `pytest.ini`, `uv.lock`, Gradle/Xcode/Swift package files, shell scripts, `.gitignore`
- Documentation that claims current behavior: `README.md`, `AGENTS.md`, `docs/README.md`, `docs/dev/README.md`, `docs/agent_audit/**`, active plans/reports, HDR/GPU/color docs
- Runtime data contracts and resource manifests: profile JSON, ICC/data READMEs, HDR curve-profile JSON/README, small calibration data

Review as inventory or sampled data rather than line-by-line source:

- Large generated curve-analysis reports and generated benchmark result files
- ICC binary profiles and static LUT/profile assets
- Android AOT static libraries and Gradle wrapper binaries
- Image assets

## Exclusions

Exclude from line-by-line review, while listing the path/reason in the final report:

- `.git/`: repository internals
- `.venv/`: local virtual environment
- `__pycache__/`, `.pytest_cache/`, `.mypy_cache/`, `.ruff_cache/`, `.tox/`, `.nox/`: generated caches
- Build artifacts such as `build/`, `dist/`, Android/Gradle build intermediates, and Xcode derived products
- `.DS_Store`: operating-system metadata
- Large binary/generated assets where source review is not meaningful, including Android AOT `.a` files, Gradle wrapper JAR, ICC binary profiles, `.npz` baselines, image assets, and generated benchmark/result corpora

Excluded binary/data resources still require inventory-level review for packaging risk, provenance, test dependency, and documentation consistency.

## Review Shards

Use parallel read-only subagents for bounded shards. The main agent owns final evidence calibration, duplicate merging, severity decisions, report writing, and no-edit enforcement.

1. Runtime/model core: public API, params, topology, film/print/scan stages, profile loading, core math.
2. HDR/color/I/O: RouteMaster, HDR projection, `HDRPhotoMapping`, gain maps, HEIC/EXR/PNG/JPEG/TIFF, ICC, RAW/DNG, Apple metadata.
3. GPU/backends: backend selection, MLX/CuPy/Halide, kernels, residency/materialization, precision contract, benchmarks.
4. GUI: controller, state/persistence, display transform, HDR export wiring, layer/output flow, Qt/napari platform assumptions.
5. LUT creator: bundle builder, color-space registry, topology outputs, file formats, OCIO, QA suite, CLI.
6. Android/macOS: Kotlin UI/viewmodel/processor, JNI/C++/AOT pipeline, Swift macOS shell, Python bridge, packaging/build contracts.
7. Tests/docs/security/tools: test inventory and quality, docs drift, subprocess/temp/path handling, dependency/config/CI gaps, resource-exhaustion risks.

Each shard must return: covered files, file responsibilities, entry points, implicit assumptions, checked failure modes, candidate findings with evidence, and low-confidence areas.

## Evidence Rules

Every finding must include:

- Severity: Critical, High, Medium, Low, or Nit
- Category: Correctness, HDR-Color, Performance, Memory, Platform, Security, Test, Docs, or Maintainability
- Path and precise line/function when possible
- Evidence from code, call chain, test gap, docs mismatch, or command output
- Trigger condition
- User-visible impact
- Why existing tests did not block it
- Recommended fix direction
- Recommended validation
- Confidence: High, Medium, or Low

Speculative items must be marked `Hypothesis` and must state the additional proof required.

## Severity Rubric

- Critical: likely data loss, destructive output, security exposure, core pipeline semantic break, wrong HDR/SDR result in important workflows, or severe user-file corruption.
- High: common workflow produces wrong results, critical feature unreliable, major platform unavailable, or severe avoidable performance/memory regression.
- Medium: edge-case wrong result, meaningful test gap, platform/tooling fragility, or maintainability debt likely to cause regression.
- Low: localized quality, documentation, compatibility, or maintainability issue with limited blast radius.
- Nit: naming, comments, style, or small cleanup recommendation.

## Validation Commands

Run safe commands where feasible and record pass/fail/skip, stdout/stderr summary, duration, and credibility impact:

```bash
git status --short --branch --untracked-files=all
git remote -v
git log -1 --oneline --decorate --show-signature
git ls-files
git ls-files --others --exclude-standard
.venv/bin/python -m pytest --ignore=tests/gui --collect-only -q
.venv/bin/python -m pytest --ignore=tests/gui -q
.venv/bin/python -m pytest tests/test_hdr_photo.py tests/test_gain_map.py tests/test_image_io_color_metadata.py tests/test_hdr_routemaster_projection.py tests/test_hdr_routemaster_export.py -q
.venv/bin/python -m pytest tests/test_gpu_backend.py tests/test_gpu_primitives.py tests/test_gpu_density.py tests/test_gpu_lut.py tests/test_gpu_filters.py tests/test_gpu_color_chain.py tests/test_gpu_validate.py tests/test_gpu_pipeline.py tests/test_runtime_materialize_policy.py tests/test_backend_resident_float32.py tests/test_backend_resident_runtime_boundaries.py tests/test_backend_resident_p4_hdr_grain.py -q
.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_generators.py tests/test_halide_filters.py tests/test_halide_lut.py tests/test_halide_color.py tests/test_halide_spectral.py tests/test_halide_android.py tests/test_halide_mlx_benchmark.py -q
.venv/bin/python -m pytest tests/lut_creator tests/test_runtime_api.py tests/test_pipeline_smoke.py tests/test_raw_file_processor.py tests/test_profiles.py -q
.venv/bin/python -m pytest tests/gui -q
cd android && ./gradlew test
swift test --package-path macos/SpektrafilmMac
.venv/bin/python -c "import spektrafilm; import spektrafilm_gui.macos_bridge; print('import-ok')"
.venv/bin/python -m spektrafilm_gui.macos_bridge describe
```

Also run static searches for subprocess/shell/tempfile/path traversal, broad exception swallowing, full-frame materialization, dtype casts, clipping, CCTF/gamma/linear transitions, HDR/gain-map/ICC metadata, CoreGraphics/ImageIO/ctypes, and platform guards.

## Final Artifacts

The main Markdown report must contain:

- Executive Summary
- Repository State
- Review Scope and Exclusions
- Architecture Map
- Critical Invariants
- Top 10 Highest-Risk Findings
- Findings by Severity
- Findings by Subsystem
- Per-File Review Notes
- Test Coverage Gaps
- Performance Hotspots
- HDR/Color Pipeline Risks
- Platform Compatibility Risks
- Security/Robustness Risks
- Documentation Drift
- Recommended Fix Roadmap
- Commands Run and Results
- Open Questions / Low-Confidence Areas
- Final Confidence Statement

The JSON finding index must be an array of objects with:

`id`, `severity`, `category`, `path`, `symbol`, `line_start`, `line_end`, `title`, `evidence`, `impact`, `trigger`, `recommendation`, `validation`, `confidence`.

## Closure Checklist

- Plan artifact exists before main report work.
- Dirty worktree state is recorded without modification.
- Every in-scope source/test/script/platform file has either a review note or explicit exclusion.
- Every Critical/High finding has an adversarial false-positive check.
- Commands and platform skips are recorded with credibility impact.
- Only `docs/reviews/` files were written.
