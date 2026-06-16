#!/usr/bin/env python3
"""Benchmark P4 HDR sidecar, grain, preview, export, and real-sample boundaries."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from dataclasses import dataclass
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
DEFAULT_REAL_INPUT = ROOT / "scratch" / "IMG_9121_converted.DNG"


@dataclass(frozen=True)
class Workload:
    label: str
    grain: bool
    hdr_metadata: bool
    preview: bool
    export: bool
    route: str = "print_scan"
    scanner_lut: bool = False


def _type_name(value: object | None) -> str | None:
    if value is None:
        return None
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _array_nbytes(value: object | None) -> int:
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
        text = str(dtype)
        itemsize = 4 if "float32" in text else 8 if "float64" in text else 0
        return int(np.prod(tuple(int(dim) for dim in shape)) * itemsize)


def _describe(value: object | None) -> dict[str, Any]:
    if value is None:
        return {"type": None, "shape": None, "dtype": None, "nbytes": 0}
    return {
        "type": _type_name(value),
        "shape": list(getattr(value, "shape", ())),
        "dtype": str(getattr(value, "dtype", None)),
        "nbytes": _array_nbytes(value),
    }


def _generated_image(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.02, 0.98, width, dtype=np.float32)[None, :]
    y = np.linspace(0.03, 0.93, height, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (height, width))
    yy = np.broadcast_to(y, (height, width))
    return np.stack(
        [
            0.04 + 0.85 * xx,
            0.05 + 0.75 * yy,
            0.08 + 0.40 * (xx + yy),
        ],
        axis=-1,
    ).astype(np.float32, copy=False)


def _load_real_image(path: Path) -> tuple[np.ndarray | None, str | None]:
    if not path.exists():
        return None, f"missing real input: {path}"
    try:
        if path.suffix.lower() in {".dng", ".raw", ".arw", ".cr2", ".cr3", ".nef", ".raf", ".rw2"}:
            from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

            image = load_and_process_raw_file(
                path,
                white_balance="as_shot",
                lens_correction=False,
                output_colorspace="sRGB",
                output_cctf_encoding=False,
            )
        else:
            from spektrafilm.utils.io import load_image_oiio

            image = load_image_oiio(str(path))
        image = np.asarray(image, dtype=np.float32)[..., :3]
        if image.shape[0] <= 512 or image.shape[1] <= 512:
            return None, f"real input did not decode at full resolution: shape={image.shape}"
        return image, None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _sample_inputs(*, include_real: bool, real_input: Path) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = [
        {
            "label": "synthetic_256",
            "source": "generated",
            "image": _generated_image(256, 256),
            "reason": None,
        },
        {
            "label": "synthetic_512x384",
            "source": "generated",
            "image": _generated_image(512, 384),
            "reason": None,
        },
    ]
    if include_real:
        image, reason = _load_real_image(real_input)
        samples.append(
            {
                "label": "real_dng",
                "source": str(real_input),
                "image": image,
                "reason": reason,
            }
        )
    return samples


def _workloads(real_sample: bool, *, include_scanner_lut: bool) -> list[Workload]:
    if real_sample:
        workloads = [
            Workload("runtime_grain_off_hdr_off", False, False, False, False),
            Workload("runtime_grain_off_hdr_on", False, True, False, False),
            Workload("runtime_grain_on_hdr_off", True, False, False, False),
            Workload("runtime_scan_film_grain_off_hdr_off", False, False, False, False, route="scan_film"),
            Workload("preview_export_grain_off_hdr_off", False, False, True, True),
        ]
        if include_scanner_lut:
            workloads.extend(
                [
                    Workload(
                        "runtime_grain_off_hdr_off_scanner_lut_on",
                        False,
                        False,
                        False,
                        False,
                        scanner_lut=True,
                    ),
                    Workload(
                        "runtime_grain_on_hdr_off_scanner_lut_on",
                        True,
                        False,
                        False,
                        False,
                        scanner_lut=True,
                    ),
                ]
            )
        return workloads
    workloads = [
        Workload("runtime_grain_off_hdr_off", False, False, False, False),
        Workload("runtime_grain_off_hdr_on", False, True, False, False),
        Workload("runtime_grain_on_hdr_off", True, False, False, False),
        Workload("runtime_grain_on_hdr_on", True, True, False, False),
        Workload("runtime_scan_film_grain_off_hdr_off", False, False, False, False, route="scan_film"),
        Workload("preview_only_grain_off_hdr_off", False, False, True, False),
        Workload("export_only_grain_off_hdr_off", False, False, False, True),
        Workload("preview_export_grain_off_hdr_off", False, False, True, True),
    ]
    if include_scanner_lut:
        workloads.append(
            Workload(
                "runtime_grain_off_hdr_off_scanner_lut_on",
                False,
                False,
                False,
                False,
                scanner_lut=True,
            )
        )
    return workloads


def _backend_available(backend: str, precision: str) -> tuple[bool, str | None]:
    from spektrafilm.gpu.backend import BackendUnavailableError, select_backend

    try:
        select_backend(backend, precision=precision)
    except (BackendUnavailableError, RuntimeError, OSError, ValueError, ModuleNotFoundError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    return True, None


def _build_params(
    *,
    backend: str,
    precision: str,
    materialize_policy: str,
    grain: bool,
    route: str,
    scanner_lut: bool,
):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = not grain
    params.settings.compute_backend = backend
    params.settings.gpu_precision = precision
    params.settings.materialize_policy = materialize_policy
    params.settings.gpu_validate = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = bool(scanner_lut)
    params.settings.use_fast_stats = True
    params.film_render.grain.active = bool(grain)
    params.film_render.grain.sublayers_active = False
    params.film_render.grain.blur = 0.0
    params.film_render.grain.blur_dye_clouds_um = 0.0
    params.film_render.grain.micro_structure = (0.0, 0.0)
    params.print_render.glare.active = False
    params.io.scan_film = route == "scan_film"
    return digest_params(params)


def _sync_backend(pipeline: Any, value: Any) -> float:
    backend = getattr(pipeline, "_backend", None)
    start = time.perf_counter()
    eval_fn = getattr(backend, "eval", None)
    if callable(eval_fn):
        eval_fn(value)
    sync_fn = getattr(backend, "synchronize", None)
    if callable(sync_fn):
        sync_fn()
    return time.perf_counter() - start


def _prepare_preview(output_source: Any, phase_timings: dict[str, float]) -> tuple[dict[str, Any], float]:
    from spektrafilm_gui import controller_runtime

    start = time.perf_counter()
    display_image, display_status = controller_runtime.prepare_output_display_image(
        output_source,
        output_color_space="sRGB",
        output_cctf_encoding=True,
        use_display_transform=False,
        imagecms_module=SimpleNamespace(PyCMSError=RuntimeError),
        colour_module=SimpleNamespace(),
        pil_image_module=SimpleNamespace(),
        phase_timings=phase_timings,
    )
    return {
        "requested": True,
        "status": display_status,
        "display": _describe(display_image),
    }, time.perf_counter() - start


def _materialize_export(output_source: Any, phase_timings: dict[str, float]) -> tuple[dict[str, Any], float]:
    from spektrafilm_gui import controller_runtime

    start = time.perf_counter()
    export_image = controller_runtime.materialize_export_image(
        output_source,
        phase_timings=phase_timings,
    )
    return {
        "requested": True,
        "image": _describe(export_image),
    }, time.perf_counter() - start


def _run_once(image: np.ndarray, *, backend: str, precision: str, workload: Workload) -> dict[str, Any]:
    from spektrafilm.gpu.residency import record_backend_residency
    from spektrafilm.runtime.pipeline import SimulationPipeline

    materialize_policy = "backend" if backend == "mlx" else "numpy_float64"
    params = _build_params(
        backend=backend,
        precision=precision,
        materialize_policy=materialize_policy,
        grain=workload.grain,
        route=workload.route,
        scanner_lut=workload.scanner_lut,
    )
    pipeline = SimulationPipeline(params)
    phase_timings: dict[str, float] = {}
    start = time.perf_counter()
    with record_backend_residency() as recorder:
        if workload.hdr_metadata:
            result = pipeline.process_with_metadata(image)
            output_source = result.image
            hdr_scene_energy = result.hdr_scene_energy
        else:
            output_source = pipeline.process(image)
            hdr_scene_energy = None
        sync_seconds = _sync_backend(pipeline, output_source)
    runtime_wall_seconds = time.perf_counter() - start

    preview = {"requested": False}
    preview_seconds = 0.0
    if workload.preview:
        preview, preview_seconds = _prepare_preview(output_source, phase_timings)

    export = {"requested": False}
    export_seconds = 0.0
    if workload.export:
        export, export_seconds = _materialize_export(output_source, phase_timings)

    scene_luminance = getattr(hdr_scene_energy, "scene_luminance", None)
    total_seconds = runtime_wall_seconds + preview_seconds + export_seconds
    return {
        "status": "ok",
        "runtime_wall_seconds": runtime_wall_seconds,
        "total_wall_seconds": total_seconds,
        "sync_seconds": sync_seconds,
        "backend": backend,
        "precision": precision,
        "materialize_policy": materialize_policy,
        "route": workload.route,
        "flags": {
            "grain": workload.grain,
            "hdr_metadata": workload.hdr_metadata,
            "preview": workload.preview,
            "export": workload.export,
            "scanner_lut": workload.scanner_lut,
        },
        "preview_seconds": preview_seconds,
        "export_seconds": export_seconds,
        "output_source": _describe(output_source),
        "hdr_scene_luminance": _describe(scene_luminance),
        "preview": preview,
        "export": export,
        "pipeline_timings": {str(k): float(v) for k, v in pipeline.get_timings().items()},
        "gui_phase_timings": {str(k): float(v) for k, v in phase_timings.items()},
        "residency_summary": recorder.summary(),
    }


def _summarize(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    values = [float(row[key]) for row in rows if row.get("status") == "ok"]
    if not values:
        return {"median": 0.0, "min": 0.0, "max": 0.0}
    return {
        "median": float(statistics.median(values)),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def _run_workload(
    image: np.ndarray | None,
    *,
    sample: dict[str, Any],
    backend: str,
    precision: str,
    workload: Workload,
    warmups: int,
    runs: int,
) -> dict[str, Any]:
    if image is None:
        return {
            "sample": sample["label"],
            "source": sample["source"],
            "workload": workload.__dict__,
            "backend": backend,
            "precision": precision,
            "materialize_policy": "backend" if backend == "mlx" else "numpy_float64",
            "status": "skipped",
            "reason": sample["reason"],
        }
    available, reason = _backend_available(backend, precision)
    if not available:
        return {
            "sample": sample["label"],
            "source": sample["source"],
            "workload": workload.__dict__,
            "backend": backend,
            "precision": precision,
            "materialize_policy": "backend" if backend == "mlx" else "numpy_float64",
            "status": "skipped",
            "reason": reason,
        }

    warmup_rows = [
        _run_once(image, backend=backend, precision=precision, workload=workload)
        for _ in range(max(0, warmups))
    ]
    run_rows = [
        _run_once(image, backend=backend, precision=precision, workload=workload)
        for _ in range(max(1, runs))
    ]
    return {
        "sample": sample["label"],
        "source": sample["source"],
        "shape": list(image.shape),
        "dtype": str(image.dtype),
        "workload": workload.__dict__,
        "backend": backend,
        "precision": precision,
        "materialize_policy": "backend" if backend == "mlx" else "numpy_float64",
        "status": "ok",
        "warmups": warmup_rows,
        "runs": run_rows,
        "summary": {
            "runtime_wall_seconds": _summarize(run_rows, "runtime_wall_seconds"),
            "total_wall_seconds": _summarize(run_rows, "total_wall_seconds"),
            "sync_seconds": _summarize(run_rows, "sync_seconds"),
            "preview_seconds": _summarize(run_rows, "preview_seconds"),
            "export_seconds": _summarize(run_rows, "export_seconds"),
        },
    }


def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    backends = ["cpu", "mlx"] if args.backend == "all" else [args.backend]
    samples = _sample_inputs(include_real=bool(args.include_real), real_input=Path(args.real_input))
    payload = {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "config": {
            "backend": args.backend,
            "precision": args.precision,
            "runs": int(args.runs),
            "warmups": int(args.warmups),
            "include_real": bool(args.include_real),
            "include_scanner_lut": bool(args.include_scanner_lut),
            "real_input": str(args.real_input),
        },
        "results": [],
    }
    for sample in samples:
        real_sample = sample["label"] == "real_dng"
        for workload in _workloads(real_sample, include_scanner_lut=bool(args.include_scanner_lut)):
            for backend in backends:
                print(
                    f"Running sample={sample['label']} workload={workload.label} backend={backend}",
                    flush=True,
                )
                payload["results"].append(
                    _run_workload(
                        sample["image"],
                        sample=sample,
                        backend=backend,
                        precision=args.precision,
                        workload=workload,
                        warmups=args.warmups,
                        runs=args.runs,
                    )
                )
    return payload


def format_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Backend Resident Float32 P4 Validation Benchmark - {payload['run_id']}",
        "",
        "## Config",
        "",
        f"- Backend: `{payload['config']['backend']}`",
        f"- Precision: `{payload['config']['precision']}`",
        f"- Runs: `{payload['config']['runs']}`",
        f"- Warmups: `{payload['config']['warmups']}`",
        f"- Include real: `{payload['config']['include_real']}`",
        f"- Include scanner LUT workloads: `{payload['config'].get('include_scanner_lut', False)}`",
        f"- Real input: `{payload['config']['real_input']}`",
        "",
        "## Results",
        "",
        "| Sample | Workload | Backend | Policy | Route | Flags | Status | Runtime | Total | Sync | Preview | Export | Output | HDR Y | Unallowed to_numpy |",
        "|---|---|---|---|---|---|---|---:|---:|---:|---:|---:|---|---|---:|",
    ]
    for result in payload["results"]:
        workload = result["workload"]["label"]
        route = result["workload"].get("route", "print_scan")
        flags = ",".join(
            name
            for name in ("grain", "hdr_metadata", "preview", "export", "scanner_lut")
            if result["workload"].get(name)
        ) or "none"
        if result["status"] != "ok":
            lines.append(
                f"| {result['sample']} | {workload} | {result['backend']} | "
                f"{result.get('materialize_policy', '')} | {route} | {flags} | skipped | | | | | | | | |"
            )
            continue
        last = result["runs"][-1]
        summary = result["summary"]
        output = last["output_source"]
        hdr_y = last["hdr_scene_luminance"]
        lines.append(
            f"| {result['sample']} | {workload} | {result['backend']} | "
            f"{result['materialize_policy']} | {route} | {flags} | ok | "
            f"{summary['runtime_wall_seconds']['median']:.6f}s | "
            f"{summary['total_wall_seconds']['median']:.6f}s | "
            f"{summary['sync_seconds']['median']:.6f}s | "
            f"{summary['preview_seconds']['median']:.6f}s | "
            f"{summary['export_seconds']['median']:.6f}s | "
            f"{output['type']} {output['dtype']} | "
            f"{hdr_y['type']} {hdr_y['dtype']} | "
            f"{last['residency_summary']['unallowed_to_numpy']} |"
        )
    return "\n".join(lines) + "\n"


def write_artifacts(payload: dict[str, Any], out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"backend-resident-float32-p4-validation-benchmark-{payload['run_id']}"
    json_path = out_dir / f"{stem}.json"
    md_path = out_dir / f"{stem}.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(format_markdown(payload), encoding="utf-8")
    return json_path, md_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("all", "cpu", "mlx"), default="all")
    parser.add_argument("--precision", default="float32")
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=0)
    parser.add_argument("--include-real", action="store_true")
    parser.add_argument("--include-scanner-lut", action="store_true")
    parser.add_argument("--real-input", type=Path, default=DEFAULT_REAL_INPUT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = run_benchmark(args)
    if args.no_write:
        print(json.dumps(payload, indent=2))
    else:
        json_path, md_path = write_artifacts(payload, args.out_dir)
        print(f"Wrote JSON: {json_path}")
        print(f"Wrote Markdown: {md_path}")
    failed = [result for result in payload["results"] if result["status"] not in {"ok", "skipped"}]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
