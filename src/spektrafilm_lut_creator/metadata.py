"""Bundle metadata (``bundle.json``) schema.

This module defines the typed shape of a bundle's metadata side-car.
I/O (serialization to/from JSON) lands with the builder in M4; the
dataclasses are here so other modules can reference them and tests can
assert on shape.

See studies/a40_lut_system/n030_lut_package_design.md §4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from spektrafilm_lut_creator.wires import DensityWire, LogEWire


SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ColorSpaceMeta:
    """One end of the bundle's color-space contract."""
    name: str
    cctf: bool  # True if the wire carries an encoded (CCTF-applied) signal


@dataclass(frozen=True)
class StocksMeta:
    """Stock identifiers used to build the bundle."""
    film: str
    prints: tuple[str, ...]  # one entry for 1-lut, ≥1 for 2-lut/4-lut


@dataclass(frozen=True)
class WiresMeta:
    """Per-bundle wire constants for the four internal taps.

    Entries can be ``None`` for topologies that don't expose the
    corresponding tap (e.g. 1-lut bundles need none of these because the
    intermediate taps aren't materialized as separate LUTs).
    """
    log_e_film: LogEWire | None = None
    cmy_film: DensityWire | None = None
    log_e_print: LogEWire | None = None
    cmy_print: DensityWire | None = None


@dataclass(frozen=True)
class LutFileMeta:
    """One LUT entry within a bundle."""
    role: str            # "combined" (1-lut) | "film" | "print"
    path: str            # relative to the bundle root
    domain: str          # source tap name (e.g. "input_rgb", "cmy_film")
    range: str           # destination tap name (e.g. "cmy_film", "output_rgb")
    paper: str | None = None  # set for role="print"


@dataclass
class BundleMeta:
    """The full ``bundle.json`` payload."""
    schema_version: int = SCHEMA_VERSION
    name: str = ""
    topology: str = "1-lut"  # "1-lut" | "2-lut" | "4-lut"
    spektrafilm_version: str = ""
    spektrafilm_lut_creator_version: str = ""
    build_timestamp: str = ""
    resolution: int = 33
    stocks: StocksMeta | None = None
    color_spaces: dict[str, ColorSpaceMeta] = field(default_factory=dict)  # "input", "output"
    wires: WiresMeta = field(default_factory=WiresMeta)
    luts: tuple[LutFileMeta, ...] = ()
    params_snapshot: dict[str, Any] = field(default_factory=dict)
