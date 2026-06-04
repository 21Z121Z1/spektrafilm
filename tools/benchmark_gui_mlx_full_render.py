#!/usr/bin/env python3
"""Benchmark the GUI-like Spektrafilm full-render worker path."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_OUT_DIR = ROOT / "docs" / "reports"


def parse_size(value: str) -> tuple[int, int] | None:
    normalized = value.strip().lower()
    if normalized == "full":
        return None
    if "x" not in normalized:
        raise ValueError("size must be 'full' or WIDTHxHEIGHT")
    width_text, height_text = normalized.split("x", 1)
    width = int(width_text)
    height = int(height_text)
    if width <= 0 or height <= 0:
        raise ValueError("size dimensions must be positive")
    return width, height


def summarize_seconds(values: list[float]) -> dict[str, float]:
    if not values:
        return {"median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "median": float(statistics.median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def array_nbytes(value: object | None) -> int:
    if value is None:
        return 0
    nbytes = getattr(value, "nbytes", None)
    if nbytes is not None:
        return int(nbytes)
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is None or dtype is None:
        return 0
    try:
        return int(np.prod(tuple(int(dim) for dim in shape)) * np.dtype(dtype).itemsize)
    except (TypeError, ValueError):
        return 0


def generated_image(size: tuple[int, int] | None) -> np.ndarray:
    width, height = size or (1600, 1200)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    return np.stack(
        [
            0.05 + 0.90 * np.broadcast_to(x, (height, width)),
            0.05 + 0.90 * np.broadcast_to(y, (height, width)),
            0.10 + 0.45 * (np.broadcast_to(x, (height, width)) + np.broadcast_to(y, (height, width))),
        ],
        axis=-1,
    ).astype(np.float32, copy=False)


def build_params(*, backend: str, precision: str):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.camera.auto_exposure = False
    params.film_render.grain.active = False
    params.debug.deactivate_stochastic_effects = True
    params.debug.print_timings = False
    params.settings.compute_backend = backend
    params.settings.gpu_precision = precision
    params.settings.gpu_validate = False
    params.settings.preview_mode = False
    params.settings.use_fast_stats = True
    params.settings.use_enlarger_lut = True
    params.settings.use_scanner_lut = True
    params.settings.lut_resolution = 17
    return digest_params(params)


def run_once(source_image: np.ndarray, params) -> dict[str, Any]:
    from spektrafilm.runtime.pipeline import SimulationPipeline
    from spektrafilm_gui import controller_runtime
    from spektrafilm_gui.controller import _prepare_simulation_input_image

    simulator = SimulationPipeline(params)
    image, phase_timings, memory_estimates = _prepare_simulation_input_image(source_image, params)
    request = controller_runtime.SimulationRequest(
        mode_label="Scan",
        image=image,
        params=params,
        output_color_space=params.io.output_color_space,
        output_cctf_encoding=params.io.output_cctf_encoding,
        use_display_transform=False,
        phase_timings=phase_timings,
        memory_estimates=memory_estimates,
        require_hdr_metadata=False,
    )

    def run_simulation(runtime_image, _params):
        return simulator.process(runtime_image)

    def prepare_display(runtime_image, **kwargs):
        return controller_runtime.prepare_output_display_image(
            runtime_image,
            imagecms_module=SimpleNamespace(PyCMSError=RuntimeError),
            colour_module=SimpleNamespace(),
            pil_image_module=SimpleNamespace(),
            **kwargs,
        )

    start = time.perf_counter()
    result = controller_runtime.execute_simulation_request(
        request,
        run_simulation_fn=run_simulation,
        prepare_output_display_image_fn=prepare_display,
        runtime_status_fn=simulator.backend_runtime_summary,
        runtime_timings_fn=lambda: dict(simulator.get_timings()),
    )
    wall_seconds = time.perf_counter() - start
    return {
        "status": "ok",
        "wall_seconds": wall_seconds,
        "phase_timings": dict(result.phase_timings),
        "runtime_stage_timings": dict(result.runtime_stage_timings),
        "memory_estimates": dict(result.memory_estimates),
        "display_shape": list(result.display_image.shape),
        "display_dtype": str(result.display_image.dtype),
        "float_shape": list(result.float_image.shape),
        "float_dtype": str(result.float_image.dtype),
        "status_message": result.status_message,
    }


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    size = parse_size(args.size)
    source_image = generated_image(size)
    params = build_params(backend=args.backend, precision=args.precision)
    measured: list[dict[str, Any]] = []
    warmups: list[dict[str, Any]] = []

    try:
        for _ in range(max(0, int(args.warmups))):
            warmups.append(run_once(source_image, params))
        for _ in range(max(1, int(args.runs))):
            measured.append(run_once(source_image, params))
    except Exception as exc:
        return {
            "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
            "status": "failed",
            "backend": args.backend,
            "precision": args.precision,
            "error": f"{type(exc).__name__}: {exc}",
        }

    wall_values = [float(run["wall_seconds"]) for run in measured]
    phase_keys = sorted({key for run in measured for key in run["phase_timings"]})
    phase_summary = {
        key: summarize_seconds([float(run["phase_timings"].get(key, 0.0)) for run in measured])
        for key in phase_keys
    }
    return {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "status": "ok",
        "backend": args.backend,
        "precision": args.precision,
        "size": args.size,
        "input": {
            "shape": list(source_image.shape),
            "dtype": str(source_image.dtype),
            "nbytes": array_nbytes(source_image),
        },
        "warmups": warmups,
        "runs": measured,
        "wall_seconds": summarize_seconds(wall_values),
        "phase_summary": phase_summary,
    }


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# GUI MLX Full Render Benchmark - {payload['run_id']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Backend: `{payload.get('backend')}`",
        f"- Precision: `{payload.get('precision')}`",
    ]
    if payload["status"] != "ok":
        lines.append(f"- Error: `{payload.get('error')}`")
        return "\n".join(lines) + "\n"

    lines.extend(
        [
            f"- Input shape: `{payload['input']['shape']}`",
            f"- Input dtype: `{payload['input']['dtype']}`",
            f"- Input nbytes: `{payload['input']['nbytes']}`",
            "",
            "## Wall Time",
            "",
            "| Metric | Seconds |",
            "|---|---:|",
        ]
    )
    for key, value in payload["wall_seconds"].items():
        lines.append(f"| {key} | {float(value):.6f} |")

    lines.extend(["", "## GUI Phase Timings", "", "| Phase | Median | Min | Max |", "|---|---:|---:|---:|"])
    for key, summary in payload["phase_summary"].items():
        lines.append(
            f"| {key} | {summary['median']:.6f} | {summary['min']:.6f} | {summary['max']:.6f} |"
        )

    last_run = payload["runs"][-1]
    lines.extend(["", "## Last Run Runtime Stages", "", "| Stage | Seconds |", "|---|---:|"])
    for key, value in last_run.get("runtime_stage_timings", {}).items():
        lines.append(f"| {key} | {float(value):.6f} |")

    lines.extend(["", "## Last Run Memory Estimates", "", "| Key | Bytes |", "|---|---:|"])
    for key, value in last_run.get("memory_estimates", {}).items():
        lines.append(f"| {key} | {int(value)} |")

    return "\n".join(lines) + "\n"


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    backend = str(payload.get("backend", "run")).replace("/", "-")
    json_path = out_dir / f"gui-mlx-full-render-benchmark-20260604-{backend}.json"
    md_path = out_dir / f"gui-mlx-full-render-benchmark-20260604-{backend}.md"
    markdown = format_markdown(payload)
    json_text = json.dumps(payload, indent=2)
    json_path.write_text(json_text, encoding="utf-8")
    md_path.write_text(markdown, encoding="utf-8")
    (out_dir / "gui-mlx-full-render-benchmark-20260604.json").write_text(json_text, encoding="utf-8")
    (out_dir / "gui-mlx-full-render-benchmark-20260604.md").write_text(markdown, encoding="utf-8")
    return json_path, md_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("cpu", "mlx"), default="cpu")
    parser.add_argument("--precision", default=None)
    parser.add_argument("--size", default="512x384")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    if args.precision is None:
        args.precision = "float64" if args.backend == "cpu" else "float32"
    payload = run_benchmark(args)
    json_path, md_path = write_artifacts(payload, Path(args.out_dir))
    print(f"Wrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    if payload["status"] != "ok":
        print(payload["error"])
        return 1
    return 0


__all__ = [
    "array_nbytes",
    "format_markdown",
    "parse_size",
    "run_benchmark",
    "summarize_seconds",
]


if __name__ == "__main__":
    raise SystemExit(main())
