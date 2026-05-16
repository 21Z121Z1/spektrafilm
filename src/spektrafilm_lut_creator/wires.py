"""Wire contracts for the 4-LUT chain.

Each non-RGB wire in the chain (log E, normalized density) needs an
explicit shaper that encodes it into the [0,1] range that .cube-class
formats require. The contracts live here; the shaper math lives in
``shapers.py``.

See studies/a40_lut_system/n030_lut_package_design.md §3.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LogEWire:
    """Linear-in-log shaper for log10(E) wires.

    The encoding is ``code = (log_e - min) / (max - min)``; the decode is
    the inverse. Constants are per-bundle and recorded in ``bundle.json``.
    """
    min: float
    max: float


@dataclass(frozen=True)
class DensityWire:
    """Per-channel linear normalization for CMY-density wires.

    The encoding maps ``[d_min, d_max]`` linearly onto ``[0, 1]``
    per channel and clamps:
    ``code_c = clip((D_c - d_min_c) / (d_max_c - d_min_c), 0, 1)``.
    The decode is the inverse (no clamp).

    ``d_max`` and ``d_min`` are per-channel so anisotropic ranges use
    the cube efficiently. ``d_min`` defaults to ``(0, 0, 0)`` — the
    pure-D≥0 case — and is set slightly negative (e.g. ``-0.2``) when
    the wire carries density above-base+fog and a user wants headroom
    for downstream grain models that can dip below zero (grain
    fluctuates *around* the dye density, including in the fog).
    """
    d_max: tuple[float, float, float]
    d_min: tuple[float, float, float] = (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class RgbWire:
    """RGB wire identified by a registry name + CCTF state.

    ``color_space`` is a name resolvable by the
    :mod:`spektrafilm_lut_creator.color_spaces` registry. ``cctf_applied``
    indicates whether the wire carries encoded (CCTF-applied) RGB or
    decoded linear RGB.
    """
    color_space: str
    cctf_applied: bool
