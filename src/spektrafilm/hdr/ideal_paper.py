from __future__ import annotations

import numpy as np

from spektrafilm.hdr.projection import (
    HDRProjectionConfig,
    HDRProjectionResult,
    _build_result,
    _scene_authority,
    build_hdr_y_from_route,
)
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils.hdr_curve_profiles import luminance_y


def project_hdr_ideal_paper(
    master: RouteMaster,
    config: HDRProjectionConfig | None = None,
) -> HDRProjectionResult:
    """Project a print-scan RouteMaster to Idealized HDR Paper output.

    This is a counterfactual digital medium. Below paper white it preserves
    the legacy photographic print projection; above paper white it extends
    highlights from scene/material energy into display headroom.
    """

    config = HDRProjectionConfig() if config is None else config
    if master.route_kind != "print_scan":
        raise ValueError("Idealized HDR Paper requires a print_scan RouteMaster.")

    sdr_y = luminance_y(np.asarray(master.sdr_legacy_rgb, dtype=np.float32))
    scene_y = _scene_authority(master, sdr_y.shape)
    hdr_y = build_hdr_y_from_route(
        master,
        config,
        authority_y=scene_y,
        white=1.0,
        strength=config.paper_extension_strength,
    )
    hdr_y = np.where(scene_y <= np.float32(1.0), sdr_y, hdr_y)
    hdr_y = hdr_y.astype(np.float32, copy=False)
    return _build_result(
        master=master,
        mode="paper",
        hdr_y=hdr_y,
        config=config,
        path_to_white_strength=config.paper_path_to_white_strength,
        diagnostics={
            "hdr_mode": "paper",
            "authority_y": "scene_y_raw",
            "paper_below_white": "legacy_sdr_print_look",
            "paper_medium": "counterfactual_digital",
        },
    )


__all__ = ["project_hdr_ideal_paper"]
