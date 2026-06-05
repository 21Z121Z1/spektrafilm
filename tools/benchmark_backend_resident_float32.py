#!/usr/bin/env python3
"""P1 benchmark for backend-resident float32 materialization policies."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_OUT_DIR = ROOT / "docs" / "reports"


@dataclass(frozen=True)
class BenchmarkCase:
    label: str
    compute_backend: str
    gpu_precision: str
    materialize_policy: str


def parse_shape(value: str) -> tuple[int, int]:
    normalized = value.strip().lower()
    if "x" not in normalized:
        raise ValueError("shape must be WIDTHxHEIGHT")
    width_text, height_text = normalized.split("x", 1)
    width = int(width_text)
    height = int(height_text)
    if width <= 0 or height <= 0:
        raise ValueError("shape dimensions must be positive")
    return width, height


def generated_image(shape: tuple[int, int]) -> np.ndarray:
    width, height = shape
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (height, width))
    yy = np.broadcast_to(y, (height, width))
    return np.stack(
        (
            0.02 + 1.18 * xx,
            0.02 + 1.18 * yy,
            0.05 + 0.75 * (xx + yy),
        ),
        axis=-1,
    ).astype(np.float32, copy=False)


def build_cases(backend: str, precision: str) -> list[BenchmarkCase]:
    cases = [BenchmarkCase("cpu_default", "cpu", "float32", "numpy_float64")]
    if backend in {"all", "mlx"}:
        cases.extend(
            [
                BenchmarkCase("mlx_numpy_float64", "mlx", precision, "numpy_float64"),
                BenchmarkCase("mlx_numpy_float32", "mlx", precision, "numpy_float32"),
                BenchmarkCase("mlx_backend", "mlx", precision, "backend"),
            ]
        )
    if backend == "cpu":
        return cases
    return cases


def build_params(case: BenchmarkCase):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.scan_film = False
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.film_render.grain.active = False
    params.film_render.halation.boost_ev = 1.5
    params.film_render.halation.boost_range = 0.35
    params.film_render.halation.protect_ev = 0.0
    params.settings.compute_backend = case.compute_backend
    params.settings.gpu_precision = case.gpu_precision
    params.settings.materialize_policy = case.materialize_policy
    params.settings.gpu_validate = False
    params.settings.preview_mode = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.use_fast_stats = True
    return digest_params(params)


def describe_array(value: Any) -> dict[str, Any]:
    module = type(value).__module__
    if isinstance(value, np.ndarray):
        type_name = "numpy.ndarray"
        backend = "numpy"
    elif module.startswith("mlx."):
        type_name = f"{module}.{type(value).__qualname__}"
        backend = "mlx"
    else:
        type_name = f"{module}.{type(value).__qualname__}"
        backend = module.split(".", 1)[0]
    return {
        "type": type_name,
        "backend": backend,
        "shape": [int(dim) for dim in getattr(value, "shape", [])],
        "dtype": str(getattr(value, "dtype", "")),
        "nbytes": int(getattr(value, "nbytes", 0) or 0),
    }


def backend_available(case: BenchmarkCase) -> tuple[bool, str | None]:
    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend

    try:
        select_backend(case.compute_backend, precision=case.gpu_precision)
    except (BackendUnavailableError, RuntimeError, OSError, ValueError, ModuleNotFoundError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def sync_backend(backend: Any, value: Any) -> float:
    start = time.perf_counter()
    eval_fn = getattr(backend, "eval", None)
    if callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()
    return time.perf_counter() - start


def explicit_to_numpy(backend: Any, value: Any) -> tuple[np.ndarray, float]:
    start = time.perf_counter()
    to_numpy = getattr(backend, "to_numpy", None)
    if callable(to_numpy):
        converted = to_numpy(value)
    else:
        converted = np.asarray(value)
    return np.asarray(converted), time.perf_counter() - start


def run_case(
    image: np.ndarray,
    case: BenchmarkCase,
    *,
    warmups: int,
    runs: int,
    cpu_reference: np.ndarray | None,
) -> dict[str, Any]:
    from spektrafilm.runtime.pipeline import SimulationPipeline

    available, reason = backend_available(case)
    if not available:
        return {
            "label": case.label,
            "status": "skipped",
            "case": case.__dict__,
            "reason": reason,
        }

    params = build_params(case)
    pipeline = SimulationPipeline(params)

    warmup_seconds: list[float] = []
    for _ in range(max(0, warmups)):
        start = time.perf_counter()
        warmup_result = pipeline.process(image)
        sync_backend(pipeline._backend, warmup_result)
        warmup_seconds.append(time.perf_counter() - start)

    measured: list[dict[str, Any]] = []
    for _ in range(max(1, runs)):
        start = time.perf_counter()
        result = pipeline.process(image)
        sync_seconds = sync_backend(pipeline._backend, result)
        wall_seconds = time.perf_counter() - start
        output = describe_array(result)
        numpy_result, explicit_numpy_seconds = explicit_to_numpy(pipeline._backend, result)
        finite = bool(np.all(np.isfinite(numpy_result)))
        max_abs_diff = None
        if cpu_reference is not None:
            max_abs_diff = float(np.max(np.abs(numpy_result.astype(np.float64) - cpu_reference)))
        measured.append(
            {
                "wall_seconds": wall_seconds,
                "sync_seconds": sync_seconds,
                "explicit_numpy_seconds": explicit_numpy_seconds,
                "pipeline_total_seconds": pipeline.get_total_elapsed_time(),
                "timings": {str(k): float(v) for k, v in pipeline.get_timings().items()},
                "output": output,
                "numpy_dtype_after_explicit_conversion": str(numpy_result.dtype),
                "finite_after_explicit_conversion": finite,
                "max_abs_diff_vs_cpu": max_abs_diff,
            }
        )

    wall_values = [row["wall_seconds"] for row in measured]
    materialize_values = [
        float(row["timings"].get("SimulationPipeline.materialize", 0.0))
        for row in measured
    ]
    sync_values = [float(row["sync_seconds"]) for row in measured]
    explicit_numpy_values = [float(row["explicit_numpy_seconds"]) for row in measured]
    return {
        "label": case.label,
        "status": "ok",
        "case": case.__dict__,
        "backend_selected": getattr(pipeline._backend, "name", case.compute_backend),
        "supports_gpu": bool(getattr(pipeline._backend, "supports_gpu", False)),
        "requires_serial_runtime": bool(getattr(pipeline._backend, "requires_serial_runtime", False)),
        "warmup_seconds": warmup_seconds,
        "runs": measured,
        "summary": {
            "median_wall_seconds": statistics.median(wall_values),
            "min_wall_seconds": min(wall_values),
            "max_wall_seconds": max(wall_values),
            "median_materialize_seconds": statistics.median(materialize_values),
            "median_sync_seconds": statistics.median(sync_values),
            "median_explicit_numpy_seconds": statistics.median(explicit_numpy_values),
        },
    }


def cpu_reference_for(image: np.ndarray) -> np.ndarray:
    case = BenchmarkCase("cpu_reference", "cpu", "float32", "numpy_float64")
    from spektrafilm.runtime.pipeline import SimulationPipeline

    return np.asarray(SimulationPipeline(build_params(case)).process(image), dtype=np.float64)


def summarize(payload: dict[str, Any]) -> None:
    ok_runs = {run["label"]: run for run in payload["runs"] if run["status"] == "ok"}
    cpu = ok_runs.get("cpu_default")
    if cpu is None:
        return
    cpu_median = float(cpu["summary"]["median_wall_seconds"])
    for label, run in ok_runs.items():
        median = float(run["summary"]["median_wall_seconds"])
        run["summary"]["speedup_vs_cpu_default"] = cpu_median / median if median > 0 else None


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Backend Resident Float32 P1 Benchmark - {payload['run_id']}",
        "",
        f"- Image source: `{payload['image_source']}`",
        f"- Image shape: `{payload['image_shape']}`",
        f"- Image dtype: `{payload['image_dtype']}`",
        f"- Warmups: `{payload['warmups']}`",
        f"- Runs: `{payload['runs_per_case']}`",
        "",
        "## Summary",
        "",
        "| Case | Status | Backend | Policy | Output | Median Wall | Materialize | Sync | Explicit NumPy | Max Abs Diff vs CPU |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for run in payload["runs"]:
        case = run["case"]
        if run["status"] != "ok":
            lines.append(
                f"| {run['label']} | {run['status']} | {case['compute_backend']} | "
                f"{case['materialize_policy']} |  |  |  |  |  | {run.get('reason', '')} |"
            )
            continue
        first = run["runs"][0]
        output = first["output"]
        diff = first["max_abs_diff_vs_cpu"]
        diff_text = "" if diff is None else f"{diff:.6g}"
        summary = run["summary"]
        lines.append(
            f"| {run['label']} | ok | {run['backend_selected']} | {case['materialize_policy']} | "
            f"{output['type']} {output['dtype']} | "
            f"{summary['median_wall_seconds']:.6f}s | "
            f"{summary['median_materialize_seconds']:.6f}s | "
            f"{summary['median_sync_seconds']:.6f}s | "
            f"{summary['median_explicit_numpy_seconds']:.6f}s | {diff_text} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `SimulationPipeline.materialize` records pipeline policy cost.",
            "- `Sync` is an explicit benchmark-side backend eval/synchronize after `process()`.",
            "- `Explicit NumPy` is a benchmark-side conversion for validation/export-style inspection.",
            "- This P1 benchmark is a residency/materialization diagnostic, not a 12MP RAW performance proof.",
            "",
        ]
    )
    return "\n".join(lines)


def write_outputs(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"backend-resident-float32-p1-benchmark-{payload['run_id']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    image = generated_image(parse_shape(args.shape))
    reference = cpu_reference_for(image)
    cases = build_cases(args.backend, args.precision)
    payload = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "image_source": "generated",
        "image_shape": [int(dim) for dim in image.shape],
        "image_dtype": str(image.dtype),
        "warmups": int(args.warmups),
        "runs_per_case": int(args.runs),
        "runs": [
            run_case(
                image,
                case,
                warmups=int(args.warmups),
                runs=int(args.runs),
                cpu_reference=reference,
            )
            for case in cases
        ],
    }
    summarize(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("all", "cpu", "mlx"), default="all")
    parser.add_argument("--precision", default="float32")
    parser.add_argument("--shape", default="512x384")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args(argv)

    payload = run_benchmark(args)
    if not args.no_write:
        json_path, md_path = write_outputs(payload, args.out_dir)
        print(f"Wrote {json_path}")
        print(f"Wrote {md_path}")
    print(format_markdown(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
