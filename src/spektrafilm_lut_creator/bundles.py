"""Bundle specification and assembled-bundle data.

A :class:`BundleSpec` is the user-facing description of what to build.
A :class:`Bundle` is the built result: one or more LUTs plus the
metadata describing them, ready to be written to disk by
:class:`spektrafilm_lut_creator.builders.BundleBuilder`.

See studies/a40_lut_system/n030_lut_package_design.md §6.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from spektrafilm.utils.gamut_compression import (
    GamutCompressSpec,
    OutputGamutCompressSpec,
)
from spektrafilm_lut_creator.formats import Lut
from spektrafilm_lut_creator.metadata import BundleMeta


_VALID_TOPOLOGIES = frozenset({"1lut", "2lut", "3lut", "4lut"})
_VALID_GAMUT_CLIPS = frozenset({"hard", "soft"})
_VALID_CONTAINERS = frozenset({"directory", "zip"})


@dataclass(frozen=True)
class BundleSpec:
    """User-facing description of a LUT bundle to build.

    All three topologies (``1lut``, ``2lut``, ``4lut``) are implemented.
    The bundle's
    on-disk name defaults to the canonical pattern from
    :func:`spektrafilm_lut_creator.naming.default_bundle_name`
    (``spektrafilm_<version>_<film>[_<paper>]_<topology>_<in>_<out>``)
    when ``name`` is left as the empty string. Pass an explicit
    ``name`` to override.

    ``print_profiles`` is a tuple of one or more print stocks. For
    multi-paper bundles, the auto-name omits the paper segment (the
    bundle covers all of them — naming after one is misleading).
    """
    film_profile: str
    print_profiles: tuple[str, ...]
    input_color_space: str
    output_color_space: str
    name: str = ""
    """Bundle name. Auto-computed via
    :mod:`spektrafilm_lut_creator.naming` when empty."""
    topology: str = "1lut"
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
    qa: bool = False
    """Whether :class:`BundleBuilder.write` should auto-run the QA suite
    after writing the bundle. The reports land at
    ``<bundle>/qa/<per-paper-bundle-name>/`` (one folder per QA'd paper);
    the QA cache is deleted after the run so the bundle directory stays
    ship-ready."""
    qa_paper_index: int | None = None
    """Which paper(s) to QA when :attr:`qa` is True. ``None`` (the
    default) runs QA for every paper in :attr:`print_profiles`; an
    explicit integer runs QA for only that paper. Validated against the
    bundle's paper count up-front so a wrong index fails fast at spec
    construction rather than partway through a long build."""
    input_gamut_compress: GamutCompressSpec = field(default_factory=GamutCompressSpec)
    """Input gamut compression spec (algorithm + Reinhard knee parameters)
    used when baking the per-film tc_lut. Default is the ACES Reference
    Gamut Compression v1.3 cyan threshold and power with the asymptote
    limit reduced to 1.0 so the knee converges exactly at the spectral
    locus boundary (see spektrafilm-research n100 §5). Pass
    ``GamutCompressSpec(mode='off')`` to disable; pass
    ``GamutCompressSpec(algorithm='oklch')`` to use the perceptual-
    chroma-axis variant. The chosen spec is forwarded to
    ``params.io.input_gamut_compress`` so GUI users and bundle bakes
    share the same code path."""
    output_gamut_compress: OutputGamutCompressSpec = field(default_factory=OutputGamutCompressSpec)
    """Output gamut compression spec (ACES Reference Gamut Compression
    v1.3 in destination RGB). Default compresses out-of-output-gamut
    samples — chromaticities the film simulation reaches that fall
    outside ``output_color_space`` — smoothly onto the output primaries
    cube via a per-channel Reinhard knee on the achromatic distance.
    The cinema-industry standard for output gamut mapping (same
    operation as OCIO ``FixedFunctionTransform(style=ACES_GamutComp13)``).
    The existing ``gamut_clip`` knob remains as the final safety net.
    Pass ``OutputGamutCompressSpec(mode='off')`` to disable."""
    ocio_config: bool = False
    """Whether the bundle includes a standalone OCIO 2 config file
    (``config.ocio``) alongside its LUT files. Opt-in: most bundles
    are consumed by grading apps that read the ``.cube`` files
    directly (Resolve, Lumix Lab, FFmpeg), and the OCIO config is only
    useful for OCIO-managed pipelines (Nuke, Maya, Houdini, Blender,
    OCIO-aware Resolve modes). Pass ``True`` to emit the config.
    See studies/a40_lut_system/n120_ocio_config_emission.md."""

    def __post_init__(self):
        if self.topology not in _VALID_TOPOLOGIES:
            raise ValueError(
                f"topology must be one of {sorted(_VALID_TOPOLOGIES)}, "
                f"got {self.topology!r}"
            )
        if not self.print_profiles:
            raise ValueError("print_profiles must contain at least one entry")
        # Auto-compute the canonical bundle name when not explicitly
        # given. Done here (rather than in the builder) so consumers can
        # rely on ``spec.name`` being populated immediately after
        # construction — bundle dirpaths, on-disk filenames, and the
        # report directory all derive from it.
        if not self.name:
            from spektrafilm_lut_creator.naming import default_bundle_name
            object.__setattr__(self, "name", default_bundle_name(
                film_profile=self.film_profile,
                print_profiles=self.print_profiles,
                topology=self.topology,
                input_color_space=self.input_color_space,
                output_color_space=self.output_color_space,
            ))
        # For 1lut topology with multiple print profiles, the builder
        # bakes one (film, print) cube per paper and packs them all
        # into the same bundle. The 2lut / 4lut topologies share the
        # film half across papers; for 1lut each combination is
        # independent.
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
        if self.qa_paper_index is not None:
            n_papers = len(self.print_profiles)
            if not 0 <= self.qa_paper_index < n_papers:
                raise ValueError(
                    f"qa_paper_index={self.qa_paper_index} is out of range for a bundle "
                    f"with {n_papers} paper(s); valid range is [0, {n_papers - 1}] or None"
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
