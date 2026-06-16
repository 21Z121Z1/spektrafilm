from __future__ import annotations

from spektrafilm.hdr.projection import (
    HDRProjectionConfig,
    HDRProjectionResult,
    _build_result,
    _spatial_authority,
    build_hdr_y_from_route,
)
from spektrafilm.runtime.route_master import RouteMaster


def project_hdr_light_table(
    master: RouteMaster,
    config: HDRProjectionConfig | None = None,
) -> HDRProjectionResult:
    """Project a film-scan RouteMaster to HDR Light Table output.

    The projection uses the positive film/scan route look as its colour
    authority and scene/post-halation luminance only as HDR energy authority.
    It deliberately ignores paper and print controls because those are not
    part of the light-table route.
    """

    config = HDRProjectionConfig() if config is None else config
    if master.route_kind != "film_scan":
        raise ValueError("HDR Light Table requires a film_scan RouteMaster.")
    if master.diagnostics.get("profile_kind") == "raw_negative_scan":
        raise ValueError("HDR Light Table requires positive rendering, not a raw negative scan.")

    shape = master.sdr_legacy_rgb.shape[:2]
    authority_y = _spatial_authority(master, shape)
    hdr_y = build_hdr_y_from_route(
        master,
        config,
        authority_y=authority_y,
        white=float(config.diffuse_white_scene_anchor),
        strength=config.light_table_extension_strength,
    )
    return _build_result(
        master=master,
        mode="light_table",
        hdr_y=hdr_y,
        config=config,
        path_to_white_strength=config.light_table_path_to_white_strength,
        diagnostics={
            "hdr_mode": "light_table",
            "authority_y": "post_halation_y",
            "paper_parameters_ignored": True,
        },
    )


__all__ = ["project_hdr_light_table"]
