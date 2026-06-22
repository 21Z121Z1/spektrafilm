#!/usr/bin/env python3
"""Benchmark Spektrafilm's MLX runtime hot path with type tracing."""

import argparse
import functools
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_INPUT = Path("IMG20260530191638.dng")
DEFAULT_OUT_DIR = ROOT / "docs" / "dev" / "benchmark-artifacts" / "mlx_runtime_hotpath_20260602"


@dataclass(frozen=True)
class BenchmarkSpec:
    label: str
    requested_backend: str
    gpu_precision: str
    gpu_validate: bool
    preview_max_size: int | None = None


def parse_size_spec(value: str) -> tuple[int, int] | None:
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


def benchmark_specs(
    *,
    include_preview_640: bool = True,
    only_backend: str = "all",
    include_gpu_validate: bool = True,
) -> list[BenchmarkSpec]:
    specs: list[BenchmarkSpec] = []
    if only_backend in {"all", "cpu"}:
        specs.append(BenchmarkSpec("cpu_full_res", "cpu", "float64", False))
    if only_backend in {"all", "mlx"}:
        specs.append(BenchmarkSpec("mlx_full_res_validate_false", "mlx", "float32", False))
        if include_gpu_validate:
            specs.append(BenchmarkSpec("mlx_full_res_validate_true", "mlx", "float32", True))
    if include_preview_640 and only_backend in {"all", "mlx"}:
        specs.append(BenchmarkSpec("preview_640", "mlx", "float32", False, preview_max_size=640))
    return specs


def describe_array(value: Any) -> dict[str, Any]:
    if value is None:
        return {"type": "None", "backend": "none", "shape": [], "dtype": None, "bytes": 0}

    module = type(value).__module__
    qualname = type(value).__qualname__
    type_name = f"{module}.{qualname}"
    if isinstance(value, np.ndarray):
        type_name = "numpy.ndarray"
        backend = "numpy"
    elif module.startswith("mlx."):
        backend = "mlx"
    else:
        backend = module.split(".", 1)[0]

    shape = [int(dim) for dim in getattr(value, "shape", [])]
    dtype = getattr(value, "dtype", None)
    dtype_text = str(dtype) if dtype is not None else None
    nbytes = getattr(value, "nbytes", None)
    if nbytes is None and shape and dtype_text is not None:
        try:
            nbytes = int(np.prod(shape)) * np.dtype(dtype_text).itemsize
        except TypeError:
            nbytes = None

    return {
        "type": type_name,
        "backend": backend,
        "shape": shape,
        "dtype": dtype_text,
        "bytes": int(nbytes or 0),
    }


class ConversionTrace:
    def __init__(self) -> None:
        self._stats: dict[str, dict[str, int]] = {}

    def reset(self) -> None:
        self._stats.clear()

    def _record(self, key: str, value: Any) -> None:
        info = describe_array(value)
        entry = self._stats.setdefault(key, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += int(info["bytes"] or 0)

    def wrap_backend(self, backend: Any) -> None:
        if getattr(backend, "_spektrafilm_hotpath_benchmark_wrapped", False):
            return
        for method_name in ("asarray", "to_numpy"):
            if not hasattr(backend, method_name):
                continue
            original = getattr(backend, method_name)
            try:
                setattr(backend, method_name, self._wrap_method(f"backend.{method_name}", original))
            except AttributeError:
                self._record(f"backend.{method_name}.wrap_skipped", None)
        try:
            setattr(backend, "_spektrafilm_hotpath_benchmark_wrapped", True)
        except AttributeError:
            pass

    def _wrap_method(self, key: str, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if args:
                self._record(f"{key}.input", args[0])
            result = original(*args, **kwargs)
            self._record(f"{key}.output", result)
            return result

        return wrapped

    def summary(self) -> dict[str, dict[str, int]]:
        return {key: dict(value) for key, value in sorted(self._stats.items())}


def sync_backend(backend: Any, value: Any = None) -> None:
    eval_fn = getattr(backend, "eval", None)
    if value is not None and callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()


def load_input_image(path: Path, fallback_size: tuple[int, int]) -> np.ndarray:
    if path.exists():
        suffix = path.suffix.lower()
        if suffix in {".dng", ".raw", ".nef", ".arw", ".cr2", ".cr3"}:
            from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

            return load_and_process_raw_file(
                str(path),
                white_balance="as_shot",
                output_colorspace="ProPhoto RGB",
                output_cctf_encoding=False,
            )
        from spektrafilm.utils.io import load_image_oiio

        return load_image_oiio(str(path))

    width, height = fallback_size
    x = np.linspace(0.0, 1.0, width, dtype=np.float64)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float64)[:, None]
    return np.stack(
        [
            0.05 + 0.9 * np.broadcast_to(x, (height, width)),
            0.05 + 0.9 * np.broadcast_to(y, (height, width)),
            0.1 + 0.45 * (np.broadcast_to(x, (height, width)) + np.broadcast_to(y, (height, width))),
        ],
        axis=-1,
    )


def resize_image(image: np.ndarray, size: tuple[int, int] | None) -> np.ndarray:
    image = np.asarray(image, dtype=np.float64)
    if size is None:
        return image
    width, height = size
    src_h, src_w = image.shape[:2]
    if (src_w, src_h) == (width, height):
        return image
    try:
        from scipy.ndimage import zoom

        return np.asarray(zoom(image, (height / src_h, width / src_w, 1.0), order=1), dtype=np.float64)
    except Exception:
        from PIL import Image

        pil = Image.fromarray((np.clip(image, 0.0, 1.0) * 65535.0).astype(np.uint16))
        pil = pil.resize((width, height), Image.Resampling.BILINEAR)
        return np.asarray(pil, dtype=np.float64) / 65535.0


def preview_image(image: np.ndarray, max_size: int) -> np.ndarray:
    from spektrafilm.utils.preview import resize_for_preview

    return np.asarray(resize_for_preview(image, max_size), dtype=np.float64)


def build_params(spec: BenchmarkSpec):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = True
    params.camera.auto_exposure = False
    params.film_render.grain.active = False
    params.debug.deactivate_stochastic_effects = True
    params.settings.compute_backend = spec.requested_backend
    params.settings.gpu_precision = spec.gpu_precision
    params.settings.gpu_validate = bool(spec.gpu_validate)
    params.settings.preview_mode = spec.preview_max_size is not None
    params.settings.preview_max_size = int(spec.preview_max_size or params.settings.preview_max_size)
    params.settings.use_fast_stats = True
    params.debug.print_timings = False
    return digest_params(params)


def _wrap_type_trace_methods(sim: Any, rows: list[dict[str, Any]]) -> None:
    def wrap(obj: Any, method_name: str, label: str) -> None:
        if not hasattr(obj, method_name):
            return
        original = getattr(obj, method_name)

        @functools.wraps(original)
        def wrapped(value, *args: Any, **kwargs: Any):
            result = original(value, *args, **kwargs)
            rows.append(
                {
                    "stage": label,
                    "input": describe_array(value),
                    "output": describe_array(result),
                }
            )
            return result

        setattr(obj, method_name, wrapped)

    wrap(sim._filming_stage, "_rgb_to_film_raw", "LUT/spectral compute: filming.tc_lut")
    wrap(sim._printing_stage, "_spectral_compute_enlarger_gpu", "LUT/spectral compute: printing.enlarger")
    wrap(sim._lut_service, "spectral_compute_enlarger", "LUT/spectral compute: lut.enlarger")
    wrap(sim._lut_service, "spectral_compute_scanner", "LUT/spectral compute: lut.scanner")


def run_type_trace(sim: Any, image: np.ndarray) -> list[dict[str, Any]]:
    backend = sim._backend
    rows: list[dict[str, Any]] = []
    _wrap_type_trace_methods(sim, rows)

    def timed(stage: str, fn: Callable[[Any], Any], value: Any) -> Any:
        input_info = describe_array(value)
        start = time.perf_counter()
        result = fn(value)
        sync_backend(backend, result)
        elapsed = time.perf_counter() - start
        rows.append(
            {
                "stage": stage,
                "seconds": elapsed,
                "input": input_info,
                "output": describe_array(result),
            }
        )
        return result

    current = timed("preprocess", sim._preprocess, image.copy())
    log_raw_film = timed("filming.expose", sim._filming_stage.expose, current)
    cmy_film = timed("filming.develop", sim._filming_stage.develop, log_raw_film)
    if sim.io.scan_film:
        rgb_scan = timed("scanning", sim._scanning_stage.scan, cmy_film)
    else:
        log_raw_print = timed("printing.expose", sim._printing_stage.expose, cmy_film)
        cmy_print = timed("printing.develop", sim._printing_stage.develop, log_raw_print)
        rgb_scan = timed("scanning", sim._scanning_stage.scan, cmy_print)

    timed("final.to_numpy_float64", lambda value: np.asarray(backend.to_numpy(value), dtype=np.float64), rgb_scan)
    return rows


def run_benchmark_case(
    source_image: np.ndarray,
    spec: BenchmarkSpec,
    *,
    warmups: int,
    runs: int,
    collect_type_trace: bool,
) -> dict[str, Any]:
    from spektrafilm.gpu.backend import BackendUnavailableError, backend_summary, select_backend
    from spektrafilm.runtime.pipeline import SimulationPipeline

    image = preview_image(source_image, spec.preview_max_size) if spec.preview_max_size else source_image

    try:
        select_backend(spec.requested_backend, precision=spec.gpu_precision)
    except (BackendUnavailableError, Exception) as exc:
        return {
            "label": spec.label,
            "status": "skipped",
            "requested_backend": spec.requested_backend,
            "gpu_precision": spec.gpu_precision,
            "gpu_validate": spec.gpu_validate,
            "reason": f"{type(exc).__name__}: {exc}",
        }

    params = build_params(spec)
    sim = SimulationPipeline(params)
    trace = ConversionTrace()
    trace.wrap_backend(sim._backend)

    warmup_seconds = []
    for _ in range(max(0, warmups)):
        start = time.perf_counter()
        _ = sim.process(image.copy())
        sync_backend(sim._backend)
        warmup_seconds.append(time.perf_counter() - start)

    trace.reset()
    timed_seconds = []
    output = None
    for _ in range(max(1, runs)):
        start = time.perf_counter()
        output = sim.process(image.copy())
        sync_backend(sim._backend)
        timed_seconds.append(time.perf_counter() - start)

    type_trace: list[dict[str, Any]] = []
    if collect_type_trace:
        trace_sim = SimulationPipeline(params)
        type_trace = run_type_trace(trace_sim, image.copy())

    backend = sim._backend
    backend_runtime_summary = (
        sim.backend_runtime_summary()
        if hasattr(sim, "backend_runtime_summary")
        else backend_summary(backend)
    )
    return {
        "label": spec.label,
        "status": "ok",
        "requested_backend": spec.requested_backend,
        "selected_backend": getattr(backend, "name", spec.requested_backend),
        "supports_gpu": bool(getattr(backend, "supports_gpu", False)),
        "requires_serial_runtime": bool(getattr(backend, "requires_serial_runtime", False)),
        "backend_summary": backend_runtime_summary,
        "backend_summary_default": backend_summary(backend),
        "image_shape": list(image.shape),
        "gpu_precision": spec.gpu_precision,
        "gpu_validate": bool(spec.gpu_validate),
        "preview_max_size": spec.preview_max_size,
        "warmup_seconds": warmup_seconds,
        "timed_seconds": timed_seconds,
        "best_seconds": min(timed_seconds),
        "avg_seconds": sum(timed_seconds) / len(timed_seconds),
        "outer_wall_seconds": timed_seconds[-1],
        "total_seconds": sim.get_total_elapsed_time(),
        "timings": {str(key): float(value) for key, value in sim.get_timings().items()},
        "output": describe_array(output),
        "conversions": trace.summary(),
        "type_trace": type_trace,
    }


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# MLX Runtime Hot Path Benchmark - {payload['run_id']}",
        "",
        "## Input",
        "",
        f"- Path: `{payload['input']['path']}`",
        f"- Full shape: `{payload['input']['full_shape']}`",
        f"- Dtype: `{payload['input']['dtype']}`",
        f"- Load/decode: `{payload['input'].get('load_seconds', 0.0):.4f}s`",
        f"- Resize: `{payload['input'].get('resize_seconds', 0.0):.4f}s`",
        "",
        "## Runs",
        "",
        "| Label | Status | Backend | supports_gpu | requires_serial_runtime | Shape | Precision | gpu_validate | Total | Wall | backend_summary |",
        "|---|---|---|---:|---:|---|---|---:|---:|---:|---|",
    ]
    for run in payload["runs"]:
        if run["status"] != "ok":
            lines.append(
                f"| {run['label']} | skipped | {run['requested_backend']} | | | | "
                f"{run.get('gpu_precision', '')} | {run.get('gpu_validate', '')} | | | {run['reason']} |"
            )
            continue
        lines.append(
            f"| {run['label']} | ok | {run['selected_backend']} | "
            f"{run['supports_gpu']} | {run['requires_serial_runtime']} | "
            f"{run['image_shape']} | {run['gpu_precision']} | {run['gpu_validate']} | "
            f"{run['total_seconds']:.4f}s | {run['outer_wall_seconds']:.4f}s | "
            f"{run['backend_summary']} |"
        )

    lines.extend(["", "## Pipeline Stage Timings", ""])
    for run in payload["runs"]:
        if run.get("status") != "ok":
            continue
        lines.extend([f"### {run['label']}", "", "| Stage | Seconds |", "|---|---:|"])
        for key, value in run.get("timings", {}).items():
            lines.append(f"| {key} | {float(value):.6f} |")
        lines.append("")

    lines.extend(["", "## Hot Path Type Trace", ""])
    for run in payload["runs"]:
        if run.get("status") != "ok":
            continue
        lines.extend([f"### {run['label']}", "", "| Stage | Seconds | Input | Output |", "|---|---:|---|---|"])
        for row in run.get("type_trace", []):
            input_info = row["input"]
            output_info = row["output"]
            seconds = row.get("seconds")
            seconds_text = "" if seconds is None else f"{float(seconds):.6f}"
            lines.append(
                f"| {row['stage']} | {seconds_text} | "
                f"{input_info['type']} {input_info['shape']} {input_info['dtype']} | "
                f"{output_info['type']} {output_info['shape']} {output_info['dtype']} |"
            )
        lines.append("")

    lines.extend(["", "## Conversion Counters", ""])
    for run in payload["runs"]:
        if run.get("status") != "ok":
            continue
        lines.extend([f"### {run['label']}", "", "| Key | Count | Bytes |", "|---|---:|---:|"])
        for key, value in run.get("conversions", {}).items():
            lines.append(f"| {key} | {value['count']} | {value['bytes']} |")
        lines.append("")

    return "\n".join(lines)


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"benchmark-{payload['run_id']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--size", default="full", help="'full' or WIDTHxHEIGHT before benchmark cases")
    parser.add_argument("--generated-size", default="1280x960", help="Generated fallback WIDTHxHEIGHT")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--no-preview-640", action="store_true")
    parser.add_argument("--no-type-trace", action="store_true")
    parser.add_argument("--only-backend", choices=("all", "cpu", "mlx"), default="all")
    parser.add_argument("--skip-gpu-validate", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    requested_size = parse_size_spec(args.size)
    generated_size = parse_size_spec(args.generated_size)
    if generated_size is None:
        raise ValueError("--generated-size must be WIDTHxHEIGHT")

    input_path = Path(args.input)
    print(f"Loading input: {input_path}", flush=True)
    load_start = time.perf_counter()
    full_image = load_input_image(input_path, fallback_size=generated_size)
    load_seconds = time.perf_counter() - load_start

    resize_start = time.perf_counter()
    full_image = resize_image(full_image, requested_size)
    resize_seconds = time.perf_counter() - resize_start
    print(
        f"Loaded shape={full_image.shape} dtype={full_image.dtype} "
        f"load={load_seconds:.3f}s resize={resize_seconds:.3f}s",
        flush=True,
    )
    payload = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "input": {
            "path": str(args.input),
            "full_shape": list(full_image.shape),
            "dtype": str(full_image.dtype),
            "megapixels": float(full_image.shape[0] * full_image.shape[1] / 1_000_000.0),
            "load_seconds": load_seconds,
            "resize_seconds": resize_seconds,
        },
        "config": {
            "size": args.size,
            "warmups": int(args.warmups),
            "runs": int(args.runs),
            "type_trace": not args.no_type_trace,
            "only_backend": args.only_backend,
            "skip_gpu_validate": bool(args.skip_gpu_validate),
        },
        "runs": [],
    }

    for spec in benchmark_specs(
        include_preview_640=not args.no_preview_640,
        only_backend=args.only_backend,
        include_gpu_validate=not args.skip_gpu_validate,
    ):
        print(f"\n=== {spec.label} ({spec.requested_backend}, {spec.gpu_precision}, validate={spec.gpu_validate}) ===", flush=True)
        run = run_benchmark_case(
            full_image,
            spec,
            warmups=args.warmups,
            runs=args.runs,
            collect_type_trace=not args.no_type_trace,
        )
        payload["runs"].append(run)
        if run["status"] == "ok":
            print(
                f"selected={run['selected_backend']} total={run['total_seconds']:.3f}s "
                f"wall={run['outer_wall_seconds']:.3f}s summary={run['backend_summary']}",
                flush=True,
            )
        else:
            print(f"skipped: {run['reason']}", flush=True)

    return payload


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_matrix(args)
    json_path, md_path = write_artifacts(payload, Path(args.out_dir))
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    return 0


__all__ = [
    "BenchmarkSpec",
    "ConversionTrace",
    "benchmark_specs",
    "describe_array",
    "format_markdown",
    "parse_size_spec",
    "run_matrix",
]


if __name__ == "__main__":
    raise SystemExit(main())
