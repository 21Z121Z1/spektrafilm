from __future__ import annotations

import os
from time import perf_counter
import warnings
from pathlib import Path
from typing import Literal

import numpy as np

from spektrafilm.hdr.ideal_paper import project_hdr_ideal_paper
from spektrafilm.hdr.light_table import project_hdr_light_table
from spektrafilm.hdr.projection import HDRProjectionConfig, HDRProjectionResult
from spektrafilm.runtime.route_master import HDRMode, RouteMaster
from spektrafilm.utils import hdr_photo

LegacyHDRMode = Literal["generic", "profile_aware", "film_scan_aware"]


def _save_timing_enabled() -> bool:
    return os.environ.get("SPEKTRAFILM_LOG_SAVE_TIMINGS", "").strip().lower() in {"1", "true", "yes", "on"}


def _log_save_timing(message: str) -> None:
    if _save_timing_enabled():
        print(f"[spektrafilm save timing] {message}", flush=True)


def normalize_hdr_mode(mode: HDRMode | LegacyHDRMode) -> HDRMode:
    if mode == "light_table" or mode == "paper":
        return mode
    if mode == "film_scan_aware":
        warnings.warn(
            "film_scan_aware is a legacy alias; use light_table.",
            DeprecationWarning,
            stacklevel=2,
        )
        return "light_table"
    if mode == "profile_aware":
        warnings.warn(
            "profile_aware is a legacy alias; use paper.",
            DeprecationWarning,
            stacklevel=2,
        )
        return "paper"
    if mode == "generic":
        warnings.warn(
            "generic HDR mapping is legacy and not a public RouteMaster mode; using paper.",
            DeprecationWarning,
            stacklevel=2,
        )
        return "paper"
    raise ValueError("hdr_mode must be 'light_table' or 'paper'.")


def render_hdr_pair_from_master(
    master: RouteMaster,
    *,
    hdr_mode: HDRMode | LegacyHDRMode | None = None,
    config: HDRProjectionConfig | None = None,
) -> HDRProjectionResult:
    mode = normalize_hdr_mode(master.mode if hdr_mode is None else hdr_mode)
    if mode == "light_table":
        return project_hdr_light_table(master, config)
    return project_hdr_ideal_paper(master, config)


def render_hdr_film_pair_from_master(
    master: RouteMaster,
    *,
    hdr_mode: HDRMode | LegacyHDRMode | None = None,
    config: HDRProjectionConfig | None = None,
) -> HDRProjectionResult:
    return render_hdr_pair_from_master(master, hdr_mode=hdr_mode, config=config)


def export_hdr_heic_from_simulator(
    simulator,
    image,
    filename: str | Path,
    *,
    hdr_mode: HDRMode | LegacyHDRMode = "paper",
    config: HDRProjectionConfig | None = None,
    color_space: str,
    quality: float = 0.95,
    gain_map_mode: Literal["luma", "rgb"] = "rgb",
    master: RouteMaster | None = None,
) -> tuple[str, ...]:
    mode = normalize_hdr_mode(hdr_mode)
    total_start = perf_counter()
    process_start = perf_counter()
    used_cached_master = master is not None
    if master is None:
        master = simulator.process_master(image, hdr_mode=mode)
    process_elapsed = perf_counter() - process_start
    render_start = perf_counter()
    result = render_hdr_pair_from_master(master, hdr_mode=mode, config=config)
    render_elapsed = perf_counter() - render_start
    encode_start = perf_counter()
    diagnostics = hdr_photo.save_hdr_photo_heic_from_pair(
        filename,
        np.ascontiguousarray(result.sdr_rgb),
        np.ascontiguousarray(result.hdr_rgb),
        color_space=color_space,
        headroom=result.headroom,
        quality=quality,
        gain_map_mode=gain_map_mode,
    )
    _log_save_timing(
        "export_hdr_heic_from_simulator "
        f"cached_master={used_cached_master} "
        f"process_master={process_elapsed:.4f}s "
        f"render_pair={render_elapsed:.4f}s "
        f"encode={perf_counter() - encode_start:.4f}s "
        f"total={perf_counter() - total_start:.4f}s"
    )
    return diagnostics


__all__ = [
    "export_hdr_heic_from_simulator",
    "normalize_hdr_mode",
    "render_hdr_film_pair_from_master",
    "render_hdr_pair_from_master",
]
