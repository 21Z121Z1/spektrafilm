from __future__ import annotations

import argparse
import json
import math
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import rawpy
from skimage.transform import resize

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.process import Simulator
from spektrafilm.utils.hdr_curve_profiles import (
    build_profile_hdr_curve,
    evaluate_profile_sdr_curve,
    get_hdr_curve_profile,
    luminance_y,
)
from spektrafilm.utils.hdr_photo import HDRPhotoMapping, prepare_hdr_photo_renditions
from spektrafilm.utils.gain_map import compute_gain_map, normalize_gain_map
from spektrafilm.utils.gain_map_io import save_gain_map_jpeg
from spektrafilm.utils.gain_map_metadata import GainMapChannel, GainMapMetadata
from spektrafilm.utils.hdr_photo import (
    build_gain_map_xmp_packet,
    build_iso_21496_1_gain_map_metadata,
    encode_gain_map_log2,
    validate_gain_map,
)
from spektrafilm.utils.raw_file_processor import load_and_process_raw_file


SAFE_FILM = "kodak_portra_400"
SAFE_PAPER = "kodak_portra_endura"
UNSAFE_FILM = "fujifilm_velvia_100"
UNSAFE_PAPER = "kodak_portra_endura"


@dataclass(frozen=True, slots=True)
class RawProcessingDiagnostics:
    rawpy_rgb_min: float
    rawpy_rgb_max: float
    rawpy_rgb_p50: float
    rawpy_rgb_p99: float
    rawpy_rgb_p999: float
    rawpy_rgb_clip_fraction: float
    raw_sensor_normalized_max: float | None
    raw_sensor_normalized_p99: float | None
    raw_sensor_normalized_p999: float | None
    diffuse_white_estimate: float
    headroom_estimate: float
    method: str
    confidence: str


def _float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _stats(values: np.ndarray) -> dict[str, float]:
    flat = np.asarray(values, dtype=np.float64).reshape(-1)
    return {
        "min": float(np.min(flat)),
        "max": float(np.max(flat)),
        "p50": float(np.percentile(flat, 50.0)),
        "p99": float(np.percentile(flat, 99.0)),
        "p999": float(np.percentile(flat, 99.9)),
    }


def _quick_raw_sensor_stats(path: Path) -> dict[str, Any]:
    with rawpy.imread(str(path)) as raw:
        raw_image = np.asarray(raw.raw_image_visible, dtype=np.float64)
        sizes = raw.sizes
        white_level = _float(getattr(raw, "white_level", None))
        black_levels = np.asarray(getattr(raw, "black_level_per_channel", []), dtype=np.float64)
        black_level = float(np.nanmin(black_levels)) if black_levels.size else 0.0
        stats: dict[str, Any] = {
            "width": int(getattr(sizes, "width", raw_image.shape[1])),
            "height": int(getattr(sizes, "height", raw_image.shape[0])),
            "raw_sensor_white_level": white_level,
            "raw_sensor_black_level": black_level,
        }
        if white_level is None or white_level <= black_level:
            stats.update(
                {
                    "raw_sensor_normalized_max": None,
                    "raw_sensor_normalized_p50": None,
                    "raw_sensor_normalized_p99": None,
                    "raw_sensor_normalized_p999": None,
                    "raw_sensor_clip_fraction": None,
                }
            )
            return stats
        normalized = (raw_image - black_level) / (white_level - black_level)
        finite = normalized[np.isfinite(normalized)]
        stats.update(
            {
                "raw_sensor_normalized_max": float(np.max(finite)),
                "raw_sensor_normalized_p50": float(np.percentile(finite, 50.0)),
                "raw_sensor_normalized_p99": float(np.percentile(finite, 99.0)),
                "raw_sensor_normalized_p999": float(np.percentile(finite, 99.9)),
                "raw_sensor_clip_fraction": float(np.mean(finite >= 0.999)),
            }
        )
        return stats


def _paired_exports(sample_dir: Path) -> dict[str, list[str]]:
    paired: dict[str, list[str]] = {}
    for path in sample_dir.rglob("*"):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in {".jpg", ".jpeg", ".heic"}:
            continue
        stem = path.stem.replace("_preview", "").replace("_converted", "")
        paired.setdefault(stem, []).append(path.name)
    return paired


def _diagnostic_subset(paths: list[Path], limit: int) -> list[Path]:
    if len(paths) <= limit:
        return paths
    indices = np.linspace(0, len(paths) - 1, limit, dtype=int)
    return [paths[int(index)] for index in np.unique(indices)]


def _scan_raw_files(sample_dir: Path, *, diagnostic_limit: int) -> tuple[list[Path], list[dict[str, Any]]]:
    dng_paths = [path for path in sorted(sample_dir.rglob("*")) if path.is_file() and path.suffix.lower() == ".dng"]
    diagnostic_paths = set(_diagnostic_subset(dng_paths, diagnostic_limit))
    candidates: list[dict[str, Any]] = []
    paired = _paired_exports(sample_dir)
    for index, path in enumerate(dng_paths, start=1):
        if path not in diagnostic_paths:
            continue
        print(f"Scanning RAW sensor stats {index}/{len(dng_paths)}: {path.name}", flush=True)
        try:
            stats = _quick_raw_sensor_stats(path)
        except Exception as exc:
            candidates.append({"path": str(path), "filename": path.name, "error": str(exc)})
            continue
        stem = path.stem.replace("_converted", "")
        stats.update(
            {
                "path": str(path),
                "filename": path.name,
                "paired_exports": paired.get(stem, []),
            }
        )
        candidates.append(stats)
    return dng_paths, candidates


def _select_samples(candidates: list[dict[str, Any]], max_samples: int) -> list[dict[str, Any]]:
    usable = [item for item in candidates if "error" not in item and item.get("raw_sensor_normalized_p50") is not None]
    if not usable:
        return []

    selected: list[tuple[str, dict[str, Any]]] = []

    def add(reason: str, item: dict[str, Any]) -> None:
        if any(existing["path"] == item["path"] for _, existing in selected):
            return
        if len(selected) < max_samples:
            selected.append((reason, item))

    ordered_p50 = sorted(usable, key=lambda item: float(item["raw_sensor_normalized_p50"]))
    normal_pool = [
        item for item in usable
        if float(item["raw_sensor_normalized_p99"]) >= 0.05
        and float(item["raw_sensor_clip_fraction"] or 0.0) <= 0.001
    ] or usable
    median_p50 = float(np.median([float(item["raw_sensor_normalized_p50"]) for item in normal_pool]))
    normal = min(normal_pool, key=lambda item: abs(float(item["raw_sensor_normalized_p50"]) - median_p50))
    add("normal_or_balanced_exposure", normal)
    add("low_key_or_darkest_sensor_median", ordered_p50[0])
    add("bright_highlight_sensor_p999", max(usable, key=lambda item: float(item["raw_sensor_normalized_p999"])))
    add("most_clipped_or_near_white_sensor_values", max(usable, key=lambda item: float(item["raw_sensor_clip_fraction"] or 0.0)))

    for item in usable:
        add("fill_to_max_samples", item)
        if len(selected) >= max_samples:
            break

    result = []
    for reason, item in selected:
        copy = dict(item)
        copy["selection_reason"] = reason
        result.append(copy)
    return result


def _resize_for_validation(image: np.ndarray, max_edge: int = 768) -> np.ndarray:
    height, width = image.shape[:2]
    scale = min(1.0, float(max_edge) / float(max(height, width)))
    if scale >= 1.0:
        return np.asarray(image, dtype=np.float32)
    new_shape = (max(1, int(round(height * scale))), max(1, int(round(width * scale))), 3)
    resized = resize(
        image,
        new_shape,
        order=1,
        mode="reflect",
        preserve_range=True,
        anti_aliasing=True,
    )
    return np.asarray(resized, dtype=np.float32)


def _raw_processing_diagnostics(image: np.ndarray, sample: dict[str, Any]) -> RawProcessingDiagnostics:
    rgb = np.asarray(image, dtype=np.float32)
    finite = rgb[np.isfinite(rgb)]
    if finite.size == 0:
        finite = np.array([0.0], dtype=np.float32)
    diffuse_white = max(float(np.percentile(finite, 99.0)), 0.1)
    p999 = float(np.percentile(finite, 99.9))
    headroom = p999 / max(diffuse_white, 1e-8)
    confidence = "low" if diffuse_white <= 0.10001 else "medium"
    return RawProcessingDiagnostics(
        rawpy_rgb_min=float(np.min(finite)),
        rawpy_rgb_max=float(np.max(finite)),
        rawpy_rgb_p50=float(np.percentile(finite, 50.0)),
        rawpy_rgb_p99=float(np.percentile(finite, 99.0)),
        rawpy_rgb_p999=p999,
        rawpy_rgb_clip_fraction=float(np.mean(finite >= 0.999)),
        raw_sensor_normalized_max=_float(sample.get("raw_sensor_normalized_max")),
        raw_sensor_normalized_p99=_float(sample.get("raw_sensor_normalized_p99")),
        raw_sensor_normalized_p999=_float(sample.get("raw_sensor_normalized_p999")),
        diffuse_white_estimate=diffuse_white,
        headroom_estimate=headroom,
        method="postprocess_percentile",
        confidence=confidence,
    )


def _validation_params():
    params = init_params(film_profile=SAFE_FILM, print_profile=SAFE_PAPER)
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.io.full_image = True
    params.io.input_color_space = "ACES2065-1"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "ACES2065-1"
    params.io.output_cctf_encoding = False
    params.camera.auto_exposure = True
    return digest_params(params)


def _binned_conformance(
    *,
    scene_y: np.ndarray,
    sdr_y: np.ndarray,
    hdr_y: np.ndarray,
    profile,
    mapping: HDRPhotoMapping,
) -> tuple[list[dict[str, float]], dict[str, float]]:
    eps = 1e-8
    scene = np.maximum(np.asarray(scene_y, dtype=np.float32), eps)
    scene_ev = np.log2(scene)
    bins = np.arange(-8.0, 6.0 + 0.5, 0.5, dtype=np.float32)
    rows: list[dict[str, float]] = []
    for low, high in zip(bins[:-1], bins[1:]):
        mask = (scene_ev >= low) & (scene_ev < high)
        count = int(np.count_nonzero(mask))
        if count < 64:
            continue
        median_scene_y = float(np.median(scene[mask]))
        expected_sdr_y = float(evaluate_profile_sdr_curve(profile, np.array([median_scene_y], dtype=np.float32))[0])
        expected_hdr_y = float(build_profile_hdr_curve(profile, np.array([median_scene_y], dtype=np.float32), mapping=mapping)[0])
        median_sdr_y = float(np.median(sdr_y[mask]))
        median_hdr_y = float(np.median(hdr_y[mask]))
        gain = median_hdr_y / max(median_sdr_y, eps)
        rows.append(
            {
                "scene_ev_bin": float((low + high) * 0.5),
                "pixel_count": float(count),
                "median_scene_y": median_scene_y,
                "expected_sdr_y": expected_sdr_y,
                "empirical_sdr_y": median_sdr_y,
                "expected_hdr_y": expected_hdr_y,
                "empirical_hdr_y": median_hdr_y,
                "median_gain_y": float(gain),
                "median_log_gain_y": float(math.log2(max(gain, eps))),
                "sdr_error": float(median_sdr_y - expected_sdr_y),
                "hdr_error": float(median_hdr_y - expected_hdr_y),
            }
        )

    if not rows:
        return rows, {
            "occupied_bin_count": 0.0,
            "weighted_rmse_empirical_sdr_vs_S_profile": float("nan"),
            "weighted_rmse_empirical_hdr_vs_H_profile": float("nan"),
            "highlight_separation_ratio": float("nan"),
            "max_adjacent_log_gain_jump": float("nan"),
        }

    weights = np.array([row["pixel_count"] for row in rows], dtype=np.float64)
    sdr_errors = np.array([row["sdr_error"] for row in rows], dtype=np.float64)
    hdr_errors = np.array([row["hdr_error"] for row in rows], dtype=np.float64)
    log_gain = np.array([row["median_log_gain_y"] for row in rows], dtype=np.float64)
    highlight = [row for row in rows if row["median_scene_y"] >= 1.0]
    if len(highlight) >= 2:
        empirical_sdr = np.array([row["empirical_sdr_y"] for row in highlight], dtype=np.float64)
        empirical_hdr = np.array([row["empirical_hdr_y"] for row in highlight], dtype=np.float64)
        highlight_ratio = float(np.ptp(empirical_hdr) / max(np.ptp(empirical_sdr), eps))
    else:
        highlight_ratio = float("nan")
    metrics = {
        "occupied_bin_count": float(len(rows)),
        "weighted_rmse_empirical_sdr_vs_S_profile": float(np.sqrt(np.average(sdr_errors * sdr_errors, weights=weights))),
        "weighted_rmse_empirical_hdr_vs_H_profile": float(np.sqrt(np.average(hdr_errors * hdr_errors, weights=weights))),
        "highlight_separation_ratio": highlight_ratio,
        "max_adjacent_log_gain_jump": float(np.max(np.abs(np.diff(log_gain)))) if log_gain.size > 1 else 0.0,
        "low_confidence_bin_count": 0.0,
    }
    return rows, metrics


def _validate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    path = Path(sample["path"])
    raw_image_full = load_and_process_raw_file(
        path,
        white_balance="as_shot",
        output_colorspace="ACES2065-1",
        output_cctf_encoding=False,
    )
    raw_diagnostics = _raw_processing_diagnostics(raw_image_full, sample)
    raw_image = _resize_for_validation(raw_image_full)

    params = _validation_params()
    simulator = Simulator(params)
    process_output = simulator.process(raw_image)
    metadata_output = simulator.process_with_metadata(raw_image)
    look_rgb = np.asarray(metadata_output.image, dtype=np.float32)
    scene_luminance = metadata_output.hdr_scene_energy.scene_luminance if metadata_output.hdr_scene_energy else None
    if scene_luminance is None:
        raise RuntimeError("process_with_metadata did not return scene_luminance")

    darker_result = Simulator(_validation_params()).process_with_metadata(raw_image * np.float32(0.5))
    brighter_result = Simulator(_validation_params()).process_with_metadata(raw_image * np.float32(2.0))
    darker_meta = darker_result.hdr_scene_energy
    brighter_meta = brighter_result.hdr_scene_energy
    low_sidecar = darker_meta.scene_luminance
    high_sidecar = brighter_meta.scene_luminance
    auto_ev_sidecar_pairs = sorted(
        [
            (float(darker_meta.auto_exposure_ev), float(np.median(low_sidecar))),
            (float(brighter_meta.auto_exposure_ev), float(np.median(high_sidecar))),
        ],
        key=lambda item: item[0],
    )
    auto_sidecar_median_delta = abs(auto_ev_sidecar_pairs[1][1] - auto_ev_sidecar_pairs[0][1])
    auto_sidecar_median_scale = max(abs(auto_ev_sidecar_pairs[1][1]), abs(auto_ev_sidecar_pairs[0][1]), 1e-8)

    profile = get_hdr_curve_profile(SAFE_FILM, SAFE_PAPER)
    if profile is None:
        raise RuntimeError(f"Missing generated curve profile for {SAFE_FILM}/{SAFE_PAPER}")
    mapping = HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        film=SAFE_FILM,
        paper=SAFE_PAPER,
        max_headroom=8.0,
        headroom_percentile=99.9,
    )
    renditions = prepare_hdr_photo_renditions(look_rgb, mapping=mapping, scene_luminance=scene_luminance)
    with tempfile.TemporaryDirectory(prefix="spektrafilm-hdr-metadata-probe-") as probe_dir:
        metadata_checks = _metadata_validation_checks(
            renditions,
            probe_dir=Path(probe_dir),
            color_space="Display P3",
        )
    look_y = luminance_y(look_rgb)
    sdr_y = luminance_y(renditions.sdr_rgb)
    hdr_y = luminance_y(renditions.hdr_rgb)
    rows, conformance = _binned_conformance(
        scene_y=scene_luminance,
        sdr_y=sdr_y,
        hdr_y=hdr_y,
        profile=profile,
        mapping=mapping,
    )

    fallback = {
        "missing_sidecar_raises": False,
        "unsafe_profile_falls_back": False,
        "unsafe_profile_raises": False,
        "missing_profile_falls_back": False,
        "missing_profile_raises": False,
        "low_confidence_raw_diffuse_white": raw_diagnostics.confidence == "low",
    }
    try:
        prepare_hdr_photo_renditions(look_rgb, mapping=mapping, scene_luminance=None)
    except ValueError:
        fallback["missing_sidecar_raises"] = True

    unsafe_mapping = HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        film=UNSAFE_FILM,
        paper=UNSAFE_PAPER,
        max_headroom=8.0,
    )
    try:
        unsafe_renditions = prepare_hdr_photo_renditions(look_rgb, mapping=unsafe_mapping, scene_luminance=scene_luminance)
        fallback["unsafe_profile_falls_back"] = unsafe_renditions.mapping_mode_used == "generic"
    except ValueError:
        fallback["unsafe_profile_raises"] = True

    missing_mapping = HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        film="missing_film_profile",
        paper="missing_paper_profile",
        max_headroom=8.0,
    )
    try:
        missing_renditions = prepare_hdr_photo_renditions(look_rgb, mapping=missing_mapping, scene_luminance=scene_luminance)
        fallback["missing_profile_falls_back"] = missing_renditions.mapping_mode_used == "generic"
    except ValueError:
        fallback["missing_profile_raises"] = True

    highlight_mask = scene_luminance >= np.percentile(scene_luminance, 95.0)
    look_highlight_span = float(np.percentile(look_y[highlight_mask], 90.0) - np.percentile(look_y[highlight_mask], 10.0))
    hdr_highlight_span = float(np.percentile(hdr_y[highlight_mask], 90.0) - np.percentile(hdr_y[highlight_mask], 10.0))

    return {
        **sample,
        "raw_diagnostics": asdict(raw_diagnostics),
        "validation_shape": list(raw_image.shape),
        "sidecar_shape": list(scene_luminance.shape),
        "sidecar_stats": _stats(scene_luminance),
        "sidecar_finite_nonnegative": bool(np.isfinite(scene_luminance).all() and np.min(scene_luminance) >= 0.0),
        "process_vs_metadata_max_abs": float(np.max(np.abs(process_output - look_rgb))),
        "auto_exposure_sidecar_low_ev": auto_ev_sidecar_pairs[0][0],
        "auto_exposure_sidecar_low_ev_median": auto_ev_sidecar_pairs[0][1],
        "auto_exposure_sidecar_high_ev": auto_ev_sidecar_pairs[1][0],
        "auto_exposure_sidecar_high_ev_median": auto_ev_sidecar_pairs[1][1],
        "auto_exposure_sidecar_scale_invariant": bool(auto_sidecar_median_delta / auto_sidecar_median_scale <= 1e-4),
        "headroom": float(renditions.headroom),
        "sdr_stats": _stats(sdr_y),
        "hdr_stats": _stats(hdr_y),
        "look_highlight_span_p10_p90": look_highlight_span,
        "hdr_highlight_span_p10_p90": hdr_highlight_span,
        "highlight_separation_improved": bool(hdr_highlight_span > look_highlight_span),
        "metadata_checks": metadata_checks,
        "conformance_metrics": conformance,
        "tone_curve_rows": rows,
        "fallback": fallback,
    }


def _metadata_validation_checks(
    renditions,
    *,
    probe_dir: Path,
    color_space: str,
) -> dict[str, Any]:
    """Validate gain-map metadata contracts using real rendered SDR/HDR arrays."""

    probe_dir.mkdir(parents=True, exist_ok=True)
    sdr_rgb = np.asarray(renditions.sdr_rgb, dtype=np.float32)
    hdr_rgb = np.asarray(renditions.hdr_rgb, dtype=np.float32)
    headroom = max(float(renditions.headroom), 1.0 + 1e-6)
    headroom_ev = float(math.log2(headroom))

    hdr_photo_gain_map = encode_gain_map_log2(sdr_rgb, hdr_rgb, headroom=headroom)
    hdr_photo_metadata = build_iso_21496_1_gain_map_metadata(renditions)
    hdr_photo_log_gain = hdr_photo_gain_map * np.float32(max(math.log2(headroom), 1e-6))
    hdr_photo_xmp = build_gain_map_xmp_packet(
        hdr_photo_metadata,
        image_width=int(sdr_rgb.shape[1]),
        image_height=int(sdr_rgb.shape[0]),
        gain_map_width=int(hdr_photo_gain_map.shape[1]),
        gain_map_height=int(hdr_photo_gain_map.shape[0]),
    )
    gain_map_warnings = validate_gain_map(hdr_photo_log_gain, hdr_photo_metadata)

    gain = compute_gain_map(sdr_rgb, hdr_rgb, h_baseline=0.0, h_alternate=headroom_ev)
    normalized_gain, g_min, g_max = normalize_gain_map(gain)
    channels = tuple(
        GainMapChannel(
            gain_map_min=g_min,
            gain_map_max=g_max,
            gamma=1.0,
            base_offset=1.0 / 1023.0,
            alternate_offset=1.0 / 1023.0,
        )
        for _ in range(3)
    )
    iso_binary_metadata = GainMapMetadata(
        is_multichannel=True,
        use_base_colour_space=True,
        base_hdr_headroom=0.0,
        alternate_hdr_headroom=headroom_ev,
        channels=channels,
    )
    serialized_roundtrip = GainMapMetadata.deserialize(iso_binary_metadata.serialize())
    serialized_roundtrip_ok = (
        serialized_roundtrip.is_multichannel is iso_binary_metadata.is_multichannel
        and serialized_roundtrip.use_base_colour_space is iso_binary_metadata.use_base_colour_space
        and abs(serialized_roundtrip.alternate_hdr_headroom - iso_binary_metadata.alternate_hdr_headroom) <= 1e-3
        and len(serialized_roundtrip.channels) == len(iso_binary_metadata.channels)
    )
    android_xmp = iso_binary_metadata.to_xmp(gain_map_length=normalized_gain.size)

    jpeg_probe: dict[str, Any] = {
        "written": False,
        "roundtrip_metadata": False,
        "roundtrip_gain_map": False,
        "error": None,
    }
    try:
        probe_path = probe_dir / "iso21496_gain_map_probe.jpg"
        save_gain_map_jpeg(probe_path, sdr_rgb, normalized_gain, iso_binary_metadata)
        probe_bytes = probe_path.read_bytes()
        jpeg_probe.update(
            {
                "written": probe_path.exists(),
                "roundtrip_metadata": (
                    b"urn:iso:std:iso:ts:21496:-1" in probe_bytes
                    and b"Container:Directory" in probe_bytes
                ),
                "roundtrip_gain_map": b"MPF\x00" in probe_bytes,
                "format": "jpeg",
            }
        )
    except Exception as exc:
        jpeg_probe["error"] = f"{type(exc).__name__}: {exc}"

    required_exr_attributes = [
        "chromaticities",
        "colorInteropID",
        "oiio:ColorSpace",
        "whiteLuminance",
        "hdrHeadroom",
    ]
    return {
        "color_space": color_space,
        "android_ultra_hdr": {
            "container_directory": "Container:Directory" in android_xmp,
            "primary_and_gain_map_items": (
                'Item:Semantic="Primary"' in android_xmp
                and 'Item:Semantic="GainMap"' in android_xmp
            ),
            "gain_map_length_declared": "Item:Length=" in android_xmp,
            "single_gain_map_can_carry_android_and_iso_metadata": True,
        },
        "iso_21496_1": {
            "serialized_metadata_roundtrip": serialized_roundtrip_ok,
            "xmp_hdrgm_namespace": "http://ns.adobe.com/hdr-gain-map/1.0/" in hdr_photo_xmp,
            "gain_map_shape": list(hdr_photo_gain_map.shape),
            "gain_map_finite_unit_range": bool(
                np.isfinite(hdr_photo_gain_map).all()
                and np.min(hdr_photo_gain_map) >= 0.0
                and np.max(hdr_photo_gain_map) <= 1.0
            ),
            "gain_map_validation_warnings": gain_map_warnings,
            "hdr_capacity_max": float(hdr_photo_metadata.hdr_capacity_max),
        },
        "jpeg_probe": jpeg_probe,
        "exr": {
            "required_attributes": required_exr_attributes,
            "color_space": color_space,
            "white_luminance_nits": 203.0,
        },
    }


def _markdown_report(
    *,
    sample_dir: Path,
    output_path: Path,
    candidates: list[dict[str, Any]],
    diagnostic_candidate_count: int,
    selected: list[dict[str, Any]],
    results: list[dict[str, Any]],
    command: str,
) -> str:
    lines = [
        "# Profile-Aware HDR ProRAW Validation",
        "",
        f"Command: `{command}`",
        f"Sample directory: `{sample_dir}`",
        f"Discovered DNG files: {sum(1 for item in candidates if item.get('filename', '').lower().endswith('.dng'))}",
        f"DNG files inspected for selection diagnostics: {diagnostic_candidate_count}",
        "",
        "## Selected Samples",
        "",
        "| File | Reason | Dimensions | Paired exports |",
        "| --- | --- | ---: | --- |",
    ]
    selected_by_path = {item["path"]: item for item in selected}
    for result in results:
        selected_item = selected_by_path[result["path"]]
        lines.append(
            f"| {result['filename']} | {result['selection_reason']} | "
            f"{selected_item.get('width')}x{selected_item.get('height')} | "
            f"{', '.join(selected_item.get('paired_exports') or []) or 'none found'} |"
        )

    lines.extend(
        [
            "",
            "## RAW Diagnostics",
            "",
            "| File | rawpy min/max/p50/p99/p999 | rawpy clip | sensor max/p99/p999 | diffuse white | headroom | confidence |",
            "| --- | --- | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for result in results:
        diag = result["raw_diagnostics"]
        sensor = (
            f"{diag.get('raw_sensor_normalized_max'):.3f}/"
            f"{diag.get('raw_sensor_normalized_p99'):.3f}/"
            f"{diag.get('raw_sensor_normalized_p999'):.3f}"
            if diag.get("raw_sensor_normalized_max") is not None
            else "n/a"
        )
        lines.append(
            f"| {result['filename']} | "
            f"{diag['rawpy_rgb_min']:.4f}/{diag['rawpy_rgb_max']:.4f}/{diag['rawpy_rgb_p50']:.4f}/"
            f"{diag['rawpy_rgb_p99']:.4f}/{diag['rawpy_rgb_p999']:.4f} | "
            f"{diag['rawpy_rgb_clip_fraction']:.5f} | {sensor} | "
            f"{diag['diffuse_white_estimate']:.4f} | {diag['headroom_estimate']:.3f} | "
            f"{diag['method']} / {diag['confidence']} |"
        )

    lines.extend(
        [
            "",
            "## Sidecar And SDR Preservation",
            "",
            "| File | validation shape | sidecar shape | finite nonnegative | process vs metadata max abs | auto exposure scale invariant |",
            "| --- | --- | --- | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        lines.append(
            f"| {result['filename']} | {result['validation_shape']} | {result['sidecar_shape']} | "
            f"{result['sidecar_finite_nonnegative']} | {result['process_vs_metadata_max_abs']:.3e} | "
            f"{result['auto_exposure_sidecar_scale_invariant']} |"
        )

    lines.extend(
        [
            "",
            "## HDR Rendition And Curve Conformance",
            "",
            "| File | headroom | SDR RMSE vs S_profile | HDR RMSE vs H_profile | highlight separation ratio | max log-gain jump | HDR highlight span > look |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        metrics = result["conformance_metrics"]
        lines.append(
            f"| {result['filename']} | {result['headroom']:.3f} | "
            f"{metrics['weighted_rmse_empirical_sdr_vs_S_profile']:.4f} | "
            f"{metrics['weighted_rmse_empirical_hdr_vs_H_profile']:.4f} | "
            f"{metrics['highlight_separation_ratio']:.3f} | "
            f"{metrics['max_adjacent_log_gain_jump']:.3f} | "
            f"{result['highlight_separation_improved']} |"
        )

    lines.extend(
        [
            "",
            "## Gain-Map And EXR Metadata Checks",
            "",
            "| File | Android container | ISO metadata roundtrip | ISO gain-map warnings | JPEG probe metadata | JPEG probe gain map | EXR attributes tracked |",
            "| --- | ---: | ---: | --- | ---: | ---: | --- |",
        ]
    )
    for result in results:
        metadata = result["metadata_checks"]
        android = metadata["android_ultra_hdr"]
        iso = metadata["iso_21496_1"]
        jpeg_probe = metadata["jpeg_probe"]
        exr = metadata["exr"]
        warnings = ", ".join(iso["gain_map_validation_warnings"]) or "none"
        lines.append(
            f"| {result['filename']} | {android['container_directory'] and android['primary_and_gain_map_items']} | "
            f"{iso['serialized_metadata_roundtrip']} | {warnings} | "
            f"{jpeg_probe['roundtrip_metadata']} | {jpeg_probe['roundtrip_gain_map']} | "
            f"{', '.join(exr['required_attributes'])} |"
        )

    lines.extend(
        [
            "",
            "## Fallback Cases",
            "",
            "| File | missing sidecar | unsafe profile fallback | unsafe profile rejected | missing profile fallback | missing profile rejected | low-confidence RAW white |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for result in results:
        fallback = result["fallback"]
        lines.append(
            f"| {result['filename']} | {fallback['missing_sidecar_raises']} | "
            f"{fallback['unsafe_profile_falls_back']} | {fallback['unsafe_profile_raises']} | "
            f"{fallback['missing_profile_falls_back']} | {fallback['missing_profile_raises']} | "
            f"{fallback['low_confidence_raw_diffuse_white']} |"
        )

    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Runtime validation uses a bounded downsampled RGB array for speed; RAW diagnostics come from the full DNG decode.",
            "- Real-image curve conformance is statistical because chroma, texture, glare, grain, and gamut compression prevent exact per-pixel curve matching.",
            "- SDR preservation is checked as `Simulator.process()` vs `Simulator.process_with_metadata()` on the same RAW-derived validation array; historical pre-change arrays are not available in this script.",
            "",
            f"Machine-readable diagnostics: `{output_path.with_suffix('.json')}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate profile-aware HDR mapping on local Apple ProRAW/DNG samples.")
    parser.add_argument("--sample-dir", type=Path, required=True)
    parser.add_argument("--max-samples", type=int, default=4)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--diagnostic-scan-limit", type=int, default=0)
    args = parser.parse_args()

    sample_dir = args.sample_dir.expanduser()
    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    diagnostic_limit = int(args.diagnostic_scan_limit) if args.diagnostic_scan_limit else max(16, int(args.max_samples) * 8)
    dng_paths, candidates = _scan_raw_files(sample_dir, diagnostic_limit=diagnostic_limit)
    selected = _select_samples(candidates, max(1, int(args.max_samples)))
    if not selected:
        raise SystemExit(f"No usable DNG samples found under {sample_dir}")

    results = []
    for sample in selected:
        print(f"Validating {sample['filename']} ({sample['selection_reason']})")
        results.append(_validate_sample(sample))

    command = "uv run python tools/validate_profile_aware_hdr_raw_samples.py " + " ".join(
        [
            f'--sample-dir "{sample_dir}"',
            f"--max-samples {args.max_samples}",
            f"--output {output_path}",
            f"--diagnostic-scan-limit {diagnostic_limit}",
        ]
    )
    output_path.write_text(
        _markdown_report(
            sample_dir=sample_dir,
            output_path=output_path,
            candidates=[{"filename": path.name} for path in dng_paths],
            diagnostic_candidate_count=len(candidates),
            selected=selected,
            results=results,
            command=command,
        ),
        encoding="utf-8",
    )
    output_path.with_suffix(".json").write_text(
        json.dumps(
            {
                "sample_dir": str(sample_dir),
                "dng_count": len(dng_paths),
                "diagnostic_candidate_count": len(candidates),
                "selected": selected,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
