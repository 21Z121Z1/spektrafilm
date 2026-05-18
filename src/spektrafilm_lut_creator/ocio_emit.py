"""OCIO 2 standalone config emission for spektrafilm LUT bundles.

Emits a ``config.ocio`` sibling to the bundle's ``.cube`` files. The
config makes the bundle's film simulation appear as a named OCIO
colorspace, so OCIO-managed applications (Nuke, Maya, Houdini, Blender,
Krita, OCIO-aware Resolve modes, ...) can pick it up by setting the
``OCIO`` env var to the bundle's ``config.ocio`` path.

Reference space is ACES2065-1 (AP0 / scene-linear), matching the ACES
Studio Config convention. Every emitted colorspace is asymmetric:
``from_scene_reference`` is defined, ``to_scene_reference`` is not.
That means applications can convert *into* the spektrafilm colorspace
(applying the look) but cannot invert it — inverse LUTs are M13 backlog
work.

YAML emission is hand-rolled (string templating) rather than going
through a YAML library. The output structure is tightly constrained
and the OCIO ``!<Tag>`` tag syntax mangles via PyYAML's safe loader
anyway; a hand-rolled emitter keeps the source readable and avoids a
new runtime dependency. PyOpenColorIO is required only at test time to
validate the produced file loads.

M8a scope: ``topology == "1lut"`` only, and only color-space pairs
that have direct OCIO BuiltinTransforms (see ``_INPUT_BUILTIN`` /
``_OUTPUT_BUILTIN``). Multi-LUT topologies and Display+View emission
land in M8b / M8c.

See ``studies/a40_lut_system/n120_ocio_config_emission.md``.
"""
from __future__ import annotations

from spektrafilm_lut_creator.bundles import Bundle, BundleSpec
from spektrafilm_lut_creator.color_spaces import get as get_color_space


OCIO_PROFILE_VERSION = (2, 4)
"""Major.minor of the emitted ``ocio_profile_version``. OCIO 2.4 syntax
covers everything we use; older 2.x runtimes loading the config will
accept it as long as they understand the BuiltinTransforms referenced."""

REFERENCE_COLORSPACE = "ACES2065-1"
"""The config's scene-reference space. Every other colorspace declares
its transform as ``from_scene_reference`` into this space."""


# Maps registry color-space names to a sequence of (builtin_style, direction)
# pairs whose composition produces "from_scene_reference" (AP0 → encoded).
#
# OCIO 2.5's camera-log builtins are documented as <SPACE>_to_ACES2065-1
# (going *out of* the camera space). To go AP0 → camera-encoded we apply
# the same builtin with direction="inverse".
#
# Empty list means the registry name IS the reference (identity).
_INPUT_BUILTIN: dict[str, list[tuple[str, str]]] = {
    "ACES2065-1": [],
    "ACEScg":     [("ACEScg_to_ACES2065-1", "inverse")],
    "Panasonic V-Log":              [("PANASONIC_VLOG-VGAMUT_to_ACES2065-1", "inverse")],
    "Sony S-Log3":                  [("SONY_SLOG3-SGAMUT3_to_ACES2065-1", "inverse")],
    "Sony S-Log3 (S-Gamut3.Cine)":  [("SONY_SLOG3-SGAMUT3.CINE_to_ACES2065-1", "inverse")],
    "ARRI LogC3 (EI800)":           [("ARRI_ALEXA-LOGC-EI800-AWG_to_ACES2065-1", "inverse")],
    "ARRI LogC4":                   [("ARRI_LOGC4_to_ACES2065-1", "inverse")],
    "Apple Log":                    [("APPLE_LOG_to_ACES2065-1", "inverse")],
}

# Display output spaces. Path is AP0 → CIE-XYZ-D65 (via Bradford CAT) →
# display-encoded.
_OUTPUT_BUILTIN: dict[str, list[tuple[str, str]]] = {
    "sRGB": [
        ("UTILITY - ACES-AP0_to_CIE-XYZ-D65_BFD", "forward"),
        ("DISPLAY - CIE-XYZ-D65_to_sRGB",          "forward"),
    ],
    "Display P3": [
        ("UTILITY - ACES-AP0_to_CIE-XYZ-D65_BFD", "forward"),
        ("DISPLAY - CIE-XYZ-D65_to_DisplayP3",     "forward"),
    ],
    "DCI-P3": [
        ("UTILITY - ACES-AP0_to_CIE-XYZ-D65_BFD",   "forward"),
        ("DISPLAY - CIE-XYZ-D65_to_G2.6-P3-DCI-BFD", "forward"),
    ],
}


def is_supported(spec: BundleSpec) -> bool:
    """Cheap predicate for callers that want to decide before emitting.

    Returns True iff M8a can produce a working config for ``spec`` —
    topology is ``"1lut"`` and both input/output spaces appear in
    the BuiltinTransform tables above.
    """
    return (
        spec.topology == "1lut"
        and spec.input_color_space in _INPUT_BUILTIN
        and spec.output_color_space in _OUTPUT_BUILTIN
    )


def unsupported_reason(spec: BundleSpec) -> str:
    """Human-readable explanation of why ``spec`` cannot be emitted.

    Returns the empty string if ``spec`` is supported.
    """
    if spec.topology != "1lut":
        return (
            f"OCIO emission for topology={spec.topology!r} ships in M8b "
            f"(multi-LUT intermediates); only '1lut' is supported in M8a"
        )
    if spec.input_color_space not in _INPUT_BUILTIN:
        return (
            f"input color space {spec.input_color_space!r} has no OCIO "
            f"BuiltinTransform mapping; supported inputs in M8a: "
            f"{sorted(_INPUT_BUILTIN)}"
        )
    if spec.output_color_space not in _OUTPUT_BUILTIN:
        return (
            f"output color space {spec.output_color_space!r} has no OCIO "
            f"BuiltinTransform mapping; supported outputs in M8a: "
            f"{sorted(_OUTPUT_BUILTIN)}"
        )
    return ""


def emit_ocio_config(bundle: Bundle, spec: BundleSpec) -> str:
    """Render the OCIO 2 YAML for a built bundle.

    Returns the YAML text. The caller writes it to
    ``<bundle_dir>/config.ocio``.

    Raises :class:`NotImplementedError` for unsupported topology / color
    space combinations; callers that want to skip silently should check
    :func:`is_supported` first or pass ``BundleSpec.emit_ocio=False``.
    """
    reason = unsupported_reason(spec)
    if reason:
        raise NotImplementedError(reason)

    lines: list[str] = []
    lines.extend(_header_lines(spec))
    lines.extend(_roles_block())
    lines.extend(_displays_block(spec))
    lines.extend(_colorspaces_block(bundle, spec))
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Section emitters.
# ---------------------------------------------------------------------------

def _header_lines(spec: BundleSpec) -> list[str]:
    major, minor = OCIO_PROFILE_VERSION
    papers = ", ".join(spec.print_profiles)
    return [
        f"ocio_profile_version: {major}.{minor}",
        "",
        f"name: {_yaml_str(spec.name)}",
        "description: |",
        f"  Standalone OCIO 2 config for the {spec.name} bundle.",
        f"  Spektrafilm: {spec.film_profile} -> {papers}",
        f"  Input: {spec.input_color_space}  Output: {spec.output_color_space}",
        f"  Reference: {REFERENCE_COLORSPACE} (AP0)",
        "  See n120_ocio_config_emission.md in spektrafilm-research for design notes.",
        "",
        "search_path: .",
        "family_separator: /",
        "",
    ]


def _roles_block() -> list[str]:
    # OCIO 2.2+ requires `compositing_log` and `color_timing` roles. We
    # don't ship a dedicated log working space in M8a, so both point at
    # the scene-reference — functional, if not idiomatic. M8c can refine
    # if a more useful target appears.
    return [
        "roles:",
        f"  aces_interchange: {REFERENCE_COLORSPACE}",
        f"  color_timing: {REFERENCE_COLORSPACE}",
        f"  compositing_log: {REFERENCE_COLORSPACE}",
        f"  default: {REFERENCE_COLORSPACE}",
        f"  scene_linear: {REFERENCE_COLORSPACE}",
        "",
    ]


def _displays_block(spec: BundleSpec) -> list[str]:
    # OCIO 2 requires at least one display for `Config.validate()` to
    # pass. M8a ships a minimal stub: one display named after the bundle's
    # output color space, with a single Raw view that re-uses that
    # colorspace. This gives the user a valid pickable display+view in
    # any viewer without committing to the M8c "look as view" structure
    # (which adds one View per (film, paper) referencing the spektrafilm
    # colorspace).
    out_cs = spec.output_color_space
    return [
        "displays:",
        f"  {_yaml_str(out_cs)}:",
        f"    - !<View> {{name: Raw, colorspace: {_yaml_str(out_cs)}}}",
        "",
        f"active_displays: [{_yaml_str(out_cs)}]",
        "active_views: [Raw]",
        "",
    ]


def _colorspaces_block(bundle: Bundle, spec: BundleSpec) -> list[str]:
    lines = ["colorspaces:"]
    lines.extend(_reference_colorspace_yaml())
    if spec.input_color_space != REFERENCE_COLORSPACE:
        lines.extend(_input_colorspace_yaml(spec))
    if spec.output_color_space != REFERENCE_COLORSPACE:
        lines.extend(_output_colorspace_yaml(spec))
    for paper, lut_relpath in _spektrafilm_papers(bundle):
        lines.extend(_spektrafilm_colorspace_yaml(spec, paper, lut_relpath))
    return lines


def _reference_colorspace_yaml() -> list[str]:
    entry = get_color_space(REFERENCE_COLORSPACE)
    aliases = ["lin_ap0"]
    if entry.ocio_alias and entry.ocio_alias not in aliases:
        aliases.insert(0, entry.ocio_alias)
    return [
        "  - !<ColorSpace>",
        f"    name: {_yaml_str(REFERENCE_COLORSPACE)}",
        f"    aliases: [{', '.join(_yaml_str(a) for a in aliases)}]",
        "    family: ACES",
        "    encoding: scene-linear",
        "    description: |",
        "      The Academy Color Encoding System reference primaries (AP0)",
        "      in scene-linear encoding. The reference space of this config.",
        "    isdata: false",
        "",
    ]


def _input_colorspace_yaml(spec: BundleSpec) -> list[str]:
    entry = get_color_space(spec.input_color_space)
    name = spec.input_color_space
    encoding = _encoding_for_kind(entry.kind)
    builtins = _INPUT_BUILTIN[name]

    lines = [
        "  - !<ColorSpace>",
        f"    name: {_yaml_str(name)}",
    ]
    if entry.ocio_alias:
        lines.append(f"    aliases: [{_yaml_str(entry.ocio_alias)}]")
    lines.extend([
        "    family: Input",
        f"    encoding: {encoding}",
        "    description: |",
        f"      Bundle input color space: {name}.",
        "    isdata: false",
        "    from_scene_reference: !<GroupTransform>",
        "      children:",
    ])
    lines.extend(_builtin_transform_lines(builtins, indent="        "))
    lines.append("")
    return lines


def _output_colorspace_yaml(spec: BundleSpec) -> list[str]:
    entry = get_color_space(spec.output_color_space)
    name = spec.output_color_space
    encoding = _encoding_for_kind(entry.kind)
    builtins = _OUTPUT_BUILTIN[name]

    lines = [
        "  - !<ColorSpace>",
        f"    name: {_yaml_str(name)}",
    ]
    if entry.ocio_alias:
        lines.append(f"    aliases: [{_yaml_str(entry.ocio_alias)}]")
    lines.extend([
        "    family: Output",
        f"    encoding: {encoding}",
        "    description: |",
        f"      Bundle output color space: {name}.",
        "    isdata: false",
        "    from_scene_reference: !<GroupTransform>",
        "      children:",
    ])
    lines.extend(_builtin_transform_lines(builtins, indent="        "))
    lines.append("")
    return lines


def _spektrafilm_papers(bundle: Bundle) -> list[tuple[str, str]]:
    """Pair each combined LUT in a 1-LUT bundle with its paper name.

    Iterates ``bundle.meta.luts`` (the metadata side-car), pulling the
    LUTs whose role is ``"combined"`` — i.e., the per-paper 1-LUT
    cubes. Other roles (film / print halves, L1..L4) belong to
    multi-LUT topologies and aren't relevant to M8a.
    """
    return [
        (lut.paper, lut.path)
        for lut in bundle.meta.luts
        if lut.role == "combined" and lut.paper
    ]


def _spektrafilm_colorspace_yaml(
    spec: BundleSpec, paper: str, lut_relpath: str
) -> list[str]:
    """Emit one spektrafilm colorspace for a (film, paper) pair.

    The colorspace's ``from_scene_reference`` is:
    AP0 -> input-encoded (via the input colorspace's transform chain,
    resolved by OCIO at evaluation time) -> apply the .cube ->
    output-encoded.
    """
    from spektrafilm_lut_creator.naming import normalize_stock

    film_tag = normalize_stock(spec.film_profile)
    paper_tag = normalize_stock(paper)
    cs_name = f"spektrafilm_{film_tag}_{paper_tag}"
    out_entry = get_color_space(spec.output_color_space)
    encoding = _encoding_for_kind(out_entry.kind)

    return [
        "  - !<ColorSpace>",
        f"    name: {_yaml_str(cs_name)}",
        f"    family: spektrafilm/{film_tag}/{paper_tag}",
        f"    encoding: {encoding}",
        "    description: |",
        f"      Spektrafilm film simulation: {spec.film_profile} negative",
        f"      printed on {paper} paper, output as {spec.output_color_space}.",
        "      Asymmetric: from_scene_reference defined,",
        "      to_scene_reference undefined (no inverse LUT in this bundle).",
        "    isdata: false",
        "    from_scene_reference: !<GroupTransform>",
        "      children:",
        f"        - !<ColorSpaceTransform> {{src: {_yaml_str(REFERENCE_COLORSPACE)}, "
        f"dst: {_yaml_str(spec.input_color_space)}}}",
        f"        - !<FileTransform> {{src: {_yaml_str(lut_relpath)}, "
        "interpolation: tetrahedral}",
        "",
    ]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------

def _builtin_transform_lines(
    builtins: list[tuple[str, str]], *, indent: str
) -> list[str]:
    """Emit a list of ``!<BuiltinTransform>`` YAML entries.

    Identity (empty builtins list) falls through to a single
    ``!<MatrixTransform>`` identity so the parent GroupTransform isn't
    childless — OCIO refuses empty children blocks.
    """
    if not builtins:
        return [
            f"{indent}- !<MatrixTransform> "
            "{matrix: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]}"
        ]
    out: list[str] = []
    for style, direction in builtins:
        if direction == "inverse":
            out.append(
                f"{indent}- !<BuiltinTransform> "
                f"{{style: {_yaml_str(style)}, direction: inverse}}"
            )
        else:
            out.append(
                f"{indent}- !<BuiltinTransform> {{style: {_yaml_str(style)}}}"
            )
    return out


def _encoding_for_kind(kind: str) -> str:
    """Map our registry ``kind`` to OCIO 2's ``encoding`` hint.

    OCIO ``data`` is deliberately not produced here — it pairs with
    ``isdata: true`` which makes OCIO bypass colorspace transforms,
    breaking the chain.
    """
    return {
        "linear":      "scene-linear",
        "encoded_sdr": "sdr-video",
        "log":         "log",
    }.get(kind, "scene-linear")


def _yaml_str(value: str) -> str:
    """Quote a string for safe inline YAML emission.

    Always emits a double-quoted scalar with backslashes / quotes
    escaped — robust against names containing spaces, hyphens, parens,
    or the colon that would otherwise terminate a flow-mapping key.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
