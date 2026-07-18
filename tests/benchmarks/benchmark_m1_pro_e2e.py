#!/usr/bin/env python3
"""Synchronized end-to-end Spektrafilm benchmark for Apple Silicon.

This is a manual benchmark, not a pytest test.  It deliberately materializes
the output inside the measured boundary and reports MLX evaluation separately
from the final NumPy readback so lazy execution cannot manufacture a speedup.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import resource
import statistics
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


@dataclass(frozen=True)
class RunConfig:
    width: int
    height: int
    backend: str
    precision: str
    materialize_policy: str
    film_profile: str
    print_profile: str
    route: str
    input_peak: float
    runs: int
    auto_exposure: bool
    effects: str


class RSSPeakSampler:
    """Sample process RSS while a timed render is active."""

    def __init__(self, interval_seconds: float = 0.005) -> None:
        self.interval_seconds = interval_seconds
        self.peak_bytes = 0
        self.start_bytes = 0
        self.end_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None

    def __enter__(self) -> "RSSPeakSampler":
        try:
            import psutil

            self._process = psutil.Process(os.getpid())
            self.start_bytes = int(self._process.memory_info().rss)
            self.peak_bytes = self.start_bytes
            self._thread = threading.Thread(target=self._sample, daemon=True)
            self._thread.start()
        except (ImportError, OSError):
            self._process = None
        return self

    def _sample(self) -> None:
        assert self._process is not None
        while not self._stop.wait(self.interval_seconds):
            try:
                self.peak_bytes = max(self.peak_bytes, int(self._process.memory_info().rss))
            except OSError:
                break

    def __exit__(self, *_exc: object) -> None:
        if self._process is None:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        try:
            self.end_bytes = int(self._process.memory_info().rss)
            self.peak_bytes = max(self.peak_bytes, self.end_bytes)
        except OSError:
            pass


def generated_linear_image(height: int, width: int, peak: float) -> np.ndarray:
    """Create a deterministic scene-linear stress image without random state."""

    x = np.linspace(0.001, peak, width, dtype=np.float32)
    y = np.linspace(0.001, 1.0, height, dtype=np.float32)
    image = np.empty((height, width, 3), dtype=np.float32)
    image[..., 0] = x[None, :]
    image[..., 1] = y[:, None]
    np.sqrt(image[..., 0] * image[..., 1], out=image[..., 2])
    return image


def build_params(config: RunConfig):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(config.film_profile, config.print_profile)
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.io.scan_film = config.route in {"film", "hdr-light-table"}
    params.camera.auto_exposure = config.auto_exposure
    params.settings.compute_backend = config.backend
    params.settings.gpu_precision = config.precision
    params.settings.materialize_policy = config.materialize_policy
    params.settings.gpu_validate = False
    params.settings.preview_mode = False
    if config.effects == "spatial-off":
        params.debug.deactivate_spatial_effects = True
    elif config.effects == "stochastic-off":
        params.debug.deactivate_stochastic_effects = True
    elif config.effects == "all-off":
        params.debug.deactivate_spatial_effects = True
        params.debug.deactivate_stochastic_effects = True
    return digest_params(params)


def _memory_value(backend: Any, name: str) -> int | None:
    mx = getattr(backend, "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, name, None)
        if callable(getter):
            try:
                return int(getter())
            except (OSError, RuntimeError, TypeError, ValueError):
                return None
    return None


def _reset_peak_memory(backend: Any) -> None:
    mx = getattr(backend, "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        reset = getattr(owner, "reset_peak_memory", None)
        if callable(reset):
            try:
                reset()
            except (OSError, RuntimeError):
                pass
            return


def _swap_used_bytes() -> int | None:
    try:
        import psutil

        return int(psutil.swap_memory().used)
    except (ImportError, OSError):
        return None


def _evaluate(backend: Any, value: Any) -> None:
    evaluate = getattr(backend, "eval", None)
    if callable(evaluate):
        evaluate(value)
    synchronize = getattr(backend, "synchronize", None)
    if callable(synchronize):
        synchronize()


def _to_numpy(backend: Any, value: Any) -> np.ndarray:
    if isinstance(value, np.ndarray):
        return value
    convert = getattr(backend, "to_numpy", None)
    if not callable(convert):
        return np.asarray(value)
    result = np.asarray(convert(value))
    synchronize = getattr(backend, "synchronize", None)
    if callable(synchronize):
        synchronize()
    return result


def _render(pipeline: Any, image: np.ndarray, route: str) -> Any:
    if route == "hdr-paper":
        return pipeline.process_with_master(image, hdr_mode="paper")
    if route == "hdr-light-table":
        return pipeline.process_with_master(image, hdr_mode="light_table")
    return pipeline.process(image)


def _output_value(result: Any) -> Any:
    return getattr(result, "image", result)


def _array_digest(array: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(array)
    flat = contiguous.reshape(-1)
    finite_count = 0
    non_nan_count = 0
    total = 0.0
    minimum = np.inf
    maximum = -np.inf
    # Do not turn a 50 MP float32 output into a second full-size float64
    # allocation merely to calculate benchmark metadata.  The reduction is
    # intentionally outside the timed region, but it must also remain outside
    # the measured workload's memory footprint.
    for start in range(0, flat.size, 4_000_000):
        chunk = flat[start:start + 4_000_000]
        finite_count += int(np.count_nonzero(np.isfinite(chunk)))
        non_nan_count += int(chunk.size - np.count_nonzero(np.isnan(chunk)))
        total += float(np.nansum(chunk, dtype=np.float64))
        minimum = min(minimum, float(np.nanmin(chunk)))
        maximum = max(maximum, float(np.nanmax(chunk)))
    return {
        "shape": list(contiguous.shape),
        "dtype": str(contiguous.dtype),
        "sha256": hashlib.sha256(contiguous.view(np.uint8)).hexdigest(),
        "finite_fraction": float(finite_count / flat.size),
        "min": minimum,
        "max": maximum,
        "mean": float(total / non_nan_count),
        "sum": total,
    }


def run_once(pipeline: Any, image: np.ndarray, route: str, label: str) -> tuple[dict[str, Any], np.ndarray]:
    backend = pipeline._backend
    _reset_peak_memory(backend)
    swap_start = _swap_used_bytes()
    process_start = time.perf_counter()
    process_cpu_start = time.process_time()
    with RSSPeakSampler() as rss:
        result = _render(pipeline, image, route)
        value = _output_value(result)
        dispatch_seconds = time.perf_counter() - process_start

        eval_start = time.perf_counter()
        _evaluate(backend, value)
        eval_seconds = time.perf_counter() - eval_start
        synchronized_seconds = time.perf_counter() - process_start

        materialize_start = time.perf_counter()
        output = _to_numpy(backend, value)
        materialize_seconds = time.perf_counter() - materialize_start
        output_boundary_seconds = time.perf_counter() - process_start
    cpu_seconds = time.process_time() - process_cpu_start
    swap_end = _swap_used_bytes()

    row = {
        "label": label,
        "dispatch_seconds": dispatch_seconds,
        "eval_sync_seconds": eval_seconds,
        "synchronized_core_seconds": synchronized_seconds,
        "materialize_seconds": materialize_seconds,
        "output_boundary_seconds": output_boundary_seconds,
        "process_cpu_seconds": cpu_seconds,
        "pipeline_reported_seconds": pipeline.get_total_elapsed_time(),
        "pipeline_stage_dispatch_seconds": {
            str(key): float(value) for key, value in pipeline.get_timings().items()
        },
        "rss_start_bytes": rss.start_bytes,
        "rss_peak_bytes": rss.peak_bytes,
        "rss_end_bytes": rss.end_bytes,
        "mlx_peak_bytes": _memory_value(backend, "get_peak_memory"),
        "mlx_cache_bytes": _memory_value(backend, "get_cache_memory"),
        "system_swap_start_bytes": swap_start,
        "system_swap_end_bytes": swap_end,
        "system_swap_delta_bytes": (
            None if swap_start is None or swap_end is None else swap_end - swap_start
        ),
        "ru_maxrss_raw": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
    }
    return row, output


def run_full_hdr_export(
    pipeline: Any,
    image: np.ndarray,
    route: str,
    output_path: Path,
) -> dict[str, Any]:
    from spektrafilm.hdr.routemaster_export import export_hdr_heic_from_simulator
    from spektrafilm.utils.heif_iso21496 import validate_heif_iso21496

    if route not in {"hdr-paper", "hdr-light-table"}:
        raise ValueError("--export-heic requires an HDR route")
    mode = "paper" if route == "hdr-paper" else "light_table"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    backend = pipeline._backend
    _reset_peak_memory(backend)
    swap_start = _swap_used_bytes()
    start = time.perf_counter()
    cpu_start = time.process_time()
    export_diagnostics: dict[str, object] = {}
    with RSSPeakSampler() as rss:
        diagnostics = export_hdr_heic_from_simulator(
            pipeline,
            image,
            output_path,
            hdr_mode=mode,
            color_space="sRGB",
            export_diagnostics_out=export_diagnostics,
        )
        synchronize = getattr(backend, "synchronize", None)
        if callable(synchronize):
            synchronize()
    elapsed = time.perf_counter() - start
    swap_end = _swap_used_bytes()
    validation = validate_heif_iso21496(output_path)
    return {
        "kind": "steady_full_pipeline_projection_and_heic_encode",
        "wall_seconds": elapsed,
        "cpu_seconds": time.process_time() - cpu_start,
        "rss_start_bytes": rss.start_bytes,
        "rss_peak_bytes": rss.peak_bytes,
        "rss_end_bytes": rss.end_bytes,
        "mlx_peak_bytes": _memory_value(backend, "get_peak_memory"),
        "mlx_cache_bytes": _memory_value(backend, "get_cache_memory"),
        "system_swap_start_bytes": swap_start,
        "system_swap_end_bytes": swap_end,
        "system_swap_delta_bytes": (
            None if swap_start is None or swap_end is None else swap_end - swap_start
        ),
        "output_path": str(output_path),
        "output_bytes": output_path.stat().st_size,
        "encoder_diagnostics": list(diagnostics),
        "export_diagnostics": export_diagnostics,
        "iso_21496_ok": validation.ok,
        "iso_21496_errors": list(validation.errors),
        "iso_21496_warnings": list(validation.warnings),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    keys = (
        "synchronized_core_seconds",
        "materialize_seconds",
        "output_boundary_seconds",
        "rss_peak_bytes",
        "mlx_peak_bytes",
    )
    result: dict[str, dict[str, float]] = {}
    for key in keys:
        values = [float(row[key]) for row in rows if row.get(key) is not None]
        if values:
            result[key] = {
                "median": float(statistics.median(values)),
                "min": float(min(values)),
                "max": float(max(values)),
            }
    return result


def run_benchmark(
    config: RunConfig,
    *,
    save_output: Path | None = None,
    export_heic: Path | None = None,
) -> dict[str, Any]:
    from spektrafilm.gpu.residency import record_backend_residency
    from spektrafilm.runtime.pipeline import SimulationPipeline

    image_start = time.perf_counter()
    image = generated_linear_image(config.height, config.width, config.input_peak)
    image_build_seconds = time.perf_counter() - image_start

    setup_start = time.perf_counter()
    params = build_params(config)
    pipeline = SimulationPipeline(params)
    setup_seconds = time.perf_counter() - setup_start

    rows: list[dict[str, Any]] = []
    output: np.ndarray | None = None
    with record_backend_residency() as recorder:
        first, output = run_once(pipeline, image, config.route, "first")
        rows.append(first)
        for index in range(config.runs):
            # Model consecutive user operations, not a caller intentionally
            # retaining every previous full-resolution output.
            del output
            gc.collect()
            row, output = run_once(pipeline, image, config.route, f"steady_{index + 1}")
            rows.append(row)

    assert output is not None
    digest = _array_digest(output)
    if save_output is not None:
        save_output.parent.mkdir(parents=True, exist_ok=True)
        np.save(save_output, output, allow_pickle=False)
    if export_heic is not None:
        del output
        gc.collect()
        full_export = run_full_hdr_export(pipeline, image, config.route, export_heic)
    else:
        full_export = None

    return {
        "schema": 1,
        "config": asdict(config),
        "environment": {
            "python": sys.version,
            "platform": platform.platform(),
            "numpy": np.__version__,
        },
        "input": {
            "shape": list(image.shape),
            "dtype": str(image.dtype),
            "nbytes": int(image.nbytes),
            "build_seconds": image_build_seconds,
        },
        "setup_seconds": setup_seconds,
        "backend": {
            "name": getattr(pipeline._backend, "name", config.backend),
            "precision": getattr(pipeline._backend, "precision", config.precision),
            "supports_gpu": bool(getattr(pipeline._backend, "supports_gpu", False)),
        },
        "runs": rows,
        "steady_summary": _summary(rows[1:]),
        "residency": recorder.to_json_dict(),
        "output": digest,
        "full_export": full_export,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    parser.add_argument("--backend", choices=("cpu", "mlx"), default="mlx")
    parser.add_argument("--precision", default="float32")
    parser.add_argument(
        "--materialize-policy",
        choices=("backend", "numpy_float32", "numpy_float64"),
        default="backend",
    )
    parser.add_argument("--film-profile", default="kodak_portra_400")
    parser.add_argument("--print-profile", default="kodak_portra_endura")
    parser.add_argument(
        "--route",
        choices=("paper", "film", "hdr-paper", "hdr-light-table"),
        default="paper",
    )
    parser.add_argument("--input-peak", type=float, default=4.0)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--disable-auto-exposure", action="store_true")
    parser.add_argument(
        "--effects",
        choices=("default", "spatial-off", "stochastic-off", "all-off"),
        default="default",
    )
    parser.add_argument("--save-output", type=Path)
    parser.add_argument("--export-heic", type=Path)
    parser.add_argument("--output-json", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.width <= 0 or args.height <= 0 or args.runs < 0:
        raise SystemExit("width and height must be positive; runs must be non-negative")
    config = RunConfig(
        width=args.width,
        height=args.height,
        backend=args.backend,
        precision=args.precision,
        materialize_policy=args.materialize_policy,
        film_profile=args.film_profile,
        print_profile=args.print_profile,
        route=args.route,
        input_peak=args.input_peak,
        runs=args.runs,
        auto_exposure=not args.disable_auto_exposure,
        effects=args.effects,
    )
    payload = run_benchmark(
        config,
        save_output=args.save_output,
        export_heic=args.export_heic,
    )
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(text + "\n", encoding="utf-8")
        print(args.output_json)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
