#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import platform
import sys
import time
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

RESULTS_DIR = Path(__file__).resolve().parent / "results"
DEFAULT_SAMPLE_ROOT = Path("/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片")
RAW_EXTENSIONS = {
    ".3fr",
    ".arw",
    ".cr2",
    ".cr3",
    ".dng",
    ".erf",
    ".fff",
    ".iiq",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".nrw",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rw2",
    ".sr2",
    ".srf",
    ".x3f",
}
TAPS = ("rgb_in", "rgb_pre", "log_e_film", "cmy_film", "log_e_print", "cmy_print", "rgb_out")
EPS = 1.0e-8


def safe_name(value: str) -> str:
    keep = []
    for ch in value:
        if ch.isalnum() or ch in {"-", "_", "."}:
            keep.append(ch)
        else:
            keep.append("_")
    return "".join(keep).strip("_")[:120] or "sample"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        keys: list[str] = []
        for row in rows:
            for key in row:
                if key not in keys:
                    keys.append(key)
        fieldnames = keys
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def command_line() -> str:
    return " ".join([sys.executable, *sys.argv])


def inventory_samples(sample_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not sample_root.exists():
        return rows
    for path in sorted(sample_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in RAW_EXTENSIONS:
            continue
        stat = path.stat()
        try:
            rel = path.relative_to(sample_root)
        except ValueError:
            rel = path
        rows.append(
            {
                "path": str(path),
                "relative_path": str(rel),
                "folder": str(rel.parent),
                "name": path.name,
                "extension": path.suffix.lower(),
                "size_bytes": stat.st_size,
                "size_mb": round(stat.st_size / 1024 / 1024, 3),
                "mtime": int(stat.st_mtime),
            }
        )
    return rows


def choose_representative_inventory_rows(rows: list[dict[str, Any]], limit: int = 8) -> list[dict[str, Any]]:
    if not rows:
        return []
    by_folder: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_folder.setdefault(str(row["folder"]), []).append(row)
    selected: list[dict[str, Any]] = []
    for _folder, group in sorted(by_folder.items(), key=lambda item: (-len(item[1]), item[0])):
        selected.append(max(group, key=lambda row: int(row["size_bytes"])))
        if len(selected) >= limit:
            return selected
    remaining = [row for row in sorted(rows, key=lambda row: int(row["size_bytes"]), reverse=True) if row not in selected]
    selected.extend(remaining[: max(0, limit - len(selected))])
    return selected[:limit]


def raw_load(path: Path, *, output_colorspace: str = "ProPhoto RGB") -> np.ndarray:
    from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

    return load_and_process_raw_file(
        path,
        white_balance="as_shot",
        temperature=5500.0,
        tint=1.0,
        lens_correction=False,
        output_colorspace=output_colorspace,
        output_cctf_encoding=False,
    )


def center_crop_or_stride(image: np.ndarray, max_size: int) -> np.ndarray:
    image = np.asarray(image)[..., :3]
    if max_size <= 0:
        return image
    h, w = image.shape[:2]
    if max(h, w) <= max_size:
        return image
    step = int(math.ceil(max(h, w) / max_size))
    sampled = image[::step, ::step, :]
    h2, w2 = sampled.shape[:2]
    crop_h = min(h2, max_size)
    crop_w = min(w2, max_size)
    y0 = max(0, (h2 - crop_h) // 2)
    x0 = max(0, (w2 - crop_w) // 2)
    return np.ascontiguousarray(sampled[y0 : y0 + crop_h, x0 : x0 + crop_w, :])


def gui_prepare_input(image: np.ndarray, *, backend: str, precision: str) -> np.ndarray:
    source = np.asarray(image)
    if backend == "mlx" and precision == "float32":
        return np.asarray(source[..., :3], dtype=np.float32)
    return np.double(source)


def build_params(*, backend: str, precision: str, materialize_policy: str, deterministic: bool) -> tuple[Any, str, str | None]:
    source = "spektrafilm_gui.PROJECT_DEFAULT_GUI_STATE"
    fallback_error: str | None = None
    try:
        from spektrafilm_gui.params_mapper import build_params_from_state
        from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, clone_gui_state

        state = clone_gui_state(PROJECT_DEFAULT_GUI_STATE)
        state.input_image.settings.compute_backend = backend
        state.input_image.settings.gpu_precision = precision
        state.input_image.settings.materialize_policy = materialize_policy
        state.input_image.settings.gpu_validate = False
        params = build_params_from_state(state)
    except Exception as exc:  # noqa: BLE001 - this is an analysis fallback.
        fallback_error = f"{type(exc).__name__}: {exc}"
        source = "runtime.init_params fallback"
        from spektrafilm.runtime.params_builder import init_params

        params = init_params()
        params.settings.compute_backend = backend
        params.settings.gpu_precision = precision
        params.settings.materialize_policy = materialize_policy
        params.settings.use_enlarger_lut = True
        params.settings.use_scanner_lut = True
        params.settings.lut_resolution = 17
        params.settings.use_fast_stats = True

    if deterministic:
        params.debug.deactivate_spatial_effects = True
        params.debug.deactivate_stochastic_effects = True
        params.camera.auto_exposure = False
        params.scanner.white_correction = False
        params.scanner.black_correction = False
        params.scanner.unsharp_mask = (0.0, 0.0)
        params.film_render.halation.boost_ev = 0.0
        params.film_render.grain.active = False
        params.print_render.glare.active = False

    from spektrafilm.runtime.params_builder import digest_params

    params = digest_params(params)
    params.settings.compute_backend = backend
    params.settings.gpu_precision = precision
    params.settings.materialize_policy = materialize_policy
    params.settings.gpu_validate = False
    return params, source, fallback_error


def params_summary(params: Any) -> dict[str, Any]:
    return {
        "film_stock": getattr(getattr(params.film, "info", None), "stock", None),
        "print_stock": getattr(getattr(params.print, "info", None), "stock", None),
        "input_color_space": params.io.input_color_space,
        "input_cctf_decoding": params.io.input_cctf_decoding,
        "output_color_space": params.io.output_color_space,
        "output_cctf_encoding": params.io.output_cctf_encoding,
        "output_clip_min": params.io.output_clip_min,
        "output_clip_max": params.io.output_clip_max,
        "scan_film": params.io.scan_film,
        "rgb_to_raw_method": params.settings.rgb_to_raw_method,
        "use_enlarger_lut": params.settings.use_enlarger_lut,
        "use_scanner_lut": params.settings.use_scanner_lut,
        "lut_resolution": params.settings.lut_resolution,
        "compute_backend": params.settings.compute_backend,
        "gpu_precision": params.settings.gpu_precision,
        "materialize_policy": params.settings.materialize_policy,
        "auto_exposure": params.camera.auto_exposure,
        "grain_active": params.film_render.grain.active,
        "glare_active": params.print_render.glare.active,
    }


def to_numpy(value: Any, pipeline: Any | None = None) -> np.ndarray:
    if pipeline is not None:
        backend = getattr(pipeline, "_backend", None)
        if backend is not None and getattr(backend, "supports_gpu", False) and hasattr(backend, "to_numpy"):
            return np.asarray(backend.to_numpy(value))
    return np.asarray(value)


def capture_pipeline(params: Any, image: np.ndarray) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    from spektrafilm.runtime.pipeline import SimulationPipeline
    from spektrafilm.runtime.topology import Tap

    pipeline = SimulationPipeline(params)
    state: dict[str, Any] = {Tap.RGB_IN: image}
    timings: dict[str, float] = {}
    started = time.perf_counter()
    for node in getattr(pipeline, "_topology"):
        if all(name in state for name in node.reads):
            node_start = time.perf_counter()
            node.fire(state)
            timings[node.label] = time.perf_counter() - node_start
    elapsed = time.perf_counter() - started
    captured: dict[str, np.ndarray] = {}
    for tap in TAPS:
        if tap in state:
            captured[tap] = to_numpy(state[tap], pipeline)
    if "rgb_out" in state:
        materialized = getattr(pipeline, "_materialize_output_value")(state["rgb_out"])
        captured["materialized_rgb_out"] = to_numpy(materialized, pipeline)
    metadata = {
        "backend_summary": pipeline.backend_runtime_summary(),
        "timings": timings,
        "elapsed_seconds": elapsed,
        "pipeline_timings": dict(pipeline.get_timings()),
    }
    return captured, metadata


def array_stats(name: str, array: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(array)
    finite_mask = np.isfinite(arr)
    finite = arr[finite_mask]
    row: dict[str, Any] = {
        "name": name,
        "shape": "x".join(str(int(dim)) for dim in arr.shape),
        "dtype": str(arr.dtype),
        "size": int(arr.size),
        "finite_count": int(finite.size),
        "nan_count": int(np.isnan(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
        "posinf_count": int(np.isposinf(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
        "neginf_count": int(np.isneginf(arr).sum()) if np.issubdtype(arr.dtype, np.floating) else 0,
    }
    if finite.size:
        row.update(
            {
                "min": float(np.min(finite)),
                "max": float(np.max(finite)),
                "mean": float(np.mean(finite)),
                "std": float(np.std(finite)),
                "negative_count": int((finite < 0.0).sum()),
                "above_one_count": int((finite > 1.0).sum()),
                "at_or_below_zero_count": int((finite <= 0.0).sum()),
                "at_or_above_one_count": int((finite >= 1.0).sum()),
            }
        )
    return row


def percentile_map(values: np.ndarray, prefix: str) -> dict[str, float]:
    values = np.asarray(values, dtype=np.float64)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return {f"{prefix}_{label}": float("nan") for label in ("p50", "p90", "p95", "p99", "p999", "max")}
    percentiles = np.percentile(values, [50, 90, 95, 99, 99.9])
    return {
        f"{prefix}_p50": float(percentiles[0]),
        f"{prefix}_p90": float(percentiles[1]),
        f"{prefix}_p95": float(percentiles[2]),
        f"{prefix}_p99": float(percentiles[3]),
        f"{prefix}_p999": float(percentiles[4]),
        f"{prefix}_max": float(np.max(values)),
    }


def luminance_y(rgb: np.ndarray) -> np.ndarray:
    arr = np.asarray(rgb, dtype=np.float64)[..., :3]
    return np.tensordot(arr, np.array([0.2126, 0.7152, 0.0722], dtype=np.float64), axes=([-1], [0]))


def compute_delta_e(cpu: np.ndarray, candidate: np.ndarray, color_space: str = "sRGB") -> dict[str, float]:
    try:
        import colour
    except Exception:  # noqa: BLE001
        return {"deltaE2000_mean": float("nan"), "deltaE2000_p95": float("nan"), "deltaE2000_max": float("nan")}
    cpu_rgb = np.asarray(cpu, dtype=np.float64)[..., :3]
    cand_rgb = np.asarray(candidate, dtype=np.float64)[..., :3]
    if cpu_rgb.shape != cand_rgb.shape or cpu_rgb.ndim != 3:
        return {"deltaE2000_mean": float("nan"), "deltaE2000_p95": float("nan"), "deltaE2000_max": float("nan")}
    total = int(np.prod(cpu_rgb.shape[:2]))
    step = max(1, int(math.ceil(total / 200000)))
    cpu_sub = np.clip(cpu_rgb.reshape(-1, 3)[::step], 0.0, 1.0)
    cand_sub = np.clip(cand_rgb.reshape(-1, 3)[::step], 0.0, 1.0)
    try:
        xyz_cpu = colour.RGB_to_XYZ(cpu_sub, colourspace=colour.RGB_COLOURSPACES[color_space], apply_cctf_decoding=True)
        xyz_cand = colour.RGB_to_XYZ(cand_sub, colourspace=colour.RGB_COLOURSPACES[color_space], apply_cctf_decoding=True)
        lab_cpu = colour.XYZ_to_Lab(xyz_cpu)
        lab_cand = colour.XYZ_to_Lab(xyz_cand)
        de = colour.delta_E(lab_cpu, lab_cand, method="CIE 2000")
    except Exception:  # noqa: BLE001
        return {"deltaE2000_mean": float("nan"), "deltaE2000_p95": float("nan"), "deltaE2000_max": float("nan")}
    return {
        "deltaE2000_mean": float(np.mean(de)),
        "deltaE2000_p95": float(np.percentile(de, 95)),
        "deltaE2000_max": float(np.max(de)),
    }


def image_quality_metrics(cpu: np.ndarray, candidate: np.ndarray) -> dict[str, float]:
    result: dict[str, float] = {"psnr": float("nan"), "ssim": float("nan")}
    cpu_arr = np.asarray(cpu, dtype=np.float64)
    cand_arr = np.asarray(candidate, dtype=np.float64)
    if cpu_arr.shape != cand_arr.shape or cpu_arr.ndim < 2:
        return result
    data_min = float(min(np.nanmin(cpu_arr), np.nanmin(cand_arr)))
    data_max = float(max(np.nanmax(cpu_arr), np.nanmax(cand_arr)))
    data_range = max(1.0, data_max - data_min)
    try:
        from skimage.metrics import peak_signal_noise_ratio, structural_similarity

        result["psnr"] = float(peak_signal_noise_ratio(cpu_arr, cand_arr, data_range=data_range))
        channel_axis = -1 if cpu_arr.ndim == 3 and cpu_arr.shape[-1] in {3, 4} else None
        min_dim = min(cpu_arr.shape[0], cpu_arr.shape[1]) if cpu_arr.ndim >= 2 else 0
        win_size = 7 if min_dim >= 7 else max(3, min_dim if min_dim % 2 == 1 else min_dim - 1)
        if win_size >= 3:
            result["ssim"] = float(
                structural_similarity(cpu_arr, cand_arr, data_range=data_range, channel_axis=channel_axis, win_size=win_size)
            )
    except Exception:  # noqa: BLE001
        pass
    return result


def compare_arrays(sample_id: str, stage: str, cpu: np.ndarray, candidate: np.ndarray, *, color_space: str) -> dict[str, Any]:
    cpu_arr = np.asarray(cpu, dtype=np.float64)
    cand_arr = np.asarray(candidate, dtype=np.float64)
    row: dict[str, Any] = {
        "sample_id": sample_id,
        "stage": stage,
        "cpu_shape": "x".join(str(int(dim)) for dim in cpu_arr.shape),
        "candidate_shape": "x".join(str(int(dim)) for dim in cand_arr.shape),
        "cpu_dtype": str(np.asarray(cpu).dtype),
        "candidate_dtype": str(np.asarray(candidate).dtype),
    }
    if cpu_arr.shape != cand_arr.shape:
        row["status"] = "shape_mismatch"
        return row
    finite_mask = np.isfinite(cpu_arr) & np.isfinite(cand_arr)
    if not finite_mask.any():
        row["status"] = "no_finite_overlap"
        return row
    diff = cand_arr - cpu_arr
    abs_diff = np.abs(diff[finite_mask])
    rel = abs_diff / np.maximum(np.abs(cpu_arr[finite_mask]), EPS)
    ev = np.log2((np.maximum(cand_arr[finite_mask], 0.0) + EPS) / (np.maximum(cpu_arr[finite_mask], 0.0) + EPS))
    row.update({"status": "ok"})
    row.update(percentile_map(abs_diff, "abs"))
    row.update(percentile_map(rel, "rel"))
    row.update(percentile_map(np.abs(ev), "abs_ev"))
    row["mae"] = float(np.mean(abs_diff))
    row["rmse"] = float(np.sqrt(np.mean(diff[finite_mask] ** 2)))
    row["max_signed_error"] = float(np.max(diff[finite_mask]))
    row["min_signed_error"] = float(np.min(diff[finite_mask]))
    if cpu_arr.ndim == 3 and cpu_arr.shape[-1] >= 3:
        y_cpu = luminance_y(cpu_arr)
        y_cand = luminance_y(cand_arr)
        y_abs = np.abs(y_cand - y_cpu)
        row.update(percentile_map(y_abs, "luma_abs"))
        row.update(image_quality_metrics(np.clip(cpu_arr[..., :3], 0.0, 1.0), np.clip(cand_arr[..., :3], 0.0, 1.0)))
        row.update(compute_delta_e(cpu_arr, cand_arr, color_space=color_space))
    return row


def save_heatmap_and_histogram(out_dir: Path, sample_id: str, stage: str, cpu: np.ndarray, candidate: np.ndarray) -> tuple[str | None, str | None]:
    if np.asarray(cpu).shape != np.asarray(candidate).shape:
        return None, None
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return None, None
    diff = np.abs(np.asarray(candidate, dtype=np.float64) - np.asarray(cpu, dtype=np.float64))
    if diff.ndim == 3:
        heat = np.max(diff[..., :3], axis=-1)
    else:
        heat = diff
    heat_path = out_dir / f"error_heatmap_{safe_name(sample_id)}_{safe_name(stage)}.png"
    hist_path = out_dir / f"error_histogram_{safe_name(sample_id)}_{safe_name(stage)}.png"
    plt.figure(figsize=(7, 5))
    plt.imshow(heat, cmap="magma")
    plt.colorbar(label="max abs error")
    plt.title(f"{sample_id} {stage}")
    plt.tight_layout()
    plt.savefig(heat_path, dpi=140)
    plt.close()
    finite = heat[np.isfinite(heat)]
    plt.figure(figsize=(7, 4))
    plt.hist(finite.ravel(), bins=100)
    plt.xlabel("max abs error")
    plt.ylabel("pixel count")
    plt.title(f"{sample_id} {stage}")
    plt.tight_layout()
    plt.savefig(hist_path, dpi=140)
    plt.close()
    return str(heat_path), str(hist_path)


def high_error_pixels(sample_id: str, stage: str, cpu: np.ndarray, candidate: np.ndarray, limit: int = 25) -> list[dict[str, Any]]:
    if np.asarray(cpu).shape != np.asarray(candidate).shape:
        return []
    cpu_arr = np.asarray(cpu, dtype=np.float64)
    cand_arr = np.asarray(candidate, dtype=np.float64)
    diff = np.abs(cand_arr - cpu_arr)
    if diff.ndim == 3:
        score = np.max(diff[..., :3], axis=-1)
    else:
        score = diff
    flat = score.reshape(-1)
    if flat.size == 0:
        return []
    indexes = np.argpartition(flat, -min(limit, flat.size))[-min(limit, flat.size) :]
    indexes = indexes[np.argsort(flat[indexes])[::-1]]
    rows: list[dict[str, Any]] = []
    for idx in indexes:
        yx = np.unravel_index(int(idx), score.shape)
        row: dict[str, Any] = {
            "sample_id": sample_id,
            "stage": stage,
            "y": int(yx[0]) if len(yx) >= 1 else 0,
            "x": int(yx[1]) if len(yx) >= 2 else 0,
            "max_abs_error": float(flat[idx]),
        }
        if cpu_arr.ndim == 3:
            row.update(
                {
                    "cpu_r": float(cpu_arr[yx][0]),
                    "cpu_g": float(cpu_arr[yx][1]),
                    "cpu_b": float(cpu_arr[yx][2]),
                    "candidate_r": float(cand_arr[yx][0]),
                    "candidate_g": float(cand_arr[yx][1]),
                    "candidate_b": float(cand_arr[yx][2]),
                }
            )
        rows.append(row)
    return rows


def synthetic_inputs(size: int = 256) -> dict[str, np.ndarray]:
    x = np.linspace(0.0, 1.0, size, dtype=np.float32)
    ramp = np.tile(x[None, :], (size, 1))
    shadow = np.tile(np.geomspace(1e-6, 0.05, size).astype(np.float32)[None, :], (size, 1))
    highlight = np.tile(np.linspace(0.18, 8.0, size, dtype=np.float32)[None, :], (size, 1))
    rgb_patches = np.zeros((size, size, 3), dtype=np.float32)
    thirds = max(1, size // 3)
    rgb_patches[:, :thirds, 0] = np.linspace(0, 2.0, thirds, dtype=np.float32)[None, :]
    rgb_patches[:, thirds : 2 * thirds, 1] = np.linspace(0, 2.0, thirds, dtype=np.float32)[None, :]
    rgb_patches[:, 2 * thirds :, 2] = np.linspace(0, 2.0, size - 2 * thirds, dtype=np.float32)[None, :]
    near_clip = np.stack(
        [
            np.tile(np.linspace(0.95, 1.05, size, dtype=np.float32)[None, :], (size, 1)),
            ramp,
            1.0 - ramp,
        ],
        axis=-1,
    )
    return {
        "synthetic_gray_ramp": np.dstack([ramp, ramp, ramp]).astype(np.float32),
        "synthetic_shadow_ramp": np.dstack([shadow, shadow, shadow]).astype(np.float32),
        "synthetic_highlight_ramp": np.dstack([highlight, highlight, highlight]).astype(np.float32),
        "synthetic_saturated_rgb": rgb_patches,
        "synthetic_near_clip_mix": near_clip.astype(np.float32),
    }


def try_export_roundtrip(out_dir: Path, sample_id: str, cpu: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "not_run"}
    try:
        from spektrafilm.color_management import ColorEncoding
        from spektrafilm.utils.io import load_image_oiio, save_image_oiio
    except Exception as exc:  # noqa: BLE001
        result.update({"status": "unavailable", "error": f"{type(exc).__name__}: {exc}"})
        return result
    cpu_path = out_dir / f"export_cpu_{safe_name(sample_id)}.png"
    cand_path = out_dir / f"export_mlx_{safe_name(sample_id)}.png"
    try:
        encoding = ColorEncoding(
            color_space="sRGB",
            transfer="cctf",
            role="display",
            clip_negatives=True,
            clip_highlights=True,
        )
        save_image_oiio(str(cpu_path), np.asarray(cpu, dtype=np.float32), bit_depth=16, encoding=encoding)
        save_image_oiio(str(cand_path), np.asarray(candidate, dtype=np.float32), bit_depth=16, encoding=encoding)
        decoded_cpu = load_image_oiio(cpu_path, dtype=np.float32)
        decoded_cand = load_image_oiio(cand_path, dtype=np.float32)
        metrics = compare_arrays(sample_id, "export_png16_roundtrip", decoded_cpu, decoded_cand, color_space="sRGB")
        result.update({"status": "ok", "cpu_path": str(cpu_path), "candidate_path": str(cand_path), "metrics": metrics})
    except Exception as exc:  # noqa: BLE001
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    return result


def measure_one(sample_id: str, image: np.ndarray, args: argparse.Namespace, out_dir: Path) -> dict[str, Any]:
    cpu_params, cpu_source, cpu_fallback = build_params(
        backend="cpu",
        precision="float64",
        materialize_policy="numpy_float64",
        deterministic=args.deterministic,
    )
    mlx_params, mlx_source, mlx_fallback = build_params(
        backend="mlx",
        precision="float32",
        materialize_policy="backend",
        deterministic=args.deterministic,
    )
    cpu_input = gui_prepare_input(image, backend="cpu", precision="float64")
    mlx_input = gui_prepare_input(image, backend="mlx", precision="float32")
    stats_rows = [array_stats("decoded_or_synthetic_source", image), array_stats("cpu_gui_prepared_input", cpu_input), array_stats("mlx_gui_prepared_input", mlx_input)]
    sample_result: dict[str, Any] = {
        "sample_id": sample_id,
        "source_shape": list(np.asarray(image).shape),
        "source_dtype": str(np.asarray(image).dtype),
        "cpu_params_source": cpu_source,
        "mlx_params_source": mlx_source,
        "cpu_params_fallback_error": cpu_fallback,
        "mlx_params_fallback_error": mlx_fallback,
        "cpu_params": params_summary(cpu_params),
        "mlx_params": params_summary(mlx_params),
        "stage_metrics": [],
        "stage_stats": stats_rows,
        "artifacts": {},
    }
    try:
        cpu_stages, cpu_meta = capture_pipeline(cpu_params, cpu_input)
        mlx_stages, mlx_meta = capture_pipeline(mlx_params, mlx_input)
    except Exception as exc:  # noqa: BLE001
        sample_result["status"] = "pipeline_failed"
        sample_result["error"] = f"{type(exc).__name__}: {exc}"
        return sample_result
    sample_result["status"] = "ok"
    sample_result["cpu_meta"] = cpu_meta
    sample_result["mlx_meta"] = mlx_meta
    for stage, array in cpu_stages.items():
        stats_rows.append(array_stats(f"cpu_{stage}", array))
    for stage, array in mlx_stages.items():
        stats_rows.append(array_stats(f"mlx_{stage}", array))
    for stage in [*TAPS, "materialized_rgb_out"]:
        if stage not in cpu_stages or stage not in mlx_stages:
            continue
        row = compare_arrays(sample_id, stage, cpu_stages[stage], mlx_stages[stage], color_space=cpu_params.io.output_color_space)
        sample_result["stage_metrics"].append(row)
        if stage in {"rgb_out", "materialized_rgb_out"}:
            heat, hist = save_heatmap_and_histogram(out_dir, sample_id, stage, cpu_stages[stage], mlx_stages[stage])
            if heat:
                sample_result["artifacts"][f"{stage}_heatmap"] = heat
            if hist:
                sample_result["artifacts"][f"{stage}_histogram"] = hist
            high_rows = high_error_pixels(sample_id, stage, cpu_stages[stage], mlx_stages[stage])
            high_path = out_dir / f"high_error_pixels_{safe_name(sample_id)}_{safe_name(stage)}.csv"
            write_csv(high_path, high_rows)
            sample_result["artifacts"][f"{stage}_high_error_pixels"] = str(high_path)
    if not args.skip_export_roundtrip and "materialized_rgb_out" in cpu_stages and "materialized_rgb_out" in mlx_stages:
        sample_result["export_png16_roundtrip"] = try_export_roundtrip(
            out_dir,
            sample_id,
            cpu_stages["materialized_rgb_out"],
            mlx_stages["materialized_rgb_out"],
        )
    return sample_result


def flatten_stage_metrics(per_sample: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample in per_sample:
        for row in sample.get("stage_metrics", []):
            rows.append(row)
        export = sample.get("export_png16_roundtrip", {})
        if export.get("status") == "ok" and isinstance(export.get("metrics"), dict):
            rows.append(export["metrics"])
    return rows


def flatten_stage_stats(per_sample: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sample in per_sample:
        for row in sample.get("stage_stats", []):
            out = {"sample_id": sample.get("sample_id"), **row}
            rows.append(out)
    return rows


def environment_report() -> dict[str, Any]:
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "command": command_line(),
        "cwd": os.getcwd(),
    }
    try:
        import mlx.core as mx

        metal = getattr(mx, "metal", None)
        report["mlx_importable"] = True
        report["mlx_metal_available"] = bool(getattr(metal, "is_available", lambda: False)())
    except Exception as exc:  # noqa: BLE001
        report["mlx_importable"] = False
        report["mlx_error"] = f"{type(exc).__name__}: {exc}"
    return report


def run_inventory(args: argparse.Namespace, out_dir: Path) -> list[dict[str, Any]]:
    rows = inventory_samples(args.sample_root)
    write_csv(Path(__file__).resolve().parent / "sample_inventory.csv", rows)
    selected = choose_representative_inventory_rows(rows, args.max_samples)
    write_csv(out_dir / "selected_sample_candidates.csv", selected)
    return selected


def run_measurements(args: argparse.Namespace, out_dir: Path) -> list[dict[str, Any]]:
    per_sample: list[dict[str, Any]] = []
    if args.synthetic_only or not args.samples:
        for sample_id, image in synthetic_inputs(args.synthetic_size).items():
            per_sample.append(measure_one(sample_id, image, args, out_dir))
    for raw_path_text in args.samples:
        raw_path = Path(raw_path_text)
        sample_id = safe_name(raw_path.stem)
        try:
            decoded = raw_load(raw_path)
            measured = center_crop_or_stride(decoded, args.max_working_size)
        except Exception as exc:  # noqa: BLE001
            per_sample.append({"sample_id": sample_id, "path": str(raw_path), "status": "raw_load_failed", "error": f"{type(exc).__name__}: {exc}"})
            continue
        result = measure_one(sample_id, measured, args, out_dir)
        result["path"] = str(raw_path)
        result["decoded_shape"] = list(decoded.shape)
        result["measured_shape"] = list(measured.shape)
        result["max_working_size"] = args.max_working_size
        per_sample.append(result)
    return per_sample


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spektrafilm CPU float64 vs MLX/Metal float32 precision measurement")
    parser.add_argument("--sample-root", type=Path, default=DEFAULT_SAMPLE_ROOT)
    parser.add_argument("--results-dir", type=Path, default=RESULTS_DIR)
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--synthetic-only", action="store_true")
    parser.add_argument("--samples", nargs="*", default=[])
    parser.add_argument("--max-samples", type=int, default=8)
    parser.add_argument("--max-working-size", type=int, default=384)
    parser.add_argument("--synthetic-size", type=int, default=192)
    parser.add_argument("--deterministic", action="store_true", help="Disable stochastic/spatial effects where runtime params allow it.")
    parser.add_argument("--skip-export-roundtrip", action="store_true")
    args = parser.parse_args(argv)

    out_dir = args.results_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "environment.json", environment_report())
    selected = run_inventory(args, out_dir)
    config = {
        "sample_root": str(args.sample_root),
        "results_dir": str(out_dir),
        "inventory_count": len(inventory_samples(args.sample_root)),
        "selected_sample_candidates": selected,
        "args": vars(args) | {"sample_root": str(args.sample_root), "results_dir": str(out_dir)},
    }
    write_json(out_dir / "measurement_config.json", config)
    write_json(Path(__file__).resolve().parent / "measurement_config.json", config)
    if args.inventory_only:
        return 0
    per_sample = run_measurements(args, out_dir)
    write_json(out_dir / "per_sample_metrics.json", per_sample)
    write_json(Path(__file__).resolve().parent / "per_sample_metrics.json", per_sample)
    write_csv(out_dir / "metrics_summary.csv", flatten_stage_metrics(per_sample))
    write_csv(Path(__file__).resolve().parent / "metrics_summary.csv", flatten_stage_metrics(per_sample))
    write_csv(out_dir / "stage_stats.csv", flatten_stage_stats(per_sample))
    failed = [sample for sample in per_sample if sample.get("status") != "ok"]
    write_json(out_dir / "failures.json", failed)
    return 1 if failed and not any(sample.get("status") == "ok" for sample in per_sample) else 0


if __name__ == "__main__":
    raise SystemExit(main())
