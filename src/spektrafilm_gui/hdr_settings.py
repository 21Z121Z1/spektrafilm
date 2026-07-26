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

    return HDRProjectionConfig(
        max_headroom=float(settings.hdr_peak_headroom),
        headroom_percentile=float(settings.headroom_percentile),
        reference_white_ev=float(settings.hdr_reference_white_ev),
        gain_map_mode=settings.gain_map_mode,
    )


@dataclass(slots=True)
class HDRExportSettings:
    """GUI-owned settings for explicit HDR photo export paths.

    Only the degrees of freedom the RouteMaster projection actually has
    are exposed. The rest of the contract is fixed: the authored SDR
    look is always the preserved base rendition, scene authority comes
    from the film pipeline, the diffuse-white anchor sits at scene 1.0
    (trimmed by ``hdr_reference_white_ev``), and the HDR delta above the
    SDR base is encoded 1:1 (no output diffuse-white rescaling).
    """

    hdr_mapping_mode: str = "paper"
    hdr_heic_gain_map_enabled: bool = False
    hdr_reference_white_ev: float = 0.0
    hdr_peak_headroom: float = 8.0
    headroom_percentile: float = 99.9
    gain_map_mode: str = "rgb"
    heic_quality: float = 0.95

    def __post_init__(self) -> None:
        self.hdr_mapping_mode = normalize_hdr_mapping_mode(self.hdr_mapping_mode)
