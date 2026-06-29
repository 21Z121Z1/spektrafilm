from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.density import cmy_to_log_xyz_backend
from spektrafilm.gpu.kernels.lut import (
    apply_lut_trilinear_3d_mlx,
    apply_lut_trilinear_3d_mlx_ops,
)
from spektrafilm.testing.float32_reference_backend import (
    Float32ReferenceBackend,
    apply_lut_trilinear_3d_same_order,
    cmy_to_log_raw_same_order,
    cmy_to_log_xyz_same_order,
    gain_map_ev_same_order,
)
from spektrafilm.testing.precision_metrics import (
    difference_metrics,
    gain_map_ev,
    gain_map_ev_metrics,
    headroom_metrics,
    luminance_y,
    monotonicity_violation_count,
    precision_report,
    tile_seam_statistics,
)


SCENARIOS = (
    "smooth_ramp",
    "random_bounded_rgb",
    "near_black_white_stress",
    "hdr_luminance_ramp",
    "tile_seam_stress",
)

STAGE_NAMES = (
    "preprocess_input_conversion",
    "filming.expose",
    "filming.develop",
    "printing.expose",
    "printing.develop",
    "scanning.scan_film",
    "scanning.scan_print",
    "RouteMaster projection light_table",
    "RouteMaster projection paper generic",
    "paper chemical fallback",
    "gain_map encode",
    "final materialize",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build MLX float32 precision staircase reports.")
    parser.add_argument("--height", type=int, default=512)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--seed", type=int, default=20260629)
    parser.add_argument("--scenario", choices=("all",) + SCENARIOS, default="smooth_ramp")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    parser.add_argument("--raw-image", type=Path, default=None)
    parser.add_argument("--tile-rows", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.height <= 0 or args.width <= 0:
        raise ValueError("--height and --width must be positive")
    if args.runs <= 0:
        raise ValueError("--runs must be positive")

    rng = np.random.default_rng(args.seed)
    mlx_backend, mlx_status = _try_mlx_backend()
    selected_scenarios = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    if args.raw_image is not None:
        selected_scenarios = ["raw_image"]

    payload: dict[str, Any] = {
        "goal": "MLX float32 precision staircase against CPU float64 and CPU float32 same-order references",
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "numpy": np.__version__,
            "mlx": mlx_status,
            "height": args.height,
            "width": args.width,
            "runs": args.runs,
            "seed": args.seed,
            "scenario": args.scenario,
            "selected_scenarios": selected_scenarios,
            "supported_scenarios": list(SCENARIOS),
            "tile_rows": args.tile_rows or max(256, args.height // 8),
        },
        "stage_probe_note": (
            "This benchmark uses focused numeric probes for the named pipeline stages. "
            "It does not alter production defaults and does not claim complete production-stage coverage."
        ),
        "scenarios": [],
        "conclusion": {
            "near_theoretical_limit_proven": False,
            "reason": "The harness provides staircase evidence, but complete proof also requires production-stage hook coverage and review of any measured MLX tails.",
        },
    }

    for scenario_index, scenario in enumerate(selected_scenarios):
        image_seed = int(args.seed + scenario_index * 1009)
        image = _load_or_generate_image(
            scenario,
            args.height,
            args.width,
            seed=image_seed,
            raw_image=args.raw_image,
        )
        tables = _spectral_tables(np.random.default_rng(args.seed + 17), spectral_size=8)
        lut, lut_image = _lut_fixture(np.random.default_rng(args.seed + 29), args.height, args.width)

        scenario_payload = {
            "name": scenario,
            "seed": image_seed,
            "shape": list(image.shape),
            "runs": [],
            "summary": {},
        }
        for run in range(args.runs):
            run_payload = _run_scenario(
                image,
                tables,
                lut,
                lut_image,
                tile_rows=args.tile_rows or max(256, args.height // 8),
                mlx_backend=mlx_backend,
            )
            run_payload["run_index"] = run
            scenario_payload["runs"].append(run_payload)
        scenario_payload["summary"] = _summarize_runs(scenario_payload["runs"])
        payload["scenarios"].append(scenario_payload)

    _write_outputs(payload, args.output_json, args.output_markdown)
    return 0


def _try_mlx_backend():
    try:
        backend = select_backend("mlx", precision="float32")
        return backend, {"available": True, "backend": backend.name, "precision": getattr(backend, "precision", None)}
    except (BackendUnavailableError, Exception) as exc:
        return None, {"available": False, "reason": str(exc)}


def _load_or_generate_image(
    scenario: str,
    height: int,
    width: int,
    *,
    seed: int,
    raw_image: Path | None,
) -> np.ndarray:
    if raw_image is not None:
        return _load_raw_image(raw_image, height, width)
    return _generate_scenario(scenario, height, width, seed=seed)


def _load_raw_image(path: Path, height: int, width: int) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        arr = np.load(path)
    elif path.suffix.lower() == ".npz":
        with np.load(path) as data:
            key = "image" if "image" in data else data.files[0]
            arr = data[key]
    else:
        try:
            import imageio.v3 as iio
        except ModuleNotFoundError as exc:
            raise RuntimeError("--raw-image for non-npy files requires imageio") from exc
        arr = iio.imread(path)
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim == 2:
        arr = np.repeat(arr[..., None], 3, axis=-1)
    if arr.shape[-1] > 3:
        arr = arr[..., :3]
    if arr.max(initial=0.0) > 4.0:
        arr = arr / np.float32(255.0 if arr.max() <= 255.0 else 65535.0)
    return _resize_nearest(arr, height, width).astype(np.float64)


def _resize_nearest(image: np.ndarray, height: int, width: int) -> np.ndarray:
    if image.shape[0] == height and image.shape[1] == width:
        return image
    y = np.linspace(0, image.shape[0] - 1, height).round().astype(np.int64)
    x = np.linspace(0, image.shape[1] - 1, width).round().astype(np.int64)
    return image[y][:, x]


def _generate_scenario(scenario: str, height: int, width: int, *, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, width, dtype=np.float64)[None, :]
    y = np.linspace(0.0, 1.0, height, dtype=np.float64)[:, None]
    if scenario == "smooth_ramp":
        image = np.stack(
            (
                np.broadcast_to(x, (height, width)),
                np.broadcast_to(y, (height, width)),
                np.broadcast_to((x + y) * 0.5, (height, width)),
            ),
            axis=-1,
        )
        return image
    if scenario == "random_bounded_rgb":
        return rng.uniform(0.0, 1.35, size=(height, width, 3)).astype(np.float64)
    if scenario == "near_black_white_stress":
        image = rng.uniform(0.0, 1.0, size=(height, width, 3)).astype(np.float64)
        mask = (np.indices((height, width)).sum(axis=0) % 4)[..., None]
        return np.where(mask == 0, image * 1e-5, np.where(mask == 1, 1.0 - image * 1e-5, image))
    if scenario == "hdr_luminance_ramp":
        ramp = np.exp2(np.broadcast_to(x * 4.0 - 2.0, (height, width)))
        chroma = np.stack((ramp, ramp * 0.7 + 0.1, ramp * 0.45 + 0.2), axis=-1)
        return np.clip(chroma, 0.0, 4.0)
    if scenario == "tile_seam_stress":
        base = np.stack(
            (
                np.broadcast_to(x, (height, width)),
                np.broadcast_to(1.0 - x, (height, width)),
                np.broadcast_to(y, (height, width)),
            ),
            axis=-1,
        )
        stripes = ((np.arange(height)[:, None] // max(1, height // 16)) % 2).astype(np.float64)
        return np.clip(base + stripes[..., None] * 0.15, 0.0, 1.4)
    raise ValueError(f"unknown scenario: {scenario}")


def _spectral_tables(rng: np.random.Generator, *, spectral_size: int) -> dict[str, np.ndarray | float]:
    channel_density = rng.uniform(0.03, 0.75, size=(spectral_size, 3)).astype(np.float32)
    base_density = rng.uniform(0.0, 0.08, size=(spectral_size,)).astype(np.float32)
    illuminant = rng.uniform(0.2, 1.0, size=(spectral_size,)).astype(np.float32)
    sensitivity = rng.uniform(0.02, 0.85, size=(spectral_size, 3)).astype(np.float32)
    return {
        "channel_density": channel_density,
        "base_density": base_density,
        "illuminant": illuminant,
        "sensitivity": sensitivity,
        "exposure": np.array([0.85], dtype=np.float32),
        "preflash": np.array([0.0, 0.0005, 0.001], dtype=np.float32),
        "normalization": float(np.sum(illuminant * sensitivity[:, 1], dtype=np.float64)),
    }


def _lut_fixture(rng: np.random.Generator, height: int, width: int) -> tuple[np.ndarray, np.ndarray]:
    lut_size = 17
    grid = np.linspace(0.0, 1.0, lut_size, dtype=np.float32)
    rr, gg, bb = np.meshgrid(grid, grid, grid, indexing="ij")
    lut = np.stack(
        (
            np.clip(rr * 0.92 + gg * 0.04 + bb * 0.02, 0.0, 1.0),
            np.clip(gg * 0.95 + rr * 0.03, 0.0, 1.0),
            np.clip(bb * 0.90 + rr * 0.04 + gg * 0.02, 0.0, 1.0),
        ),
        axis=-1,
    ).astype(np.float32)
    sample_h = min(height, 512)
    sample_w = min(width, 512)
    image = rng.uniform(-0.1, 1.1, size=(sample_h, sample_w, 3)).astype(np.float32)
    return lut, image


def _run_scenario(
    image: np.ndarray,
    tables: dict[str, np.ndarray | float],
    lut: np.ndarray,
    lut_image: np.ndarray,
    *,
    tile_rows: int,
    mlx_backend: Any | None,
) -> dict[str, Any]:
    timings: dict[str, float] = {}
    stages: dict[str, Any] = {}
    same_backend = Float32ReferenceBackend()

    ref = _timed(timings, "cpu_float64.total", lambda: _cpu_pipeline(image, tables, dtype=np.float64))
    legacy = _timed(timings, "cpu_float32_legacy.total", lambda: _cpu_pipeline(image, tables, dtype=np.float32))
    same = _timed(
        timings,
        "cpu_float32_same_order.total",
        lambda: _same_order_pipeline(image, tables, same_backend, tile_rows=tile_rows),
    )

    for stage in STAGE_NAMES:
        if stage == "gain_map encode":
            stages[stage] = {
                "cpu_float32_legacy_vs_cpu_float64": gain_map_ev_metrics(
                    ref["sdr_rgb"],
                    ref["hdr_rgb"],
                    legacy["sdr_rgb"],
                    legacy["hdr_rgb"],
                ),
                "cpu_float32_same_order_vs_cpu_float64": gain_map_ev_metrics(
                    ref["sdr_rgb"],
                    ref["hdr_rgb"],
                    same["sdr_rgb"],
                    same["hdr_rgb"],
                ),
                "cpu_float32_same_order_vs_cpu_float32_legacy": difference_metrics(
                    legacy["gain_map_ev"],
                    same["gain_map_ev"],
                    data_range=1.0,
                ),
            }
        else:
            stages[stage] = {
                "cpu_float32_legacy_vs_cpu_float64": precision_report(ref[stage], legacy[stage]),
                "cpu_float32_same_order_vs_cpu_float64": precision_report(ref[stage], same[stage]),
                "cpu_float32_same_order_vs_cpu_float32_legacy": precision_report(legacy[stage], same[stage]),
            }

    stages["HDR headroom"] = {
        "cpu_float32_legacy_vs_cpu_float64": headroom_metrics(
            ref["sdr_rgb"], ref["hdr_rgb"], legacy["sdr_rgb"], legacy["hdr_rgb"]
        ),
        "cpu_float32_same_order_vs_cpu_float64": headroom_metrics(
            ref["sdr_rgb"], ref["hdr_rgb"], same["sdr_rgb"], same["hdr_rgb"]
        ),
    }
    stages["monotonicity"] = {
        "cpu_float64_luminance_violations": monotonicity_violation_count(np.sort(luminance_y(ref["hdr_rgb"]).reshape(-1))),
        "cpu_float32_same_order_luminance_violations": monotonicity_violation_count(
            np.sort(luminance_y(same["hdr_rgb"]).reshape(-1))
        ),
    }
    stages["tile seam stress"] = tile_seam_statistics(ref["final materialize"], same["final materialize"], tile_rows=tile_rows)
    stages["MLX LUT path"] = _run_lut_probe(lut, lut_image, mlx_backend, timings)

    if mlx_backend is None:
        stages["MLX layers"] = {"status": "skipped", "reason": "MLX/Metal unavailable"}
    else:
        stages["MLX layers"] = _run_mlx_layers(
            image,
            tables,
            ref,
            same,
            mlx_backend,
            timings,
            tile_rows=tile_rows,
        )

    return {
        "timings_seconds": timings,
        "stages": stages,
    }


def _cpu_pipeline(image: np.ndarray, tables: dict[str, np.ndarray | float], *, dtype: Any) -> dict[str, np.ndarray]:
    arr = np.asarray(image, dtype=dtype)
    out: dict[str, np.ndarray] = {}
    pre = np.clip(arr, dtype(0.0), dtype(4.0)).astype(dtype, copy=False)
    out["preprocess_input_conversion"] = pre
    exposed = np.log10(np.fmax(pre * dtype(0.85) + dtype(0.015), dtype(0.0)) + dtype(1e-10)).astype(dtype, copy=False)
    out["filming.expose"] = exposed
    developed = np.clip(dtype(0.55) + dtype(0.18) * exposed + dtype(0.015) * exposed * exposed, dtype(0.0), dtype(1.8))
    developed = developed.astype(dtype, copy=False)
    out["filming.develop"] = developed
    legacy_vectorized = np.dtype(dtype) == np.dtype(np.float32)
    print_exposed = _cmy_to_log_raw_cpu(developed, tables, dtype=dtype, vectorized=legacy_vectorized)
    out["printing.expose"] = print_exposed
    print_developed = np.clip(dtype(0.8) - dtype(0.22) * print_exposed, dtype(0.0), dtype(2.2)).astype(dtype, copy=False)
    out["printing.develop"] = print_developed
    scan_film = _cmy_to_log_xyz_cpu(print_developed, tables, dtype=dtype, vectorized=legacy_vectorized)
    out["scanning.scan_film"] = scan_film
    scan_print = _scan_print_cpu(scan_film, dtype=dtype)
    out["scanning.scan_print"] = scan_print
    sdr, hdr_light = _route_light_table_cpu(scan_print, dtype=dtype)
    out["RouteMaster projection light_table"] = hdr_light
    hdr_paper = _route_paper_cpu(sdr, hdr_light, dtype=dtype)
    out["RouteMaster projection paper generic"] = hdr_paper
    chemical = _paper_chemical_fallback_cpu(sdr, hdr_paper, dtype=dtype)
    out["paper chemical fallback"] = chemical
    out["gain_map encode"] = gain_map_ev(sdr, chemical).astype(dtype, copy=False)
    out["final materialize"] = np.asarray(chemical, dtype=dtype)
    out["sdr_rgb"] = sdr
    out["hdr_rgb"] = chemical
    out["gain_map_ev"] = out["gain_map encode"]
    return out


def _same_order_pipeline(
    image: np.ndarray,
    tables: dict[str, np.ndarray | float],
    backend: Float32ReferenceBackend,
    *,
    tile_rows: int,
) -> dict[str, np.ndarray]:
    out: dict[str, np.ndarray] = {}
    pre = backend.clip(image, 0.0, 4.0)
    out["preprocess_input_conversion"] = pre
    exposed = backend.log10(backend.fmax(pre * np.float32(0.85) + np.float32(0.015), 0.0) + np.float32(1e-10))
    out["filming.expose"] = exposed
    developed = backend.clip(
        np.float32(0.55) + np.float32(0.18) * exposed + np.float32(0.015) * exposed * exposed,
        0.0,
        1.8,
    )
    out["filming.develop"] = developed
    print_exposed = cmy_to_log_raw_same_order(
        developed,
        tables["channel_density"],
        tables["base_density"],
        tables["illuminant"],
        tables["sensitivity"],
        tables["exposure"],
        tables["preflash"],
        tile_rows=tile_rows,
    )
    out["printing.expose"] = print_exposed
    print_developed = backend.clip(np.float32(0.8) - np.float32(0.22) * print_exposed, 0.0, 2.2)
    out["printing.develop"] = print_developed
    scan_film = cmy_to_log_xyz_same_order(
        print_developed,
        tables["channel_density"],
        tables["base_density"],
        tables["illuminant"],
        tables["sensitivity"],
        float(tables["normalization"]),
        tile_rows=tile_rows,
    )
    out["scanning.scan_film"] = scan_film
    scan_print = _scan_print_same_order(scan_film, backend)
    out["scanning.scan_print"] = scan_print
    sdr, hdr_light = _route_light_table_same_order(scan_print, backend)
    out["RouteMaster projection light_table"] = hdr_light
    hdr_paper = _route_paper_same_order(sdr, hdr_light, backend)
    out["RouteMaster projection paper generic"] = hdr_paper
    chemical = _paper_chemical_fallback_same_order(sdr, hdr_paper, backend)
    out["paper chemical fallback"] = chemical
    out["gain_map encode"] = gain_map_ev_same_order(sdr, chemical)
    out["final materialize"] = np.asarray(chemical, dtype=np.float32)
    out["sdr_rgb"] = sdr
    out["hdr_rgb"] = chemical
    out["gain_map_ev"] = out["gain_map encode"]
    return out


def _cmy_to_log_raw_cpu(
    image: np.ndarray,
    tables: dict[str, np.ndarray | float],
    *,
    dtype: Any,
    vectorized: bool = False,
) -> np.ndarray:
    density = np.asarray(image, dtype=dtype)
    channel = np.asarray(tables["channel_density"], dtype=dtype)
    base = np.asarray(tables["base_density"], dtype=dtype)
    illuminant = np.asarray(tables["illuminant"], dtype=dtype)
    sensitivity = np.asarray(tables["sensitivity"], dtype=dtype)
    exposure = np.asarray(tables["exposure"], dtype=dtype).reshape(-1)
    preflash = np.asarray(tables["preflash"], dtype=dtype).reshape((1, 1, 3))
    if vectorized:
        density_spectral = np.einsum("ijk,lk->ijl", density, channel).astype(dtype, copy=False)
        density_spectral = density_spectral + base.reshape((1, 1, -1))
        density_spectral = np.where(density_spectral < dtype(-35.0), dtype(-35.0), density_spectral)
        light = np.power(dtype(10.0), -density_spectral) * illuminant.reshape((1, 1, -1))
        light = np.nan_to_num(light, nan=dtype(0.0)).astype(dtype, copy=False)
        raw = np.einsum("ijk,kl->ijl", light, sensitivity).astype(dtype, copy=False)
        raw = raw * exposure[0] + preflash
        raw = np.where(np.isfinite(raw), raw, dtype(0.0))
        raw = np.where(raw < dtype(0.0), dtype(0.0), raw)
        return np.log10(raw + dtype(1e-10)).astype(dtype, copy=False)

    raw = np.zeros(density.shape, dtype=dtype)
    with np.errstate(invalid="ignore", over="ignore"):
        for k in range(channel.shape[0]):
            d = density[..., 0] * channel[k, 0] + density[..., 1] * channel[k, 1] + density[..., 2] * channel[k, 2] + base[k]
            d = np.where(d < dtype(-35.0), dtype(-35.0), d)
            light = np.power(dtype(10.0), -d) * illuminant[k]
            raw += light[..., None] * sensitivity[k]
    raw = raw * exposure[0] + preflash
    raw = np.where(np.isfinite(raw), raw, dtype(0.0))
    raw = np.where(raw < dtype(0.0), dtype(0.0), raw)
    return np.log10(raw + dtype(1e-10)).astype(dtype, copy=False)


def _cmy_to_log_xyz_cpu(
    image: np.ndarray,
    tables: dict[str, np.ndarray | float],
    *,
    dtype: Any,
    vectorized: bool = False,
) -> np.ndarray:
    density = np.asarray(image, dtype=dtype)
    channel = np.asarray(tables["channel_density"], dtype=dtype)
    base = np.asarray(tables["base_density"], dtype=dtype)
    illuminant = np.asarray(tables["illuminant"], dtype=dtype)
    cmfs = np.asarray(tables["sensitivity"], dtype=dtype)
    norm = dtype(tables["normalization"])
    if vectorized:
        density_spectral = np.einsum("ijk,lk->ijl", density, channel).astype(dtype, copy=False)
        density_spectral = density_spectral + base.reshape((1, 1, -1))
        density_spectral = np.where(density_spectral < dtype(-35.0), dtype(-35.0), density_spectral)
        light = np.power(dtype(10.0), -density_spectral) * illuminant.reshape((1, 1, -1))
        light = np.nan_to_num(light, nan=dtype(0.0)).astype(dtype, copy=False)
        xyz = np.einsum("ijk,kl->ijl", light, cmfs).astype(dtype, copy=False) / norm
        xyz = np.where(xyz < dtype(0.0), dtype(0.0), xyz)
        return np.log10(xyz + dtype(1e-10)).astype(dtype, copy=False)

    xyz = np.zeros(density.shape, dtype=dtype)
    with np.errstate(invalid="ignore", over="ignore"):
        for k in range(channel.shape[0]):
            d = density[..., 0] * channel[k, 0] + density[..., 1] * channel[k, 1] + density[..., 2] * channel[k, 2] + base[k]
            d = np.where(d < dtype(-35.0), dtype(-35.0), d)
            light = np.power(dtype(10.0), -d) * illuminant[k]
            xyz += light[..., None] * cmfs[k]
    xyz = xyz / norm
    xyz = np.where(xyz < dtype(0.0), dtype(0.0), xyz)
    return np.log10(xyz + dtype(1e-10)).astype(dtype, copy=False)


def _scan_print_cpu(log_xyz: np.ndarray, *, dtype: Any) -> np.ndarray:
    xyz = np.power(dtype(10.0), np.asarray(log_xyz, dtype=dtype))
    matrix = np.asarray(
        [[2.02, -0.75, -0.27], [-0.21, 1.35, -0.14], [0.03, -0.24, 1.21]],
        dtype=dtype,
    )
    rgb = xyz @ matrix.T
    rgb = np.maximum(rgb, dtype(0.0))
    rgb = np.power(rgb, dtype(1.0 / 2.2))
    return np.clip(rgb, dtype(0.0), dtype(1.0)).astype(dtype, copy=False)


def _scan_print_same_order(log_xyz: np.ndarray, backend: Float32ReferenceBackend) -> np.ndarray:
    xyz = backend.power(10.0, log_xyz)
    matrix = np.asarray(
        [[2.02, -0.75, -0.27], [-0.21, 1.35, -0.14], [0.03, -0.24, 1.21]],
        dtype=np.float32,
    )
    rgb = backend.matmul(xyz, matrix.T)
    rgb = backend.maximum(rgb, 0.0)
    rgb = backend.pow(rgb, np.float32(1.0 / 2.2))
    return backend.clip(rgb, 0.0, 1.0)


def _route_light_table_cpu(rgb: np.ndarray, *, dtype: Any) -> tuple[np.ndarray, np.ndarray]:
    sdr = np.clip(np.asarray(rgb, dtype=dtype), dtype(0.0), dtype(1.0))
    y = luminance_y(sdr).astype(dtype, copy=False)
    progress = np.clip((y - dtype(0.15)) / dtype(0.55), dtype(0.0), dtype(1.0))
    gain = dtype(1.0) + progress * dtype(2.0)
    hdr = np.clip(sdr * gain[..., None], dtype(0.0), dtype(4.0)).astype(dtype, copy=False)
    return sdr, hdr


def _route_light_table_same_order(rgb: np.ndarray, backend: Float32ReferenceBackend) -> tuple[np.ndarray, np.ndarray]:
    sdr = backend.clip(rgb, 0.0, 1.0)
    y = (
        sdr[..., 0] * np.float32(0.2126)
        + sdr[..., 1] * np.float32(0.7152)
        + sdr[..., 2] * np.float32(0.0722)
    ).astype(np.float32)
    progress = backend.clip((y - np.float32(0.15)) / np.float32(0.55), 0.0, 1.0)
    gain = np.float32(1.0) + progress * np.float32(2.0)
    return sdr, backend.clip(sdr * gain[..., None], 0.0, 4.0)


def _route_paper_cpu(sdr: np.ndarray, hdr: np.ndarray, *, dtype: Any) -> np.ndarray:
    y = luminance_y(hdr).astype(dtype, copy=False)
    progress = np.clip((y - dtype(0.35)) / dtype(2.2), dtype(0.0), dtype(1.0))
    white = np.ones_like(hdr, dtype=dtype)
    paper = hdr * (dtype(1.0) - progress[..., None] * dtype(0.12)) + white * progress[..., None] * dtype(0.12)
    return np.clip(np.maximum(paper, sdr), dtype(0.0), dtype(4.0)).astype(dtype, copy=False)


def _route_paper_same_order(sdr: np.ndarray, hdr: np.ndarray, backend: Float32ReferenceBackend) -> np.ndarray:
    y = (
        hdr[..., 0] * np.float32(0.2126)
        + hdr[..., 1] * np.float32(0.7152)
        + hdr[..., 2] * np.float32(0.0722)
    ).astype(np.float32)
    progress = backend.clip((y - np.float32(0.35)) / np.float32(2.2), 0.0, 1.0)
    paper = hdr * (np.float32(1.0) - progress[..., None] * np.float32(0.12)) + progress[..., None] * np.float32(0.12)
    return backend.clip(np.maximum(paper, sdr), 0.0, 4.0)


def _paper_chemical_fallback_cpu(sdr: np.ndarray, hdr: np.ndarray, *, dtype: Any) -> np.ndarray:
    y = luminance_y(sdr).astype(dtype, copy=False)
    lift = np.clip((y - dtype(0.2)) / dtype(0.5), dtype(0.0), dtype(1.0)) * dtype(0.15)
    return np.clip(np.maximum(hdr, sdr * (dtype(1.0) + lift[..., None])), dtype(0.0), dtype(4.0)).astype(dtype, copy=False)


def _paper_chemical_fallback_same_order(sdr: np.ndarray, hdr: np.ndarray, backend: Float32ReferenceBackend) -> np.ndarray:
    y = (
        sdr[..., 0] * np.float32(0.2126)
        + sdr[..., 1] * np.float32(0.7152)
        + sdr[..., 2] * np.float32(0.0722)
    ).astype(np.float32)
    lift = backend.clip((y - np.float32(0.2)) / np.float32(0.5), 0.0, 1.0) * np.float32(0.15)
    return backend.clip(np.maximum(hdr, sdr * (np.float32(1.0) + lift[..., None])), 0.0, 4.0)


def _run_lut_probe(lut: np.ndarray, image: np.ndarray, mlx_backend: Any | None, timings: dict[str, float]) -> dict[str, Any]:
    same = _timed(timings, "lut.same_order", lambda: apply_lut_trilinear_3d_same_order(lut, image))
    result: dict[str, Any] = {
        "cpu_float32_same_order": {"shape": list(same.shape), "dtype": str(same.dtype)},
    }
    if mlx_backend is None:
        result["mlx_float32_lut_fused"] = {"status": "skipped", "reason": "MLX/Metal unavailable"}
        return result

    mx = mlx_backend.mx
    lut_mx = mlx_backend.asarray(lut, dtype=mx.float32)
    image_mx = mlx_backend.asarray(image, dtype=mx.float32)
    mlx_ops = _timed(
        timings,
        "lut.mlx_unfused_ops",
        lambda: mlx_backend.to_numpy(apply_lut_trilinear_3d_mlx_ops(lut_mx, image_mx, mx=mx)),
    )
    mlx_fused = _timed(
        timings,
        "lut.mlx_fused_metal",
        lambda: mlx_backend.to_numpy(apply_lut_trilinear_3d_mlx(lut_mx, image_mx, mx=mx)),
    )
    result["mlx_float32_unfused_ops_vs_same_order"] = precision_report(same, mlx_ops)
    result["mlx_float32_fused_vs_same_order"] = precision_report(same, mlx_fused)
    result["mlx_float32_fused_vs_unfused_ops"] = precision_report(mlx_ops, mlx_fused)
    return result


def _run_mlx_layers(
    image: np.ndarray,
    tables: dict[str, np.ndarray | float],
    ref: dict[str, np.ndarray],
    same: dict[str, np.ndarray],
    backend: Any,
    timings: dict[str, float],
    *,
    tile_rows: int,
) -> dict[str, Any]:
    mx = backend.mx
    current = backend.asarray(image, dtype=mx.float32)

    def to_np(value: Any) -> np.ndarray:
        return np.asarray(backend.to_numpy(value), dtype=np.float32)

    result: dict[str, Any] = {"status": "ok", "stages": {}}

    current = backend.clip(current, 0.0, 4.0)
    pre = to_np(current)
    result["stages"]["preprocess_input_conversion"] = _mlx_stage_metrics(ref, same, "preprocess_input_conversion", pre)

    current = backend.log10(backend.fmax(current * np.float32(0.85) + np.float32(0.015), 0.0) + np.float32(1e-10))
    exposed = to_np(current)
    result["stages"]["filming.expose"] = _mlx_stage_metrics(ref, same, "filming.expose", exposed)

    current = backend.clip(current * np.float32(0.18) + current * current * np.float32(0.015) + np.float32(0.55), 0.0, 1.8)
    developed = to_np(current)
    result["stages"]["filming.develop"] = _mlx_stage_metrics(ref, same, "filming.develop", developed)

    channel = backend.asarray(tables["channel_density"], dtype=mx.float32)
    base = backend.asarray(tables["base_density"], dtype=mx.float32)
    illum = backend.asarray(tables["illuminant"], dtype=mx.float32)
    sens = backend.asarray(tables["sensitivity"], dtype=mx.float32)
    exposure = backend.asarray(tables["exposure"], dtype=mx.float32)
    preflash = backend.asarray(tables["preflash"], dtype=mx.float32)

    current = _timed(
        timings,
        "mlx_fused.printing_expose",
        lambda: backend.cmy_to_log_raw(current, channel, base, illum, sens, exposure, preflash),
    )
    print_exposed = to_np(current)
    result["stages"]["printing.expose"] = _mlx_stage_metrics(ref, same, "printing.expose", print_exposed)

    current = backend.clip(current * np.float32(-0.22) + np.float32(0.8), 0.0, 2.2)
    print_developed = to_np(current)
    result["stages"]["printing.develop"] = _mlx_stage_metrics(ref, same, "printing.develop", print_developed)

    current = _timed(
        timings,
        "mlx_fused.scanning_scan_film",
        lambda: cmy_to_log_xyz_backend(current, channel, base, illum, sens, float(tables["normalization"]), backend),
    )
    scan_film = to_np(current)
    result["stages"]["scanning.scan_film"] = _mlx_stage_metrics(ref, same, "scanning.scan_film", scan_film)
    result["tile_rows"] = int(tile_rows)
    result["note"] = "MLX stage probe uses fused spectral kernels where production MLX exposes them."
    return result


def _mlx_stage_metrics(ref: dict[str, np.ndarray], same: dict[str, np.ndarray], stage: str, mlx_value: np.ndarray) -> dict[str, Any]:
    return {
        "mlx_float32_vs_cpu_float64": precision_report(ref[stage], mlx_value),
        "mlx_float32_vs_cpu_float32_same_order": precision_report(same[stage], mlx_value),
    }


def _timed(timings: dict[str, float], key: str, fn: Callable[[], Any]) -> Any:
    start = perf_counter()
    value = fn()
    timings[key] = timings.get(key, 0.0) + (perf_counter() - start)
    return value


def _summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    timing_keys = sorted({key for run in runs for key in run["timings_seconds"]})
    timing_summary = {}
    for key in timing_keys:
        values = [float(run["timings_seconds"][key]) for run in runs if key in run["timings_seconds"]]
        timing_summary[key] = {
            "min": min(values),
            "median": statistics.median(values),
            "max": max(values),
        }
    first = runs[0]["stages"]
    summary = {
        "timings_seconds": timing_summary,
        "representative_stage_metrics": {},
    }
    for stage in STAGE_NAMES:
        stage_metrics = first.get(stage)
        if not isinstance(stage_metrics, dict):
            continue
        representative = {}
        for label, metrics in stage_metrics.items():
            if isinstance(metrics, dict) and "max_abs_diff" in metrics:
                representative[label] = {
                    "max_abs_diff": metrics.get("max_abs_diff"),
                    "mean_abs_diff": metrics.get("mean_abs_diff"),
                    "rmse": metrics.get("rmse"),
                    "psnr": metrics.get("psnr"),
                }
        summary["representative_stage_metrics"][stage] = representative
    return summary


def _write_outputs(payload: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Precision Staircase Report",
        "",
        "## Environment",
        "",
    ]
    env = payload["environment"]
    for key in ("python", "platform", "numpy", "height", "width", "runs", "seed", "scenario", "selected_scenarios", "tile_rows"):
        lines.append(f"- {key}: `{env[key]}`")
    lines.append(f"- MLX: `{env['mlx']}`")
    lines.extend(
        [
            "",
            "## Scope",
            "",
            payload["stage_probe_note"],
            "",
            "## Conclusion",
            "",
            f"- near_theoretical_limit_proven: `{payload['conclusion']['near_theoretical_limit_proven']}`",
            f"- reason: {payload['conclusion']['reason']}",
            "",
        ]
    )
    for scenario in payload["scenarios"]:
        lines.extend(
            [
                f"## Scenario: {scenario['name']}",
                "",
                f"- shape: `{scenario['shape']}`",
                f"- seed: `{scenario['seed']}`",
                "",
                "### Timing Summary",
                "",
            ]
        )
        for key, stats in scenario["summary"]["timings_seconds"].items():
            lines.append(
                f"- `{key}`: median {stats['median']:.6f}s "
                f"(min {stats['min']:.6f}s, max {stats['max']:.6f}s)"
            )
        lines.extend(["", "### Representative Metrics", ""])
        representative = scenario["summary"]["representative_stage_metrics"]
        for stage, metrics_by_label in representative.items():
            lines.append(f"#### {stage}")
            if not metrics_by_label:
                lines.append("- no scalar diff metrics")
                continue
            for label, metrics in metrics_by_label.items():
                lines.append(
                    f"- `{label}`: max_abs={_fmt(metrics['max_abs_diff'])}, "
                    f"mean_abs={_fmt(metrics['mean_abs_diff'])}, "
                    f"rmse={_fmt(metrics['rmse'])}, psnr={_fmt(metrics['psnr'])}"
                )
            lines.append("")
        mlx = scenario["runs"][0]["stages"].get("MLX layers", {})
        if mlx.get("status") == "skipped":
            lines.extend(["### MLX Layers", "", f"- skipped: {mlx.get('reason')}", ""])
        else:
            lines.extend(["### MLX Layers", "", "- MLX fused spectral stage metrics are present in JSON.", ""])
    return "\n".join(lines).rstrip() + "\n"


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return "n/a"
    value = float(value)
    if np.isinf(value):
        return "inf"
    if np.isnan(value):
        return "nan"
    return f"{value:.6g}"


if __name__ == "__main__":
    raise SystemExit(main())
