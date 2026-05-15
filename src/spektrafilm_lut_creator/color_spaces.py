"""Curated color-space registry for the LUT exporter.

This registry is the single source of truth for color-space names
accepted anywhere in :mod:`spektrafilm_lut_creator`. Every entry is
gatekept: only names registered here are valid. Adding a space is a
one-line :func:`register` call.

Backend is `colour-science`. The :func:`to_xyz` / :func:`from_xyz` /
:func:`decode_cctf` / :func:`encode_cctf` helpers wrap the backend so
callers never need to import it directly.

See studies/a40_lut_system/n040_color_space_registry.md.
"""
from __future__ import annotations

from dataclasses import dataclass

import colour
import numpy as np


VERSION = "0.1.0"

# Allowed kinds: linear (scene-referred), encoded_sdr (gamma/CCTF), log (camera log).
_ALLOWED_KINDS = frozenset({"linear", "encoded_sdr", "log"})
_ALLOWED_ROLES = frozenset({"input", "output"})


@dataclass(frozen=True)
class ColorSpaceEntry:
    """One curated entry in the color-space registry.

    ``primaries`` is the ``colour.RGB_COLOURSPACES`` key supplying the
    RGB gamut + white point. ``cctf`` is the ``colour.CCTF_ENCODINGS``
    key supplying the curve, or ``None`` for scene-linear spaces. ``kind``
    is the grid-sampling distribution category (see n040 §5). ``role``
    declares which sides of the bundle this space may appear on.
    """
    name: str
    primaries: str
    cctf: str | None
    kind: str
    role: tuple[str, ...]
    notes: str = ""


_REGISTRY: dict[str, ColorSpaceEntry] = {}


def register(entry: ColorSpaceEntry) -> None:
    """Validate and add ``entry`` to the registry."""
    if entry.kind not in _ALLOWED_KINDS:
        raise ValueError(
            f"{entry.name!r}: kind must be one of {sorted(_ALLOWED_KINDS)}, "
            f"got {entry.kind!r}"
        )
    for role in entry.role:
        if role not in _ALLOWED_ROLES:
            raise ValueError(
                f"{entry.name!r}: role entries must be in {sorted(_ALLOWED_ROLES)}, "
                f"got {role!r}"
            )
    if entry.primaries not in colour.RGB_COLOURSPACES:
        raise KeyError(
            f"{entry.name!r}: primaries {entry.primaries!r} not in colour.RGB_COLOURSPACES"
        )
    if entry.cctf is not None and entry.cctf not in colour.CCTF_ENCODINGS:
        raise KeyError(
            f"{entry.name!r}: cctf {entry.cctf!r} not in colour.CCTF_ENCODINGS"
        )
    if entry.kind == "linear" and entry.cctf is not None:
        raise ValueError(f"{entry.name!r}: linear spaces must have cctf=None")
    if entry.kind != "linear" and entry.cctf is None:
        raise ValueError(f"{entry.name!r}: kind={entry.kind!r} requires a cctf")
    _REGISTRY[entry.name] = entry


def get(name: str) -> ColorSpaceEntry:
    """Return the registered entry for ``name`` or raise ``KeyError``."""
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown color space {name!r}; registered: {sorted(_REGISTRY)}"
        ) from None


def list_input_spaces() -> list[str]:
    """Names of spaces eligible as bundle input."""
    return sorted(name for name, entry in _REGISTRY.items() if "input" in entry.role)


def list_output_spaces() -> list[str]:
    """Names of spaces eligible as bundle output."""
    return sorted(name for name, entry in _REGISTRY.items() if "output" in entry.role)


def decode_cctf(rgb, name: str) -> np.ndarray:
    """Apply the inverse CCTF, producing linear-light RGB.

    For ``kind='linear'`` spaces this is a no-op (input returned as
    float ndarray).
    """
    entry = get(name)
    rgb = np.asarray(rgb, dtype=float)
    if entry.cctf is None:
        return rgb
    return np.asarray(colour.cctf_decoding(rgb, function=entry.cctf), dtype=float)


def encode_cctf(rgb, name: str) -> np.ndarray:
    """Apply the forward CCTF to linear-light RGB."""
    entry = get(name)
    rgb = np.asarray(rgb, dtype=float)
    if entry.cctf is None:
        return rgb
    return np.asarray(colour.cctf_encoding(rgb, function=entry.cctf), dtype=float)


def to_xyz(rgb, name: str) -> np.ndarray:
    """Convert RGB (in the named space, encoded as the space requires)
    to CIE XYZ tristimulus values."""
    entry = get(name)
    linear = decode_cctf(rgb, name)
    return np.asarray(
        colour.RGB_to_XYZ(linear, colourspace=entry.primaries, apply_cctf_decoding=False),
        dtype=float,
    )


def from_xyz(xyz, name: str) -> np.ndarray:
    """Convert CIE XYZ to RGB in the named space (encoded as the space requires)."""
    entry = get(name)
    linear = np.asarray(
        colour.XYZ_to_RGB(np.asarray(xyz, dtype=float),
                          colourspace=entry.primaries,
                          apply_cctf_encoding=False),
        dtype=float,
    )
    return encode_cctf(linear, name)


# ---------------------------------------------------------------------------
# v1 entries.
#
# Skipped from v1 (documented for future addition):
#   - Nikon N-Log: colour-science ships the curve but not a Nikon gamut.
#     Will be added once a Nikon RGB colourspace is in upstream or modeled
#     manually here.
# ---------------------------------------------------------------------------

# Scene-linear (input only).
register(ColorSpaceEntry("ACES2065-1",       "ACES2065-1",   None, "linear", ("input",),
                         notes="ACES interchange (AP0 primaries)."))
register(ColorSpaceEntry("ACEScg",           "ACEScg",       None, "linear", ("input",),
                         notes="AP1 primaries; VFX rendering workhorse."))
register(ColorSpaceEntry("Rec.709 Linear",   "ITU-R BT.709", None, "linear", ("input",)))
register(ColorSpaceEntry("Rec.2020 Linear",  "ITU-R BT.2020", None, "linear", ("input",)))
register(ColorSpaceEntry("ProPhoto Linear",  "ProPhoto RGB", None, "linear", ("input",),
                         notes="Current spektrafilm default."))
register(ColorSpaceEntry("sRGB Linear",      "sRGB",         None, "linear", ("input",),
                         notes="Same primaries as sRGB, no CCTF."))

# Encoded SDR (input and output).
register(ColorSpaceEntry("sRGB",        "sRGB",         "sRGB",          "encoded_sdr", ("input", "output"),
                         notes="The web default."))
register(ColorSpaceEntry("Rec.709",     "ITU-R BT.709", "ITU-R BT.1886", "encoded_sdr", ("input", "output"),
                         notes="Broadcast; BT.1886 EOTF."))
register(ColorSpaceEntry("Display P3",  "Display P3",   "sRGB",          "encoded_sdr", ("input", "output"),
                         notes="Apple devices."))
register(ColorSpaceEntry("Rec.2020",    "ITU-R BT.2020", "ITU-R BT.1886","encoded_sdr", ("input", "output"),
                         notes="Wide-gamut SDR."))
register(ColorSpaceEntry("DCI-P3",      "DCI-P3",       "Gamma 2.6",     "encoded_sdr", ("input", "output"),
                         notes="Theatrical (xenon white ~6300K, gamma 2.6)."))
register(ColorSpaceEntry("Adobe RGB",   "Adobe RGB (1998)", "Gamma 2.2", "encoded_sdr", ("input", "output"),
                         notes="Standard inkjet/lab print delivery. Adobe's spec uses gamma 2.19921875; we approximate as 2.2 (error ~1e-4, below LUT precision)."))

# Camera log (input only).
register(ColorSpaceEntry("ACEScct",                  "ACEScct",            "ACEScct",
                         "log", ("input",)))
register(ColorSpaceEntry("ARRI LogC3 (EI800)",       "ARRI Wide Gamut 3",  "ARRI LogC3",
                         "log", ("input",),
                         notes="EI800 is colour-science's default LogC3 curve."))
register(ColorSpaceEntry("ARRI LogC4",               "ARRI Wide Gamut 4",  "ARRI LogC4",
                         "log", ("input",)))
register(ColorSpaceEntry("Sony S-Log3",              "S-Gamut3",           "S-Log3",
                         "log", ("input",)))
register(ColorSpaceEntry("Sony S-Log3 (S-Gamut3.Cine)", "S-Gamut3.Cine",   "S-Log3",
                         "log", ("input",)))
register(ColorSpaceEntry("Panasonic V-Log",          "V-Gamut",            "V-Log",
                         "log", ("input",)))
register(ColorSpaceEntry("Fujifilm F-Log",           "F-Gamut",            "F-Log",
                         "log", ("input",)))
register(ColorSpaceEntry("Fujifilm F-Log2",          "F-Gamut",            "F-Log2",
                         "log", ("input",)))
register(ColorSpaceEntry("Canon Log 3",              "Cinema Gamut",       "Canon Log 3",
                         "log", ("input",)))
register(ColorSpaceEntry("RED Log3G10",              "REDWideGamutRGB",    "Log3G10",
                         "log", ("input",)))
register(ColorSpaceEntry("DaVinci Intermediate",     "DaVinci Wide Gamut", "DaVinci Intermediate",
                         "log", ("input",)))
register(ColorSpaceEntry("Apple Log",                "ITU-R BT.2020",      "Apple Log Profile",
                         "log", ("input",),
                         notes="iPhone 15+ Pro, iPhone 17 Pro, Vision Pro Immersive. Apple Log pairs with BT.2020 primaries per Apple's spec."))
register(ColorSpaceEntry("Blackmagic Film Gen 5",    "Blackmagic Wide Gamut", "Blackmagic Film Generation 5",
                         "log", ("input",),
                         notes="Resolve-native. All current Blackmagic bodies (Pocket 4K/6K, URSA, Cine 12K, Pyxis)."))

# HDR — Rec.2100 family. Both PQ and HLG are valid in both input and output roles:
#  - Input: source camera HDR (e.g., a PQ-graded delivery being processed through spektrafilm)
#  - Output: final master deliverable (streaming HDR master = PQ; broadcast HDR = HLG)
# See studies/a40_lut_system/n060_color_space_v2_research.md for film-LUT-in-HDR gotchas
# (peak-nit assumption, never apply Rec.709 LUTs to PQ signal, etc.).
register(ColorSpaceEntry("Rec.2100 PQ", "ITU-R BT.2020", "ITU-R BT.2100 PQ", "log", ("input", "output"),
                         notes="HDR streaming master (Netflix/Apple TV+/Disney+/Amazon/Max). ST.2084 transfer. Domain [0,1] = 0..10,000 nits; document per-LUT peak-luminance assumption."))
register(ColorSpaceEntry("Rec.2100 HLG", "ITU-R BT.2020", "ITU-R BT.2100 HLG", "log", ("input", "output"),
                         notes="HDR broadcast (BBC/NHK/EBU live, YouTube HDR). HLG bakes OOTF + nominal peak luminance; not portable across display peaks the way PQ is."))
