from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from spektrafilm.runtime.route_master import RouteMaster

if TYPE_CHECKING:
    from spektrafilm.hdr.projection import HDRProjectionConfig


@dataclass(frozen=True, slots=True)
class HDRReferenceWhiteCalibration:
    mode: str
    scene_diffuse_white_y: float
    output_diffuse_white: float
    display_reference_white_nits: float
    max_headroom: float
    headroom_percentile: float
    source: str
    diagnostics: dict[str, object] = field(default_factory=dict)


def resolve_reference_white(
    master: RouteMaster,
    config: "HDRProjectionConfig",
) -> HDRReferenceWhiteCalibration:
    del master
    reference_white_ev = float(config.reference_white_ev)
    ev_scale = 2.0 ** reference_white_ev
    scene_white = float(config.diffuse_white_scene_anchor)
    base_scene_anchor = scene_white / ev_scale
    diagnostics: dict[str, Any] = {
        "mode": str(config.reference_white_mode),
        "scene_diffuse_white_y": scene_white,
        "base_diffuse_white_scene_anchor": float(base_scene_anchor),
        "reference_white_ev": reference_white_ev,
        "output_diffuse_white": float(config.output_diffuse_white),
        "display_reference_white_nits": float(config.display_reference_white_nits),
        "max_headroom": float(config.max_headroom),
        "headroom_percentile": float(config.headroom_percentile),
        "source": "HDRProjectionConfig",
    }
    return HDRReferenceWhiteCalibration(
        mode=str(config.reference_white_mode),
        scene_diffuse_white_y=scene_white,
        output_diffuse_white=float(config.output_diffuse_white),
        display_reference_white_nits=float(config.display_reference_white_nits),
        max_headroom=float(config.max_headroom),
        headroom_percentile=float(config.headroom_percentile),
        source="HDRProjectionConfig",
        diagnostics=diagnostics,
    )


__all__ = ["HDRReferenceWhiteCalibration", "resolve_reference_white"]
