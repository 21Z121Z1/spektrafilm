"""Bundle specification and assembled-bundle data.

A :class:`BundleSpec` is the user-facing description of what to build.
A :class:`Bundle` is the built result: one or more LUTs plus the
metadata describing them, ready to be written to disk by
:class:`spektrafilm_lut_creator.builders.BundleBuilder`.

See studies/a40_lut_system/n030_lut_package_design.md §6.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from spektrafilm_lut_creator.formats import Lut
from spektrafilm_lut_creator.metadata import BundleMeta


_VALID_TOPOLOGIES = frozenset({"1-lut", "2-lut", "4-lut"})


@dataclass(frozen=True)
class BundleSpec:
    """User-facing description of a LUT bundle to build.

    For M4 only ``topology="1-lut"`` is implemented; 2-lut and 4-lut
    raise ``NotImplementedError`` in the builder. ``print_profiles`` is
    a tuple even for 1-lut (always length 1) so the field shape
    survives the eventual expansion to multi-paper bundles.
    """
    name: str
    film_profile: str
    print_profiles: tuple[str, ...]
    input_color_space: str
    output_color_space: str
    topology: str = "1-lut"
    resolution: int = 33

    def __post_init__(self):
        if self.topology not in _VALID_TOPOLOGIES:
            raise ValueError(
                f"topology must be one of {sorted(_VALID_TOPOLOGIES)}, "
                f"got {self.topology!r}"
            )
        if not self.print_profiles:
            raise ValueError("print_profiles must contain at least one entry")
        if self.topology == "1-lut" and len(self.print_profiles) != 1:
            raise ValueError(
                f"1-lut topology requires exactly one print profile, "
                f"got {len(self.print_profiles)}"
            )
        if self.resolution < 2:
            raise ValueError(f"resolution must be >= 2, got {self.resolution}")


@dataclass
class Bundle:
    """A built bundle ready to write to disk.

    ``luts`` is a list of ``(relative_path, Lut)`` pairs; the path is
    relative to the bundle's root directory and is the on-disk location
    of the LUT file when written. ``meta`` is the typed metadata payload
    that becomes ``bundle.json`` on disk.
    """
    luts: list[tuple[str, Lut]] = field(default_factory=list)
    meta: BundleMeta = field(default_factory=BundleMeta)
