from __future__ import annotations

from spektrafilm.hdr.projection import (
    HDRProjectionConfig,
    HDRProjectionResult,
    _backend_projection_profile,
    _build_hdr_y_from_route_backend,
    _build_hdr_y_from_route_numpy,
    _build_result,
    _is_mlx_array,
    _sdr_rgb_backend,
    _spatial_authority_for_projection,
)
from spektrafilm.hdr.reference_white import resolve_reference_white
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
    calibration = resolve_reference_white(master, config)

    with _backend_projection_profile():
        shape = master.sdr_legacy_rgb.shape[:2]
        authority_y = _spatial_authority_for_projection(master, shape)
        white = float(calibration.scene_diffuse_white_y)
        strength = config.light_table_extension_strength
        # Validate/decode the SDR base once and share it between the HDR-Y
        # builder and _build_result instead of recomputing it in each stage.
        sdr = None
        hdr_y = None
        if _is_mlx_array(authority_y):
            sdr = _sdr_rgb_backend(master)
            if sdr is not None:
                hdr_y = _build_hdr_y_from_route_backend(
                    master,
                    config,
                    authority_y=authority_y,
                    white=white,
                    strength=strength,
                    sdr=sdr,
                    authority_prevalidated=True,
                )
        if hdr_y is None:
            hdr_y, sdr = _build_hdr_y_from_route_numpy(
                master,
                config,
                authority_y=authority_y,
                white=white,
                strength=strength,
            )
        return _build_result(
            master=master,
            mode="light_table",
            hdr_y=hdr_y,
            config=config,
            calibration=calibration,
            path_to_white_strength=config.light_table_path_to_white_strength,
            diagnostics={
                "hdr_mode": "light_table",
                "authority_y": "post_halation_y",
                "paper_parameters_ignored": True,
            },
            sdr=sdr,
            scene_y=authority_y,
        )


__all__ = ["project_hdr_light_table"]
