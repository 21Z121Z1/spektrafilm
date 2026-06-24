from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.memory_budget import estimate_runtime_peak_budget, validate_resize_policy
from spektrafilm.gpu.residency_profile import ProfilingBackendProxy, record_residency_profile

SCENARIOS = (
    ("12MP MLX scan only", {"hdr_mode": None, "sidecar": "minimal", "resize": 1.0}),
    ("12MP MLX HDR light_table", {"hdr_mode": "light_table", "sidecar": "minimal", "resize": 1.0}),
    ("12MP MLX HDR paper generic", {"hdr_mode": "paper", "sidecar": "minimal", "resize": 1.0}),
    ("12MP MLX paper chemical fallback", {"hdr_mode": "paper", "sidecar": "full", "resize": 1.0}),
    ("24MP synthetic scan/projection", {"hdr_mode": "paper", "sidecar": "on_demand", "resize": 1.0, "scale_24mp": True}),
    ("12MP resize policy 1.25", {"hdr_mode": "paper", "sidecar": "minimal", "resize": 1.25}),
)
POLICIES = ("backend", "numpy_float32", "numpy_float64")


def _mib(value: int | None) -> float | None:
    return None if value is None else float(value) / (1024.0 * 1024.0)


def _memory_bytes(backend: Any, getter_name: str) -> int | None:
    mx = getattr(getattr(backend, "_backend", backend), "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, getter_name, None)
        if callable(getter):
            try:
                return int(getter())
            except Exception:
                return None
    return None


def _reset_peak(backend: Any) -> None:
    mx = getattr(getattr(backend, "_backend", backend), "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        reset = getattr(owner, "reset_peak_memory", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                pass
            return


def _synthetic_workload(backend: Any, height: int, width: int, materialize_policy: str, *, final_encoder: bool) -> None:
    ramp = np.linspace(0.0, 1.0, width, dtype=np.float32)
    row = np.stack([ramp, ramp * np.float32(0.75), ramp * np.float32(0.5)], axis=1)
    image = np.broadcast_to(row[None, :, :], (height, width, 3)).copy()
    arr = backend.asarray(image, label="input_upload")
    y = arr[..., 0] * np.float32(0.2126) + arr[..., 1] * np.float32(0.7152) + arr[..., 2] * np.float32(0.0722)
    hdr = backend.maximum(arr * np.float32(1.25), np.float32(0.0))
    backend.eval(hdr, label="projection_eval")
    if materialize_policy != "backend" or final_encoder:
        out = backend.to_numpy(hdr, label="final_encoder_boundary" if final_encoder else "policy_materialize")
        np.ascontiguousarray(out)
    else:
        backend.eval(y, label="route_luminance_eval")
    backend.clear_cache(label="post_run_clear_cache")


def run_benchmark(height: int, width: int, runs: int) -> dict[str, Any]:
    try:
        raw_backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"mlx_available": False, "mlx_unavailable_reason": str(exc), "records": []}
    records: list[dict[str, Any]] = []
    for scenario_name, options in SCENARIOS:
        scenario_height = height * 2 if options.get("scale_24mp") else height
        resize = float(options.get("resize", 1.0))
        for materialize_policy in POLICIES:
            elapsed_runs: list[float] = []
            summaries: list[dict[str, Any]] = []
            warnings: list[str] = []
            resize_allowed, resize_warning = validate_resize_policy(
                compute_backend="mlx",
                materialize_policy=materialize_policy,
                upscale_factor=resize,
                preview_mode=False,
                gpu_resize_policy="warn",
            )
            if resize_warning:
                warnings.append(resize_warning)
            estimate = estimate_runtime_peak_budget(
                height=scenario_height,
                width=width,
                compute_backend="mlx",
                gpu_precision="float32",
                materialize_policy=materialize_policy,
                hdr_mode=options.get("hdr_mode"),
                hdr_route_sidecar_policy=str(options.get("sidecar", "minimal")),
                upscale_factor=resize,
            )
            for _ in range(max(1, runs)):
                _reset_peak(raw_backend)
                backend = ProfilingBackendProxy(raw_backend, label_prefix=scenario_name.replace(" ", "_"))
                start = time.perf_counter()
                with record_residency_profile() as recorder:
                    _synthetic_workload(
                        backend,
                        max(1, int(round(scenario_height * resize))),
                        max(1, int(round(width * resize))),
                        materialize_policy,
                        final_encoder=options.get("hdr_mode") is not None,
                    )
                    elapsed_runs.append(time.perf_counter() - start)
                    recorder.warnings.extend(warnings)
                    summaries.append(recorder.to_json_dict())
            summary = summaries[-1]["summary"] if summaries else {}
            records.append(
                {
                    "scenario": scenario_name,
                    "height": scenario_height,
                    "width": width,
                    "upscale_factor": resize,
                    "materialize_policy": materialize_policy,
                    "hdr_route_sidecar_policy": options.get("sidecar", "minimal"),
                    "wall_clock_median_seconds": statistics.median(elapsed_runs) if elapsed_runs else None,
                    "peak_memory_mib": _mib(_memory_bytes(raw_backend, "get_peak_memory")),
                    "cache_memory_mib": _mib(_memory_bytes(raw_backend, "get_cache_memory")),
                    "to_numpy_count": summary.get("backend.to_numpy", 0),
                    "asarray_count": summary.get("backend.asarray", 0),
                    "eval_count": summary.get("backend.eval", 0),
                    "synchronize_count": summary.get("backend.synchronize", 0),
                    "cleanup_count": summary.get("backend.cleanup", 0),
                    "clear_cache_count": summary.get("backend.clear_cache", 0),
                    "resize_fallback_count": 1 if resize_warning else 0,
                    "route_sidecar_materialization_count": 1 if options.get("sidecar") == "full" and materialize_policy != "backend" else 0,
                    "final_encoder_boundary_materialization": bool(options.get("hdr_mode") is not None),
                    "estimated_peak_mib": estimate.estimated_peak_mib,
                    "warnings": warnings,
                    "policy_stop_reasons": [] if resize_allowed else [resize_warning],
                }
            )
    return {"mlx_available": True, "mlx_unavailable_reason": None, "runs": runs, "records": records}


def write_markdown(payload: dict[str, Any], path: Path) -> None:
    lines = ["# MLX Memory Residency Benchmark", "", f"- `mlx_available`: `{payload.get('mlx_available')}`"]
    if payload.get("mlx_unavailable_reason"):
        lines.append(f"- `mlx_unavailable_reason`: `{payload['mlx_unavailable_reason']}`")
    lines.extend(["", "| Scenario | Policy | Sidecar | Median s | Peak MiB | Cache MiB | to_numpy | asarray | eval | clear_cache | Resize fallback | Encoder boundary |", "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |"])
    for record in payload.get("records", []):
        lines.append(
            f"| {record['scenario']} | {record['materialize_policy']} | {record['hdr_route_sidecar_policy']} | "
            f"{record['wall_clock_median_seconds'] if record['wall_clock_median_seconds'] is not None else 'n/a'} | "
            f"{record['peak_memory_mib'] if record['peak_memory_mib'] is not None else 'n/a'} | "
            f"{record['cache_memory_mib'] if record['cache_memory_mib'] is not None else 'n/a'} | "
            f"{record['to_numpy_count']} | {record['asarray_count']} | {record['eval_count']} | "
            f"{record['clear_cache_count']} | {record['resize_fallback_count']} | {record['final_encoder_boundary_materialization']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    payload = run_benchmark(args.height, args.width, args.runs)
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(payload, args.output_markdown)


if __name__ == "__main__":
    main()
