"""Filename + bundle-name normalization helpers.

Centralized so :class:`spektrafilm_lut_creator.bundles.BundleSpec` can
auto-compute a canonical default ``name`` in its ``__post_init__``
without importing ``builders`` (which would create a cycle —
``builders`` already imports ``bundles``).

The canonical bundle name shape is::

    spektrafilm_<version>_<film>[_<paper>]_<topology>_<input>_<output>

For single-paper bundles ``<paper>`` is the normalized paper stock
tag. For multi-paper bundles it becomes ``<N>paperpack`` (e.g.
``3paperpack``) — the count communicates the pack's scope without
falsely naming after one paper. Every tag is normalized:

- ``<version>``: ``0.3.2`` → ``v032``
- ``<film>`` / ``<paper>``: brand prefix stripped, first two
  underscore-separated tokens fused (``kodak_portra_400`` →
  ``portra400``; ``fujifilm_crystal_archive_typeii`` →
  ``crystalarchive``)
- ``<topology>``: passes through (``1lut`` / ``2lut`` / ``4lut``)
- ``<input>`` / ``<output>``: the color-space registry's ``short_tag``
  (``Panasonic V-Log`` → ``vlog``; ``Rec.2020`` → ``rec2020``)
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as distribution_version


# Brand prefixes stripped from profile stock names when building canonical
# camera-safe filename tags. Order matters when prefixes share a stem
# (none here yet). Extend as new vendors arrive.
_BRAND_PREFIXES: tuple[str, ...] = (
    "kodak", "fujifilm", "fuji", "ilford", "agfa",
    "cinestill", "polaroid", "ferrania", "lomography",
)

_TOPOLOGY_TAGS: dict[str, str] = {
    "1lut": "1lut",
    "2lut": "2lut",
    "3lut": "3lut",
    "4lut": "4lut",
}


def normalize_stock(stock: str) -> str:
    """``kodak_portra_400`` → ``portra400``; ``fujifilm_c200`` → ``c200``;
    ``fujifilm_crystal_archive_typeii`` → ``crystalarchive``.

    Strips the brand prefix (if recognized) and fuses the first two
    remaining underscore-separated segments without delimiter.
    """
    parts = stock.lower().split("_")
    if parts and parts[0] in _BRAND_PREFIXES:
        parts = parts[1:]
    return "".join(parts[:2])


def normalize_version(version: str) -> str:
    """``0.3.2`` → ``v032``; ``0.4.1.dev0+abc`` → ``v041``.

    Strips PEP 440 dev / local-version suffixes, drops dots, prepends ``v``.
    """
    base = version.split("+", 1)[0].split(".dev", 1)[0]
    digit_groups = [g for g in base.split(".") if g.isdigit()]
    return "v" + "".join(digit_groups)


def topology_tag(topology: str) -> str:
    """Short topology identifier for filenames/bundle names.

    Today this is an identity for the canonical short forms (``1lut`` /
    ``2lut`` / ``4lut``). Kept as a thin indirection so future variants
    (e.g. ``4lut-special_label``) can collapse to a family tag here
    without touching call sites.
    """
    return _TOPOLOGY_TAGS.get(topology, topology)


def spektrafilm_version() -> str:
    """The installed ``spektrafilm`` distribution version, or
    ``"0+unknown"`` when the package isn't installed (rare — usually
    only happens during a from-source dev install with editable mode
    misconfigured)."""
    try:
        return distribution_version("spektrafilm")
    except PackageNotFoundError:
        return "0+unknown"


def default_bundle_name(
    film_profile: str,
    print_profiles: tuple[str, ...],
    topology: str,
    input_color_space: str,
    output_color_space: str,
) -> str:
    """Compute the canonical default bundle name from a spec's components.

    The paper slot carries the normalized paper tag for single-paper
    bundles and ``<N>paperpack`` (e.g. ``3paperpack``) for multi-paper
    bundles — keeps the count discoverable from the filename without
    misleadingly naming the pack after one of its papers.
    """
    # Lazy import to avoid a cycle with the registry (color_spaces
    # imports nothing from this package's core layout but its registry
    # is populated at module-load time so the import is light).
    from spektrafilm_lut_creator.color_spaces import short_tag as _cs_short_tag

    v_tag = normalize_version(spektrafilm_version())
    film_tag = normalize_stock(film_profile)
    topo_tag = topology_tag(topology)
    in_tag = _cs_short_tag(input_color_space)
    out_tag = _cs_short_tag(output_color_space)

    parts = ["spektrafilm", v_tag, film_tag]
    if len(print_profiles) == 1:
        parts.append(normalize_stock(print_profiles[0]))
    else:
        parts.append(f"{len(print_profiles)}paperpack")
    parts.extend([topo_tag, in_tag, out_tag])
    return "_".join(parts)


def per_paper_qa_folder_name(
    film_profile: str,
    print_profile: str,
    input_color_space: str,
    output_color_space: str,
) -> str:
    """Folder name for one paper's QA report inside ``<bundle>/qa/``.

    Shape: ``<film>_<paper>_<input>_<output>`` (e.g.
    ``portra160_portraendura_vlog_srgb``). Deliberately short —
    the parent bundle directory already carries the spektrafilm
    version + topology, so the QA folder only disambiguates by the
    fields that change *within* a bundle (the paper) and the
    color-space pair that frames the test.
    """
    from spektrafilm_lut_creator.color_spaces import short_tag as _cs_short_tag

    film_tag = normalize_stock(film_profile)
    paper_tag = normalize_stock(print_profile)
    in_tag = _cs_short_tag(input_color_space)
    out_tag = _cs_short_tag(output_color_space)
    return f"{film_tag}_{paper_tag}_{in_tag}_{out_tag}"
