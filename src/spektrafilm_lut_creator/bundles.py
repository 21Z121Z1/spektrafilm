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


_VALID_TOPOLOGIES = frozenset({
    "1-lut-combined",
    "2-lut-film-print",
    "4-lut-film-develop-print-develop",
})
_VALID_GAMUT_CLIPS = frozenset({"hard", "soft"})
_VALID_CONTAINERS = frozenset({"directory", "zip"})


@dataclass(frozen=True)
class BundleSpec:
    """User-facing description of a LUT bundle to build.

    For M4 only ``topology="1-lut-combined"`` is implemented;
    ``2-lut-film-print`` and ``4-lut-film-develop-print-develop`` raise
    ``NotImplementedError`` in the builder. ``print_profiles`` is a
    tuple of one or more print stocks: for ``1-lut-combined``, each
    ``(film, print)`` combination is baked to its own cube and packed in
    the same bundle.
    """
    name: str
    film_profile: str
    print_profiles: tuple[str, ...]
    input_color_space: str
    output_color_space: str
    topology: str = "1-lut-combined"
    resolution: int = 33
    target: str | None = None
    """Registry name of a :class:`DeliveryTarget`, or ``None`` for the
    generic Adobe ``.cube`` path. When set, the builder also writes a
    target-specific file (e.g., a Lumix-strict ``.cube``) and validates
    the input/output color spaces against the target's allowed set."""
    container: str = "directory"
    """How :class:`BundleBuilder.write` packages the bundle on disk.
    ``"directory"`` writes a normal folder. ``"zip"`` writes the folder
    contents, then archives that folder into a sibling ``.zip`` file and
    returns the archive path."""
    gamut_clip: str = "soft"
    """How the runtime handles negative RGB values that emerge when the
    simulated chromaticity falls outside the output primaries' gamut
    triangle. ``"soft"`` (LUT export default) applies a smooth soft-plus
    that maps negatives to small positives and is near-identity for the
    rest of the cube — better for downstream interpolation. ``"hard"``
    matches the runtime's GUI-default ``np.clip(0, 1)``. The physical
    reflectance bound (``Y <= 1``) is upstream and always satisfied; this
    knob only controls per-channel behavior at the gamut boundary."""

    def __post_init__(self):
        if self.topology not in _VALID_TOPOLOGIES:
            raise ValueError(
                f"topology must be one of {sorted(_VALID_TOPOLOGIES)}, "
                f"got {self.topology!r}"
            )
        if not self.print_profiles:
            raise ValueError("print_profiles must contain at least one entry")
        # For 1-lut-combined topology with multiple print profiles, the
        # builder bakes one (film, print) cube per paper and packs them
        # all into the same bundle. The 2-lut-film-print /
        # 4-lut-film-develop-print-develop topologies will share the
        # film half across papers (see M5+); for 1-lut-combined each
        # combination is independent.
        if self.resolution < 2:
            raise ValueError(f"resolution must be >= 2, got {self.resolution}")
        if self.gamut_clip not in _VALID_GAMUT_CLIPS:
            raise ValueError(
                f"gamut_clip must be one of {sorted(_VALID_GAMUT_CLIPS)}, "
                f"got {self.gamut_clip!r}"
            )
        if self.container not in _VALID_CONTAINERS:
            raise ValueError(
                f"container must be one of {sorted(_VALID_CONTAINERS)}, "
                f"got {self.container!r}"
            )
        if self.target is not None:
            # Deferred to avoid the module-level circular dependency
            # between bundles and delivery_targets (the target registry
            # references format names that bundles also know about).
            from spektrafilm_lut_creator.delivery_targets import get as _get_target
            target = _get_target(self.target)
            if self.input_color_space not in target.valid_inputs:
                raise ValueError(
                    f"target {self.target!r} requires input in "
                    f"{target.valid_inputs}; got {self.input_color_space!r}"
                )
            if self.output_color_space not in target.valid_outputs:
                raise ValueError(
                    f"target {self.target!r} requires output in "
                    f"{target.valid_outputs}; got {self.output_color_space!r}"
                )


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
