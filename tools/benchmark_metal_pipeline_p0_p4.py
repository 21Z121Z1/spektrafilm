#!/usr/bin/env python3
"""Benchmark the P0-P4 Metal/MLX pipeline materialization policies."""

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
    x = np.linspace(0.02, 0.98, width, dtype=np.float32)[None, :]
    y = np.linspace(0.02, 0.98, height, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (height, width))
    yy = np.broadcast_to(y, (height, width))
    return np.stack(
        (
            0.05 + 0.80 * xx,
            0.05 + 0.80 * yy,
            0.10 + 0.40 * (xx + yy),
        ),
        axis=-1,
    ).astype(np.float32)


def load_image(path: Path | None, shape: tuple[int, int]) -> tuple[np.ndarray, str]:
    if path is None:
        return generated_image(shape), "generated"
    if not path.exists():
        raise FileNotFoundError(path)
    from spektrafilm.utils.io import load_image_oiio

    return np.asarray(load_image_oiio(str(path)), dtype=np.float32)[..., :3], str(path)


def build_cases(backend: str, precision: str) -> list[BenchmarkCase]:
    cases = [BenchmarkCase("cpu_baseline", "cpu", "float32", "numpy_float64")]
    if backend in {"all", "mlx"}:
        cases.extend(
            [
                BenchmarkCase("mlx_numpy_float64", "mlx", precision, "numpy_float64"),
                BenchmarkCase("mlx_backend_resident", "mlx", precision, "backend"),
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
    params.settings.compute_backend = case.compute_backend
    params.settings.gpu_precision = case.gpu_precision
    params.settings.materialize_policy = case.materialize_policy
    params.settings.gpu_validate = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.use_fast_stats = True
    return digest_params(params)


def describe_array(value: Any) -> dict[str, Any]:
    module = type(value).__module__
    type_name = f"{module}.{type(value).__qualname__}"
    if isinstance(value, np.ndarray):
        backend = "numpy"
        type_name = "numpy.ndarray"
    elif module.startswith("mlx."):
        backend = "mlx"
    else:
        backend = module.split(".", 1)[0]
    return {
        "type": type_name,
        "backend": backend,
        "shape": [int(dim) for dim in getattr(value, "shape", [])],
        "dtype": str(getattr(value, "dtype", "")),
    }


def sync_backend(backend: Any, value: Any) -> float:
    start = time.perf_counter()
    eval_fn = getattr(backend, "eval", None)
    if callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()
    return time.perf_counter() - start


def backend_available(case: BenchmarkCase) -> tuple[bool, str | None]:
    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend

    try:
        select_backend(case.compute_backend, precision=case.gpu_precision)
    except (BackendUnavailableError, RuntimeError, OSError, ValueError, ModuleNotFoundError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def run_case(image: np.ndarray, case: BenchmarkCase, *, warmups: int, runs: int) -> dict[str, Any]:
    from spektrafilm.runtime.pipeline import SimulationPipeline

    available, reason = backend_available(case)
    if not available:
        return {
            "label": case.label,
            "status": "skipped",
            "backend_selected": None,
            "reason": reason,
            "case": case.__dict__,
        }

    params = build_params(case)
    pipeline = SimulationPipeline(params)
    warmup_seconds: list[float] = []
    for _ in range(max(0, warmups)):
        start = time.perf_counter()
        result = pipeline.process(image)
        sync_backend(pipeline._backend, result)
        warmup_seconds.append(time.perf_counter() - start)

    measured: list[dict[str, Any]] = []
    for _ in range(max(1, runs)):
        start = time.perf_counter()
        result = pipeline.process(image)
        sync_seconds = sync_backend(pipeline._backend, result)
        wall_seconds = time.perf_counter() - start
        measured.append(
            {
                "wall_seconds": wall_seconds,
                "sync_seconds": sync_seconds,
                "pipeline_total_seconds": pipeline.get_total_elapsed_time(),
                "timings": {str(k): float(v) for k, v in pipeline.get_timings().items()},
                "output": describe_array(result),
            }
        )

    wall_values = [row["wall_seconds"] for row in measured]
    backend = pipeline._backend
    return {
        "label": case.label,
        "status": "ok",
        "case": case.__dict__,
        "backend_selected": getattr(backend, "name", case.compute_backend),
        "supports_gpu": bool(getattr(backend, "supports_gpu", False)),
        "requires_serial_runtime": bool(getattr(backend, "requires_serial_runtime", False)),
        "image_shape": list(image.shape),
        "warmup_seconds": warmup_seconds,
        "runs": measured,
        "summary": {
            "median_seconds": statistics.median(wall_values),
            "min_seconds": min(wall_values),
            "max_seconds": max(wall_values),
        },
    }


def add_speedups(payload: dict[str, Any]) -> None:
    ok_runs = {run["label"]: run for run in payload["runs"] if run["status"] == "ok"}
    cpu = ok_runs.get("cpu_baseline")
    if cpu is None:
        return
    cpu_median = float(cpu["summary"]["median_seconds"])
    for label in ("mlx_numpy_float64", "mlx_backend_resident"):
        run = ok_runs.get(label)
        if run is not None:
            median = float(run["summary"]["median_seconds"])
            run["summary"]["speedup_vs_cpu"] = cpu_median / median if median > 0 else None
    legacy = ok_runs.get("mlx_numpy_float64")
    resident = ok_runs.get("mlx_backend_resident")
    if legacy is not None and resident is not None:
        legacy_median = float(legacy["summary"]["median_seconds"])
        resident_median = float(resident["summary"]["median_seconds"])
        resident["summary"]["speedup_vs_mlx_numpy_float64"] = (
            legacy_median / resident_median if resident_median > 0 else None
        )


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Metal P0-P4 Benchmark - {payload['run_id']}",
        "",
        "## Environment",
        "",
        f"- Image source: `{payload['image']['source']}`",
        f"- Image shape: `{payload['image']['shape']}`",
        f"- Image dtype: `{payload['image']['dtype']}`",
        f"- Warmups: `{payload['config']['warmups']}`",
        f"- Measured runs: `{payload['config']['runs']}`",
        "",
        "## Summary",
        "",
        "| Case | Status | Backend | Policy | Median | Min | Max | Speedup vs CPU | Output |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for run in payload["runs"]:
        case = run["case"]
        if run["status"] != "ok":
            lines.append(
                f"| {run['label']} | skipped | {case['compute_backend']} | "
                f"{case['materialize_policy']} | | | | | {run['reason']} |"
            )
            continue
        summary = run["summary"]
        output = run["runs"][-1]["output"]
        speedup = summary.get("speedup_vs_cpu")
        speedup_text = "" if speedup is None else f"{speedup:.3f}x"
        lines.append(
            f"| {run['label']} | ok | {run['backend_selected']} | "
            f"{case['materialize_policy']} | {summary['median_seconds']:.6f}s | "
            f"{summary['min_seconds']:.6f}s | {summary['max_seconds']:.6f}s | "
            f"{speedup_text} | {output['type']} {output['dtype']} |"
        )

    lines.extend(["", "## Stage Timings", ""])
    for run in payload["runs"]:
        if run["status"] != "ok":
            continue
        last = run["runs"][-1]
        lines.extend([f"### {run['label']}", "", "| Stage | Seconds |", "|---|---:|"])
        desired = (
            "preprocess",
            "filming.expose",
            "filming.develop",
            "printing.expose",
            "printing.develop",
            "scanning.scan",
            "scanning.scan_print",
            "SimulationPipeline.materialize",
        )
        timings = last["timings"]
        for key in desired:
            if key in timings:
                lines.append(f"| {key} | {timings[key]:.6f} |")
        lines.append(f"| gpu_sync | {last['sync_seconds']:.6f} |")
        lines.append(f"| total elapsed | {last['pipeline_total_seconds']:.6f} |")
        lines.append("")

    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- `mlx_numpy_float64` keeps the old public materialization behavior.",
            "- `mlx_backend_resident` returns the backend array and times an explicit benchmark sync after `process()`.",
            "- Resize, metadata, export, GUI texture upload, and GPU validation remain explicit CPU/materialization boundaries.",
        ]
    )
    return "\n".join(lines)


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = payload["run_id"]
    json_path = out_dir / f"metal-p0-p4-benchmark-{stamp}.json"
    md_path = out_dir / f"metal-p0-p4-benchmark-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("all", "cpu", "mlx"), default="all")
    parser.add_argument("--precision", default="float32")
    parser.add_argument("--shape", default="128x128", help="Generated image WIDTHxHEIGHT")
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    shape = parse_shape(args.shape)
    image, source = load_image(args.input, shape)
    payload = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "config": {
            "backend": args.backend,
            "precision": args.precision,
            "warmups": int(args.warmups),
            "runs": int(args.runs),
        },
        "image": {
            "source": source,
            "shape": list(image.shape),
            "dtype": str(image.dtype),
        },
        "runs": [],
    }
    for case in build_cases(args.backend, args.precision):
        print(
            f"Running {case.label}: backend={case.compute_backend} "
            f"precision={case.gpu_precision} policy={case.materialize_policy}",
            flush=True,
        )
        payload["runs"].append(run_case(image, case, warmups=args.warmups, runs=args.runs))
    add_speedups(payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_benchmark(args)
    json_path, md_path = write_artifacts(payload, args.out_dir)
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    return 0


__all__ = [
    "BenchmarkCase",
    "build_cases",
    "describe_array",
    "format_markdown",
    "parse_shape",
    "run_benchmark",
]


if __name__ == "__main__":
    raise SystemExit(main())
