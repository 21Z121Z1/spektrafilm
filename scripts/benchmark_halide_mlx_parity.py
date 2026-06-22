#!/usr/bin/env python3
"""Halide / MLX parity benchmark with explicit timing boundaries."""

from __future__ import annotations

import argparse
import functools
import json
import math
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_DNG = Path("IMG20260530191638.dng")
DEFAULT_OUT_DIR = ROOT / "docs" / "dev" / "benchmark-artifacts" / "halide_mlx_parity_20260531"


def parse_size_spec(value: str) -> tuple[int, int] | None:
    """Parse ``full`` or ``WIDTHxHEIGHT`` into a benchmark resize target."""
    normalized = value.strip().lower()
    if normalized == "full":
        return None
    if "x" not in normalized:
        raise ValueError("size must be 'full' or WIDTHxHEIGHT")
    left, right = normalized.split("x", 1)
    try:
        width = int(left)
        height = int(right)
    except ValueError as exc:
        raise ValueError("size must be 'full' or WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise ValueError("size dimensions must be positive")
    return width, height


def precision_metrics(reference: Any, actual: Any) -> dict[str, Any]:
    """Return absolute-difference metrics for two image-like arrays."""
    ref = np.asarray(reference, dtype=np.float64)
    got = np.asarray(actual, dtype=np.float64)
    if ref.shape != got.shape:
        raise ValueError(f"shape mismatch: reference={ref.shape}, actual={got.shape}")

    diff = np.abs(ref - got)
    mse = float(np.mean(np.square(diff)))
    psnr = math.inf if mse == 0.0 else 10.0 * math.log10(1.0 / mse)
    metrics: dict[str, Any] = {
        "max_diff": float(np.max(diff)),
        "mean_diff": float(np.mean(diff)),
        "median_diff": float(np.median(diff)),
        "rmse": float(math.sqrt(mse)),
        "psnr": float(psnr),
        "psnr_db": float(psnr),
    }
    if diff.ndim >= 3:
        axes = tuple(range(diff.ndim - 1))
        metrics["channel_max_diff"] = np.max(diff, axis=axes).astype(float).tolist()
        metrics["channel_mean_diff"] = np.mean(diff, axis=axes).astype(float).tolist()
    else:
        metrics["channel_max_diff"] = [metrics["max_diff"]]
        metrics["channel_mean_diff"] = [metrics["mean_diff"]]
    return metrics


def describe_array(value: Any) -> dict[str, Any]:
    """Describe array type, shape, dtype, and byte size without copying when possible."""
    shape = list(getattr(value, "shape", []))
    dtype = getattr(value, "dtype", None)
    nbytes = getattr(value, "nbytes", None)
    if nbytes is None and shape and dtype is not None:
        nbytes = int(np.prod(shape)) * np.dtype(dtype).itemsize
    module = type(value).__module__
    backend = "mlx" if module.startswith("mlx.") else "numpy" if isinstance(value, np.ndarray) else module.split(".", 1)[0]
    byte_count = int(nbytes) if nbytes is not None else None
    return {
        "type": f"{module}.{type(value).__qualname__}",
        "backend": backend,
        "shape": shape,
        "dtype": str(dtype) if dtype is not None else None,
        "bytes": byte_count,
        "nbytes": byte_count,
    }


describe_value = describe_array
compute_precision_metrics = precision_metrics


@dataclass
class ConversionTrace:
    """Count backend array conversion calls and approximate byte volume."""

    _stats: dict[str, dict[str, int]] = field(default_factory=dict)
    _samples: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def reset(self) -> None:
        self._stats.clear()
        self._samples.clear()

    def _record(self, key: str, value: Any) -> None:
        info = describe_array(value)
        entry = self._stats.setdefault(key, {"count": 0, "bytes": 0})
        entry["count"] += 1
        entry["bytes"] += int(info["bytes"] or 0)
        samples = self._samples.setdefault(key, [])
        if len(samples) < 12:
            samples.append(info)

    def wrap_backend(self, backend: Any) -> Any:
        """Wrap ``backend.asarray`` and ``backend.to_numpy`` in-place."""
        if getattr(backend, "_spektrafilm_benchmark_wrapped", False):
            return backend
        for method_name in ("asarray", "to_numpy"):
            if hasattr(backend, method_name):
                original = getattr(backend, method_name)
                try:
                    setattr(
                        backend,
                        method_name,
                        self._wrap_method(f"backend.{method_name}", original),
                    )
                except AttributeError:
                    self._record(f"backend.{method_name}.wrap_skipped", None)
        try:
            setattr(backend, "_spektrafilm_benchmark_wrapped", True)
        except AttributeError:
            pass
        return backend

    def wrap_halide_buffer(self, backend: Any) -> None:
        """Wrap Halide Buffer construction for a single process benchmark."""
        hl = getattr(backend, "hl", None)
        if hl is None or getattr(hl, "_spektrafilm_benchmark_wrapped", False):
            return
        original = hl.Buffer
        trace = self

        def wrapped(value=None, *args: Any, **kwargs: Any):
            trace._record("halide.Buffer", value)
            if value is None:
                return original(*args, **kwargs)
            return original(value, *args, **kwargs)

        hl.Buffer = wrapped
        setattr(hl, "_spektrafilm_benchmark_wrapped", True)

    def _wrap_method(self, key: str, original: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(original)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            result = original(*args, **kwargs)
            self._record(key, result)
            return result

        return wrapped

    def summary(self) -> dict[str, dict[str, Any]]:
        data = {}
        for key, value in sorted(self._stats.items()):
            data[key] = dict(value)
            data[key]["samples"] = list(self._samples.get(key, []))
        return data


def load_input_image(path: Path, fallback_size: tuple[int, int]) -> np.ndarray:
    """Load a real image or build a deterministic synthetic fallback."""
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
    """Resize float HWC image to ``(width, height)``; ``None`` keeps full size."""
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


def build_params(*, backend_name: str, precision: str, grain_on: bool, use_lut: bool):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = True
    params.camera.auto_exposure = False
    params.film_render.halation.active = True
    params.film_render.halation.boost_ev = 1.0
    params.film_render.halation.scatter_amount = 1.0
    params.film_render.halation.halation_amount = 1.0
    params.film_render.grain.active = bool(grain_on)
    params.settings.compute_backend = backend_name
    params.settings.gpu_precision = precision
    params.settings.use_enlarger_lut = bool(use_lut)
    params.settings.use_scanner_lut = bool(use_lut)
    params.settings.lut_resolution = 17
    params.settings.use_fast_stats = True
    params.debug.print_timings = False
    return digest_params(params)


def sync_backend(backend: Any, value: Any = None) -> None:
    eval_fn = getattr(backend, "eval", None)
    if value is not None and callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()


def run_manual_stages(sim: Any, image: np.ndarray, *, collect: bool) -> tuple[np.ndarray, list[dict[str, Any]]]:
    backend = sim._backend
    rows: list[dict[str, Any]] = []

    def timed(name: str, fn: Callable[[Any], Any], value: Any) -> Any:
        input_info = describe_array(value)
        t0 = time.perf_counter()
        result = fn(value)
        sync_backend(backend, result)
        elapsed = time.perf_counter() - t0
        if collect:
            rows.append(
                {
                    "name": name,
                    "seconds": elapsed,
                    "input": input_info,
                    "output": describe_array(result),
                }
            )
        return result

    img = np.double(np.array(image)[:, :, 0:3])
    img = timed("preprocess.auto_exposure", sim._filming_stage.auto_exposure, img)
    img = timed("preprocess.crop_rescale", sim._resize_service.crop_and_rescale, img)
    log_raw_film = timed("film.expose", sim._filming_stage.expose, img)
    cmy_film = timed("film.develop", sim._filming_stage.develop, log_raw_film)
    log_raw_print = timed("print.expose", sim._printing_stage.expose, cmy_film)
    cmy_print = timed("print.develop", sim._printing_stage.develop, log_raw_print)
    rgb_scan = timed("scan", sim._scanning_stage.scan, cmy_print)

    t0 = time.perf_counter()
    final = np.asarray(rgb_scan, dtype=np.float64)
    elapsed = time.perf_counter() - t0
    if collect:
        rows.append(
            {
                "name": "final.asarray_float64",
                "seconds": elapsed,
                "input": describe_array(rgb_scan),
                "output": describe_array(final),
            }
        )
    return final, rows


def run_backend(
    image: np.ndarray,
    *,
    label: str,
    backend_name: str,
    precision: str,
    grain_on: bool,
    use_lut: bool,
    warmups: int,
    runs: int,
    collect_synced: bool,
) -> tuple[dict[str, Any], np.ndarray | None]:
    from spektrafilm.gpu.backend import select_backend
    from spektrafilm.runtime.pipeline import SimulationPipeline

    try:
        select_backend(backend_name, precision=precision)
    except Exception as exc:
        return (
            {
                "label": label,
                "requested_backend": backend_name,
                "precision": precision,
                "status": "skipped",
                "reason": f"{type(exc).__name__}: {exc}",
            },
            None,
        )

    params = build_params(backend_name=backend_name, precision=precision, grain_on=grain_on, use_lut=use_lut)
    sim = SimulationPipeline(params)
    trace = ConversionTrace()
    trace.wrap_backend(sim._backend)
    trace.wrap_halide_buffer(sim._backend)

    warmup_times = []
    for _ in range(max(0, warmups)):
        t0 = time.perf_counter()
        _ = sim.process(image.copy())
        sync_backend(sim._backend)
        warmup_times.append(time.perf_counter() - t0)

    trace.reset()
    output = None
    timed_runs = []
    internal_timings = {}
    for _ in range(max(1, runs)):
        t0 = time.perf_counter()
        output = sim.process(image.copy())
        sync_backend(sim._backend)
        timed_runs.append(time.perf_counter() - t0)
        internal_timings = dict(sim.get_timings())

    run: dict[str, Any] = {
        "label": label,
        "requested_backend": backend_name,
        "selected_backend": getattr(sim._backend, "name", backend_name),
        "precision": precision,
        "effective_precision_note": (
            "CPU runtime remains float64; gpu_precision is ignored"
            if backend_name == "cpu" and precision == "float32"
            else precision
        ),
        "status": "ok",
        "supports_gpu": bool(getattr(sim._backend, "supports_gpu", False)),
        "halide_target": str(getattr(sim._backend, "target", "")),
        "warmup_seconds": warmup_times,
        "timed_seconds": timed_runs,
        "best_seconds": min(timed_runs),
        "avg_seconds": sum(timed_runs) / len(timed_runs),
        "internal_timings": internal_timings,
        "output": describe_array(output),
        "conversions": trace.summary(),
    }

    if collect_synced:
        synced_sim = SimulationPipeline(params)
        synced_trace = ConversionTrace()
        synced_trace.wrap_backend(synced_sim._backend)
        synced_trace.wrap_halide_buffer(synced_sim._backend)
        _ = run_manual_stages(synced_sim, image.copy(), collect=False)
        synced_trace.reset()
        synced_output, stages = run_manual_stages(synced_sim, image.copy(), collect=True)
        run["synced_stages"] = stages
        run["synced_total_seconds"] = sum(row["seconds"] for row in stages)
        run["synced_output"] = describe_array(synced_output)
        run["synced_conversions"] = synced_trace.summary()

    return run, output


def backend_specs(include_cpu_float32: bool) -> list[tuple[str, str, str]]:
    specs = [("cpu_float64", "cpu", "float64")]
    if include_cpu_float32:
        specs.append(("cpu_float32_requested", "cpu", "float32"))
    specs.extend([("mlx_float32", "mlx", "float32"), ("halide_float32", "halide", "float32")])
    return specs


def format_markdown(payload: dict[str, Any]) -> str:
    def _format_seconds(values: list[float]) -> str:
        if not values:
            return ""
        return ", ".join(f"{value:.3f}s" for value in values)

    def _format_bytes(value: int | float) -> str:
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(value)
        for unit in units:
            if abs(size) < 1024.0 or unit == units[-1]:
                return f"{size:.2f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{int(value)} B"

    def _format_counts(counts: dict[str, Any]) -> str:
        if not counts:
            return ""
        parts = []
        for key, value in sorted(counts.items()):
            if isinstance(value, dict):
                count = int(value.get("count", 0))
                byte_count = int(value.get("bytes", 0))
                parts.append(f"`{key}`: {count} / {_format_bytes(byte_count)}")
            else:
                parts.append(f"`{key}`: {value}")
        return ", ".join(parts)

    lines = [
        f"# Halide / MLX Parity Benchmark - {payload['run_id']}",
        "",
        "## Configuration",
        "",
        f"- Input: `{payload['input']['path']}`",
        f"- Size: `{payload['input']['size_label']}`",
        f"- Shape: `{payload['input']['shape']}`",
        f"- Grain: `{payload['config']['grain']}`",
        f"- Halation: `on`",
        f"- LUT mode: `{payload['config']['use_lut']}`",
        "",
        "## Wall-Clock",
        "",
        "| Label | Status | Backend | Best | Avg | Output |",
        "|---|---|---|---:|---:|---|",
    ]
    for run in payload["runs"]:
        if run["status"] != "ok":
            lines.append(f"| {run['label']} | skipped | {run['requested_backend']} | | | {run['reason']} |")
            continue
        output = run["output"]
        lines.append(
            f"| {run['label']} | ok | {run['selected_backend']} | "
            f"{run['best_seconds']:.3f}s | {run['avg_seconds']:.3f}s | "
            f"{output['shape']} {output['dtype']} |"
        )

    lines.extend(
        [
            "",
            "## Run Diagnostics",
            "",
            "| Label | Warmup | Synced Total | Wall Conversions | Synced Conversions |",
            "|---|---:|---:|---|---|",
        ]
    )
    for run in payload["runs"]:
        if run["status"] != "ok":
            continue
        synced_total = run.get("synced_total_seconds")
        synced_text = f"{synced_total:.3f}s" if synced_total is not None else ""
        lines.append(
            f"| {run['label']} | {_format_seconds(run.get('warmup_seconds', []))} | "
            f"{synced_text}"
        )
        lines[-1] += (
            f" | {_format_counts(run.get('conversions', {}))} | "
            f"{_format_counts(run.get('synced_conversions', {}))} |"
        )

    lines.extend(["", "## Precision", "", "| Actual | Reference | max_diff | mean_diff | RMSE | PSNR |", "|---|---|---:|---:|---:|---:|"])
    for item in payload["precision"]:
        m = item["metrics"]
        lines.append(
            f"| {item['actual']} | {item['reference']} | {m['max_diff']:.4e} | "
            f"{m['mean_diff']:.4e} | {m['rmse']:.4e} | {m['psnr']:.2f} |"
        )

    lines.extend(["", "## Synced Stage Times", ""])
    for run in payload["runs"]:
        if run.get("status") != "ok" or "synced_stages" not in run:
            continue
        lines.extend([f"### {run['label']}", "", "| Stage | Seconds | Input | Output |", "|---|---:|---|---|"])
        for row in run["synced_stages"]:
            lines.append(
                f"| {row['name']} | {row['seconds']:.4f} | "
                f"{row['input']['shape']} {row['input']['dtype']} {row['input']['type']} | "
                f"{row['output']['shape']} {row['output']['dtype']} {row['output']['type']} |"
            )
        lines.append("")

    lines.extend(
        [
            "## Self-Audit Notes",
            "",
            "- Warm-up/JIT time is stored separately as `warmup_seconds` in JSON.",
            "- Final materialization is the `final.asarray_float64` synced stage.",
            "- Halide Buffer construction and backend conversions are counted in JSON conversion summaries.",
            "- Main run keeps halation enabled and does not change profile or scan semantics.",
            "",
        ]
    )
    return "\n".join(lines)


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"benchmark-{payload['run_id']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def run_matrix(args: argparse.Namespace) -> dict[str, Any]:
    size = parse_size_spec(args.size)
    image = load_input_image(Path(args.input), fallback_size=size or (512, 512))
    image = resize_image(image, size)
    size_label = "full" if size is None else f"{size[0]}x{size[1]}"

    payload: dict[str, Any] = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "input": {
            "path": str(args.input),
            "size_label": size_label,
            "shape": list(image.shape),
            "dtype": str(image.dtype),
            "megapixels": float(image.shape[0] * image.shape[1] / 1_000_000.0),
        },
        "config": {
            "grain": args.grain,
            "use_lut": bool(args.use_lut),
            "warmups": int(args.warmups),
            "runs": int(args.runs),
            "synced": not args.no_synced,
        },
        "runs": [],
        "precision": [],
    }

    outputs: dict[str, np.ndarray] = {}
    for label, backend_name, precision in backend_specs(args.include_cpu_float32):
        if args.backends and backend_name not in args.backends and label not in args.backends:
            continue
        print(f"\n=== {label} ({backend_name}, {precision}) ===", flush=True)
        run, output = run_backend(
            image,
            label=label,
            backend_name=backend_name,
            precision=precision,
            grain_on=args.grain == "on",
            use_lut=args.use_lut,
            warmups=args.warmups,
            runs=args.runs,
            collect_synced=not args.no_synced,
        )
        payload["runs"].append(run)
        if run["status"] == "ok" and output is not None:
            outputs[label] = np.asarray(output, dtype=np.float64)
            print(f"best={run['best_seconds']:.3f}s avg={run['avg_seconds']:.3f}s", flush=True)
        else:
            print(f"skipped: {run.get('reason')}", flush=True)

    cpu_ref = outputs.get("cpu_float64")
    if cpu_ref is not None:
        for label, output in outputs.items():
            if label == "cpu_float64":
                continue
            payload["precision"].append(
                {
                    "reference": "cpu_float64",
                    "actual": label,
                    "metrics": precision_metrics(cpu_ref, output),
                }
            )
    if "mlx_float32" in outputs and "halide_float32" in outputs:
        payload["precision"].append(
            {
                "reference": "mlx_float32",
                "actual": "halide_float32",
                "metrics": precision_metrics(outputs["mlx_float32"], outputs["halide_float32"]),
            }
        )
    return payload


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_DNG))
    parser.add_argument("--size", default="2048x1536", help="'full' or WIDTHxHEIGHT")
    parser.add_argument("--backends", nargs="*", default=None, help="Subset: cpu mlx halide or exact labels")
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--grain", choices=["off", "on"], default="off")
    parser.add_argument("--use-lut", action="store_true", help="Enable enlarger/scanner LUT mode")
    parser.add_argument("--include-cpu-float32", action="store_true")
    parser.add_argument("--no-synced", action="store_true")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    payload = run_matrix(args)
    json_path, md_path = write_artifacts(payload, Path(args.out_dir))
    print(f"\nWrote JSON: {json_path}")
    print(f"Wrote Markdown: {md_path}")
    return 0


__all__ = [
    "ConversionTrace",
    "describe_array",
    "describe_value",
    "compute_precision_metrics",
    "parse_size_spec",
    "precision_metrics",
]


if __name__ == "__main__":
    raise SystemExit(main())
