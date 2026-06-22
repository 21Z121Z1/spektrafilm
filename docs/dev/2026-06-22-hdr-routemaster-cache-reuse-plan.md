# HDR RouteMaster Cache Reuse Report

Date: 2026-06-22

## Goal

When HDR HEIC gain-map export is enabled, a full-resolution Scan should request a RouteMaster during the same runtime pass that produces the output image and HDR scene sidecar. The GUI stores that RouteMaster on the output layer so Save -> HEIC can reuse it instead of calling `process_master()` again.

Non-HDR paths remain unchanged:

- Preview requests do not ask for a RouteMaster.
- Standard full-resolution Scan requests do not ask for a RouteMaster unless HDR HEIC gain-map export is enabled.
- PNG/JPEG/TIFF/EXR Save paths do not inspect or pass RouteMaster data.

## Implemented

- Added `route_master` to `SimulationPipelineResult`.
- Added `SimulationPipeline.process_with_master()`, `Simulator.process_with_master()`, and `simulate_with_master()`.
- Kept `process()` and `process_with_metadata()` on their existing pipeline paths.
- Added GUI request/result fields for `require_route_master` and `hdr_mode`.
- Cached the RouteMaster under output layer metadata key `pipeline_route_master`.
- Passed a matching cached master into `export_hdr_heic_from_simulator(master=...)`.
- If a cached master is missing or has a different mode, export falls back to the existing simulator render path.
- Added opt-in timing probes controlled by `SPEKTRAFILM_LOG_SAVE_TIMINGS=1`.
- Replaced HEIC raw pair writing with mmap-backed payload writes and use Swift `.mappedIfSafe` raw reads.

## Verification

- `.venv/bin/python -m pytest tests/test_process_with_master.py tests/test_hdr_routemaster_export.py -q` -> `28 passed`
- `.venv/bin/python -m pytest tests/gui/test_controller_runtime_module.py tests/gui/test_controller_flow.py tests/gui/test_controller_output.py -q` -> `85 passed`
- `.venv/bin/python -m compileall -q src/spektrafilm/runtime src/spektrafilm/hdr src/spektrafilm/utils/hdr_photo.py src/spektrafilm_gui tests/test_process_with_master.py`
- `git diff --check`
- `.venv/bin/python -m pytest --ignore=tests/gui -q` -> `1638 passed, 7 skipped, 4 xfailed, 4 warnings`

Manual macOS HEIC preview validation is still required for the user-facing HDR display check:

- `SPEKTRAFILM_LOG_SAVE_TIMINGS=1` should show `cached_master=True` and `process_master=0.0000s` when Save -> HEIC reuses the Scan cache.
- Preview.app should show the exported HEIC with expected HDR gain-map behavior.
