#!/usr/bin/env python3
"""End-to-end MLX performance and 50MP memory reaudit harness.

The parent process runs each scenario in an isolated child and samples the
whole process tree.  The child records MLX allocator counters, residency
events, cold/hot timings, explicit host boundaries, and output signatures.
Prototype candidates are installed only inside the child process; this script
never changes production defaults.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import gc
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SCHEMA_VERSION = 1
DEFAULT_SEED = 20260710
DEFAULT_HEIGHT = 6120
DEFAULT_WIDTH = 8160
PASS_FOOTPRINT_BYTES = 12 * 1024**3
FAIL_FOOTPRINT_BYTES = 13 * 1024**3
REQUIRED_SCENARIOS = (
    "scan-only",
    "film-paper",
    "film-paper-spatial-grain",
    "hdr-light-table",
    "hdr-paper",
    "preprocess-resize",
    "save-boundary",
    "hdr-export-boundary",
)
CANDIDATES = (
    "baseline",
    "stable-compile-cache",
    "fused-filming-tiling",
    "partition-percentile",
    "poisson-all-normal",
    "legacy-poisson",
    "tile-cache-release",
)


def _package_version(name: str) -> str | None:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def _run_text(command: list[str], *, timeout: float = 10.0) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout if completed.stdout else completed.stderr


def _git_head() -> str:
    value = _run_text(["git", "rev-parse", "HEAD"]).strip()
    return value or "unknown"


def environment_payload() -> dict[str, Any]:
    sw_vers = _run_text(["sw_vers"])
    memsize = _run_text(["sysctl", "-n", "hw.memsize"]).strip()
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "sw_vers": sw_vers.strip(),
        "unified_memory_bytes": int(memsize) if memsize.isdigit() else None,
        "mlx": _package_version("mlx"),
        "numpy": np.__version__,
        "rawpy": _package_version("rawpy"),
        "psutil": _package_version("psutil"),
        "physical_footprint_tool": str(Path("/usr/bin/footprint")) if Path("/usr/bin/footprint").exists() else None,
    }


def result_envelope(*, head_sha: str, environment: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "head_sha": head_sha,
        "environment": environment,
        "input": {},
        "scenarios": {},
        "memory": {},
        "parity": {},
        "findings": [],
        "verdict": {},
        "limitations": [],
        "commands": [],
        "agent_configuration": {},
    }


def direct_input_spec(*, height: int, width: int, seed: int) -> dict[str, Any]:
    return {
        "height": int(height),
        "width": int(width),
        "channels": 3,
        "pixels": int(height) * int(width),
        "dtype": "float32",
        "seed": int(seed),
        "generation": "direct_deterministic_linear_rgb",
        "upscaled": False,
        "real_50mp_raw": False,
    }


def make_deterministic_rgb(
    height: int,
    width: int,
    *,
    seed: int = DEFAULT_SEED,
    chunk_rows: int = 128,
) -> np.ndarray:
    """Build deterministic full-size linear RGB directly, in bounded row chunks."""
    if height <= 0 or width <= 0 or chunk_rows <= 0:
        raise ValueError("height, width, and chunk_rows must be positive")
    output = np.empty((height, width, 3), dtype=np.float32)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    phase = np.float32((int(seed) % 10007) / 10007.0)
    two_pi = np.float32(2.0 * math.pi)
    for y0 in range(0, height, chunk_rows):
        y1 = min(height, y0 + chunk_rows)
        y = (np.arange(y0, y1, dtype=np.float32) / np.float32(max(height - 1, 1)))[:, None]
        highlight = np.maximum(x + y - np.float32(1.82), np.float32(0.0))
        output[y0:y1, :, 0] = (
            np.float32(0.025)
            + np.float32(0.72) * x
            + np.float32(0.035) * np.sin((x + phase) * two_pi * np.float32(3.0))
            + np.float32(2.8) * highlight
        )
        output[y0:y1, :, 1] = (
            np.float32(0.035)
            + np.float32(0.70) * y
            + np.float32(0.030) * np.sin((y + phase) * two_pi * np.float32(2.0))
            + np.float32(2.2) * highlight
        )
        output[y0:y1, :, 2] = (
            np.float32(0.02)
            + np.float32(0.31) * x
            + np.float32(0.39) * y
            + np.float32(0.025) * np.sin((x + y + phase) * two_pi * np.float32(4.0))
            + np.float32(1.8) * highlight
        )
    np.maximum(output, np.float32(0.0), out=output)
    return output


def hdr_mode_for_scenario(scenario: str) -> str:
    """Choose an HDR route that exercises the requested boundary."""
    if scenario in {"hdr-light-table", "hdr-export-boundary"}:
        return "light_table"
    if scenario == "hdr-paper":
        return "paper"
    raise ValueError(f"Scenario {scenario!r} is not an HDR scenario")


def _timing_summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"runs": 0, "median_seconds": None, "min_seconds": None, "max_seconds": None}
    return {
        "runs": len(values),
        "median_seconds": float(statistics.median(values)),
        "min_seconds": float(min(values)),
        "max_seconds": float(max(values)),
    }


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for phase in ("cold", "hot"):
        values = [float(sample["wall_seconds"]) for sample in samples if sample.get("phase") == phase]
        result[phase] = _timing_summary(values)
    return result


def memory_snapshot(
    *,
    mlx_active_bytes: int | None,
    mlx_peak_bytes: int | None,
    mlx_cache_bytes: int | None,
    rss_bytes: int | None,
    physical_footprint_bytes: int | None,
    physical_footprint_peak_bytes: int | None,
) -> dict[str, Any]:
    return {
        "mlx_active_bytes": mlx_active_bytes,
        "mlx_peak_bytes": mlx_peak_bytes,
        "mlx_cache_bytes": mlx_cache_bytes,
        "rss_bytes": rss_bytes,
        "physical_footprint_bytes": physical_footprint_bytes,
        "physical_footprint_peak_bytes": physical_footprint_peak_bytes,
        "counters_overlap": True,
        "combined_total_bytes": None,
    }


_BYTE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024**2,
    "GB": 1024**3,
    "TB": 1024**4,
    "KIB": 1024,
    "MIB": 1024**2,
    "GIB": 1024**3,
    "TIB": 1024**4,
}


def _human_bytes(value: str, unit: str) -> int:
    multiplier = _BYTE_UNITS[unit.strip().upper()]
    return int(float(value) * multiplier)


def parse_footprint_output(output: str) -> dict[str, int | None]:
    current = re.search(r"phys_footprint:\s*([0-9.]+)\s*([KMGT]?i?B)", output, re.IGNORECASE)
    peak = re.search(r"phys_footprint_peak:\s*([0-9.]+)\s*([KMGT]?i?B)", output, re.IGNORECASE)
    return {
        "physical_footprint_bytes": _human_bytes(*current.groups()) if current else None,
        "physical_footprint_peak_bytes": _human_bytes(*peak.groups()) if peak else None,
    }


def parse_swap_usage(output: str) -> dict[str, int | None]:
    matches = {
        key: re.search(rf"{key}\s*=\s*([0-9.]+)([KMGT])", output, re.IGNORECASE)
        for key in ("total", "used", "free")
    }
    return {
        f"{key}_bytes": _human_bytes(match.group(1), match.group(2) + "B") if match else None
        for key, match in matches.items()
    }


def parse_memory_pressure(output: str) -> dict[str, Any]:
    match = re.search(r"memory free percentage:\s*([0-9.]+)%", output, re.IGNORECASE)
    free_percent = float(match.group(1)) if match else None
    if free_percent is None:
        level = "unknown"
    elif free_percent <= 5.0:
        level = "critical"
    elif free_percent <= 10.0:
        level = "warning"
    else:
        level = "normal"
    return {"free_percent": free_percent, "level": level}


def classify_swap_activity(
    *,
    start_used_bytes: int | None,
    samples: Iterable[int | None],
) -> dict[str, Any]:
    values = [int(value) for value in samples if value is not None]
    if start_used_bytes is not None and (not values or values[0] != int(start_used_bytes)):
        values.insert(0, int(start_used_bytes))
    if not values:
        return {"swap_growth_bytes": None, "swap_thrashing": False, "short_swap": False}

    start = int(start_used_bytes) if start_used_bytes is not None else values[0]
    growth = max(values) - start
    meaningful = 64 * 1024**2
    consecutive = 0
    max_consecutive = 0
    for previous, current in zip(values, values[1:]):
        if current - previous > meaningful:
            consecutive += 1
            max_consecutive = max(max_consecutive, consecutive)
        else:
            consecutive = 0
    thrashing = growth > 512 * 1024**2 and max_consecutive >= 2
    return {
        "swap_growth_bytes": growth,
        "swap_thrashing": thrashing,
        "short_swap": bool(growth > 128 * 1024**2 and not thrashing),
    }


def classify_subprocess_exit(*, returncode: int | None, timed_out: bool, stderr: str) -> str:
    if timed_out:
        return "timeout"
    if returncode == 0:
        return "ok"
    if returncode is not None and returncode < 0:
        return "system-kill" if -returncode in {signal.SIGKILL, signal.SIGTERM} else "signal"
    lowered = stderr.lower()
    if "out of memory" in lowered or "memoryerror" in lowered or "metal command buffer" in lowered:
        return "oom"
    return "error"


def safety_abort_reason(result: dict[str, Any]) -> str | None:
    status = str(result.get("status", "unknown"))
    if status in {"memory-guard", "oom", "system-kill"}:
        return status
    if result.get("critical_pressure"):
        return "critical-pressure"
    if result.get("swap_thrashing"):
        return "swap-thrashing"
    return None


def classify_16gb_verdict(scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    reasons: list[str] = []
    if not scenarios:
        return {"level": "FAIL", "reasons": ["no scenarios completed"]}
    max_footprint = max(
        (int(item["physical_footprint_peak_bytes"]) for item in scenarios if item.get("physical_footprint_peak_bytes") is not None),
        default=None,
    )
    hard_failure = False
    conditional = False
    for item in scenarios:
        status = item.get("status")
        if status != "ok":
            hard_failure = True
            reasons.append(f"scenario status={status}")
        if item.get("critical_pressure"):
            hard_failure = True
            reasons.append("critical memory pressure")
        if item.get("swap_thrashing"):
            hard_failure = True
            reasons.append("sustained swap growth")
        if item.get("exceptional_fallback"):
            hard_failure = True
            reasons.append("exceptional fallback")
        if not item.get("parity_ok", False):
            hard_failure = True
            reasons.append("output parity not proven")
        if item.get("warning_pressure"):
            conditional = True
            reasons.append("warning memory pressure")
        if item.get("short_swap"):
            conditional = True
            reasons.append("short swap growth")
        if item.get("manual_budget_required"):
            conditional = True
            reasons.append("manual budget required")
    if max_footprint is None:
        hard_failure = True
        reasons.append("physical footprint unavailable")
    elif max_footprint > FAIL_FOOTPRINT_BYTES:
        hard_failure = True
        reasons.append("physical footprint exceeded 13GiB")
    elif max_footprint > PASS_FOOTPRINT_BYTES:
        conditional = True
        reasons.append("physical footprint was between 12GiB and 13GiB")
    level = "FAIL" if hard_failure else "CONDITIONAL" if conditional else "PASS"
    return {"level": level, "max_physical_footprint_bytes": max_footprint, "reasons": sorted(set(reasons))}


def _argument_signature(value: Any) -> tuple[Any, ...]:
    shape = getattr(value, "shape", None)
    dtype = getattr(value, "dtype", None)
    if shape is not None and dtype is not None:
        return (
            type(value).__module__,
            type(value).__qualname__,
            tuple(int(dim) for dim in shape),
            str(dtype),
        )
    return (type(value).__module__, type(value).__qualname__)


def _closure_fingerprint(value: Any) -> tuple[Any, ...]:
    if isinstance(value, np.generic):
        value = value.item()
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return ("scalar", type(value).__module__, type(value).__qualname__, value)
    if hasattr(value, "shape") and hasattr(value, "dtype"):
        return ("array-object", id(value), _argument_signature(value))
    module = type(value).__module__
    qualname = type(value).__qualname__
    if module.startswith("spektrafilm.gpu"):
        return ("backend-instance", module, qualname)
    return ("object", module, qualname, id(value))


def stable_compile_key(name: str, function: Callable[..., Any], *sample_args: Any) -> tuple[Any, ...]:
    closure = tuple(
        _closure_fingerprint(cell.cell_contents)
        for cell in (function.__closure__ or ())
    )
    return (
        str(name),
        function.__code__,
        closure,
        tuple(_argument_signature(arg) for arg in sample_args),
    )


def install_stable_compile_cache_prototype() -> tuple[Callable[[], None], dict[str, Any]]:
    from spektrafilm.gpu.mlx_backend import MlxBackend

    original = MlxBackend.compiled_elementwise
    state: dict[str, Any] = {"hits": 0, "misses": 0, "clears": 0, "keys": []}

    def replacement(self, name: str, function: Callable[..., Any], *sample_args: Any):
        compile_fn = getattr(self.mx, "compile", None)
        if not callable(compile_fn):
            return function
        cache = getattr(self, "_reaudit_stable_compile_cache", None)
        if cache is None:
            cache = {}
            setattr(self, "_reaudit_stable_compile_cache", cache)
        key = stable_compile_key(name, function, *sample_args)
        compiled = cache.get(key)
        if compiled is None:
            state["misses"] += 1
            if len(cache) >= 128:
                cache.clear()
                state["clears"] += 1
            compiled = compile_fn(function)
            cache[key] = compiled
            state["keys"].append(str(name))
        else:
            state["hits"] += 1
        return compiled

    MlxBackend.compiled_elementwise = replacement

    def restore() -> None:
        MlxBackend.compiled_elementwise = original

    return restore, state


def percentile_index_plan(*, size: int, percentile: float) -> tuple[int, int, float]:
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0.0 <= percentile <= 100.0:
        raise ValueError("percentile must be between 0 and 100")
    position = (size - 1) * float(percentile) / 100.0
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    return lower, upper, float(position - lower)


def _partition_percentile(values: Any, percentile: float) -> float:
    import mlx.core as mx

    flat = mx.reshape(values, (-1,))
    size = int(flat.size)
    if size == 0:
        return float("nan")
    lower, upper, weight = percentile_index_plan(size=size, percentile=percentile)
    lower_value = mx.partition(flat, lower)[lower]
    if lower == upper:
        return float(np.asarray(lower_value))
    upper_value = mx.partition(flat, upper)[upper]
    value = lower_value * np.float32(1.0 - weight) + upper_value * np.float32(weight)
    return float(np.asarray(value))


def install_partition_percentile_prototype() -> tuple[Callable[[], None], dict[str, Any]]:
    from spektrafilm.hdr import projection

    original = projection._percentile_backend
    state = {"calls": 0, "seconds": 0.0}

    def replacement(values: Any, percentile: float, *, label: str) -> float:
        start = time.perf_counter()
        result = _partition_percentile(values, percentile)
        elapsed = time.perf_counter() - start
        state["calls"] += 1
        state["seconds"] += elapsed
        profile = projection._ACTIVE_BACKEND_PROFILE.get()
        if profile is not None:
            profile.record_percentile(
                label=label,
                percentile=percentile,
                size=int(values.size),
                elapsed_seconds=elapsed,
            )
        return result

    projection._percentile_backend = replacement

    def restore() -> None:
        projection._percentile_backend = original

    return restore, state


def install_fused_tiling_prototype(settings: Any) -> tuple[Callable[[], None], dict[str, Any]]:
    from spektrafilm.gpu.kernels.fused_ops import apply_fused_filming_filters_tiled
    from spektrafilm.runtime.stages import filming

    original = filming.apply_fused_filming_filters
    state = {"calls": 0}

    def replacement(
        raw,
        *,
        diffusion_filter,
        lens_blur_um: float,
        halation,
        pixel_size_um: float,
        backend=None,
    ):
        state["calls"] += 1
        return apply_fused_filming_filters_tiled(
            raw,
            diffusion_filter=diffusion_filter,
            lens_blur_um=lens_blur_um,
            halation=halation,
            pixel_size_um=pixel_size_um,
            backend=backend,
            settings=settings,
        )

    filming.apply_fused_filming_filters = replacement

    def restore() -> None:
        filming.apply_fused_filming_filters = original

    return restore, state


def install_poisson_all_normal_prototype() -> tuple[Callable[[], None], dict[str, Any]]:
    """Skip the unused Knuth graph only when every MLX lambda is above 10."""
    from spektrafilm.gpu.kernels import grain as grain_kernels

    original = grain_kernels.fast_poisson_backend
    state = {"calls": 0, "all_normal_fast_path": 0, "delegated": 0}

    def replacement(
        lam: Any,
        backend=None,
        *,
        seed: int | None = None,
        all_lam_above_threshold: bool = False,
    ):
        del all_lam_above_threshold
        state["calls"] += 1
        if backend is None or not hasattr(backend, "mx"):
            state["delegated"] += 1
            return original(lam, backend, seed=seed)

        mx = backend.mx
        lam_mx = backend.asarray(lam, dtype=mx.float32)
        if not bool(np.asarray(mx.all(lam_mx > np.float32(10.0)))):
            state["delegated"] += 1
            return original(lam_mx, backend, seed=seed)

        state["all_normal_fast_path"] += 1
        key = mx.random.key(seed if seed is not None else 0)
        key_norm, _ = mx.random.split(key)
        sqrt_lam = mx.sqrt(lam_mx)
        normal_samples = lam_mx + sqrt_lam * mx.random.normal(
            lam_mx.shape,
            key=key_norm,
            dtype=mx.float32,
        )
        normal_int = mx.round(normal_samples).astype(mx.int32)
        return mx.maximum(normal_int, mx.zeros_like(normal_int))

    grain_kernels.fast_poisson_backend = replacement

    def restore() -> None:
        grain_kernels.fast_poisson_backend = original

    return restore, state


def install_legacy_poisson_prototype() -> tuple[Callable[[], None], dict[str, Any]]:
    """Restore the pre-audit MLX Poisson merge for reproducible A/B runs."""
    from spektrafilm.gpu.kernels import grain as grain_kernels

    original = grain_kernels.fast_poisson_backend
    state = {"calls": 0, "mlx_legacy_calls": 0, "knuth_rounds_constructed": 0}

    def legacy(
        lam: Any,
        backend=None,
        *,
        seed: int | None = None,
        all_lam_above_threshold: bool = False,
    ):
        del all_lam_above_threshold
        state["calls"] += 1
        if not grain_kernels._backend_supports_gpu(backend) or grain_kernels._backend_supports_cupy(backend):
            return original(lam, backend, seed=seed)

        state["mlx_legacy_calls"] += 1
        mx = grain_kernels._ensure_mx(backend)
        lam_mx = backend.asarray(lam, dtype=mx.float32)
        key = grain_kernels._make_key(mx, seed)
        use_normal = lam_mx > 10.0

        sqrt_lam = mx.sqrt(lam_mx)
        key_norm, key = mx.random.split(key)
        normal_samples = lam_mx + sqrt_lam * mx.random.normal(
            lam_mx.shape,
            key=key_norm,
            dtype=mx.float32,
        )
        normal_int = mx.round(normal_samples).astype(mx.int32)
        normal_clamped = mx.maximum(normal_int, mx.zeros_like(normal_int))

        max_iter = 60
        state["knuth_rounds_constructed"] += max_iter
        knuth_count = mx.zeros(lam_mx.shape, dtype=mx.int32)
        knuth_product = mx.ones(lam_mx.shape, dtype=mx.float32)
        exp_neg_lam = mx.exp(-lam_mx)
        key_knuth_start, _ = mx.random.split(key)
        current_key = key_knuth_start
        for _ in range(max_iter):
            uniform_key, current_key = mx.random.split(current_key)
            uniform = mx.random.uniform(
                low=0.0,
                high=1.0,
                shape=lam_mx.shape,
                key=uniform_key,
                dtype=mx.float32,
            )
            knuth_product = knuth_product * uniform
            still_active = knuth_product > exp_neg_lam
            knuth_count = knuth_count + still_active.astype(mx.int32)
        return mx.where(use_normal, normal_clamped, knuth_count)

    grain_kernels.fast_poisson_backend = legacy

    def restore() -> None:
        grain_kernels.fast_poisson_backend = original

    return restore, state


def install_tile_cache_release_prototype() -> tuple[Callable[[], None], dict[str, Any]]:
    """Activate the tile utility's existing optional cache-release hook."""
    from spektrafilm.gpu.mlx_backend import MlxBackend

    sentinel = object()
    original = MlxBackend.__dict__.get("clear_cache", sentinel)
    state = {"calls": 0}

    def replacement(self) -> None:
        state["calls"] += 1
        clear = getattr(self.mx, "clear_cache", None)
        if not callable(clear):
            clear = getattr(getattr(self.mx, "metal", None), "clear_cache", None)
        if callable(clear):
            clear()

    MlxBackend.clear_cache = replacement

    def restore() -> None:
        if original is sentinel:
            delattr(MlxBackend, "clear_cache")
        else:
            MlxBackend.clear_cache = original

    return restore, state


def estimate_raw_decode_overlap(
    *,
    height: int,
    width: int,
    mosaic_bytes_per_pixel: int,
    decoder_rgb_bytes_per_channel: int,
    spektrafilm_input_bytes_per_channel: int,
) -> dict[str, Any]:
    pixels = int(height) * int(width)
    mosaic = pixels * int(mosaic_bytes_per_pixel)
    decoder = pixels * 3 * int(decoder_rgb_bytes_per_channel)
    spektrafilm = pixels * 3 * int(spektrafilm_input_bytes_per_channel)
    return {
        "height": int(height),
        "width": int(width),
        "pixels": pixels,
        "raw_mosaic_bytes": mosaic,
        "decoder_rgb_bytes": decoder,
        "spektrafilm_input_bytes": spektrafilm,
        "conservative_simultaneous_bytes": mosaic + decoder + spektrafilm,
        "includes_mlx_allocator": False,
        "overlap_assumption": "raw mosaic, decoder RGB, and Spektrafilm float32 input coexist",
    }


def _mlx_memory(backend: Any, name: str) -> int | None:
    mx = getattr(backend, "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, name, None)
        if callable(getter):
            try:
                return int(getter())
            except (OSError, RuntimeError, TypeError, ValueError):
                return None
    return None


def _reset_mlx_peak(backend: Any) -> None:
    mx = getattr(backend, "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        reset = getattr(owner, "reset_peak_memory", None)
        if callable(reset):
            reset()
            return


def _is_mlx_array(value: Any) -> bool:
    return type(value).__module__.startswith("mlx.")


def _sync_values(backend: Any, values: Iterable[Any]) -> None:
    selected = [value for value in values if _is_mlx_array(value)]
    if selected:
        backend.eval(*selected)
    backend.synchronize()


def _array_sha256(value: np.ndarray) -> str:
    contiguous = np.ascontiguousarray(value)
    return hashlib.sha256(memoryview(contiguous).cast("B")).hexdigest()


def _final_encoder_boundary_signature(
    backend: Any,
    value: Any,
    *,
    label: str,
) -> tuple[dict[str, Any], np.ndarray]:
    start = time.perf_counter()
    if _is_mlx_array(value):
        array = backend.to_numpy(value)
    else:
        array = np.asarray(value)
    array = np.asarray(array)
    elapsed = time.perf_counter() - start
    signature = {
        "label": label,
        "shape": [int(dim) for dim in array.shape],
        "dtype": str(array.dtype),
        "nbytes": int(array.nbytes),
        "sha256": _array_sha256(array),
        "finite": bool(np.isfinite(array).all()),
        "min": float(np.min(array)),
        "max": float(np.max(array)),
        "mean": float(np.mean(array, dtype=np.float64)),
        "materialize_seconds": elapsed,
    }
    return signature, array


def _scenario_params(
    scenario: str,
    *,
    gpu_budget_mib: float | None,
    gpu_budget_policy: str,
) -> Any:
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params("kodak_portra_400", "kodak_portra_endura")
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.color_precision_policy = "balanced"
    params.settings.materialize_policy = "backend"
    params.settings.gpu_validate = False
    params.settings.gpu_peak_budget_mb = gpu_budget_mib
    params.settings.gpu_budget_policy = gpu_budget_policy
    params.settings.preview_mode = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.input_color_space = "ProPhoto RGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False

    route_isolation = scenario in {"scan-only", "film-paper", "preprocess-resize", "save-boundary"}
    if route_isolation:
        params.film_render.grain.active = False
        params.film_render.dir_couplers.active = False
        params.film_render.halation.active = False
        params.camera.diffusion_filter.active = False
        params.camera.lens_blur_um = 0.0
        params.scanner.lens_blur = 0.0
        params.scanner.unsharp_mask = (0.0, 0.0)
        params.debug.deactivate_stochastic_effects = True
        params.debug.deactivate_spatial_effects = True
    else:
        params.debug.deactivate_stochastic_effects = False
        params.debug.deactivate_spatial_effects = False

    params.io.scan_film = scenario in {"scan-only", "hdr-light-table", "preprocess-resize"}
    if scenario == "preprocess-resize":
        params.io.upscale_factor = 1.25
        params.settings.gpu_resize_policy = "warn"
    return digest_params(params)


def _event_counts(events: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        operation = str(getattr(event, "operation", getattr(event, "direction", "unknown")))
        counts[operation] = counts.get(operation, 0) + 1
        category = getattr(event, "category", None)
        if category:
            key = f"category:{category}"
            counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _run_one_phase(
    *,
    pipeline: Any,
    image: np.ndarray,
    scenario: str,
    phase: str,
    artifact_dir: Path,
    init_seconds: float,
) -> dict[str, Any]:
    from spektrafilm.hdr.routemaster_export import (
        export_hdr_heic_from_simulator,
        render_hdr_pair_from_master,
    )

    backend = pipeline._backend
    _reset_mlx_peak(backend)
    start = time.perf_counter()
    process_start = start
    route_process_seconds = 0.0
    projection_seconds = 0.0
    save_seconds = 0.0
    signatures: list[dict[str, Any]] = []
    output_files: list[dict[str, Any]] = []
    values: list[tuple[str, Any]] = []
    master = None

    if scenario in {"hdr-light-table", "hdr-paper", "hdr-export-boundary"}:
        mode = hdr_mode_for_scenario(scenario)
        route_start = time.perf_counter()
        processed = pipeline.process_with_master(image, hdr_mode=mode)
        route_process_seconds = time.perf_counter() - route_start
        master = processed.route_master
        if master is None:
            raise RuntimeError("HDR scenario completed without RouteMaster")
        if scenario == "hdr-export-boundary":
            path = artifact_dir / f"{scenario}-{phase}.heic"
            diagnostics_out: dict[str, object] = {}
            export_start = time.perf_counter()
            diagnostics = export_hdr_heic_from_simulator(
                simulator=None,
                image=None,
                filename=path,
                hdr_mode=mode,
                color_space="sRGB",
                master=master,
                export_diagnostics_out=diagnostics_out,
            )
            save_seconds = time.perf_counter() - export_start
            output_files.append(
                {
                    "path": str(path),
                    "size_bytes": path.stat().st_size if path.exists() else None,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
                    "diagnostics": list(diagnostics),
                    "export_diagnostics": diagnostics_out,
                }
            )
            if path.exists():
                path.unlink()
        else:
            projection_start = time.perf_counter()
            projection = render_hdr_pair_from_master(master, hdr_mode=mode)
            values = [
                ("sdr_rgb", projection.sdr_rgb),
                ("hdr_rgb", projection.hdr_rgb),
                ("gain_map", projection.gain_map),
            ]
            _sync_values(backend, [value for _, value in values])
            projection_seconds = time.perf_counter() - projection_start
    else:
        output = pipeline.process(image)
        values = [("image", output)]
        _sync_values(backend, [output])
        route_process_seconds = time.perf_counter() - process_start
    process_seconds = time.perf_counter() - process_start

    materialize_start = time.perf_counter()
    materialized_for_save: np.ndarray | None = None
    for label, value in values:
        signature, array = _final_encoder_boundary_signature(backend, value, label=label)
        signatures.append(signature)
        if scenario == "save-boundary" and label == "image":
            materialized_for_save = array
        else:
            del array
    materialize_seconds = time.perf_counter() - materialize_start

    if scenario == "save-boundary":
        from spektrafilm.utils.io import save_image_oiio

        if materialized_for_save is None:
            raise RuntimeError("save-boundary did not materialize an image")
        path = artifact_dir / f"{scenario}-{phase}.tiff"
        save_start = time.perf_counter()
        save_image_oiio(
            str(path),
            materialized_for_save,
            bit_depth=16,
            color_space="sRGB",
            cctf_encoding=True,
        )
        save_seconds = time.perf_counter() - save_start
        output_files.append(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size if path.exists() else None,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None,
            }
        )
        if path.exists():
            path.unlink()
        del materialized_for_save

    total = time.perf_counter() - start
    if phase == "cold":
        total += init_seconds
    mlx = memory_snapshot(
        mlx_active_bytes=_mlx_memory(backend, "get_active_memory"),
        mlx_peak_bytes=_mlx_memory(backend, "get_peak_memory"),
        mlx_cache_bytes=_mlx_memory(backend, "get_cache_memory"),
        rss_bytes=None,
        physical_footprint_bytes=None,
        physical_footprint_peak_bytes=None,
    )
    warnings = list(getattr(pipeline, "memory_residency_warnings", []))
    timings = {str(key): float(value) for key, value in pipeline.get_timings().items()}
    del values, master
    gc.collect()
    return {
        "phase": phase,
        "wall_seconds": total,
        "pipeline_init_seconds": init_seconds if phase == "cold" else 0.0,
        "process_seconds": process_seconds,
        "route_process_seconds": route_process_seconds,
        "hdr_projection_seconds": projection_seconds,
        "materialize_seconds": materialize_seconds,
        "save_or_export_seconds": save_seconds,
        "mlx_memory": mlx,
        "output_signatures": signatures,
        "output_files": output_files,
        "pipeline_timings": timings,
        "warnings": warnings,
    }


def _install_candidate(candidate: str, settings: Any) -> tuple[list[Callable[[], None]], dict[str, Any]]:
    restores: list[Callable[[], None]] = []
    states: dict[str, Any] = {}
    if candidate == "stable-compile-cache":
        restore, state = install_stable_compile_cache_prototype()
        restores.append(restore)
        states["stable_compile_cache"] = state
    elif candidate == "fused-filming-tiling":
        restore, state = install_fused_tiling_prototype(settings)
        restores.append(restore)
        states["fused_filming_tiling"] = state
    elif candidate == "partition-percentile":
        restore, state = install_partition_percentile_prototype()
        restores.append(restore)
        states["partition_percentile"] = state
    elif candidate == "poisson-all-normal":
        restore, state = install_poisson_all_normal_prototype()
        restores.append(restore)
        states["poisson_all_normal"] = state
    elif candidate == "legacy-poisson":
        restore, state = install_legacy_poisson_prototype()
        restores.append(restore)
        states["legacy_poisson"] = state
    elif candidate == "tile-cache-release":
        restore, state = install_tile_cache_release_prototype()
        restores.append(restore)
        states["tile_cache_release"] = state
    elif candidate != "baseline":
        raise ValueError(f"unknown candidate: {candidate}")
    return restores, states


def _signature_map(sample: dict[str, Any]) -> dict[str, str]:
    signatures = {
        str(item["label"]): str(item["sha256"])
        for item in sample.get("output_signatures", [])
    }
    for index, item in enumerate(sample.get("output_files", [])):
        digest = item.get("sha256")
        if digest:
            suffix = Path(str(item.get("path", "output"))).suffix.lower() or ".bin"
            signatures[f"file:{suffix}:{index}"] = str(digest)
    return signatures


def run_child_scenario(args: argparse.Namespace) -> dict[str, Any]:
    from spektrafilm.gpu.residency import record_backend_residency
    from spektrafilm.runtime.pipeline import SimulationPipeline

    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    input_start = time.perf_counter()
    image = make_deterministic_rgb(args.height, args.width, seed=args.seed, chunk_rows=args.chunk_rows)
    input_seconds = time.perf_counter() - input_start
    params = _scenario_params(
        args.scenario,
        gpu_budget_mib=args.gpu_budget_mib,
        gpu_budget_policy=args.gpu_budget_policy,
    )
    restores, prototype_state = _install_candidate(args.candidate, params.settings)
    try:
        init_start = time.perf_counter()
        pipeline = SimulationPipeline(params)
        init_seconds = time.perf_counter() - init_start
        with record_backend_residency(small_array_bytes=64 * 1024) as recorder:
            samples = [
                _run_one_phase(
                    pipeline=pipeline,
                    image=image,
                    scenario=args.scenario,
                    phase="cold",
                    artifact_dir=artifact_dir,
                    init_seconds=init_seconds,
                )
            ]
            for _ in range(args.hot_runs):
                samples.append(
                    _run_one_phase(
                        pipeline=pipeline,
                        image=image,
                        scenario=args.scenario,
                        phase="hot",
                        artifact_dir=artifact_dir,
                        init_seconds=0.0,
                    )
                )
        signatures = [_signature_map(sample) for sample in samples if _signature_map(sample)]
        internal_parity = len(signatures) <= 1 or all(item == signatures[0] for item in signatures[1:])
        selected_backend = getattr(pipeline._backend, "name", None)
        return {
            "status": "ok",
            "scenario": args.scenario,
            "candidate": args.candidate,
            "input_generation_seconds": input_seconds,
            "input": direct_input_spec(height=args.height, width=args.width, seed=args.seed),
            "effects_profile": (
                "route_isolation_effects_off"
                if args.scenario in {"scan-only", "film-paper", "preprocess-resize", "save-boundary"}
                else "full_default_spatial_and_grain"
            ),
            "selected_backend": selected_backend,
            "samples": samples,
            "timing_summary": summarize_samples(samples),
            "residency_counts": _event_counts(list(recorder.events)),
            "residency_summary": recorder.summary(),
            "prototype_state": prototype_state,
            "parity_ok": bool(internal_parity),
            "exceptional_fallback": selected_backend != "mlx",
            "memory_budget_report": getattr(pipeline, "memory_budget_report", None),
        }
    finally:
        for restore in reversed(restores):
            restore()


def run_raw_decode_child(args: argparse.Namespace) -> dict[str, Any]:
    import rawpy

    from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

    path = Path(args.raw_path)
    with rawpy.imread(str(path)) as raw:
        mosaic = raw.raw_image_visible
        raw_meta = {
            "raw_width": int(raw.sizes.raw_width),
            "raw_height": int(raw.sizes.raw_height),
            "output_width": int(raw.sizes.width),
            "output_height": int(raw.sizes.height),
            "mosaic_dtype": str(mosaic.dtype),
            "mosaic_nbytes": int(mosaic.nbytes),
        }
    start = time.perf_counter()
    output = load_and_process_raw_file(
        str(path),
        white_balance="as_shot",
        output_colorspace="ProPhoto RGB",
        output_cctf_encoding=False,
    )
    elapsed = time.perf_counter() - start
    output = np.asarray(output)
    return {
        "status": "ok",
        "path": str(path),
        "file_size_bytes": path.stat().st_size,
        "real_raw": True,
        "real_50mp_raw": int(output.shape[0]) * int(output.shape[1]) >= 45_000_000,
        "raw": raw_meta,
        "output_shape": [int(dim) for dim in output.shape],
        "output_dtype": str(output.dtype),
        "output_nbytes": int(output.nbytes),
        "decode_seconds": elapsed,
        "output_sha256": _array_sha256(output),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")


def _child_main(args: argparse.Namespace) -> int:
    try:
        payload = run_raw_decode_child(args) if args.raw_decode_child else run_child_scenario(args)
        _write_json(Path(args.result_json), payload)
        return 0
    except BaseException as exc:
        payload = {
            "status": "error",
            "scenario": getattr(args, "scenario", None),
            "candidate": getattr(args, "candidate", None),
            "error": f"{type(exc).__name__}: {exc}",
        }
        with contextlib.suppress(Exception):
            _write_json(Path(args.result_json), payload)
        raise


def _process_tree(root_process: Any) -> list[Any]:
    processes = [root_process]
    with contextlib.suppress(Exception):
        processes.extend(root_process.children(recursive=True))
    unique: dict[int, Any] = {}
    for process in processes:
        with contextlib.suppress(Exception):
            unique[int(process.pid)] = process
    return list(unique.values())


def _tree_rss_bytes(root_process: Any) -> int:
    total = 0
    for process in _process_tree(root_process):
        with contextlib.suppress(Exception):
            total += int(process.memory_info().rss)
    return total


def _footprint_for_pid(pid: int) -> dict[str, int | None]:
    output = _run_text(["/usr/bin/footprint", "--noCategories", "-p", str(pid)], timeout=5.0)
    return parse_footprint_output(output)


def _tree_footprint(root_process: Any) -> dict[str, int | None]:
    current = 0
    peak = 0
    available = False
    for process in _process_tree(root_process):
        parsed = _footprint_for_pid(int(process.pid))
        if parsed["physical_footprint_bytes"] is not None:
            current += int(parsed["physical_footprint_bytes"])
            available = True
        if parsed["physical_footprint_peak_bytes"] is not None:
            peak += int(parsed["physical_footprint_peak_bytes"])
    return {
        "physical_footprint_bytes": current if available else None,
        "physical_footprint_peak_bytes": peak if available else None,
    }


def update_footprint_peaks(
    *,
    sampled_peak_bytes: int,
    reported_peak_upper_bound_bytes: int,
    current_tree_bytes: int,
    summed_process_peak_bytes: int,
) -> tuple[int, int]:
    """Track simultaneous samples separately from nonconcurrent process peaks."""
    return (
        max(int(sampled_peak_bytes), int(current_tree_bytes)),
        max(int(reported_peak_upper_bound_bytes), int(summed_process_peak_bytes)),
    )


def _system_snapshot() -> dict[str, Any]:
    return {
        "swap": parse_swap_usage(_run_text(["sysctl", "vm.swapusage"])),
        "pressure": parse_memory_pressure(_run_text(["memory_pressure", "-Q"])),
    }


def _terminate_tree(process: subprocess.Popen[Any]) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)


def run_isolated_child(
    command: list[str],
    *,
    result_path: Path,
    timeout_seconds: float,
    sample_interval: float,
    max_footprint_bytes: int,
) -> dict[str, Any]:
    import psutil

    start_snapshot = _system_snapshot()
    start = time.perf_counter()
    with tempfile.NamedTemporaryFile(prefix="mlx-reaudit-stdout-", delete=False) as stdout_file, tempfile.NamedTemporaryFile(
        prefix="mlx-reaudit-stderr-", delete=False
    ) as stderr_file:
        stdout_path = Path(stdout_file.name)
        stderr_path = Path(stderr_file.name)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout_file,
            stderr=stderr_file,
            start_new_session=True,
        )
    ps_process = psutil.Process(process.pid)
    rss_peak = 0
    footprint_peak = 0
    footprint_reported_peak_upper_bound = 0
    footprint_current = None
    footprint_available = False
    pressure_samples: list[dict[str, Any]] = []
    swap_samples: list[dict[str, Any]] = []
    timed_out = False
    memory_guard = False
    next_slow_sample = 0.0
    try:
        while process.poll() is None:
            elapsed = time.perf_counter() - start
            rss_peak = max(rss_peak, _tree_rss_bytes(ps_process))
            if elapsed >= next_slow_sample:
                footprint = _tree_footprint(ps_process)
                if footprint["physical_footprint_bytes"] is not None:
                    footprint_available = True
                    footprint_current = int(footprint["physical_footprint_bytes"])
                    footprint_peak, footprint_reported_peak_upper_bound = update_footprint_peaks(
                        sampled_peak_bytes=footprint_peak,
                        reported_peak_upper_bound_bytes=footprint_reported_peak_upper_bound,
                        current_tree_bytes=footprint_current,
                        summed_process_peak_bytes=int(footprint["physical_footprint_peak_bytes"] or 0),
                    )
                system = _system_snapshot()
                pressure_samples.append({"elapsed_seconds": elapsed, **system["pressure"]})
                swap_samples.append({"elapsed_seconds": elapsed, **system["swap"]})
                next_slow_sample = elapsed + max(1.0, sample_interval * 4.0)
            if footprint_current is not None and footprint_current > max_footprint_bytes:
                memory_guard = True
                _terminate_tree(process)
                break
            if pressure_samples and pressure_samples[-1].get("level") == "critical":
                memory_guard = True
                _terminate_tree(process)
                break
            if elapsed > timeout_seconds:
                timed_out = True
                _terminate_tree(process)
                break
            time.sleep(max(0.05, sample_interval))
    except BaseException:
        _terminate_tree(process)
        raise
    returncode = process.poll()
    elapsed = time.perf_counter() - start
    with contextlib.suppress(Exception):
        rss_peak = max(rss_peak, _tree_rss_bytes(ps_process))
    stdout = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    stderr = stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    stdout_path.unlink(missing_ok=True)
    stderr_path.unlink(missing_ok=True)
    end_snapshot = _system_snapshot()
    child_payload: dict[str, Any] = {}
    if result_path.exists():
        with contextlib.suppress(Exception):
            child_payload = json.loads(result_path.read_text(encoding="utf-8"))
        result_path.unlink(missing_ok=True)
    status = "memory-guard" if memory_guard else classify_subprocess_exit(
        returncode=returncode,
        timed_out=timed_out,
        stderr=stderr,
    )
    used_values = [sample.get("used_bytes") for sample in swap_samples if sample.get("used_bytes") is not None]
    start_used = start_snapshot["swap"].get("used_bytes")
    end_used = end_snapshot["swap"].get("used_bytes")
    observed_used = [*used_values]
    if end_used is not None:
        observed_used.append(end_used)
    max_used = max(observed_used, default=start_used)
    swap_activity = classify_swap_activity(
        start_used_bytes=start_used,
        samples=observed_used,
    )
    swap_delta = swap_activity["swap_growth_bytes"]
    min_free = min(
        (float(sample["free_percent"]) for sample in pressure_samples if sample.get("free_percent") is not None),
        default=None,
    )
    critical = any(sample.get("level") == "critical" for sample in pressure_samples)
    warning = any(sample.get("level") == "warning" for sample in pressure_samples)
    external = {
        "elapsed_seconds": elapsed,
        "returncode": returncode,
        "status": status,
        "rss_tree_peak_bytes": rss_peak,
        "physical_footprint_peak_bytes": footprint_peak if footprint_available else None,
        "physical_footprint_reported_peak_upper_bound_bytes": (
            footprint_reported_peak_upper_bound if footprint_available else None
        ),
        "physical_footprint_available": footprint_available,
        "swap_start_used_bytes": start_used,
        "swap_max_used_bytes": max_used,
        "swap_end_used_bytes": end_used,
        "swap_growth_bytes": swap_delta,
        "swap_thrashing": swap_activity["swap_thrashing"],
        "short_swap": swap_activity["short_swap"],
        "minimum_memory_free_percent": min_free,
        "critical_pressure": critical,
        "warning_pressure": warning,
        "memory_guard_triggered": memory_guard,
        "start_system": start_snapshot,
        "end_system": end_snapshot,
        "pressure_samples": pressure_samples,
        "swap_samples": swap_samples,
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-8000:],
    }
    child_payload["external_measurement"] = external
    child_payload["status"] = status if status != "ok" else child_payload.get("status", "ok")
    child_payload["physical_footprint_peak_bytes"] = external["physical_footprint_peak_bytes"]
    child_payload["rss_tree_peak_bytes"] = external["rss_tree_peak_bytes"]
    child_payload["critical_pressure"] = external["critical_pressure"]
    child_payload["warning_pressure"] = external["warning_pressure"]
    child_payload["swap_thrashing"] = external["swap_thrashing"]
    child_payload["short_swap"] = external["short_swap"]
    child_payload.setdefault("exceptional_fallback", False)
    child_payload.setdefault("parity_ok", False)
    return child_payload


def _child_command(args: argparse.Namespace, *, scenario: str, candidate: str, result_path: Path) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--scenario",
        scenario,
        "--candidate",
        candidate,
        "--height",
        str(args.height),
        "--width",
        str(args.width),
        "--seed",
        str(args.seed),
        "--chunk-rows",
        str(args.chunk_rows),
        "--hot-runs",
        str(args.hot_runs),
        "--artifact-dir",
        str(args.artifact_dir),
        "--result-json",
        str(result_path),
        "--gpu-budget-policy",
        args.gpu_budget_policy,
    ]
    if args.gpu_budget_mib is not None:
        command.extend(["--gpu-budget-mib", str(args.gpu_budget_mib)])
    return command


def _raw_child_command(args: argparse.Namespace, *, result_path: Path) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--child",
        "--raw-decode-child",
        "--raw-path",
        str(args.raw_path),
        "--result-json",
        str(result_path),
        "--artifact-dir",
        str(args.artifact_dir),
    ]


def _last_signature_map(result: dict[str, Any]) -> dict[str, str]:
    samples = result.get("samples", [])
    if not samples:
        return {}
    hot = [sample for sample in samples if sample.get("phase") == "hot"]
    return _signature_map(hot[-1] if hot else samples[-1])


def _candidate_parity(scenarios: dict[str, dict[str, Any]]) -> dict[str, Any]:
    baseline = scenarios.get("baseline", {})
    parity: dict[str, Any] = {}
    for candidate, candidate_results in scenarios.items():
        if candidate == "baseline":
            continue
        per_scenario: dict[str, Any] = {}
        for name, result in candidate_results.items():
            reference = _last_signature_map(baseline.get(name, {}))
            actual = _last_signature_map(result)
            per_scenario[name] = {
                "exact_output_hash_match": bool(reference and actual and reference == actual),
                "baseline_hashes": reference,
                "candidate_hashes": actual,
            }
        parity[candidate] = per_scenario
    return parity


def _supplemental_scenario_summary(result: dict[str, Any]) -> dict[str, Any]:
    external = result.get("external_measurement") or {}
    samples = result.get("samples") or []
    mlx_keys = ("mlx_active_bytes", "mlx_peak_bytes", "mlx_cache_bytes")
    mlx_peaks = {
        key: max(
            (
                int(sample.get("mlx_memory", {}).get(key))
                for sample in samples
                if sample.get("mlx_memory", {}).get(key) is not None
            ),
            default=None,
        )
        for key in mlx_keys
    }
    return {
        "status": result.get("status"),
        "parity_ok": bool(result.get("parity_ok", False)),
        "physical_footprint_peak_bytes": result.get("physical_footprint_peak_bytes"),
        "physical_footprint_reported_peak_upper_bound_bytes": external.get(
            "physical_footprint_reported_peak_upper_bound_bytes"
        ),
        "rss_tree_peak_bytes": result.get("rss_tree_peak_bytes"),
        "swap_growth_bytes": external.get("swap_growth_bytes"),
        "minimum_memory_free_percent": external.get("minimum_memory_free_percent"),
        "critical_pressure": bool(result.get("critical_pressure", False)),
        "swap_thrashing": bool(result.get("swap_thrashing", False)),
        "timing_summary": result.get("timing_summary", {}),
        "mlx_memory_maxima": mlx_peaks,
        "output_hashes": _last_signature_map(result),
        "prototype_state": result.get("prototype_state", {}),
        "blocked_by": result.get("blocked_by"),
        "safety_reason": result.get("safety_reason"),
    }


def summarize_supplemental_payload(payload: dict[str, Any]) -> dict[str, Any]:
    scenario_summaries: dict[str, dict[str, Any]] = {}
    for candidate, candidate_results in (payload.get("scenarios") or {}).items():
        scenario_summaries[str(candidate)] = {
            str(name): _supplemental_scenario_summary(result)
            for name, result in candidate_results.items()
        }
    return {
        "head_sha": payload.get("head_sha"),
        "input": payload.get("input", {}),
        "verdict": payload.get("verdict", {}),
        "scenarios": scenario_summaries,
        "parity": payload.get("parity", {}),
    }


def load_supplemental_results(specs: Iterable[str]) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for spec in specs:
        label, separator, raw_path = str(spec).partition("=")
        if not separator or not label or not raw_path:
            raise ValueError("--supplemental-result must use LABEL=PATH")
        payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
        summaries[label] = summarize_supplemental_payload(payload)
    return summaries


def _refresh_parent_summary(payload: dict[str, Any], results: dict[str, dict[str, Any]]) -> None:
    payload["scenarios"] = results
    payload["parity"] = _candidate_parity(results)
    payload["verdict"] = classify_16gb_verdict(list(results.get("baseline", {}).values()))


def mark_unrun_scenarios(
    results: dict[str, dict[str, Any]],
    *,
    candidates: Iterable[str],
    scenarios: Iterable[str],
    blocked_by: str,
    reason: str,
) -> None:
    for candidate in candidates:
        candidate_results = results.setdefault(str(candidate), {})
        for scenario in scenarios:
            candidate_results.setdefault(
                str(scenario),
                {
                    "candidate": str(candidate),
                    "scenario": str(scenario),
                    "status": "not-run-safety-abort",
                    "blocked_by": str(blocked_by),
                    "safety_reason": str(reason),
                    "parity_ok": False,
                    "critical_pressure": False,
                    "warning_pressure": False,
                    "swap_thrashing": False,
                    "short_swap": False,
                    "exceptional_fallback": False,
                    "physical_footprint_peak_bytes": None,
                },
            )


def run_parent(args: argparse.Namespace) -> dict[str, Any]:
    payload = result_envelope(head_sha=_git_head(), environment=environment_payload())
    payload["input"] = direct_input_spec(height=args.height, width=args.width, seed=args.seed)
    payload["memory"] = {
        "note": "MLX active/peak/cache, RSS, and physical footprint overlap and are never added.",
        "guard_bytes": int(args.max_footprint_gib * 1024**3),
        "sample_interval_seconds": args.sample_interval,
    }
    payload["agent_configuration"] = {
        "controller_requested": "GPT-5.6 Sol",
        "controller_runtime_identity_inspectable": False,
        "subagent_requested": "GPT-5.6 Luna",
        "subagent_model_assignment_supported": False,
        "actual_structure": "controller plus three model-opaque subagents; controller occupied validation seat",
    }
    payload["limitations"] = [
        "The only repository RAW is 4032x3024 (12.2MP); 50MP processing uses direct deterministic linear RGB.",
        "Route-isolation scenarios disable optional effects; PASS still requires the full spatial/grain and HDR scenarios.",
        "Physical footprint is sampled externally and includes descendants when footprint can inspect them.",
    ]
    payload["commands"] = [" ".join(sys.argv)]
    supplemental = load_supplemental_results(args.supplemental_result)
    if supplemental:
        payload["findings"].append(
            {"type": "supplemental_result_summaries", "runs": supplemental}
        )

    raw_result_path = Path(tempfile.mkstemp(prefix="mlx-reaudit-raw-", suffix=".json")[1])
    raw_result_path.unlink(missing_ok=True)
    raw_command = _raw_child_command(args, result_path=raw_result_path)
    raw_result = run_isolated_child(
        raw_command,
        result_path=raw_result_path,
        timeout_seconds=args.timeout_seconds,
        sample_interval=args.sample_interval,
        max_footprint_bytes=int(args.max_footprint_gib * 1024**3),
    )
    raw_result["conservative_50mp_overlap"] = estimate_raw_decode_overlap(
        height=DEFAULT_HEIGHT,
        width=DEFAULT_WIDTH,
        mosaic_bytes_per_pixel=2,
        decoder_rgb_bytes_per_channel=2,
        spektrafilm_input_bytes_per_channel=4,
    )
    payload["input"]["raw_decode_probe"] = raw_result
    _write_json(args.output_json, payload)

    results: dict[str, dict[str, Any]] = {}
    for candidate in args.candidates:
        candidate_results: dict[str, Any] = {}
        results[candidate] = candidate_results
        for scenario in args.scenarios:
            result_path = Path(tempfile.mkstemp(prefix="mlx-reaudit-child-", suffix=".json")[1])
            result_path.unlink(missing_ok=True)
            command = _child_command(args, scenario=scenario, candidate=candidate, result_path=result_path)
            print(f"[{candidate}] {scenario}", flush=True)
            result = run_isolated_child(
                command,
                result_path=result_path,
                timeout_seconds=args.timeout_seconds,
                sample_interval=args.sample_interval,
                max_footprint_bytes=int(args.max_footprint_gib * 1024**3),
            )
            candidate_results[scenario] = result
            _refresh_parent_summary(payload, results)
            _write_json(args.output_json, payload)
            abort_reason = safety_abort_reason(result)
            if abort_reason is not None:
                blocked_by = f"{candidate}/{scenario}"
                mark_unrun_scenarios(
                    results,
                    candidates=args.candidates,
                    scenarios=args.scenarios,
                    blocked_by=blocked_by,
                    reason=abort_reason,
                )
                payload["limitations"].append(
                    f"Matrix stopped after {blocked_by} for system safety: {abort_reason}."
                )
                _refresh_parent_summary(payload, results)
                _write_json(args.output_json, payload)
                return payload
    _refresh_parent_summary(payload, results)
    return payload


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--raw-decode-child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--scenario", choices=REQUIRED_SCENARIOS, default="scan-only")
    parser.add_argument("--candidate", choices=CANDIDATES, default="baseline")
    parser.add_argument("--scenarios", nargs="+", choices=REQUIRED_SCENARIOS, default=list(REQUIRED_SCENARIOS))
    parser.add_argument("--candidates", nargs="+", choices=CANDIDATES, default=["baseline"])
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--chunk-rows", type=int, default=128)
    parser.add_argument("--hot-runs", type=int, default=2)
    parser.add_argument("--gpu-budget-mib", type=float)
    parser.add_argument("--gpu-budget-policy", choices=("off", "warn", "soft_enforce", "fail"), default="off")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--sample-interval", type=float, default=0.5)
    parser.add_argument("--max-footprint-gib", type=float, default=10.5)
    parser.add_argument(
        "--supplemental-result",
        action="append",
        default=[],
        metavar="LABEL=PATH",
        help="Embed a bounded decision summary from an earlier harness result.",
    )
    parser.add_argument("--raw-path", type=Path, default=ROOT / "scratch" / "IMG_9121_converted.DNG")
    parser.add_argument("--artifact-dir", type=Path, default=Path("/tmp/spektrafilm-mlx-audit/artifacts"))
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--output-json", type=Path, default=ROOT / "docs/reports/mlx-performance-reaudit-20260710.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.child:
        if args.result_json is None:
            raise SystemExit("--child requires --result-json")
        return _child_main(args)
    payload = run_parent(args)
    _write_json(args.output_json, payload)
    print(f"Wrote {args.output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
