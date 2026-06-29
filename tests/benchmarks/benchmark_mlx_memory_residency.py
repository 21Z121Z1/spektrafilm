from __future__ import annotations

import argparse
import copy
import json
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.residency import record_backend_operation, record_backend_residency
from spektrafilm.runtime.pipeline import SimulationPipeline
from tests.conftest import make_fast_test_params


@dataclass(frozen=True)
class Scenario:
    name: str
    hdr_mode: str | None
    scan_film: bool
    materialize_policy: str
    hdr_route_sidecar_policy: str
    upscale_factor: float = 1.0
    use_enlarger_lut: bool = False
    use_scanner_lut: bool = False
    resize_policy: str = "cpu_fallback"


DEFAULT_SCENARIOS: tuple[Scenario, ...] = (
    Scenario("mlx_scan_only_backend_minimal", None, True, "backend", "minimal"),
    Scenario("mlx_hdr_light_table_backend_minimal", "light_table", True, "backend", "minimal"),
    Scenario("mlx_hdr_paper_backend_minimal", "paper", False, "backend", "minimal"),
    Scenario(
        "mlx_paper_chemical_fallback_backend_full",
        "paper",
        False,
        "backend",
        "full",
        use_enlarger_lut=False,
        use_scanner_lut=False,
    ),
    Scenario("mlx_scan_numpy_float32", None, True, "numpy_float32", "minimal"),
    Scenario("mlx_scan_numpy_float64", None, True, "numpy_float64", "minimal"),
    Scenario(
        "mlx_scan_backend_resize_1_25_warn",
        None,
        True,
        "backend",
        "minimal",
        upscale_factor=1.25,
        resize_policy="warn",
    ),
)


def _image(height: int, width: int) -> np.ndarray:
    x = np.linspace(0.02, 0.95, width, dtype=np.float32)[None, :]
    y = np.linspace(0.04, 0.90, height, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (height, width))
    yy = np.broadcast_to(y, (height, width))
    return np.stack((xx, yy, 0.5 * (xx + yy)), axis=-1).astype(np.float32)


def _peak_cache_mib(backend: Any) -> tuple[float | None, float | None]:
    mx = getattr(backend, "mx", None)
    return _memory_mib(mx, "get_peak_memory"), _memory_mib(mx, "get_cache_memory")


def _memory_mib(mx: Any, name: str) -> float | None:
    if mx is None:
        return None
    for owner in (mx, getattr(mx, "metal", None)):
        getter = getattr(owner, name, None)
        if callable(getter):
            try:
                return float(getter()) / (1024.0 ** 2)
            except (OSError, RuntimeError, TypeError, ValueError):
                return None
    return None


def _params_for(scenario: Scenario):
    params = make_fast_test_params()
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = scenario.materialize_policy
    params.settings.hdr_route_sidecar_policy = scenario.hdr_route_sidecar_policy
    params.settings.use_enlarger_lut = scenario.use_enlarger_lut
    params.settings.use_scanner_lut = scenario.use_scanner_lut
    params.settings.gpu_resize_policy = scenario.resize_policy
    params.settings.preview_mode = False
    params.settings.gpu_validate = False
    params.settings.lut_resolution = 17
    params.io.scan_film = scenario.scan_film
    params.io.upscale_factor = scenario.upscale_factor
    params.io.crop = False
    params.camera.auto_exposure = False
    return params


def _run_once(image: np.ndarray, scenario: Scenario) -> dict[str, Any]:
    pipeline = SimulationPipeline(_params_for(scenario))
    start = perf_counter()
    fail_reason = None
    with record_backend_residency(small_array_bytes=64 * 1024) as recorder:
        try:
            if scenario.hdr_mode is None:
                result = pipeline.process(image)
            else:
                result = pipeline.process_with_master(image, hdr_mode=scenario.hdr_mode)
            final_value = getattr(result, "image", result)
            if getattr(pipeline._backend, "supports_gpu", False):
                pipeline._backend.eval(final_value)
            final_np = (
                pipeline._backend.to_numpy(final_value)
                if getattr(pipeline._backend, "supports_gpu", False)
                and hasattr(pipeline._backend, "to_numpy")
                else np.asarray(final_value)
            )
            record_backend_operation(
                "to_numpy",
                "encoder",
                final_value,
                np.ascontiguousarray(final_np),
                category="final_encoder_boundary",
            )
        except Exception as exc:  # benchmark records fail-fast reasons.
            fail_reason = f"{type(exc).__name__}: {exc}"
        finally:
            if hasattr(pipeline._backend, "cleanup"):
                pipeline._backend.cleanup()
    elapsed = perf_counter() - start
    peak_mib, cache_mib = _peak_cache_mib(pipeline._backend)
    summary = recorder.summary()
    sidecar_count = sum(
        1
        for event in recorder.events
        if "_route_sidecar_array_value" in event.stack_label and event.direction == "to_numpy"
    )
    final_boundary_count = sum(
        1
        for event in recorder.events
        if event.category == "final_encoder_boundary"
    )
    resize_fallback_count = int(
        pipeline.timings.get("SimulationPipeline.preprocess.resize_cpu_fallback_count", 0.0)
    )
    return {
        "wall_clock_seconds": elapsed,
        "peak_memory_mib": peak_mib,
        "cache_memory_mib": cache_mib,
        "to_numpy_count": summary["to_numpy"],
        "asarray_count": summary["asarray"],
        "eval_count": summary["eval"],
        "synchronize_count": summary["synchronize"],
        "cleanup_count": summary["cleanup"],
        "clear_cache_count": summary["clear_cache"],
        "resize_fallback_count": resize_fallback_count,
        "route_sidecar_materialization_count": sidecar_count,
        "final_encoder_boundary_materialization_count": final_boundary_count,
        "warnings": list(pipeline.memory_residency_warnings),
        "fail_fast_reason": fail_reason,
    }


def _aggregate(samples: list[dict[str, Any]]) -> dict[str, Any]:
    wall = [sample["wall_clock_seconds"] for sample in samples]
    latest = samples[-1]
    return {
        "wall_clock_median_seconds": statistics.median(wall),
        "peak_memory_mib": latest["peak_memory_mib"],
        "cache_memory_mib": latest["cache_memory_mib"],
        "to_numpy_count": latest["to_numpy_count"],
        "asarray_count": latest["asarray_count"],
        "eval_count": latest["eval_count"],
        "synchronize_count": latest["synchronize_count"],
        "cleanup_count": latest["cleanup_count"],
        "clear_cache_count": latest["clear_cache_count"],
        "resize_fallback_count": latest["resize_fallback_count"],
        "route_sidecar_materialization_count": latest["route_sidecar_materialization_count"],
        "final_encoder_boundary_materialization_count": latest[
            "final_encoder_boundary_materialization_count"
        ],
        "warnings": latest["warnings"],
        "fail_fast_reasons": [
            sample["fail_fast_reason"]
            for sample in samples
            if sample["fail_fast_reason"] is not None
        ],
        "samples": samples,
    }


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        "# MLX Memory Residency Benchmark",
        "",
        f"- generated_at: `{payload['generated_at']}`",
        f"- image: `{payload['height']}x{payload['width']}`",
        f"- runs: `{payload['runs']}`",
        "",
        "| scenario | median s | peak MiB | cache MiB | to_numpy | asarray | eval | sync | cleanup | clear_cache | resize | sidecar | final boundary | warnings/failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for name, result in payload["scenarios"].items():
        warnings = "; ".join(result["warnings"] + result["fail_fast_reasons"])
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    f"{result['wall_clock_median_seconds']:.4f}",
                    "" if result["peak_memory_mib"] is None else f"{result['peak_memory_mib']:.1f}",
                    "" if result["cache_memory_mib"] is None else f"{result['cache_memory_mib']:.1f}",
                    str(result["to_numpy_count"]),
                    str(result["asarray_count"]),
                    str(result["eval_count"]),
                    str(result["synchronize_count"]),
                    str(result["cleanup_count"]),
                    str(result["clear_cache_count"]),
                    str(result["resize_fallback_count"]),
                    str(result["route_sidecar_materialization_count"]),
                    str(result["final_encoder_boundary_materialization_count"]),
                    warnings,
                ]
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--height", type=int, default=3000)
    parser.add_argument("--width", type=int, default=4000)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output-json", type=Path)
    parser.add_argument("--output-markdown", type=Path)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only the scan-only backend-resident scenario.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[scenario.name for scenario in DEFAULT_SCENARIOS],
        help="Run only the named scenario. May be repeated.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        raise SystemExit(str(exc)) from exc

    generated_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_json = args.output_json or Path(f"docs/reports/mlx-memory-residency-{stamp}.json")
    output_markdown = args.output_markdown or Path(f"docs/reports/mlx-memory-residency-{stamp}.md")
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)

    image = _image(args.height, args.width)
    if args.scenario:
        wanted = set(args.scenario)
        scenarios = tuple(scenario for scenario in DEFAULT_SCENARIOS if scenario.name in wanted)
    else:
        scenarios = DEFAULT_SCENARIOS[:1] if args.quick else DEFAULT_SCENARIOS
    payload: dict[str, Any] = {
        "generated_at": generated_at,
        "height": args.height,
        "width": args.width,
        "runs": args.runs,
        "scenarios": {},
    }
    for scenario in scenarios:
        samples = [_run_once(image, copy.deepcopy(scenario)) for _ in range(args.runs)]
        payload["scenarios"][scenario.name] = _aggregate(samples)

    output_json.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    _write_markdown(output_markdown, payload)
    print(f"Wrote {output_json}")
    print(f"Wrote {output_markdown}")


if __name__ == "__main__":
    main()
