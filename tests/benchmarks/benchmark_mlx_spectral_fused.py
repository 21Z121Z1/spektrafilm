#!/usr/bin/env python
from __future__ import annotations

import argparse
import functools
import gc
import json
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from opt_einsum import contract

from spektrafilm.config import STANDARD_OBSERVER_CMFS
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.density import (
    cmy_to_log_xyz_backend,
    compute_density_spectral as compute_density_spectral_backend,
    density_to_light as density_to_light_backend,
    light_to_raw as light_to_raw_backend,
    safe_log10_backend,
)
from spektrafilm.model.illuminants import standard_illuminant
from spektrafilm.profiles.io import load_profile
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.services import EnlargerService
from spektrafilm.utils.conversions import density_to_light


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DIR = ROOT / "docs" / "reports"
DEFAULT_SEED = 20260619
DEFAULT_ACCEPTANCE_WARMUP = 3
DEFAULT_ACCEPTANCE_RUNS = 10
DEFAULT_FULL_WARMUP = 2
DEFAULT_FULL_RUNS = 5
FULL_REFERENCE_PIXEL_LIMIT = 1024 * 1024
RAW_PIXEL_THREAD_MEDIAN_SPEEDUP_THRESHOLD = 1.25
RAW_PIXEL_THREAD_P90_SLOWDOWN_LIMIT = 1.05
RAW_PIXEL_THREAD_MEMORY_INCREASE_LIMIT = 1.05
RAW_PIXEL_THREAD_PRECISION_ATOL = 1e-6
RAW_PIXEL_THREAD_ACCEPTANCE_SIZES = {(768, 1024), (3024, 4032)}


@dataclass(frozen=True)
class SpectralCase:
    label: str
    height: int
    width: int
    warmup: int
    runs: int


def acceptance_cases() -> list[SpectralCase]:
    return [
        SpectralCase("preview_256x256", 256, 256, DEFAULT_ACCEPTANCE_WARMUP, DEFAULT_ACCEPTANCE_RUNS),
        SpectralCase("medium_768x1024", 768, 1024, DEFAULT_ACCEPTANCE_WARMUP, DEFAULT_ACCEPTANCE_RUNS),
        SpectralCase("full_3024x4032", 3024, 4032, DEFAULT_FULL_WARMUP, DEFAULT_FULL_RUNS),
    ]


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    if not 0.0 <= q <= 100.0:
        raise ValueError("q must be between 0 and 100")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * (q / 100.0)
    lower = int(np.floor(position))
    upper = int(np.ceil(position))
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize_ms(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("summarize_ms requires at least one timing")
    return {
        "runs": len(values),
        "median_ms": statistics.median(values) * 1000.0,
        "p90_ms": percentile(values, 90.0) * 1000.0,
        "min_ms": min(values) * 1000.0,
        "max_ms": max(values) * 1000.0,
    }


def precision_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    diff = np.abs(np.asarray(reference, dtype=np.float64) - np.asarray(candidate, dtype=np.float64))
    return {
        "max_abs_diff": float(np.max(diff)),
        "mean_abs_diff": float(np.mean(diff)),
        "p90_abs_diff": float(np.percentile(diff, 90.0)),
    }


def _reset_peak_memory(mx) -> None:
    reset_peak = getattr(mx, "reset_peak_memory", None)
    if callable(reset_peak):
        reset_peak()


def _peak_memory(mx) -> int | None:
    get_peak = getattr(mx, "get_peak_memory", None)
    if callable(get_peak):
        return int(get_peak())
    metal = getattr(mx, "metal", None)
    get_peak = getattr(metal, "get_peak_memory", None)
    if callable(get_peak):
        return int(get_peak())
    return None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return float(numerator) / float(denominator)


def _sync_backend(backend: Any, value: Any | None = None) -> None:
    eval_fn = getattr(backend, "eval", None)
    if value is not None and callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()


def make_density_case(height: int, width: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    ramp_x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    ramp_y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    structured = np.stack(
        [
            0.05 + 0.95 * np.broadcast_to(ramp_x, (height, width)),
            0.08 + 1.05 * np.broadcast_to(ramp_y, (height, width)),
            0.03 + 0.80 * (np.broadcast_to(ramp_x, (height, width)) + np.broadcast_to(ramp_y, (height, width))),
        ],
        axis=-1,
    )
    noise = rng.normal(0.0, 0.025, size=(height, width, 3)).astype(np.float32)
    return np.clip(structured + noise, -0.1, 2.4).astype(np.float32)


def load_real_spectral_tables() -> dict[str, np.ndarray | float | int]:
    film = load_profile("kodak_portra_400")
    paper = load_profile("kodak_portra_endura")
    enlarger = init_params("kodak_portra_400", "kodak_portra_endura").enlarger
    enlarger_service = EnlargerService(enlarger)

    print_light_source = standard_illuminant(enlarger.illuminant)
    print_illuminant = enlarger_service.enlarger_filtered_illuminant(print_light_source)
    sensitivity = np.nan_to_num(10.0 ** np.asarray(paper.data.log_sensitivity, dtype=np.float32))
    print_channel_density = np.nan_to_num(
        np.asarray(film.data.channel_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    print_base_density = np.nan_to_num(
        np.asarray(film.data.base_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    scan_channel_density = np.nan_to_num(
        np.asarray(paper.data.channel_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    scan_base_density = np.nan_to_num(
        np.asarray(paper.data.base_density, dtype=np.float32),
        nan=0.0,
        posinf=0.0,
        neginf=0.0,
    )
    scan_illuminant = np.asarray(standard_illuminant(paper.info.viewing_illuminant), dtype=np.float32)
    cmfs = np.asarray(STANDARD_OBSERVER_CMFS[:], dtype=np.float32)
    normalization = float(np.sum(scan_illuminant * cmfs[:, 1], axis=0))

    return {
        "film_profile": "kodak_portra_400",
        "print_profile": "kodak_portra_endura",
        "spectral_length": int(print_channel_density.shape[0]),
        "print_channel_density": print_channel_density,
        "print_base_density": print_base_density,
        "print_illuminant": np.asarray(print_illuminant, dtype=np.float32),
        "print_sensitivity": sensitivity.astype(np.float32),
        "print_exposure_factor": np.array([1.0], dtype=np.float32),
        "print_preflash": np.zeros((3,), dtype=np.float32),
        "scan_channel_density": scan_channel_density,
        "scan_base_density": scan_base_density,
        "scan_illuminant": scan_illuminant,
        "scan_cmfs": cmfs,
        "scan_normalization": normalization,
    }


def _reference_cmy_to_log_raw(
    density_cmy: np.ndarray,
    channel_density: np.ndarray,
    base_density: np.ndarray,
    illuminant: np.ndarray,
    sensitivity: np.ndarray,
    exposure_factor: np.ndarray,
    preflash: np.ndarray,
) -> np.ndarray:
    density_spectral = contract("ijk,lk->ijl", density_cmy, channel_density)
    density_spectral = density_spectral + base_density
    light = np.power(10.0, -density_spectral) * illuminant
    light = np.nan_to_num(light, nan=0.0)
    raw = contract("ijk,kl->ijl", light, sensitivity)
    raw = raw * exposure_factor.reshape(1, 1, -1) + preflash.reshape(1, 1, 3)
    return np.log10(np.fmax(raw, 0.0) + 1e-10).astype(np.float32)


def _reference_cmy_to_log_xyz(
    density_cmy: np.ndarray,
    channel_density: np.ndarray,
    base_density: np.ndarray | None,
    scan_illuminant: np.ndarray,
    cmfs: np.ndarray,
    normalization: float,
) -> np.ndarray:
    density_spectral = contract("ijk,lk->ijl", density_cmy, channel_density)
    if base_density is not None:
        density_spectral = density_spectral + base_density
    light = np.power(10.0, -density_spectral) * scan_illuminant
    light = np.nan_to_num(light, nan=0.0)
    xyz = contract("ijk,kl->ijl", light, cmfs) / float(normalization)
    return np.log10(np.fmax(xyz, 0.0) + 1e-10).astype(np.float32)


def _mlx_unfused_raw(
    backend: Any,
    density_cmy: Any,
    channel_density: Any,
    base_density: Any,
    illuminant: Any,
    sensitivity: Any,
    exposure_factor: Any,
    preflash: Any,
) -> Any:
    density_spectral = compute_density_spectral_backend(channel_density, density_cmy, base_density, backend)
    light = density_to_light_backend(density_spectral, illuminant, backend)
    raw = light_to_raw_backend(light, sensitivity, backend)
    raw = raw * backend.asarray(exposure_factor)
    raw = raw + backend.asarray(preflash)
    return safe_log10_backend(raw, backend)


def _mlx_unfused_xyz(
    backend: Any,
    density_cmy: Any,
    channel_density: Any,
    base_density: Any,
    scan_illuminant: Any,
    cmfs: Any,
    normalization: float,
) -> Any:
    density_spectral = compute_density_spectral_backend(channel_density, density_cmy, base_density, backend)
    light = density_to_light_backend(density_spectral, scan_illuminant, backend)
    xyz = light_to_raw_backend(light, cmfs, backend) / float(normalization)
    return safe_log10_backend(xyz, backend)


def _time_backend_call(backend: Any, function: Callable[[], Any]) -> tuple[float, Any]:
    start = time.perf_counter()
    output = function()
    _sync_backend(backend, output)
    return time.perf_counter() - start, output


def benchmark_backend_function(
    backend: Any,
    name: str,
    function: Callable[[], Any],
    *,
    warmup: int,
    runs: int,
) -> dict[str, Any]:
    output = None
    for _ in range(warmup):
        _, output = _time_backend_call(backend, function)
    _sync_backend(backend, output)

    _reset_peak_memory(backend.mx)
    timings: list[float] = []
    for _ in range(runs):
        elapsed, output = _time_backend_call(backend, function)
        timings.append(elapsed)

    return {
        "name": name,
        "summary": summarize_ms(timings),
        "timings_ms": [value * 1000.0 for value in timings],
        "peak_memory_bytes": _peak_memory(backend.mx),
        "output": output,
    }


def _output_to_numpy(backend: Any, result: dict[str, Any]) -> np.ndarray:
    output = result.pop("output")
    try:
        _sync_backend(backend, output)
        return np.array(output, copy=True)
    finally:
        del output
        gc.collect()


def run_kernel_case(
    *,
    case: SpectralCase,
    seed: int,
    compute_numpy_reference: bool,
) -> dict[str, Any]:
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"status": "skipped", "reason": str(exc), "label": case.label}

    tables = load_real_spectral_tables()
    density = make_density_case(case.height, case.width, seed)
    density_mx = backend.asarray(density, dtype=backend.mx.float32)
    print_channel_mx = backend.asarray(tables["print_channel_density"], dtype=backend.mx.float32)
    print_base_mx = backend.asarray(tables["print_base_density"], dtype=backend.mx.float32)
    print_illuminant_mx = backend.asarray(tables["print_illuminant"], dtype=backend.mx.float32)
    sensitivity_mx = backend.asarray(tables["print_sensitivity"], dtype=backend.mx.float32)
    exposure_factor = np.asarray(tables["print_exposure_factor"], dtype=np.float32)
    preflash = np.asarray(tables["print_preflash"], dtype=np.float32)
    scan_channel_mx = backend.asarray(tables["scan_channel_density"], dtype=backend.mx.float32)
    scan_base_mx = backend.asarray(tables["scan_base_density"], dtype=backend.mx.float32)
    scan_illuminant_mx = backend.asarray(tables["scan_illuminant"], dtype=backend.mx.float32)
    cmfs_mx = backend.asarray(tables["scan_cmfs"], dtype=backend.mx.float32)
    normalization = float(tables["scan_normalization"])

    # Compile/setup and static table conversion are intentionally outside timed regions.
    raw_probe = backend.cmy_to_log_raw(
        density_mx,
        print_channel_mx,
        print_base_mx,
        print_illuminant_mx,
        sensitivity_mx,
        exposure_factor,
        preflash,
    )
    raw_pixel_thread_probe = backend.cmy_to_log_raw_pixel_thread_v1(
        density_mx,
        print_channel_mx,
        print_base_mx,
        print_illuminant_mx,
        sensitivity_mx,
        exposure_factor,
        preflash,
    )
    xyz_probe = cmy_to_log_xyz_backend(
        density_mx,
        scan_channel_mx,
        scan_base_mx,
        scan_illuminant_mx,
        cmfs_mx,
        normalization,
        backend,
    )
    _sync_backend(backend, raw_probe)
    _sync_backend(backend, raw_pixel_thread_probe)
    _sync_backend(backend, xyz_probe)

    raw_unfused = benchmark_backend_function(
        backend,
        "cmy_to_log_raw_unfused_backend_chain",
        lambda: _mlx_unfused_raw(
            backend,
            density_mx,
            print_channel_mx,
            print_base_mx,
            print_illuminant_mx,
            sensitivity_mx,
            exposure_factor,
            preflash,
        ),
        warmup=case.warmup,
        runs=case.runs,
    )
    raw_unfused_np = _output_to_numpy(backend, raw_unfused)
    raw_fused = benchmark_backend_function(
        backend,
        "cmy_to_log_raw_fused_metal",
        lambda: backend.cmy_to_log_raw(
            density_mx,
            print_channel_mx,
            print_base_mx,
            print_illuminant_mx,
            sensitivity_mx,
            exposure_factor,
            preflash,
        ),
        warmup=case.warmup,
        runs=case.runs,
    )
    raw_fused_np = _output_to_numpy(backend, raw_fused)
    raw_fused["precision_vs_unfused_backend_chain"] = precision_metrics(raw_unfused_np, raw_fused_np)
    raw_unfused["precision_vs_unfused_backend_chain"] = precision_metrics(raw_unfused_np, raw_unfused_np)
    raw_fused["precision_vs_current_fused_metal"] = precision_metrics(raw_fused_np, raw_fused_np)
    raw_unfused["precision_vs_current_fused_metal"] = precision_metrics(raw_fused_np, raw_unfused_np)
    raw_pixel_thread_v1 = benchmark_backend_function(
        backend,
        "cmy_to_log_raw_pixel_thread_v1",
        lambda: backend.cmy_to_log_raw_pixel_thread_v1(
            density_mx,
            print_channel_mx,
            print_base_mx,
            print_illuminant_mx,
            sensitivity_mx,
            exposure_factor,
            preflash,
        ),
        warmup=case.warmup,
        runs=case.runs,
    )
    raw_pixel_thread_v1_np = _output_to_numpy(backend, raw_pixel_thread_v1)
    raw_pixel_thread_v1["precision_vs_unfused_backend_chain"] = precision_metrics(
        raw_unfused_np,
        raw_pixel_thread_v1_np,
    )
    raw_pixel_thread_v1["precision_vs_current_fused_metal"] = precision_metrics(
        raw_fused_np,
        raw_pixel_thread_v1_np,
    )

    xyz_unfused = benchmark_backend_function(
        backend,
        "cmy_to_log_xyz_unfused_backend_chain",
        lambda: _mlx_unfused_xyz(
            backend,
            density_mx,
            scan_channel_mx,
            scan_base_mx,
            scan_illuminant_mx,
            cmfs_mx,
            normalization,
        ),
        warmup=case.warmup,
        runs=case.runs,
    )
    xyz_unfused_np = _output_to_numpy(backend, xyz_unfused)
    xyz_fused = benchmark_backend_function(
        backend,
        "cmy_to_log_xyz_fused_metal",
        lambda: cmy_to_log_xyz_backend(
            density_mx,
            scan_channel_mx,
            scan_base_mx,
            scan_illuminant_mx,
            cmfs_mx,
            normalization,
            backend,
        ),
        warmup=case.warmup,
        runs=case.runs,
    )
    xyz_fused_np = _output_to_numpy(backend, xyz_fused)
    xyz_fused["precision_vs_unfused_backend_chain"] = precision_metrics(xyz_unfused_np, xyz_fused_np)
    xyz_unfused["precision_vs_unfused_backend_chain"] = precision_metrics(xyz_unfused_np, xyz_unfused_np)

    if compute_numpy_reference:
        raw_reference = _reference_cmy_to_log_raw(
            density,
            np.asarray(tables["print_channel_density"], dtype=np.float32),
            np.asarray(tables["print_base_density"], dtype=np.float32),
            np.asarray(tables["print_illuminant"], dtype=np.float32),
            np.asarray(tables["print_sensitivity"], dtype=np.float32),
            exposure_factor,
            preflash,
        )
        xyz_reference = _reference_cmy_to_log_xyz(
            density,
            np.asarray(tables["scan_channel_density"], dtype=np.float32),
            np.asarray(tables["scan_base_density"], dtype=np.float32),
            np.asarray(tables["scan_illuminant"], dtype=np.float32),
            np.asarray(tables["scan_cmfs"], dtype=np.float32),
            normalization,
        )
        raw_unfused["precision_vs_numpy"] = precision_metrics(raw_reference, raw_unfused_np)
        raw_fused["precision_vs_numpy"] = precision_metrics(raw_reference, raw_fused_np)
        raw_pixel_thread_v1["precision_vs_numpy"] = precision_metrics(raw_reference, raw_pixel_thread_v1_np)
        xyz_unfused["precision_vs_numpy"] = precision_metrics(xyz_reference, xyz_unfused_np)
        xyz_fused["precision_vs_numpy"] = precision_metrics(xyz_reference, xyz_fused_np)
    else:
        raw_unfused["precision_vs_numpy"] = None
        raw_fused["precision_vs_numpy"] = None
        raw_pixel_thread_v1["precision_vs_numpy"] = None
        xyz_unfused["precision_vs_numpy"] = None
        xyz_fused["precision_vs_numpy"] = None

    current_raw_median_ms = raw_fused["summary"]["median_ms"]
    current_raw_p90_ms = raw_fused["summary"]["p90_ms"]
    raw_speedup = raw_unfused["summary"]["median_ms"] / current_raw_median_ms
    raw_pixel_thread_v1_median_speedup = current_raw_median_ms / raw_pixel_thread_v1["summary"]["median_ms"]
    raw_pixel_thread_v1_p90_speedup = current_raw_p90_ms / raw_pixel_thread_v1["summary"]["p90_ms"]
    raw_pixel_thread_v1_peak_memory_ratio = _safe_ratio(
        raw_pixel_thread_v1.get("peak_memory_bytes"),
        raw_fused.get("peak_memory_bytes"),
    )
    raw_unfused["speedup_vs_current"] = current_raw_median_ms / raw_unfused["summary"]["median_ms"]
    raw_fused["speedup_vs_current"] = 1.0
    raw_pixel_thread_v1["speedup_vs_current"] = raw_pixel_thread_v1_median_speedup
    xyz_speedup = xyz_unfused["summary"]["median_ms"] / xyz_fused["summary"]["median_ms"]
    raw_vs_xyz_ratio = raw_fused["summary"]["median_ms"] / xyz_fused["summary"]["median_ms"]

    return {
        "status": "ok",
        "label": case.label,
        "case": {
            "height": case.height,
            "width": case.width,
            "dtype": "float32",
            "seed": seed,
            "film_profile": tables["film_profile"],
            "print_profile": tables["print_profile"],
            "spectral_length": tables["spectral_length"],
            "compile_setup_excluded": True,
            "static_table_conversion_excluded": True,
            "numpy_reference_computed": bool(compute_numpy_reference),
        },
        "warmup": case.warmup,
        "runs": case.runs,
        "kernels": {
            "cmy_to_log_raw": {
                "results": [raw_unfused, raw_fused, raw_pixel_thread_v1],
                "median_speedup_fused_vs_unfused": raw_speedup,
                "median_speedup_pixel_thread_v1_vs_current": raw_pixel_thread_v1_median_speedup,
                "p90_speedup_pixel_thread_v1_vs_current": raw_pixel_thread_v1_p90_speedup,
                "peak_memory_ratio_pixel_thread_v1_vs_current": raw_pixel_thread_v1_peak_memory_ratio,
            },
            "cmy_to_log_xyz": {
                "results": [xyz_unfused, xyz_fused],
                "median_speedup_fused_vs_unfused": xyz_speedup,
            },
        },
        "raw_fused_to_xyz_fused_median_ratio": raw_vs_xyz_ratio,
        "raw_pixel_thread_v1_median_speedup_vs_current": raw_pixel_thread_v1_median_speedup,
        "raw_pixel_thread_v1_p90_speedup_vs_current": raw_pixel_thread_v1_p90_speedup,
        "raw_pixel_thread_v1_peak_memory_ratio_vs_current": raw_pixel_thread_v1_peak_memory_ratio,
    }


def _make_runtime_image(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.0, 1.0, width, dtype=np.float64)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float64)[:, None]
    return np.stack(
        [
            0.04 + 0.96 * np.broadcast_to(x, (height, width)),
            0.04 + 0.96 * np.broadcast_to(y, (height, width)),
            0.08 + 0.46 * (np.broadcast_to(x, (height, width)) + np.broadcast_to(y, (height, width))),
        ],
        axis=-1,
    )


def _build_runtime_params():
    params = init_params("kodak_portra_400", "kodak_portra_endura")
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = True
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.gpu_validate = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.use_fast_stats = True
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.debug.print_timings = False
    return digest_params(params)


def _shape_text(value: Any) -> str:
    return "x".join(str(int(dim)) for dim in getattr(value, "shape", ()))


class KernelTrace:
    def __init__(self, backend: Any) -> None:
        self.backend = backend
        self.rows: list[dict[str, Any]] = []

    def wrap_pipeline(self, sim: SimulationPipeline) -> None:
        backend = self.backend
        raw_original = backend.cmy_to_log_raw

        @functools.wraps(raw_original)
        def raw_wrapped(density_cmy, *args: Any, **kwargs: Any):
            start = time.perf_counter()
            output = raw_original(density_cmy, *args, **kwargs)
            _sync_backend(backend, output)
            elapsed = time.perf_counter() - start
            self.rows.append(
                {
                    "kernel": "cmy_to_log_raw",
                    "shape": _shape_text(density_cmy),
                    "seconds": elapsed,
                }
            )
            return output

        backend.cmy_to_log_raw = raw_wrapped

        xyz_original = sim._scanning_stage.cmy_to_log_xyz

        @functools.wraps(xyz_original)
        def xyz_wrapped(density_cmy):
            start = time.perf_counter()
            output = xyz_original(density_cmy)
            _sync_backend(backend, output)
            elapsed = time.perf_counter() - start
            self.rows.append(
                {
                    "kernel": "cmy_to_log_xyz",
                    "shape": _shape_text(density_cmy),
                    "seconds": elapsed,
                }
            )
            return output

        sim._scanning_stage.cmy_to_log_xyz = xyz_wrapped
        sim._color_reference_service.cmy_to_log_xyz = xyz_wrapped

    def summary(self, wall_seconds: float) -> dict[str, Any]:
        grouped: dict[str, dict[str, Any]] = {}
        for row in self.rows:
            entry = grouped.setdefault(
                row["kernel"],
                {
                    "calls": 0,
                    "total_seconds": 0.0,
                    "shapes": {},
                    "call_seconds": [],
                },
            )
            entry["calls"] += 1
            entry["total_seconds"] += float(row["seconds"])
            entry["call_seconds"].append(float(row["seconds"]))
            entry["shapes"][row["shape"]] = entry["shapes"].get(row["shape"], 0) + 1

        for entry in grouped.values():
            entry["wall_percent"] = 0.0 if wall_seconds <= 0 else entry["total_seconds"] / wall_seconds * 100.0
            entry["median_ms"] = statistics.median(entry["call_seconds"]) * 1000.0
            entry["p90_ms"] = percentile(entry["call_seconds"], 90.0) * 1000.0
        return grouped


def run_end_to_end_attribution(
    *,
    width: int,
    height: int,
    warmup: int,
    runs: int,
) -> dict[str, Any]:
    try:
        select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"status": "skipped", "reason": str(exc)}

    params = _build_runtime_params()
    image = _make_runtime_image(width, height)
    sim = SimulationPipeline(params)
    trace = KernelTrace(sim._backend)
    trace.wrap_pipeline(sim)

    for _ in range(warmup):
        sim.process(image.copy())
        _sync_backend(sim._backend)
    trace.rows.clear()

    timed_seconds: list[float] = []
    timings_by_run: list[dict[str, float]] = []
    for _ in range(runs):
        start = time.perf_counter()
        sim.process(image.copy())
        _sync_backend(sim._backend)
        elapsed = time.perf_counter() - start
        timed_seconds.append(elapsed)
        timings_by_run.append({str(key): float(value) for key, value in sim.get_timings().items()})

    wall_seconds = sum(timed_seconds)
    stage_keys = (
        "PrintingStage.expose",
        "PrintingStage.develop",
        "ScanningStage.scan",
        "SpectralLUTService.spectral_compute_enlarger",
        "SpectralLUTService.spectral_compute_scanner",
    )
    stage_totals = {
        key: sum(run.get(key, 0.0) for run in timings_by_run)
        for key in stage_keys
    }
    return {
        "status": "ok",
        "image_shape": [height, width, 3],
        "warmup": warmup,
        "runs": runs,
        "wall_seconds": timed_seconds,
        "wall_summary": summarize_ms(timed_seconds),
        "kernel_trace": trace.summary(wall_seconds),
        "stage_totals": stage_totals,
        "stage_wall_percent": {
            key: 0.0 if wall_seconds <= 0 else value / wall_seconds * 100.0
            for key, value in stage_totals.items()
        },
    }


def evaluate_raw_pixel_thread_acceptance(
    payload: dict[str, Any],
    *,
    wall_threshold_percent: float = 10.0,
    raw_vs_xyz_ratio_threshold: float = 2.0,
    median_speedup_threshold: float = RAW_PIXEL_THREAD_MEDIAN_SPEEDUP_THRESHOLD,
    p90_slowdown_limit: float = RAW_PIXEL_THREAD_P90_SLOWDOWN_LIMIT,
    memory_increase_limit: float = RAW_PIXEL_THREAD_MEMORY_INCREASE_LIMIT,
    precision_atol: float = RAW_PIXEL_THREAD_PRECISION_ATOL,
) -> dict[str, Any]:
    kernel_runs = [run for run in payload.get("kernel_runs", []) if run.get("status") == "ok"]
    acceptance_runs = [
        run
        for run in kernel_runs
        if (
            int(run.get("case", {}).get("height", 0)),
            int(run.get("case", {}).get("width", 0)),
        )
        in RAW_PIXEL_THREAD_ACCEPTANCE_SIZES
    ]
    v1_decision_runs = acceptance_runs or kernel_runs
    attribution = payload.get("end_to_end_attribution", {})
    raw_trace = attribution.get("kernel_trace", {}).get("cmy_to_log_raw", {})
    raw_wall_percent = float(raw_trace.get("wall_percent", 0.0) or 0.0)
    ratios = [
        float(run.get("raw_fused_to_xyz_fused_median_ratio", 0.0) or 0.0)
        for run in kernel_runs
    ]
    max_raw_vs_xyz_ratio = max(ratios, default=0.0)
    v1_speedups = [
        float(run["raw_pixel_thread_v1_median_speedup_vs_current"])
        for run in v1_decision_runs
        if run.get("raw_pixel_thread_v1_median_speedup_vs_current") is not None
    ]
    v1_p90_speedups = [
        float(run["raw_pixel_thread_v1_p90_speedup_vs_current"])
        for run in v1_decision_runs
        if run.get("raw_pixel_thread_v1_p90_speedup_vs_current") is not None
    ]
    v1_memory_ratios = [
        float(run["raw_pixel_thread_v1_peak_memory_ratio_vs_current"])
        for run in v1_decision_runs
        if run.get("raw_pixel_thread_v1_peak_memory_ratio_vs_current") is not None
    ]
    v1_precision_diffs = []
    for run in v1_decision_runs:
        raw_results = run.get("kernels", {}).get("cmy_to_log_raw", {}).get("results", [])
        for result in raw_results:
            if result.get("name") != "cmy_to_log_raw_pixel_thread_v1":
                continue
            precision = result.get("precision_vs_current_fused_metal")
            if precision is not None:
                v1_precision_diffs.append(float(precision.get("max_abs_diff", 0.0) or 0.0))

    min_v1_speedup = min(v1_speedups, default=0.0)
    min_v1_p90_speedup = min(v1_p90_speedups, default=0.0)
    max_v1_memory_ratio = max(v1_memory_ratios, default=0.0)
    max_v1_precision_diff = max(v1_precision_diffs, default=float("inf"))
    p90_speedup_floor = 1.0 / p90_slowdown_limit
    has_v1 = bool(v1_speedups and v1_p90_speedups and v1_precision_diffs)
    memory_ok = not v1_memory_ratios or max_v1_memory_ratio <= memory_increase_limit
    precision_ok = has_v1 and max_v1_precision_diff <= precision_atol
    accept = (
        raw_wall_percent >= wall_threshold_percent
        and max_raw_vs_xyz_ratio >= raw_vs_xyz_ratio_threshold
        and min_v1_speedup >= median_speedup_threshold
        and min_v1_p90_speedup >= p90_speedup_floor
        and memory_ok
        and precision_ok
    )
    if accept:
        reason = (
            "accepted: pixel-thread v1 preserves current raw output and materially improves "
            "a meaningful full-render contributor"
        )
    elif raw_wall_percent < wall_threshold_percent:
        reason = "rejected: cmy_to_log_raw end-to-end wall share is below threshold"
    else:
        if max_raw_vs_xyz_ratio < raw_vs_xyz_ratio_threshold:
            reason = "rejected: cmy_to_log_raw is not at least 2x slower than cmy_to_log_xyz"
        elif not has_v1:
            reason = "rejected: cmy_to_log_raw_pixel_thread_v1 benchmark data is missing"
        elif min_v1_speedup < median_speedup_threshold:
            reason = "rejected: cmy_to_log_raw_pixel_thread_v1 median speedup is below threshold"
        elif min_v1_p90_speedup < p90_speedup_floor:
            reason = "rejected: cmy_to_log_raw_pixel_thread_v1 p90 is slower than allowed"
        elif not memory_ok:
            reason = "rejected: cmy_to_log_raw_pixel_thread_v1 peak memory increased too much"
        else:
            reason = "rejected: cmy_to_log_raw_pixel_thread_v1 precision differs from current fused raw"
    return {
        "accept_raw_pixel_thread_v1": accept,
        "replace_production_recommended": accept,
        "reason": reason,
        "raw_wall_percent": raw_wall_percent,
        "max_raw_fused_to_xyz_fused_median_ratio": max_raw_vs_xyz_ratio,
        "median_speedup_raw_pixel_thread_v1": min_v1_speedup,
        "p90_speedup_raw_pixel_thread_v1": min_v1_p90_speedup,
        "peak_memory_ratio_raw_pixel_thread_v1": None if not v1_memory_ratios else max_v1_memory_ratio,
        "max_diff_raw_pixel_thread_v1_vs_current": max_v1_precision_diff,
        "wall_threshold_percent": wall_threshold_percent,
        "raw_vs_xyz_ratio_threshold": raw_vs_xyz_ratio_threshold,
        "median_speedup_threshold": median_speedup_threshold,
        "p90_slowdown_limit": p90_slowdown_limit,
        "memory_increase_limit": memory_increase_limit,
        "precision_atol": precision_atol,
        "pixel_thread_v1_acceptance_sizes": [list(size) for size in sorted(RAW_PIXEL_THREAD_ACCEPTANCE_SIZES)],
        "pixel_thread_v1_decision_case_count": len(v1_decision_runs),
    }


def run_suite(
    *,
    seed: int,
    include_end_to_end: bool,
    e2e_width: int,
    e2e_height: int,
    e2e_warmup: int,
    e2e_runs: int,
) -> dict[str, Any]:
    kernel_runs = [
        run_kernel_case(
            case=case,
            seed=seed,
            compute_numpy_reference=case.height * case.width <= FULL_REFERENCE_PIXEL_LIMIT,
        )
        for case in acceptance_cases()
    ]
    payload = {
        "status": "ok" if all(run.get("status") == "ok" for run in kernel_runs) else "partial",
        "suite": "mlx_spectral_fused_baseline",
        "seed": seed,
        "kernel_runs": kernel_runs,
        "end_to_end_attribution": (
            run_end_to_end_attribution(
                width=e2e_width,
                height=e2e_height,
                warmup=e2e_warmup,
                runs=e2e_runs,
            )
            if include_end_to_end
            else {"status": "skipped", "reason": "disabled"}
        ),
    }
    payload["recommendation"] = evaluate_raw_pixel_thread_acceptance(payload)
    return payload


def _format_peak(value: int | None) -> str:
    return "n/a" if value is None else f"{value / (1024 * 1024):.1f} MiB"


def _format_diff(value: dict[str, float] | None, key: str = "max_abs_diff") -> str:
    return "n/a" if value is None else f"{value[key]:.3e}"


def _format_optional_ratio(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}x"


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# MLX Spectral Fused Kernel Baseline + Raw Pixel-Thread v1",
        "",
        f"- Suite: {payload.get('suite', 'mlx_spectral_fused_baseline')}",
        f"- Seed: {payload.get('seed')}",
        f"- Status: {payload.get('status')}",
        "",
    ]
    recommendation = payload.get("recommendation", {})
    if recommendation:
        lines.extend(
            [
                "## Recommendation",
                "",
                f"- accept_raw_pixel_thread_v1: `{recommendation['accept_raw_pixel_thread_v1']}`",
                f"- replace_production_recommended: `{recommendation.get('replace_production_recommended', False)}`",
                f"- Reason: {recommendation['reason']}",
                f"- Raw wall share: {recommendation['raw_wall_percent']:.2f}%",
                f"- Max raw/xyz fused median ratio: {recommendation['max_raw_fused_to_xyz_fused_median_ratio']:.3f}x",
                f"- Median speedup raw pixel-thread v1: {recommendation.get('median_speedup_raw_pixel_thread_v1', 0.0):.3f}x",
                f"- P90 speedup raw pixel-thread v1: {recommendation.get('p90_speedup_raw_pixel_thread_v1', 0.0):.3f}x",
                f"- Peak memory ratio raw pixel-thread v1: {_format_optional_ratio(recommendation.get('peak_memory_ratio_raw_pixel_thread_v1'))}",
                f"- Max diff raw pixel-thread v1 vs current: {recommendation.get('max_diff_raw_pixel_thread_v1_vs_current', 0.0):.3e}",
                "",
            ]
        )

    lines.extend(["## Kernel Microbenchmarks", ""])
    for run in payload.get("kernel_runs", []):
        lines.append(f"### {run.get('label', 'case')}")
        if run.get("status") != "ok":
            lines.append(f"Skipped: {run.get('reason', 'unknown reason')}")
            lines.append("")
            continue
        case = run["case"]
        lines.extend(
            [
                "",
                f"- Image: {case['height']}x{case['width']}x3 {case['dtype']}",
                f"- Profiles: {case['film_profile']} -> {case['print_profile']}",
                f"- Spectral length K: {case['spectral_length']}",
                f"- Compile/setup excluded: {case['compile_setup_excluded']}",
                f"- Static table conversion excluded: {case['static_table_conversion_excluded']}",
                f"- NumPy reference computed: {case['numpy_reference_computed']}",
                f"- Warmup: {run['warmup']}",
                f"- Runs: {run['runs']}",
                "",
            ]
        )
        for kernel_name, kernel_payload in run["kernels"].items():
            lines.extend(
                [
                    f"#### {kernel_name}",
                    "",
                    "| Path | Median | P90 | Min | Max | Peak memory | Speedup vs current | Max diff vs NumPy | Mean diff vs NumPy | Max diff vs unfused | Mean diff vs unfused | Max diff vs current | Mean diff vs current |",
                    "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
                ]
            )
            for result in kernel_payload["results"]:
                summary = result["summary"]
                numpy_precision = result.get("precision_vs_numpy")
                unfused_precision = result.get("precision_vs_unfused_backend_chain")
                current_precision = result.get("precision_vs_current_fused_metal")
                lines.append(
                    "| {name} | {median:.3f} ms | {p90:.3f} ms | {min_ms:.3f} ms | "
                    "{max_ms:.3f} ms | {peak} | {speedup_current} | {numpy_max} | {numpy_mean} | "
                    "{unfused_max} | {unfused_mean} | {current_max} | {current_mean} |".format(
                        name=result["name"],
                        median=summary["median_ms"],
                        p90=summary["p90_ms"],
                        min_ms=summary["min_ms"],
                        max_ms=summary["max_ms"],
                        peak=_format_peak(result.get("peak_memory_bytes")),
                        speedup_current=_format_optional_ratio(result.get("speedup_vs_current")),
                        numpy_max=_format_diff(numpy_precision, "max_abs_diff"),
                        numpy_mean=_format_diff(numpy_precision, "mean_abs_diff"),
                        unfused_max=_format_diff(unfused_precision, "max_abs_diff"),
                        unfused_mean=_format_diff(unfused_precision, "mean_abs_diff"),
                        current_max=_format_diff(current_precision, "max_abs_diff"),
                        current_mean=_format_diff(current_precision, "mean_abs_diff"),
                    )
                )
            lines.extend(
                [
                    "",
                    f"- Median speedup fused vs unfused: {kernel_payload['median_speedup_fused_vs_unfused']:.3f}x",
                    f"- Median speedup raw pixel-thread v1 vs current: {_format_optional_ratio(kernel_payload.get('median_speedup_pixel_thread_v1_vs_current'))}",
                    f"- P90 speedup raw pixel-thread v1 vs current: {_format_optional_ratio(kernel_payload.get('p90_speedup_pixel_thread_v1_vs_current'))}",
                    f"- Peak memory ratio raw pixel-thread v1 vs current: {_format_optional_ratio(kernel_payload.get('peak_memory_ratio_pixel_thread_v1_vs_current'))}",
                    "",
                ]
            )
        lines.extend(
            [
                f"- Raw fused / XYZ fused median ratio: {run['raw_fused_to_xyz_fused_median_ratio']:.3f}x",
                "",
            ]
        )

    attribution = payload.get("end_to_end_attribution", {})
    lines.extend(["## End-To-End Attribution", ""])
    if attribution.get("status") != "ok":
        lines.append(f"Skipped: {attribution.get('reason', 'unknown reason')}")
        lines.append("")
    else:
        lines.extend(
            [
                f"- Image shape: {attribution['image_shape']}",
                f"- Runs: {attribution['runs']}",
                f"- Wall median: {attribution['wall_summary']['median_ms']:.3f} ms",
                "",
                "| Kernel | Calls | Shapes | Total | Median | P90 | Wall share |",
                "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
            ]
        )
        for name, entry in attribution["kernel_trace"].items():
            shape_text = ", ".join(f"{shape}: {count}" for shape, count in sorted(entry["shapes"].items()))
            lines.append(
                f"| {name} | {entry['calls']} | {shape_text} | "
                f"{entry['total_seconds'] * 1000.0:.3f} ms | {entry['median_ms']:.3f} ms | "
                f"{entry['p90_ms']:.3f} ms | {entry['wall_percent']:.2f}% |"
            )
        lines.extend(["", "| Stage | Total | Wall share |", "| --- | ---: | ---: |"])
        for key, seconds in attribution["stage_totals"].items():
            lines.append(f"| {key} | {seconds * 1000.0:.3f} ms | {attribution['stage_wall_percent'][key]:.2f}% |")
        lines.append("")
    return "\n".join(lines)


def write_artifacts(output_dir: Path, payload: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"mlx-spectral-fused-baseline-{stamp}.json"
    md_path = output_dir / f"mlx-spectral-fused-baseline-{stamp}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--no-end-to-end", action="store_true")
    parser.add_argument("--e2e-width", type=int, default=1024)
    parser.add_argument("--e2e-height", type=int, default=768)
    parser.add_argument("--e2e-warmup", type=int, default=1)
    parser.add_argument("--e2e-runs", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_REPORT_DIR)
    args = parser.parse_args(argv)

    payload = run_suite(
        seed=args.seed,
        include_end_to_end=not args.no_end_to_end,
        e2e_width=args.e2e_width,
        e2e_height=args.e2e_height,
        e2e_warmup=args.e2e_warmup,
        e2e_runs=args.e2e_runs,
    )
    json_path, md_path = write_artifacts(args.output_dir, payload)
    print(format_markdown(payload))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
