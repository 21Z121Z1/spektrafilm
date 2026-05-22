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


def _coerce_gamut_spec(value, spec_cls):
    """``"off"`` → ``spec_cls(mode='off')``; any other string is treated
    as the ``algorithm`` field, leaving the knee and mode at their
    defaults. The spec dataclass itself validates the algorithm name."""
    if value == "off":
        return spec_cls(mode="off")
    return spec_cls(algorithm=value)


@dataclass(frozen=True)
class BundleSpec:
    """User-facing description of a LUT bundle to build.

    All three topologies (``1lut``, ``2lut``, ``4lut``) are implemented.
    The bundle's
    on-disk name defaults to the canonical pattern from
    :func:`spektrafilm_lut_creator.naming.default_bundle_name`
    (``spektrafilm_<version>_<film>[_<print>]_<topology>_<in>_<out>``)
    when ``name`` is left as the empty string. Pass an explicit
    ``name`` to override.

    ``print_profiles`` is a tuple of one or more print stocks. For
    multi-print bundles, the auto-name omits the print segment (the
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
    ``<bundle>/qa/<per-print-bundle-name>/`` (one folder per QA'd print);
    the QA cache is deleted after the run so the bundle directory stays
    ship-ready."""
    qa_print_index: int | None = None
    """Which print(s) to QA when :attr:`qa` is True. ``None`` (the
    default) runs QA for every print in :attr:`print_profiles`; an
    explicit integer runs QA for only that print. Validated against the
    bundle's print count up-front so a wrong index fails fast at spec
    construction rather than partway through a long build."""
    input_gamut_compress: GamutCompressSpec = field(default_factory=GamutCompressSpec)
    """Input gamut compression spec (algorithm + Reinhard knee parameters)
    used when baking the per-film tc_lut. Default is the ACES Reference
    Gamut Compression v1.3 cyan threshold and power with the asymptote
    limit reduced to 1.0 so the knee converges exactly at the spectral
    locus boundary (see spektrafilm-research n100 §5). A bare string is
    accepted in place of the full dataclass:
    ``input_gamut_compress="xy"`` / ``"oklch"`` constructs the spec
    with default knee parameters; ``"off"`` disables compression. Pass
    a :class:`GamutCompressSpec` directly for custom knee tuning. The
    chosen spec is forwarded to ``params.io.input_gamut_compress`` so
    GUI users and bundle bakes share the same code path."""
    stops_above_gray: float | None = None
    """How many stops above middle gray (0.18 linear) the source's
    encoded 1.0 should correspond to in the film's frame.

    Implemented as a plain linear gain — no log shaping. The bake
    computes the input's native white-to-mid-gray ratio (from
    :func:`decode_cctf`), then scales the linear values so source
    encoded 1.0 lands at ``0.18 × 2 ** stops_above_gray`` in the
    film's frame. Mid-gray drifts as a side effect of the single
    gain (this is the simple-multiplication trade-off; recovering
    fixed mid-gray *and* configurable headroom would require log
    shaping, which this design deliberately rules out).

    ``None`` (the default) leaves the input untouched — the film
    sees the source's native dynamic range. For sRGB / Rec.2020 /
    Rec.709 (BT.1886 / sRGB CCTF) the native is ≈2.47 stops above
    mid-gray. For log inputs (V-Log, S-Log3, ACEScct) the native
    is ≈7–8 stops.

    Set to a number to override. Examples:

    - ``2.47`` on sRGB input ≈ identity (matches native).
    - ``6.0`` on sRGB input → gain ≈ 11.5 → film sees source white
      at +6 stops above 0.18; the rest of the source slides up the
      exposure axis with it, so mid-gray ends up at +3.5 stops in
      the film's frame and the film walks well into its shoulder.
    - ``6.0`` on V-Log input → gain ≈ 0.25 → V-Log gets attenuated
      so its native ≈8-stop white sits at +6 stops above 0.18.

    With ``stops_above_gray`` set the LUT is no longer a strict
    colorimetric round-trip; the bundle README discloses the
    effective gain."""
    output_gamut_compress: OutputGamutCompressSpec = field(default_factory=OutputGamutCompressSpec)
    """Output gamut compression spec. Default ``oklch`` algorithm with
    the ACES RGC cyan threshold and power, limit reduced to 1.0 so the
    knee asymptotes at the output cube edge (no hard clip needed). For
    convenience, a bare string is accepted in place of the full
    dataclass: ``output_gamut_compress="oklch"`` (or ``"jzazbz"``,
    ``"aces_rgc"``) constructs the spec with default knee parameters;
    ``"off"`` disables compression. Pass an
    :class:`OutputGamutCompressSpec` directly for custom knee tuning."""
    ocio_config: bool = False
    """Whether the bundle includes a standalone OCIO 2 config file
    (``config.ocio``) alongside its LUT files. Opt-in: most bundles
    are consumed by grading apps that read the ``.cube`` files
    directly (Resolve, Lumix Lab, FFmpeg), and the OCIO config is only
    useful for OCIO-managed pipelines (Nuke, Maya, Houdini, Blender,
    OCIO-aware Resolve modes). Pass ``True`` to emit the config.
    See studies/a40_lut_system/n120_ocio_config_emission.md."""
    include_combinations: bool = False
    """Whether the bundle also ships every contiguous sub-chain of the
    canonical LUTs as pre-collapsed single cubes in a ``combinations/``
    subfolder. For a 4-LUT bundle that's 6 extra cubes per print
    (``l12``, ``l23``, ``l34``, ``l123``, ``l234``, ``l1234``); for
    3-LUT 3 extras; for 2-LUT 1 extra (``l12``); for 1-LUT a no-op.
    Combinations let single-LUT-slot grading apps (Resolve LUT slot,
    Lumix Lab, OBS, FFmpeg, Premiere) apply any sub-chain of the
    canonical chain as one cube — handy when the canonical 4-cube
    chain is impractical. The OCIO config (when ``ocio_config=True``)
    does *not* reference these cubes: it chains the canonical L1..LN
    directly. See studies/a40_lut_system/n130_sub_chain_combinations.md."""

    def __post_init__(self):
        # String shorthand for the gamut-compression specs:
        # ``"off"`` → mode='off', anything else is treated as an
        # algorithm name and constructs the spec with default knee.
        if isinstance(self.input_gamut_compress, str):
            object.__setattr__(
                self, "input_gamut_compress",
                _coerce_gamut_spec(self.input_gamut_compress, GamutCompressSpec),
            )
        if isinstance(self.output_gamut_compress, str):
            object.__setattr__(
                self, "output_gamut_compress",
                _coerce_gamut_spec(self.output_gamut_compress, OutputGamutCompressSpec),
            )
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
        # bakes one (film, print) cube per print and packs them all
        # into the same bundle. The 2lut / 4lut topologies share the
        # film half across prints; for 1lut each combination is
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
        if self.qa_print_index is not None:
            n_prints = len(self.print_profiles)
            if not 0 <= self.qa_print_index < n_prints:
                raise ValueError(
                    f"qa_print_index={self.qa_print_index} is out of range for a bundle "
                    f"with {n_prints} print(s); valid range is [0, {n_prints - 1}] or None"
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
