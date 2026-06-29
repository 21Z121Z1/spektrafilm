"""RouteMaster HDR projection public API."""

from __future__ import annotations

from spektrafilm.hdr.ideal_paper import project_hdr_ideal_paper
from spektrafilm.hdr.light_table import project_hdr_light_table
from spektrafilm.hdr.projection import HDRDisplayProfile, HDRProjectionConfig, HDRProjectionResult
from spektrafilm.hdr.routemaster_export import render_hdr_film_pair_from_master

__all__ = [
    "HDRProjectionConfig",
    "HDRDisplayProfile",
    "HDRProjectionResult",
    "project_hdr_light_table",
    "project_hdr_ideal_paper",
    "render_hdr_film_pair_from_master",
]
