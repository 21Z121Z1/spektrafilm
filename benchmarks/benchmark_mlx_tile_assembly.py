#!/usr/bin/env python
"""Benchmark MLX tiled row-output assembly strategies.

This harness intentionally lives outside the production tiling helpers.  It
compares the current ``output.at[y0:y1].add(tile)`` assembly against a
``mx.concatenate`` prototype using synthetic 12MP/24MP workloads, and records
why direct Metal scatter is not used unless MLX exposes a safe in-place output
contract.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.tile_utils import (
    default_spatial_tile_rows,
    default_tile_rows,
    process_rows_tiled,
    process_spatial_rows_tiled,
)


SIZE_SHAPES: dict[str, tuple[int, int, int]] = {
    "12mp": (3072, 4096, 3),
    "24mp": (4000, 6000, 3),
}
STRATEGIES = ("at_add", "concat", "metal_scatter")
METAL_SCATTER_FEASIBILITY_REASON = (
    "infeasible: MLX fast.metal_kernel allocates declared outputs and does "
    "not expose a supported in-place write into an existing full-frame array. "
    "A scatter prototype would need one full-frame output per tile before "
    "combining, which defeats the residency/memory goal."
)


@dataclass
class BenchmarkRecord:
    scenario: str
    size: str
    shape: tuple[int, int, int]
    strategy: str
    tile_rows: int | None
    overlap: int | None
    status: str
    run_seconds: list[float]
    peak_memory_mib: list[float | None]
    median_seconds: float | None
    min_seconds: float | None
    max_seconds: float | None
    peak_memory_max_mib: float | None
    parity_max_abs_diff: float | None
    checksum: float | None
    mean: float | None
    max_value: float | None
    error: str | None = None


@dataclass
class StrategySummary:
    size: str
    strategy: str
    status: str
    median_of_medians_seconds: float | None
    peak_memory_max_mib: float | None
    parity_max_abs_diff: float | None
    records: int


def metal_scatter_feasibility() -> tuple[bool, str]:
    """Return whether the Metal scatter strategy is safe to benchmark."""
    return False, METAL_SCATTER_FEASIBILITY_REASON


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be > 0")
    return parsed


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark MLX row-tile output assembly strategies."
    )
    parser.add_argument("--sizes", nargs="+", choices=sorted(SIZE_SHAPES), default=["12mp", "24mp"])
    parser.add_argument("--strategies", nargs="+", choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument("--tile-rows", nargs="+", type=_positive_int, default=[256, 512, 1024, 2048])
    parser.add_argument("--overlaps", nargs="+", type=_positive_int, default=[16, 64, 128])
    parser.add_argument("--runs", type=_positive_int, default=3)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument(
        "--no-default-tile-rows",
        action="store_true",
        help="Do not add default_tile_rows/default_spatial_tile_rows to the requested tile rows.",
    )
    parser.add_argument("--real-pipeline", action="store_true")
    parser.add_argument("--image", type=Path)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "docs" / "reports")
    return parser.parse_args(argv)


def resolve_benchmark_tile_rows(
    height: int,
    requested: list[int],
    *,
    spatial: bool,
    include_default: bool = True,
) -> list[int]:
    values = list(requested)
    if include_default:
        values.append(default_spatial_tile_rows(height) if spatial else default_tile_rows(height))
    return sorted({int(v) for v in values if int(v) > 0})


def _memory_owner(mx: Any) -> Any | None:
    for owner in (mx, getattr(mx, "metal", None)):
        if callable(getattr(owner, "reset_peak_memory", None)) and callable(
            getattr(owner, "get_peak_memory", None)
        ):
            return owner
    return None


def reset_peak_memory(backend: Any) -> bool:
    owner = _memory_owner(backend.mx)
    if owner is None:
        return False
    owner.reset_peak_memory()
    return True


def get_peak_memory_mib(backend: Any) -> float | None:
    owner = _memory_owner(backend.mx)
    if owner is None:
        return None
    try:
        return float(owner.get_peak_memory()) / (1024.0**2)
    except (RuntimeError, TypeError, ValueError):
        return None


def cleanup_backend(backend: Any) -> None:
    cleanup = getattr(backend, "cleanup", None)
    if callable(cleanup):
        cleanup()
    else:
        backend.synchronize()


def make_synthetic_image(backend: Any, shape: tuple[int, int, int]) -> Any:
    """Create a deterministic float32 MLX image without a large host array."""
    h, w, c = shape
    if c != 3:
        raise ValueError("synthetic benchmark expects RGB shape")
    mx = backend.mx
    dtype = backend.default_dtype
    yy = mx.arange(h, dtype=mx.float32).reshape((h, 1, 1)) / max(h - 1, 1)
    xx = mx.arange(w, dtype=mx.float32).reshape((1, w, 1)) / max(w - 1, 1)
    cc = mx.array([0.13, 0.47, 0.81], dtype=mx.float32).reshape((1, 1, 3))
    image = 0.5 + 0.25 * mx.sin(xx * 12.9898 + yy * 78.233 + cc * 3.17)
    image = image.astype(dtype)
    backend.eval(image)
    backend.synchronize()
    return image


def spectral_process_fn(mx: Any) -> Callable[[Any], Any]:
    def _process(tile: Any) -> Any:
        return tile * 1.0003 + mx.sin(tile * 0.01) * 0.001

    return _process


def spatial_process_fn(mx: Any) -> Callable[[Any], Any]:
    def _process(tile_ext: Any) -> Any:
        top = mx.concatenate([tile_ext[:1], tile_ext[:-1]], axis=0)
        bottom = mx.concatenate([tile_ext[1:], tile_ext[-1:]], axis=0)
        return tile_ext * 0.5 + (top + bottom) * 0.25 + mx.sin(tile_ext * 0.01) * 0.001

    return _process


def _iter_row_bounds(height: int, tile_rows: int) -> list[tuple[int, int]]:
    return [(y0, min(height, y0 + tile_rows)) for y0 in range(0, height, tile_rows)]


def assemble_spectral_at_add(image: Any, process_fn: Callable[[Any], Any], backend: Any, tile_rows: int) -> Any:
    return process_rows_tiled(image, process_fn, backend, tile_rows=tile_rows, eval_per_tile=True)


def assemble_spectral_concat(image: Any, process_fn: Callable[[Any], Any], backend: Any, tile_rows: int) -> Any:
    height = int(image.shape[0])
    if tile_rows <= 0 or height <= tile_rows:
        return process_fn(image)

    outputs = []
    for y0, y1 in _iter_row_bounds(height, tile_rows):
        tile_out = process_fn(image[y0:y1])
        backend.eval(tile_out)
        outputs.append(tile_out)
    return backend.mx.concatenate(outputs, axis=0)


def assemble_spatial_at_add(
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    *,
    overlap: int,
    tile_rows: int,
) -> Any:
    return process_spatial_rows_tiled(
        image,
        process_fn,
        backend,
        overlap=overlap,
        tile_rows=tile_rows,
        eval_per_tile=True,
    )


def assemble_spatial_concat(
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    *,
    overlap: int,
    tile_rows: int,
) -> Any:
    height = int(image.shape[0])
    if tile_rows <= 0 or overlap <= 0 or height <= tile_rows + 2 * overlap:
        return process_fn(image)

    outputs = []
    for y0, y1 in _iter_row_bounds(height, tile_rows):
        ext_y0 = max(0, y0 - overlap)
        ext_y1 = min(height, y1 + overlap)
        tile_out_ext = process_fn(image[ext_y0:ext_y1])
        in_offset = y0 - ext_y0
        out_len = y1 - y0
        central = tile_out_ext[in_offset : in_offset + out_len]
        backend.eval(central)
        outputs.append(central)
    return backend.mx.concatenate(outputs, axis=0)


def _strategy_callable(
    scenario: str,
    strategy: str,
) -> Callable[..., Any]:
    if scenario == "spectral" and strategy == "at_add":
        return assemble_spectral_at_add
    if scenario == "spectral" and strategy == "concat":
        return assemble_spectral_concat
    if scenario == "spatial" and strategy == "at_add":
        return assemble_spatial_at_add
    if scenario == "spatial" and strategy == "concat":
        return assemble_spatial_concat
    raise ValueError(f"unsupported strategy for benchmark execution: {strategy}")


def output_stats(output: Any, backend: Any) -> tuple[float, float, float]:
    mx = backend.mx
    checksum = mx.sum(output)
    mean = mx.mean(output)
    max_value = mx.max(output)
    backend.eval(checksum, mean, max_value)
    backend.synchronize()
    return (
        float(np.asarray(checksum)),
        float(np.asarray(mean)),
        float(np.asarray(max_value)),
    )


def max_abs_diff(left: Any, right: Any, backend: Any) -> float:
    diff = backend.mx.max(backend.mx.abs(left - right))
    backend.eval(diff)
    backend.synchronize()
    return float(np.asarray(diff))


def _is_oom_error(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "out of memory" in text or "oom" in text or "memory" in text


def run_strategy_once(
    *,
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    scenario: str,
    strategy: str,
    tile_rows: int,
    overlap: int | None,
) -> tuple[Any, float, float | None]:
    func = _strategy_callable(scenario, strategy)
    cleanup_backend(backend)
    reset_peak_memory(backend)
    start = time.perf_counter()
    if scenario == "spectral":
        output = func(image, process_fn, backend, tile_rows)
    else:
        if overlap is None:
            raise ValueError("spatial scenario requires overlap")
        output = func(image, process_fn, backend, overlap=overlap, tile_rows=tile_rows)
    backend.eval(output)
    backend.synchronize()
    elapsed = time.perf_counter() - start
    peak = get_peak_memory_mib(backend)
    return output, elapsed, peak


def compute_parity(
    *,
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    scenario: str,
    strategy: str,
    tile_rows: int,
    overlap: int | None,
) -> float | None:
    if strategy == "metal_scatter":
        return None
    if strategy == "at_add":
        return 0.0
    cleanup_backend(backend)
    if scenario == "spectral":
        reference = assemble_spectral_at_add(image, process_fn, backend, tile_rows)
        candidate = assemble_spectral_concat(image, process_fn, backend, tile_rows)
    else:
        if overlap is None:
            raise ValueError("spatial scenario requires overlap")
        reference = assemble_spatial_at_add(
            image, process_fn, backend, overlap=overlap, tile_rows=tile_rows
        )
        candidate = assemble_spatial_concat(
            image, process_fn, backend, overlap=overlap, tile_rows=tile_rows
        )
    backend.eval(reference, candidate)
    value = max_abs_diff(candidate, reference, backend)
    del reference, candidate
    cleanup_backend(backend)
    return value


def run_benchmark_record(
    *,
    image: Any,
    process_fn: Callable[[Any], Any],
    backend: Any,
    scenario: str,
    size: str,
    shape: tuple[int, int, int],
    strategy: str,
    tile_rows: int,
    overlap: int | None,
    runs: int,
    warmup: int,
) -> BenchmarkRecord:
    if strategy == "metal_scatter":
        feasible, reason = metal_scatter_feasibility()
        if not feasible:
            return BenchmarkRecord(
                scenario=scenario,
                size=size,
                shape=shape,
                strategy=strategy,
                tile_rows=tile_rows,
                overlap=overlap,
                status="infeasible",
                run_seconds=[],
                peak_memory_mib=[],
                median_seconds=None,
                min_seconds=None,
                max_seconds=None,
                peak_memory_max_mib=None,
                parity_max_abs_diff=None,
                checksum=None,
                mean=None,
                max_value=None,
                error=reason,
            )

    run_seconds: list[float] = []
    peaks: list[float | None] = []
    checksum = mean = max_value = None

    try:
        for _ in range(max(warmup, 0)):
            output, _elapsed, _peak = run_strategy_once(
                image=image,
                process_fn=process_fn,
                backend=backend,
                scenario=scenario,
                strategy=strategy,
                tile_rows=tile_rows,
                overlap=overlap,
            )
            del output
            cleanup_backend(backend)

        for _ in range(runs):
            output, elapsed, peak = run_strategy_once(
                image=image,
                process_fn=process_fn,
                backend=backend,
                scenario=scenario,
                strategy=strategy,
                tile_rows=tile_rows,
                overlap=overlap,
            )
            run_seconds.append(elapsed)
            peaks.append(peak)
            checksum, mean, max_value = output_stats(output, backend)
            del output
            cleanup_backend(backend)

        parity = compute_parity(
            image=image,
            process_fn=process_fn,
            backend=backend,
            scenario=scenario,
            strategy=strategy,
            tile_rows=tile_rows,
            overlap=overlap,
        )
    except (MemoryError, RuntimeError, OSError) as exc:
        cleanup_backend(backend)
        return BenchmarkRecord(
            scenario=scenario,
            size=size,
            shape=shape,
            strategy=strategy,
            tile_rows=tile_rows,
            overlap=overlap,
            status="oom" if _is_oom_error(exc) else "error",
            run_seconds=run_seconds,
            peak_memory_mib=peaks,
            median_seconds=statistics.median(run_seconds) if run_seconds else None,
            min_seconds=min(run_seconds) if run_seconds else None,
            max_seconds=max(run_seconds) if run_seconds else None,
            peak_memory_max_mib=max((p for p in peaks if p is not None), default=None),
            parity_max_abs_diff=None,
            checksum=checksum,
            mean=mean,
            max_value=max_value,
            error="".join(traceback.format_exception_only(type(exc), exc)).strip(),
        )

    return BenchmarkRecord(
        scenario=scenario,
        size=size,
        shape=shape,
        strategy=strategy,
        tile_rows=tile_rows,
        overlap=overlap,
        status="ok",
        run_seconds=run_seconds,
        peak_memory_mib=peaks,
        median_seconds=statistics.median(run_seconds),
        min_seconds=min(run_seconds),
        max_seconds=max(run_seconds),
        peak_memory_max_mib=max((p for p in peaks if p is not None), default=None),
        parity_max_abs_diff=parity,
        checksum=checksum,
        mean=mean,
        max_value=max_value,
        error=None,
    )


def collect_environment(backend: Any | None, *, unavailable_reason: str | None = None) -> dict[str, Any]:
    env: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "mlx_available": backend is not None,
        "mlx_unavailable_reason": unavailable_reason,
    }
    if backend is not None:
        mx = backend.mx
        env.update(
            {
                "backend": getattr(backend, "name", None),
                "backend_precision": getattr(backend, "precision", None),
                "mlx": getattr(mx, "__version__", "unknown"),
                "metal_available": bool(getattr(getattr(mx, "metal", None), "is_available", lambda: False)()),
                "peak_memory_api": _memory_owner(mx) is not None,
            }
        )
    return env


def summarize_records(records: list[BenchmarkRecord]) -> list[StrategySummary]:
    summaries: list[StrategySummary] = []
    for size in sorted({record.size for record in records}):
        for strategy in STRATEGIES:
            subset = [
                record
                for record in records
                if record.size == size and record.strategy == strategy and record.status == "ok"
            ]
            if subset:
                summaries.append(
                    StrategySummary(
                        size=size,
                        strategy=strategy,
                        status="ok",
                        median_of_medians_seconds=statistics.median(
                            record.median_seconds for record in subset if record.median_seconds is not None
                        ),
                        peak_memory_max_mib=max(
                            (
                                record.peak_memory_max_mib
                                for record in subset
                                if record.peak_memory_max_mib is not None
                            ),
                            default=None,
                        ),
                        parity_max_abs_diff=max(
                            (
                                record.parity_max_abs_diff
                                for record in subset
                                if record.parity_max_abs_diff is not None
                            ),
                            default=None,
                        ),
                        records=len(subset),
                    )
                )
                continue

            infeasible = [
                record
                for record in records
                if record.size == size and record.strategy == strategy and record.status == "infeasible"
            ]
            if infeasible:
                summaries.append(
                    StrategySummary(
                        size=size,
                        strategy=strategy,
                        status="infeasible",
                        median_of_medians_seconds=None,
                        peak_memory_max_mib=None,
                        parity_max_abs_diff=None,
                        records=len(infeasible),
                    )
                )
    return summaries


def recommendation_from_summaries(summaries: list[StrategySummary]) -> dict[str, Any]:
    by_size_strategy = {(summary.size, summary.strategy): summary for summary in summaries}
    sizes = sorted({summary.size for summary in summaries})
    winners: dict[str, str | None] = {}
    for size in sizes:
        candidates = [
            summary
            for summary in summaries
            if summary.size == size and summary.status == "ok" and summary.median_of_medians_seconds is not None
        ]
        winners[size] = min(candidates, key=lambda s: s.median_of_medians_seconds).strategy if candidates else None

    concat_qualifies = True
    checks: list[dict[str, Any]] = []
    for size in ("12mp", "24mp"):
        at_add = by_size_strategy.get((size, "at_add"))
        concat = by_size_strategy.get((size, "concat"))
        if (
            at_add is None
            or concat is None
            or at_add.median_of_medians_seconds is None
            or concat.median_of_medians_seconds is None
        ):
            concat_qualifies = False
            checks.append({"size": size, "status": "missing_required_data"})
            continue
        improvement = (
            (at_add.median_of_medians_seconds - concat.median_of_medians_seconds)
            / at_add.median_of_medians_seconds
        )
        peak_ratio = None
        if at_add.peak_memory_max_mib and concat.peak_memory_max_mib:
            peak_ratio = concat.peak_memory_max_mib / at_add.peak_memory_max_mib
        parity_ok = (
            concat.parity_max_abs_diff is not None
            and concat.parity_max_abs_diff <= 1e-6
        )
        size_ok = (
            improvement >= 0.10
            and parity_ok
            and (peak_ratio is None or peak_ratio <= 1.2)
            and concat.median_of_medians_seconds <= at_add.median_of_medians_seconds
        )
        concat_qualifies = concat_qualifies and size_ok
        checks.append(
            {
                "size": size,
                "wall_clock_improvement": improvement,
                "peak_memory_ratio": peak_ratio,
                "parity_ok": parity_ok,
                "qualifies": size_ok,
            }
        )

    if concat_qualifies:
        return {
            "default_strategy_recommendation": "concat_supported_by_data",
            "should_change_write_tile_default": True,
            "winners": winners,
            "checks": checks,
            "reason": (
                "concat met the >=10% wall-clock improvement, <=1.2x peak memory, "
                "parity, and no-regression criteria on both 12MP and 24MP."
            ),
        }
    return {
        "default_strategy_recommendation": "keep_at_add",
        "should_change_write_tile_default": False,
        "winners": winners,
        "checks": checks,
        "reason": "Keep .at.add default unless concat satisfies all 12MP/24MP wall-clock, memory, and parity gates.",
    }


def _format_seconds(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _format_mib(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f}"


def print_console_table(records: list[BenchmarkRecord], summaries: list[StrategySummary], recommendation: dict[str, Any]) -> None:
    headers = [
        "scenario",
        "size",
        "overlap",
        "rows",
        "strategy",
        "status",
        "median_s",
        "min_s",
        "max_s",
        "peak_mib",
        "parity",
    ]
    rows = []
    for record in records:
        rows.append(
            [
                record.scenario,
                record.size,
                "" if record.overlap is None else str(record.overlap),
                "" if record.tile_rows is None else str(record.tile_rows),
                record.strategy,
                record.status,
                _format_seconds(record.median_seconds),
                _format_seconds(record.min_seconds),
                _format_seconds(record.max_seconds),
                _format_mib(record.peak_memory_max_mib),
                "n/a" if record.parity_max_abs_diff is None else f"{record.parity_max_abs_diff:.3g}",
            ]
        )
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, cell in enumerate(row):
            widths[idx] = max(widths[idx], len(cell))
    print(" | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(cell.ljust(widths[idx]) for idx, cell in enumerate(row)))

    print("\nSummary:")
    for summary in summaries:
        median_text = _format_seconds(summary.median_of_medians_seconds)
        print(
            f"  {summary.size} {summary.strategy}: status={summary.status}, "
            f"median_of_medians={median_text}{'' if median_text == 'n/a' else 's'}, "
            f"peak_max={_format_mib(summary.peak_memory_max_mib)} MiB, "
            f"parity={summary.parity_max_abs_diff}"
        )
    print(f"\nRecommendation: {recommendation['default_strategy_recommendation']}")
    print(recommendation["reason"])


def markdown_report(
    *,
    environment: dict[str, Any],
    records: list[BenchmarkRecord],
    summaries: list[StrategySummary],
    recommendation: dict[str, Any],
    real_pipeline: dict[str, Any] | None,
) -> str:
    oom_records = [record for record in records if record.status == "oom"]
    error_records = [record for record in records if record.status == "error"]
    ok_records = [record for record in records if record.status == "ok"]
    peak_max = max(
        (record.peak_memory_max_mib for record in ok_records if record.peak_memory_max_mib is not None),
        default=None,
    )
    lines = [
        "# MLX Tile Assembly Benchmark",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Environment",
        "",
    ]
    for key, value in environment.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(
        [
            "",
            "## Strategy Feasibility",
            "",
            "- `at_add`: current production behavior, `output.at[y0:y1].add(tile_out)`.",
            "- `concat`: benchmark prototype that stores tile outputs and concatenates once.",
            f"- `metal_scatter`: {METAL_SCATTER_FEASIBILITY_REASON}",
            "",
            "## Summary",
            "",
            "| Size | Strategy | Status | Median Of Medians (s) | Peak Memory Max (MiB) | Parity Max Abs Diff | Records |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for summary in summaries:
        parity = "n/a" if summary.parity_max_abs_diff is None else f"{summary.parity_max_abs_diff:.3g}"
        lines.append(
            "| "
            f"{summary.size} | {summary.strategy} | {summary.status} | "
            f"{_format_seconds(summary.median_of_medians_seconds)} | "
            f"{_format_mib(summary.peak_memory_max_mib)} | "
            f"{parity} | {summary.records} |"
        )
    lines.extend(
        [
            "",
            "## OOM And Memory Pressure",
            "",
            f"- OOM records: `{len(oom_records)}`",
            f"- Error records: `{len(error_records)}`",
            f"- Maximum recorded peak memory: `{_format_mib(peak_max)} MiB`",
        ]
    )
    lines.extend(
        [
            "",
            "## Recommendation",
            "",
            f"- Default strategy recommendation: `{recommendation['default_strategy_recommendation']}`",
            f"- Should change `_write_tile()` default: `{recommendation['should_change_write_tile_default']}`",
            f"- 12MP/24MP winners: `{recommendation['winners']}`",
            f"- Reason: {recommendation['reason']}",
        ]
    )
    if not recommendation["should_change_write_tile_default"]:
        lines.append("- Conclusion: keep `.at.add` default.")
    lines.extend(["", "### Gate Checks", ""])
    for check in recommendation["checks"]:
        lines.append(f"- `{check['size']}`: `{check}`")

    lines.extend(
        [
            "",
            "## Detailed Records",
            "",
            "| Scenario | Size | Overlap | Tile Rows | Strategy | Status | Median (s) | Min (s) | Max (s) | Peak Max (MiB) | Parity | Mean | Max Value |",
            "| --- | --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for record in records:
        parity = "n/a" if record.parity_max_abs_diff is None else f"{record.parity_max_abs_diff:.3g}"
        lines.append(
            "| "
            f"{record.scenario} | {record.size} | {record.overlap if record.overlap is not None else ''} | "
            f"{record.tile_rows if record.tile_rows is not None else ''} | {record.strategy} | {record.status} | "
            f"{_format_seconds(record.median_seconds)} | {_format_seconds(record.min_seconds)} | "
            f"{_format_seconds(record.max_seconds)} | {_format_mib(record.peak_memory_max_mib)} | "
            f"{parity} | {_format_seconds(record.mean)} | {_format_seconds(record.max_value)} |"
        )
        if record.error:
            if record.status in {"error", "oom"}:
                lines.append(f"| {record.scenario} | {record.size} |  |  | {record.strategy} error |  | {record.error} |  |  |  |  |  |  |")

    if real_pipeline is not None:
        lines.extend(["", "## Optional Real Pipeline Hook", "", "```json", json.dumps(real_pipeline, indent=2, sort_keys=True), "```"])

    return "\n".join(lines) + "\n"


def run_real_pipeline_hook(args: argparse.Namespace, backend: Any) -> dict[str, Any] | None:
    if not args.real_pipeline:
        return None
    if args.image is None:
        return {"status": "skipped", "reason": "--real-pipeline was set without --image"}

    try:
        from skimage.io import imread

        from spektrafilm.runtime.params_builder import digest_params, init_params
        from spektrafilm.runtime.pipeline import SimulationPipeline
    except Exception as exc:  # pragma: no cover - optional local hook
        return {"status": "error", "reason": f"failed to import real pipeline dependencies: {exc}"}

    image = imread(args.image)
    image = np.asarray(image)
    if image.dtype.kind in {"u", "i"}:
        image = image.astype(np.float32) / np.iinfo(image.dtype).max
    else:
        image = image.astype(np.float32)
    image = image[..., :3]

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    pipeline = SimulationPipeline(digest_params(params))
    start = time.perf_counter()
    result = pipeline.process(image)
    pipeline._backend.eval(result)
    pipeline._backend.synchronize()
    elapsed = time.perf_counter() - start
    return {
        "status": "ok",
        "image": str(args.image),
        "shape": tuple(int(v) for v in image.shape),
        "strategy": "production_at_add",
        "elapsed_seconds": elapsed,
        "timings": pipeline.get_timings(),
    }


def write_artifacts(
    *,
    output_dir: Path,
    environment: dict[str, Any],
    records: list[BenchmarkRecord],
    summaries: list[StrategySummary],
    recommendation: dict[str, Any],
    real_pipeline: dict[str, Any] | None,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = output_dir / f"mlx-tile-assembly-benchmark-{timestamp}.json"
    md_path = output_dir / f"mlx-tile-assembly-benchmark-{timestamp}.md"
    payload = {
        "environment": environment,
        "records": [asdict(record) for record in records],
        "summaries": [asdict(summary) for summary in summaries],
        "recommendation": recommendation,
        "real_pipeline": real_pipeline,
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(
        markdown_report(
            environment=environment,
            records=records,
            summaries=summaries,
            recommendation=recommendation,
            real_pipeline=real_pipeline,
        ),
        encoding="utf-8",
    )
    return json_path, md_path


def run(args: argparse.Namespace) -> int:
    try:
        backend = select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        environment = collect_environment(None, unavailable_reason=str(exc))
        recommendation = {
            "default_strategy_recommendation": "skip_no_mlx",
            "should_change_write_tile_default": False,
            "winners": {},
            "checks": [],
            "reason": "MLX/Metal unavailable; no benchmark data collected.",
        }
        json_path, md_path = write_artifacts(
            output_dir=args.output_dir,
            environment=environment,
            records=[],
            summaries=[],
            recommendation=recommendation,
            real_pipeline=None,
        )
        print(str(exc))
        print(f"Wrote skip artifacts: {json_path} and {md_path}")
        return 0

    records: list[BenchmarkRecord] = []
    for size in args.sizes:
        shape = SIZE_SHAPES[size]
        print(f"\nPreparing {size} synthetic image {shape}...")
        image = make_synthetic_image(backend, shape)

        spectral_rows = resolve_benchmark_tile_rows(
            shape[0],
            args.tile_rows,
            spatial=False,
            include_default=not args.no_default_tile_rows,
        )
        spectral_fn = spectral_process_fn(backend.mx)
        for tile_rows in spectral_rows:
            for strategy in args.strategies:
                print(f"Running spectral {size} rows={tile_rows} strategy={strategy}")
                records.append(
                    run_benchmark_record(
                        image=image,
                        process_fn=spectral_fn,
                        backend=backend,
                        scenario="spectral",
                        size=size,
                        shape=shape,
                        strategy=strategy,
                        tile_rows=tile_rows,
                        overlap=None,
                        runs=args.runs,
                        warmup=args.warmup,
                    )
                )

        spatial_rows = resolve_benchmark_tile_rows(
            shape[0],
            args.tile_rows,
            spatial=True,
            include_default=not args.no_default_tile_rows,
        )
        spatial_fn = spatial_process_fn(backend.mx)
        for overlap in args.overlaps:
            for tile_rows in spatial_rows:
                for strategy in args.strategies:
                    print(
                        f"Running spatial {size} overlap={overlap} "
                        f"rows={tile_rows} strategy={strategy}"
                    )
                    records.append(
                        run_benchmark_record(
                            image=image,
                            process_fn=spatial_fn,
                            backend=backend,
                            scenario="spatial",
                            size=size,
                            shape=shape,
                            strategy=strategy,
                            tile_rows=tile_rows,
                            overlap=overlap,
                            runs=args.runs,
                            warmup=args.warmup,
                        )
                    )
        del image
        cleanup_backend(backend)

    summaries = summarize_records(records)
    recommendation = recommendation_from_summaries(summaries)
    real_pipeline = run_real_pipeline_hook(args, backend)
    environment = collect_environment(backend)
    print_console_table(records, summaries, recommendation)
    json_path, md_path = write_artifacts(
        output_dir=args.output_dir,
        environment=environment,
        records=records,
        summaries=summaries,
        recommendation=recommendation,
        real_pipeline=real_pipeline,
    )
    print(f"\nJSON artifact: {json_path}")
    print(f"Markdown report: {md_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
