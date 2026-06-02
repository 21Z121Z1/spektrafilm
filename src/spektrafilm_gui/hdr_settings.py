from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class HDRExportSettings:
    """GUI-owned settings for explicit HDR photo export paths."""

    hdr_mapping_mode: str = "generic"
    hdr_heic_gain_map_enabled: bool = False
    hdr_scene_source: str = "output_layer_metadata"
    hdr_diffuse_white_target: float = 1.0
    hdr_peak_headroom: float = 8.0
    hdr_headroom_mode: str = "content_percentile"
    headroom_percentile: float = 99.9
    preserve_sdr_base: bool = True
    gain_map_mode: str = "rgb"
    heic_quality: float = 0.95
