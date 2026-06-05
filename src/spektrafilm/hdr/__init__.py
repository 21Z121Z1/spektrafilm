"""RouteMaster HDR projection public API."""

from __future__ import annotations

from spektrafilm.hdr.ideal_paper import project_hdr_ideal_paper
from spektrafilm.hdr.light_table import project_hdr_light_table
from spektrafilm.hdr.projection import HDRProjectionConfig, HDRProjectionResult

__all__ = [
    "HDRProjectionConfig",
    "HDRProjectionResult",
    "project_hdr_light_table",
    "project_hdr_ideal_paper",
]
