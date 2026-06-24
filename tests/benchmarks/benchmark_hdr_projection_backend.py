#!/usr/bin/env python
"""Benchmark RouteMaster HDR projection backend residency.

This script is intentionally not a pytest test. Run it manually, for example:

    .venv/bin/python tests/benchmarks/benchmark_hdr_projection_backend.py --height 3000 --width 4000

It compares the NumPy projection path with backend-resident RouteMaster inputs
and reports the opt-in backend percentile sort timings from
SPEKTRAFILM_HDR_PROJECTION_PROFILE.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend  # noqa: E402
from spektrafilm.hdr import HDRProjectionConfig, project_hdr_ideal_paper, project_hdr_light_table  # noqa: E402
from spektrafilm.runtime.route_master import RouteMaster  # noqa: E402


PROFILE_ENV = "SPEKTRAFILM_HDR_PROJECTION_PROFILE"


@dataclass(frozen=True)
class ProjectionMode:
    label: str
    hdr_mode: Literal["light_table", "paper"]
    route_kind: Literal["film_scan", "print_scan"]
    chemical_profile: bool = False


def benchmark_modes() -> list[ProjectionMode]:
    return [
        ProjectionMode("light_table_backend_resident", "light_table", "film_scan"),
        ProjectionMode("paper_generic_backend_resident", "paper", "print_scan"),
        ProjectionMode("paper_chemical_numpy_fallback", "paper", "print_scan", chemical_profile=True),
    ]


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one timing")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q / 100.0
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


def make_synthetic_arrays(height: int, width: int, seed: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None]
    route_y = np.float32(0.12) + np.float32(1.05) * (
        np.float32(0.65) * x + np.float32(0.35) * y
    )
    scene_y = np.float32(0.18) + np.float32(7.5) * np.square(
        np.float32(0.55) * x + np.float32(0.45) * y
    )
    noise = rng.normal(0.0, 0.015, size=(height, width)).astype(np.float32)
    scene_y = np.maximum(scene_y + noise, np.float32(0.0))
    route_rgb = np.stack(
        [
            route_y * np.float32(1.00),
            route_y * (np.float32(0.58) + np.float32(0.08) * x),
            route_y * (np.float32(0.30) + np.float32(0.08) * y),
        ],
        axis=2,
    ).astype(np.float32, copy=False)
    return {
        "route_linear_rgb": route_rgb,
        "route_luminance_y": route_y.astype(np.float32, copy=False),
        "sdr_legacy_rgb": np.clip(route_rgb, 0.0, 1.0).astype(np.float32, copy=False),
        "scene_y_raw": scene_y.astype(np.float32, copy=False),
        "post_halation_y": (scene_y * np.float32(1.05)).astype(np.float32, copy=False),
    }


def make_master(
    arrays: dict[str, np.ndarray],
    mode: ProjectionMode,
    *,
    backend: Any | None = None,
) -> RouteMaster:
    def arr(value: np.ndarray) -> Any:
        return value if backend is None else backend.asarray(value)

    diagnostics: dict[str, Any] = {
        "output_cctf_encoding": False,
        "output_color_space": "sRGB",
    }
    if mode.chemical_profile:
        diagnostics.update({
            "film": "kodak_portra_400",
            "paper": "kodak_portra_endura",
        })
    return RouteMaster(
        mode=mode.hdr_mode,
        route_kind=mode.route_kind,
        route_linear_rgb=arr(arrays["route_linear_rgb"]),
        route_luminance_y=arr(arrays["route_luminance_y"]),
        sdr_legacy_rgb=arr(arrays["sdr_legacy_rgb"]),
        scene_y_raw=arr(arrays["scene_y_raw"]),
        post_halation_y=arr(arrays["post_halation_y"]),
        route_linear_xyz=None,
        density_cmy=None,
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics=diagnostics,
    )


def project(mode: ProjectionMode, master: RouteMaster, config: HDRProjectionConfig):
    if mode.hdr_mode == "light_table":
        return project_hdr_light_table(master, config)
    return project_hdr_ideal_paper(master, config)


def _is_mlx_array(value: Any) -> bool:
    return type(value).__module__.startswith("mlx.")


def _sync_result(backend: Any | None, result: Any) -> None:
    if backend is None:
        return
    values = [
        getattr(result, "sdr_rgb", None),
        getattr(result, "hdr_rgb", None),
        getattr(result, "hdr_luminance_y", None),
        getattr(result, "gain_map", None),
    ]
    eval_fn = getattr(backend, "eval", None)
    mlx_values = [value for value in values if _is_mlx_array(value)]
    if callable(eval_fn) and mlx_values:
        eval_fn(*mlx_values)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()


def _reset_peak_memory(mx: Any) -> None:
    for owner in (mx, getattr(mx, "metal", None)):
        reset = getattr(owner, "reset_peak_memory", None)
        if callable(reset):
            reset()
            return


def _memory_bytes(mx: Any, getter_name: str) -> int | None:
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, getter_name, None)
        if callable(getter):
            return int(getter())
    return None


def _clear_cache(backend: Any) -> None:
    clear = getattr(backend, "clear_cache", None)
    if callable(clear):
        clear()
        return
    mx = getattr(backend, "mx", None)
    for owner in (mx, getattr(mx, "metal", None)):
        clear = getattr(owner, "clear_cache", None)
        if callable(clear):
            clear()
            return


@contextmanager
def _projection_profile_env(enabled: bool) -> Iterator[None]:
    previous = os.environ.get(PROFILE_ENV)
    if enabled:
        os.environ[PROFILE_ENV] = "1"
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(PROFILE_ENV, None)
        else:
            os.environ[PROFILE_ENV] = previous


def _result_backend(result: Any) -> str:
    if _is_mlx_array(getattr(result, "hdr_rgb", None)):
        return "mlx"
    if isinstance(getattr(result, "hdr_rgb", None), np.ndarray):
        return "numpy"
    return type(getattr(result, "hdr_rgb", None)).__name__


def _time_projection(
    *,
    label: str,
    mode: ProjectionMode,
    master: RouteMaster,
    config: HDRProjectionConfig,
    backend: Any | None,
    warmups: int,
    runs: int,
    profile_backend: bool,
) -> dict[str, Any]:
    for _ in range(max(0, warmups)):
        with _projection_profile_env(False):
            warmup = project(mode, master, config)
        _sync_result(backend, warmup)
    if backend is not None:
        _clear_cache(backend)

    timings: list[float] = []
    projection_profiles: list[dict[str, Any]] = []
    last_result = None
    for _ in range(max(1, runs)):
        if backend is not None:
            _reset_peak_memory(backend.mx)
        start = time.perf_counter()
        with _projection_profile_env(profile_backend):
            last_result = project(mode, master, config)
        _sync_result(backend, last_result)
        timings.append(time.perf_counter() - start)
        profile = getattr(last_result, "diagnostics", {}).get("projection_profile")
        if isinstance(profile, dict):
            projection_profiles.append(profile)

    return {
        "label": label,
        "status": "ok",
        "summary": summarize_ms(timings),
        "timings_ms": [value * 1000.0 for value in timings],
        "result_backend": _result_backend(last_result),
        "projection_backend": getattr(last_result, "diagnostics", {}).get("projection_backend"),
        "projection_metadata_statistics": getattr(last_result, "diagnostics", {}).get("projection_metadata_statistics"),
        "projection_profiles": projection_profiles,
        "peak_memory_bytes": _memory_bytes(backend.mx, "get_peak_memory") if backend is not None else None,
        "cache_memory_bytes": _memory_bytes(backend.mx, "get_cache_memory") if backend is not None else None,
    }


def run_benchmark(
    *,
    height: int,
    width: int,
    seed: int,
    warmups: int,
    runs: int,
    modes: list[str] | None = None,
) -> dict[str, Any]:
    selected = set(modes or [mode.label for mode in benchmark_modes()])
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=99.9)
    arrays = make_synthetic_arrays(height, width, seed)
    try:
        backend = select_backend("mlx", precision="float32")
    except (BackendUnavailableError, Exception) as exc:
        return {
            "status": "skipped",
            "reason": f"{type(exc).__name__}: {exc}",
            "input": {"height": height, "width": width, "seed": seed},
        }

    results: list[dict[str, Any]] = []
    for mode in benchmark_modes():
        if mode.label not in selected:
            continue
        cpu_master = make_master(arrays, mode)
        backend_master = make_master(arrays, mode, backend=backend)
        cpu_result = _time_projection(
            label=f"{mode.label}:cpu_numpy_projection",
            mode=mode,
            master=cpu_master,
            config=config,
            backend=None,
            warmups=warmups,
            runs=runs,
            profile_backend=False,
        )
        backend_result = _time_projection(
            label=f"{mode.label}:backend_master_projection",
            mode=mode,
            master=backend_master,
            config=config,
            backend=backend,
            warmups=warmups,
            runs=runs,
            profile_backend=True,
        )
        results.append(
            {
                "mode": mode.label,
                "hdr_mode": mode.hdr_mode,
                "chemical_profile": mode.chemical_profile,
                "cpu_projection": cpu_result,
                "backend_master_projection": backend_result,
            }
        )

    return {
        "status": "ok",
        "input": {"height": height, "width": width, "pixels": height * width, "seed": seed},
        "config": {
            "max_headroom": config.max_headroom,
            "headroom_percentile": config.headroom_percentile,
        },
        "runs": runs,
        "warmups": warmups,
        "results": results,
    }


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "n/a"
    mib = float(value) / (1024.0 * 1024.0)
    return f"{mib:.1f} MiB"


def _profile_sort_total_ms(run: dict[str, Any]) -> float | None:
    profiles = run.get("projection_profiles") or []
    if not profiles:
        return None
    totals = [float(profile.get("percentile_sort_ms_total", 0.0)) for profile in profiles]
    return statistics.median(totals)


def _profile_calls(result: dict[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    profiles = result.get("backend_master_projection", {}).get("projection_profiles") or []
    for run_index, profile in enumerate(profiles, start=1):
        for call in profile.get("percentile_calls", []):
            calls.append({"run": run_index, **call})
    return calls


def format_markdown(payload: dict[str, Any]) -> str:
    if payload.get("status") != "ok":
        return f"# HDR Projection Backend Benchmark\n\nStatus: {payload.get('status')}\n\nReason: {payload.get('reason')}"
    lines = [
        "# HDR Projection Backend Benchmark",
        "",
        f"Input: {payload['input']['height']}x{payload['input']['width']} ({payload['input']['pixels']} px)",
        f"Runs: {payload['runs']} timed, {payload['warmups']} warmup",
        "",
        "## Projection Time And Memory",
        "",
        "| Mode | Path | Result backend | Median | P90 | MLX peak memory | MLX cache memory | Percentile sort total | Metadata stats |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in payload["results"]:
        for key, path in (("cpu_projection", "CPU NumPy projection"), ("backend_master_projection", "Backend RouteMaster projection")):
            run = result[key]
            sort_total = _profile_sort_total_ms(run)
            sort_text = "n/a" if sort_total is None else f"{sort_total:.3f} ms"
            lines.append(
                "| "
                f"{result['mode']} | {path} | {run['result_backend']} | "
                f"{run['summary']['median_ms']:.3f} ms | {run['summary']['p90_ms']:.3f} ms | "
                f"{_format_bytes(run.get('peak_memory_bytes'))} | {_format_bytes(run.get('cache_memory_bytes'))} | "
                f"{sort_text} | {run.get('projection_metadata_statistics') or 'full_statistics'} |"
            )
    lines.extend([
        "",
        "## Percentile Sort Calls",
        "",
        "| Mode | Run | Label | Percentile | Pixels | sort_to_scalar |",
        "| --- | ---: | --- | ---: | ---: | ---: |",
    ])
    for result in payload["results"]:
        calls = _profile_calls(result)
        if not calls:
            lines.append(f"| {result['mode']} | n/a | n/a | n/a | n/a | n/a |")
            continue
        for call in calls:
            lines.append(
                "| "
                f"{result['mode']} | {call['run']} | {call['label']} | "
                f"{call['percentile']:.3f} | {call['size']} | {call['sort_to_scalar_ms']:.3f} ms |"
            )
    return "\n".join(lines)


def parse_modes(value: str) -> list[str] | None:
    normalized = value.strip()
    if normalized == "all":
        return None
    labels = [item.strip() for item in normalized.split(",") if item.strip()]
    valid = {mode.label for mode in benchmark_modes()}
    unknown = sorted(set(labels) - valid)
    if unknown:
        raise ValueError(f"unknown mode(s): {', '.join(unknown)}")
    return labels


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--seed", type=int, default=123)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--modes", default="all")
    parser.add_argument("--output-json", type=Path, default=None)
    parser.add_argument("--output-markdown", type=Path, default=None)
    args = parser.parse_args()

    payload = run_benchmark(
        height=args.height,
        width=args.width,
        seed=args.seed,
        warmups=args.warmups,
        runs=args.runs,
        modes=parse_modes(args.modes),
    )
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    markdown = format_markdown(payload)
    if args.output_markdown is not None:
        args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
        args.output_markdown.write_text(markdown, encoding="utf-8")
    print(markdown)


if __name__ == "__main__":
    main()
