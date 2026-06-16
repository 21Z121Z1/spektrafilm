from __future__ import annotations

from dataclasses import dataclass


PUBLIC_HDR_MAPPING_MODES = {"light_table", "paper"}
LEGACY_HDR_MAPPING_MODE_ALIASES = {
    "generic": "paper",
    "profile_aware": "paper",
    "film_scan_aware": "light_table",
}


def normalize_hdr_mapping_mode(mode: str | None) -> str:
    if mode in PUBLIC_HDR_MAPPING_MODES:
        return str(mode)
    return LEGACY_HDR_MAPPING_MODE_ALIASES.get(str(mode), "paper")


def hdr_projection_config_from_settings(settings: "HDRExportSettings"):
    from spektrafilm.hdr.projection import HDRProjectionConfig

    if not bool(settings.preserve_sdr_base):
        raise ValueError("RouteMaster HDR export always preserves the authored SDR base; preserve_sdr_base=False is not supported.")
    if str(settings.hdr_scene_source) != "output_layer_metadata":
        raise ValueError("RouteMaster HDR export derives scene authority from the RouteMaster pipeline; unknown HDR scene source.")
    if str(settings.hdr_headroom_mode) != "content_percentile":
        raise ValueError("RouteMaster HDR export currently supports only content_percentile headroom mode.")

    diffuse_anchor = float(settings.hdr_diffuse_white_target)
    return HDRProjectionConfig(
        max_headroom=float(settings.hdr_peak_headroom),
        headroom_percentile=float(settings.headroom_percentile),
        diffuse_white_scene_anchor=diffuse_anchor,
        output_diffuse_white=diffuse_anchor,
        gain_map_mode=settings.gain_map_mode,
    )


@dataclass(slots=True)
class HDRExportSettings:
    """GUI-owned settings for explicit HDR photo export paths."""

    hdr_mapping_mode: str = "paper"
    hdr_heic_gain_map_enabled: bool = False
    hdr_scene_source: str = "output_layer_metadata"
    hdr_diffuse_white_target: float = 1.0
    hdr_peak_headroom: float = 8.0
    hdr_headroom_mode: str = "content_percentile"
    headroom_percentile: float = 99.9
    preserve_sdr_base: bool = True
    gain_map_mode: str = "rgb"
    heic_quality: float = 0.95

    def __post_init__(self) -> None:
        self.hdr_mapping_mode = normalize_hdr_mapping_mode(self.hdr_mapping_mode)
