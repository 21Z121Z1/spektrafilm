from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
import sys
from time import perf_counter
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for path in (ROOT, SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.residency import record_backend_residency
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.topology import Tap
from tests.conftest import make_fast_test_params


@dataclass(frozen=True)
class BenchmarkCase:
    label: str
    compute_backend: str
    gpu_precision: str
    materialize_policy: str


def _image(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.02, 0.95, width, dtype=np.float32)[None, :]
    y = np.linspace(0.04, 0.90, height, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (height, width))
    yy = np.broadcast_to(y, (height, width))
    return np.stack((xx, yy, 0.5 * (xx + yy)), axis=-1).astype(np.float32)


def _cases(backend: str, precision: str) -> list[BenchmarkCase]:
    cases = []
    if backend in {"all", "cpu"}:
        cases.append(BenchmarkCase("cpu_default", "cpu", "float64", "numpy_float64"))
    if backend in {"all", "mlx"}:
        cases.append(BenchmarkCase("mlx_backend", "mlx", precision, "backend"))
    return cases


def _params(case: BenchmarkCase, *, use_scanner_lut: bool):
    params = make_fast_test_params()
    params.settings.compute_backend = case.compute_backend
    params.settings.gpu_precision = case.gpu_precision
    params.settings.materialize_policy = case.materialize_policy
    params.settings.gpu_validate = False
    params.settings.preview_mode = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = use_scanner_lut
    params.settings.lut_resolution = 5
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    return params


def _describe(value: Any) -> dict[str, Any]:
    return {
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
        "dtype": str(getattr(value, "dtype", None)),
        "shape": list(getattr(value, "shape", ())),
    }


def _stage_trace(case: BenchmarkCase, image: np.ndarray, *, use_scanner_lut: bool) -> dict[str, dict[str, Any]]:
    pipeline = SimulationPipeline(_params(case, use_scanner_lut=use_scanner_lut))
    trace = {}
    for tap in (Tap.LOG_E_FILM, Tap.CMY_FILM, Tap.LOG_E_PRINT, Tap.CMY_PRINT, Tap.RGB_OUT):
        value = pipeline.process(image, collect=tap)
        trace[tap] = _describe(value)
    return trace


def _to_numpy_for_validation(pipeline: SimulationPipeline, value: Any) -> np.ndarray:
    backend = getattr(pipeline, "_backend", None)
    if backend is not None and getattr(backend, "supports_gpu", False) and hasattr(backend, "to_numpy"):
        return np.asarray(backend.to_numpy(value), dtype=np.float64)
    return np.asarray(value, dtype=np.float64)


def _run_once(
    case: BenchmarkCase,
    image: np.ndarray,
    *,
    use_scanner_lut: bool,
    small_array_bytes: int,
    cpu_reference: np.ndarray | None,
    cpu_direct_reference: np.ndarray | None,
) -> dict[str, Any]:
    pipeline = SimulationPipeline(_params(case, use_scanner_lut=use_scanner_lut))
    start = perf_counter()
    with record_backend_residency(small_array_bytes=small_array_bytes) as recorder:
        result = pipeline.process(image)
    process_seconds = perf_counter() - start

    sync_start = perf_counter()
    if getattr(pipeline._backend, "supports_gpu", False):
        pipeline._backend.synchronize()
    sync_seconds = perf_counter() - sync_start

    numpy_start = perf_counter()
    result_np = _to_numpy_for_validation(pipeline, result)
    explicit_numpy_seconds = perf_counter() - numpy_start

    max_abs_diff = None
    if cpu_reference is not None:
        max_abs_diff = float(np.max(np.abs(result_np - cpu_reference)))
    max_abs_diff_direct = None
    if cpu_direct_reference is not None:
        max_abs_diff_direct = float(np.max(np.abs(result_np - cpu_direct_reference)))

    return {
        "status": "ok",
        "output": _describe(result),
        "process_seconds": process_seconds,
        "sync_seconds": sync_seconds,
        "explicit_numpy_seconds": explicit_numpy_seconds,
        "timings": dict(pipeline.timings),
        "residency_summary": recorder.summary(),
        "unallowed_events": [asdict(event) for event in recorder.unallowed_events()],
        "max_abs_diff_vs_cpu": max_abs_diff,
        "max_abs_diff_vs_cpu_direct": max_abs_diff_direct,
    }


def _run_case(
    case: BenchmarkCase,
    image: np.ndarray,
    *,
    runs: int,
    warmups: int,
    use_scanner_lut: bool,
    small_array_bytes: int,
    cpu_reference: np.ndarray | None,
    cpu_direct_reference: np.ndarray | None,
) -> dict[str, Any]:
    try:
        select_backend(case.compute_backend, precision=case.gpu_precision)
    except (BackendUnavailableError, ValueError) as exc:
        return {
            "case": asdict(case),
            "status": "skipped",
            "reason": str(exc),
        }

    for _ in range(warmups):
        _run_once(
            case,
            image,
            use_scanner_lut=use_scanner_lut,
            small_array_bytes=small_array_bytes,
            cpu_reference=cpu_reference,
            cpu_direct_reference=cpu_direct_reference,
        )

    runs_out = [
        _run_once(
            case,
            image,
                use_scanner_lut=use_scanner_lut,
                small_array_bytes=small_array_bytes,
                cpu_reference=cpu_reference,
                cpu_direct_reference=cpu_direct_reference,
            )
        for _ in range(runs)
    ]
    stage_trace = _stage_trace(case, image, use_scanner_lut=use_scanner_lut)
    return {
        "case": asdict(case),
        "status": "ok",
        "runs": runs_out,
        "stage_trace": stage_trace,
        "summary": {
            "median_process_seconds": median(run["process_seconds"] for run in runs_out),
            "median_sync_seconds": median(run["sync_seconds"] for run in runs_out),
            "median_explicit_numpy_seconds": median(run["explicit_numpy_seconds"] for run in runs_out),
            "unallowed_events": sum(run["residency_summary"]["unallowed"] for run in runs_out),
            "unallowed_to_numpy": sum(run["residency_summary"]["unallowed_to_numpy"] for run in runs_out),
            "max_abs_diff_vs_cpu": max(
                (run["max_abs_diff_vs_cpu"] or 0.0) for run in runs_out
            ),
            "max_abs_diff_vs_cpu_direct": max(
                (run["max_abs_diff_vs_cpu_direct"] or 0.0) for run in runs_out
            ),
        },
    }


def _cpu_reference(image: np.ndarray, *, use_scanner_lut: bool) -> np.ndarray:
    case = BenchmarkCase("cpu_reference", "cpu", "float64", "numpy_float64")
    return np.asarray(
        SimulationPipeline(_params(case, use_scanner_lut=use_scanner_lut)).process(image),
        dtype=np.float64,
    )


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Backend Resident Float32 P2 Runtime Boundaries - {payload['timestamp']}",
        "",
        f"- Image shape: `{payload['image_shape']}`",
        f"- Warmups: `{payload['warmups']}`",
        f"- Runs: `{payload['runs']}`",
        f"- Scanner LUT: `{payload['use_scanner_lut']}`",
        "",
        "## Summary",
        "",
        "| Case | Status | Output | Median Runtime | Sync | Explicit NumPy | Unallowed to_numpy | Max Abs Diff vs CPU | Max Abs Diff vs CPU Direct |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for result in payload["results"]:
        case = result["case"]
        if result["status"] != "ok":
            lines.append(
                f"| {case['label']} | skipped | | | | | | | {result.get('reason', '')} |"
            )
            continue
        first = result["runs"][0]
        output = first["output"]
        summary = result["summary"]
        lines.append(
            f"| {case['label']} | ok | {output['type']} {output['dtype']} | "
            f"{summary['median_process_seconds']:.6f}s | "
            f"{summary['median_sync_seconds']:.6f}s | "
            f"{summary['median_explicit_numpy_seconds']:.6f}s | "
            f"{summary['unallowed_to_numpy']} | "
            f"{summary['max_abs_diff_vs_cpu']:.6g} | "
            f"{summary['max_abs_diff_vs_cpu_direct']:.6g} |"
        )
    lines.extend(["", "## Stage Trace", ""])
    for result in payload["results"]:
        if result["status"] != "ok":
            continue
        lines.append(f"### {result['case']['label']}")
        lines.append("")
        lines.append("| Tap | Type | Dtype | Shape |")
        lines.append("|---|---|---|---|")
        for tap, desc in result["stage_trace"].items():
            lines.append(
                f"| `{tap}` | `{desc['type']}` | `{desc['dtype']}` | `{desc['shape']}` |"
            )
        lines.append("")
    lines.extend([
        "## Notes",
        "",
        "- Residency diagnostics are active only inside the timed `process()` call.",
        "- Explicit sync and explicit NumPy conversion happen after diagnostics to avoid classifying validation/export inspection as runtime leakage.",
        "- This is a runtime-boundary diagnostic, not a 12MP RAW performance proof.",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("all", "cpu", "mlx"), default="all")
    parser.add_argument("--precision", default="float32")
    parser.add_argument("--width", type=int, default=512)
    parser.add_argument("--height", type=int, default=384)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--scanner-lut", action="store_true")
    parser.add_argument("--small-array-bytes", type=int, default=64 * 1024)
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    image = _image(args.width, args.height)
    cpu_ref = _cpu_reference(image, use_scanner_lut=args.scanner_lut)
    cpu_direct_ref = _cpu_reference(image, use_scanner_lut=False)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    payload = {
        "timestamp": timestamp,
        "image_shape": list(image.shape),
        "image_dtype": str(image.dtype),
        "warmups": args.warmups,
        "runs": args.runs,
        "use_scanner_lut": bool(args.scanner_lut),
        "small_array_bytes": args.small_array_bytes,
        "results": [
            _run_case(
                case,
                image,
                runs=args.runs,
                warmups=args.warmups,
                use_scanner_lut=args.scanner_lut,
                small_array_bytes=args.small_array_bytes,
                cpu_reference=cpu_ref,
                cpu_direct_reference=cpu_direct_ref,
            )
            for case in _cases(args.backend, args.precision)
        ],
    }
    markdown = _markdown(payload)
    print(markdown)
    if not args.no_write:
        out_dir = Path("docs/reports")
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"backend-resident-float32-p2-runtime-boundaries-benchmark-{timestamp}"
        (out_dir / f"{stem}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
        (out_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
