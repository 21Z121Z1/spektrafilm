"""Input gamut compression for the Hanatos 2025 spectral upsampling step.

Wide-gamut input color spaces (V-Gamut, ACEScg, AP0, …) can encode
chromaticities outside the visible spectral locus — combinations of
camera primaries that do not correspond to any physically realizable
spectrum. The Hanatos 2025 spectral upsampling is only well-defined
inside the locus; chromaticities outside it produce extrapolation noise.

This module provides:

- :class:`GamutCompressSpec` — the per-bundle configuration object that
  selects the algorithm and parameters.
- :func:`compress_xy` — the algorithm dispatcher; takes CIE xy values
  and returns compressed CIE xy values.
- :func:`remap_tc_lut_for_compression` — bakes the compression into a
  ``compute_hanatos2025_tc_lut``-produced LUT via remap-resample, so the
  runtime lookup path does not need to know about the compression.

The default settings (``algorithm="xy"`` with
``knee=(0.815, 1.0, 1.2)``) implement the ACES Reference Gamut
Compression v1.3 cyan-channel threshold and power, with the asymptote
limit reduced from 1.147 to 1.0 so the knee converges exactly at the
spectral locus boundary rather than past it. See the spektrafilm-research
note ``n100_soft_input_clipping`` §5 for the full rationale.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import colour
import numpy as np
from matplotlib.path import Path as MplPath
from scipy.ndimage import map_coordinates


# ---------------------------------------------------------------------------
# Spec dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GamutCompressSpec:
    """Configuration for input gamut compression.

    Attributes
    ----------
    mode :
        ``"soft"`` applies the Reinhard-knee compression; ``"off"``
        disables compression and passes input chromaticities through
        unchanged (the LUT bake then behaves as it did before this
        feature landed).
    algorithm :
        ``"xy"`` — radial compression in CIE 1931 chromaticity from the
        film reference illuminant toward the visible spectral locus
        (ACES RGC family). This is the production default; see n100
        §5.1 for why it won over the alternatives on smoothness probes.

        ``"oklch"`` — chroma reduction at constant Oklch (L, h) — moves
        the chromaticity radially in OkLab space toward the locus
        boundary. Available for inspection / per-bundle override.
    knee :
        ``(threshold, limit, power)`` of the Reinhard knee:
        ``d' = t + s · n / (1 + n^p)^(1/p)`` where ``n = (d - t)/s``
        and ``s = limit - t``. Default ``(0.815, 1.0, 1.2)`` matches the
        ACES RGC v1.3 cyan threshold and power with the limit reduced
        to 1.0 (see module docstring and n100 §5.2).
    """

    mode: Literal["off", "soft"] = "soft"
    algorithm: Literal["xy", "oklch"] = "xy"
    knee: tuple[float, float, float] = (0.815, 1.0, 1.2)

    def __post_init__(self) -> None:
        if self.mode not in ("off", "soft"):
            raise ValueError(
                f"mode must be 'off' or 'soft', got {self.mode!r}"
            )
        if self.algorithm not in ("xy", "oklch"):
            raise ValueError(
                f"algorithm must be 'xy' or 'oklch', got {self.algorithm!r}"
            )
        t, l, p = self.knee
        if not (0.0 <= t < 1.0):
            raise ValueError(
                f"knee threshold must be in [0, 1), got {t}"
            )
        if not (l > 0.0):
            raise ValueError(f"knee limit must be > 0, got {l}")
        if not (p > 0.0):
            raise ValueError(f"knee power must be > 0, got {p}")


@dataclass(frozen=True)
class OutputGamutCompressSpec:
    """Configuration for output gamut compression.

    Independent of :class:`GamutCompressSpec` (which targets the visible
    spectral locus on the input side, in chromaticity). This spec targets
    the *output primaries cube* on the output side, in destination RGB.
    Both algorithms reuse the same Reinhard knee math.

    Attributes
    ----------
    mode :
        ``"soft"`` applies the Reinhard-knee compression; ``"off"``
        disables compression and passes output RGB through unchanged
        (the existing per-channel ``gamut_clip`` in scanning.py is then
        the only output-side safety net).
    algorithm :
        ``"oklch"`` (default) — perceptual-hue-preserving chroma
        reduction in OkLab. Convert output RGB → OkLab → OkLch
        (L, C, h), look up ``C_max(L, h)`` for the output color
        space's RGB cube, apply the Reinhard knee to ``C / C_max``,
        reconstruct. Preserves OkLab hue ``h`` and OkLab lightness
        ``L`` — the colorist sees the same hue at the same perceptual
        brightness, just less saturated. Default because the
        simulation's output gamut is the smooth, round-to-hexagonal
        envelope of a CMY dye set (see n110 §2), and perceptual-
        chroma reduction around a round envelope reads more smoothly
        than a per-channel knee against a triangle.

        ``"aces_rgc"`` — ACES Reference Gamut Compression v1.3 native
        form. Per-channel knee on the achromatic distance
        ``d = (max(R,G,B) - c) / max(R,G,B)``. Preserves the achromatic
        RGB mixture. This is the cinema-industry standard for output
        gamut mapping; same operation as OCIO's
        ``FixedFunctionTransform(style=ACES_GamutComp13)`` (the knee
        math is verified bit-identical in
        ``validate_compression_against_references.py``). Available as
        an opt-in for users who want behavior matching downstream
        Resolve/Nuke gamut-compress tools.
    knee :
        ``(threshold, limit, power)`` of the Reinhard knee. Default
        ``(0.815, 1.0, 1.2)`` matches the ACES RGC v1.3 cyan threshold
        and power; the limit is reduced from 1.147 to 1.0 so the knee's
        asymptote lands at the output gamut boundary itself (cube edge)
        rather than past it — the LUT cube must contain values in
        [0, 1] without needing a hard clip. Same reasoning as the
        input side (see n100 §5.2).
    """

    mode: Literal["off", "soft"] = "soft"
    algorithm: Literal["aces_rgc", "oklch"] = "oklch"
    knee: tuple[float, float, float] = (0.815, 1.0, 1.2)

    def __post_init__(self) -> None:
        if self.mode not in ("off", "soft"):
            raise ValueError(
                f"mode must be 'off' or 'soft', got {self.mode!r}"
            )
        if self.algorithm not in ("aces_rgc", "oklch"):
            raise ValueError(
                f"algorithm must be 'aces_rgc' or 'oklch', "
                f"got {self.algorithm!r}"
            )
        t, l, p = self.knee
        if not (0.0 <= t < 1.0):
            raise ValueError(
                f"knee threshold must be in [0, 1), got {t}"
            )
        if not (l > 0.0):
            raise ValueError(f"knee limit must be > 0, got {l}")
        if not (p > 0.0):
            raise ValueError(f"knee power must be > 0, got {p}")


# ---------------------------------------------------------------------------
# Spectral locus singleton
# ---------------------------------------------------------------------------

_SPECTRAL_LOCUS_XY_CACHE: np.ndarray | None = None


def spectral_locus_xy() -> np.ndarray:
    """Closed polygon of the CIE 1931 2° visible spectral locus in xy.

    Sampled at 5 nm steps from 380 to 700 nm; the returned array
    repeats the first vertex at the end so it is suitable for
    `matplotlib.path.Path` and ray-polygon intersection.
    """
    global _SPECTRAL_LOCUS_XY_CACHE
    if _SPECTRAL_LOCUS_XY_CACHE is None:
        cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
        # 5 nm sampling is fine; the locus polygon is dense enough for
        # robust ray-intersection and in-polygon tests.
        wavelengths = np.arange(380, 705, 5)
        xyz = np.asarray(cmfs[wavelengths])
        total = xyz.sum(axis=-1)
        xy = xyz[:, :2] / np.fmax(total[:, None], 1e-12)
        _SPECTRAL_LOCUS_XY_CACHE = np.concatenate([xy, xy[:1]], axis=0)
    return _SPECTRAL_LOCUS_XY_CACHE


# ---------------------------------------------------------------------------
# Reinhard knee + xy radial compressor
# ---------------------------------------------------------------------------


def reinhard_knee(
    d: np.ndarray,
    *,
    threshold: float,
    limit: float,
    power: float,
) -> np.ndarray:
    """Smooth knee on normalized distance.

    Identity below ``threshold``; smoothly asymptotic at ``limit`` above
    it. The exact formula matches the ACES RGC v1.3 reference (verified
    bit-identical by spektrafilm-research/studies/a40_lut_system/
    validate_compression_against_references.py).
    """
    out = np.asarray(d, dtype=float).copy()
    mask = out > threshold
    if np.any(mask):
        scale = limit - threshold
        x = (out[mask] - threshold) / scale
        y = x / np.power(1.0 + np.power(x, power), 1.0 / power)
        out[mask] = threshold + scale * y
    return out


def _ray_polygon_distance(
    origin: np.ndarray, direction: np.ndarray, polygon: np.ndarray,
) -> np.ndarray:
    """Distance from ``origin`` along unit ``direction`` to the first
    intersection with the closed polygon.

    Vectorized: ``direction`` has shape ``(..., 2)``; the polygon is
    a single closed loop of shape ``(N+1, 2)`` with the first vertex
    repeated at the end. Returns shape ``(...)``.

    Uses the parametric line-segment intersection
    (origin + t · direction = a + s · (b - a)) with the usual
    1e-12 epsilon guard for parallel rays. NaN for rays that miss the
    polygon (should not happen for the visible locus + interior origin).
    """
    direction = np.asarray(direction, dtype=float)
    flat = direction.reshape(-1, 2)
    n_rays = flat.shape[0]
    t_min = np.full(n_rays, np.inf)

    a = polygon[:-1]
    b = polygon[1:]
    edge = b - a

    for k in range(len(edge)):
        ex, ey = edge[k]
        ax, ay = a[k]
        dx = flat[:, 0]
        dy = flat[:, 1]
        denom = dx * ey - dy * ex
        valid = np.abs(denom) > 1e-12
        ox = origin[0] - ax
        oy = origin[1] - ay
        # Solve t * d - s * edge = -o  →  t = (o × edge) / (d × edge)
        t = np.where(
            valid,
            (-ox * ey + oy * ex) / np.where(valid, denom, 1.0),
            np.inf,
        )
        s = np.where(
            valid,
            (-ox * dy + oy * dx) / np.where(valid, denom, 1.0),
            np.inf,
        )
        good = valid & (t > 1e-9) & (s >= 0.0) & (s <= 1.0)
        t_min = np.where(good & (t < t_min), t, t_min)

    return t_min.reshape(direction.shape[:-1])


def compress_xy_radial(
    xy: np.ndarray,
    white_xy: np.ndarray,
    *,
    threshold: float,
    limit: float,
    power: float,
    locus: np.ndarray | None = None,
) -> np.ndarray:
    """ACES-RGC-style radial compression toward the spectral locus.

    For each xy, compute the normalized distance ``d`` from ``white_xy``
    along the ray to the locus boundary; pass ``d`` through the Reinhard
    knee; scale ``d`` back into a new xy along the same ray. Hue
    (= dominant wavelength) is preserved by construction.
    """
    if locus is None:
        locus = spectral_locus_xy()
    xy = np.asarray(xy, dtype=float)
    white_xy = np.asarray(white_xy, dtype=float)
    delta = xy - white_xy
    dist = np.linalg.norm(delta, axis=-1)
    # At-white samples have zero distance and undefined direction; they
    # produce NaN/inf in the intermediate ray-polygon math but are
    # substituted with the original xy by the final np.where. Silence
    # the spurious intermediate warnings.
    with np.errstate(invalid="ignore", divide="ignore"):
        safe_dist = np.fmax(dist, 1e-12)
        direction = delta / safe_dist[..., None]
        boundary = _ray_polygon_distance(white_xy, direction, locus)
        d_norm = dist / np.fmax(boundary, 1e-12)
        d_compressed = reinhard_knee(
            d_norm, threshold=threshold, limit=limit, power=power,
        )
        new_xy = white_xy + direction * (d_compressed * boundary)[..., None]
    # At-white points have undefined direction; pass through unchanged.
    return np.where((dist < 1e-9)[..., None], xy, new_xy)


# ---------------------------------------------------------------------------
# Oklch chroma compressor + per-illuminant C_max(L, h) cache
# ---------------------------------------------------------------------------


_OKLCH_CMAX_TABLE_N_L = 64
_OKLCH_CMAX_TABLE_N_H = 720
_OKLCH_CMAX_TABLE_N_BISECT = 18

# Cache key: id of the locus array. The same locus instance produces
# the same table; users rebuilding the locus (e.g., a different observer)
# get a fresh table.
_OKLCH_CMAX_TABLE_CACHE: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}


def _xy_to_xyz_unit_y(xy: np.ndarray) -> np.ndarray:
    """xyY → XYZ at Y = 1 (lightness-preserving reconstruction)."""
    x = xy[..., 0]
    y = xy[..., 1]
    safe_y = np.fmax(y, 1e-12)
    X = x / safe_y
    Y = np.ones_like(x)
    Z = (1.0 - x - y) / safe_y
    return np.stack([X, Y, Z], axis=-1)


def _xyz_to_xy(xyz: np.ndarray) -> np.ndarray:
    total = xyz.sum(axis=-1, keepdims=True)
    return xyz[..., :2] / np.fmax(total, 1e-12)


def _build_oklch_c_max_table(
    locus: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bisect to find max Oklch chroma at each (L, h) such that the
    resulting xy is inside the spectral locus.

    Returns ``(L_grid, h_grid, C_max_table)`` for use with
    :func:`_c_max_lookup`. Computed once per locus and cached.
    """
    n_L = _OKLCH_CMAX_TABLE_N_L
    n_h = _OKLCH_CMAX_TABLE_N_H
    n_bisect = _OKLCH_CMAX_TABLE_N_BISECT

    L_grid = np.linspace(0.05, 1.0, n_L)
    h_grid = np.linspace(-np.pi, np.pi, n_h, endpoint=False)
    L_mesh, h_mesh = np.meshgrid(L_grid, h_grid, indexing="ij")

    lo = np.zeros_like(L_mesh)
    hi = np.full_like(L_mesh, 0.5)  # 0.5 covers all realistic chromas

    locus_path = MplPath(locus)
    for _ in range(n_bisect):
        mid = (lo + hi) * 0.5
        a = mid * np.cos(h_mesh)
        b = mid * np.sin(h_mesh)
        lab = np.stack([L_mesh, a, b], axis=-1).reshape(-1, 3)
        xyz = np.asarray(colour.Oklab_to_XYZ(lab))
        xy = _xyz_to_xy(xyz)
        in_locus = locus_path.contains_points(xy).reshape(L_mesh.shape)
        lo = np.where(in_locus, mid, lo)
        hi = np.where(in_locus, hi, mid)
    return L_grid, h_grid, lo


def _get_oklch_c_max_table(
    locus: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = id(locus)
    if key not in _OKLCH_CMAX_TABLE_CACHE:
        _OKLCH_CMAX_TABLE_CACHE[key] = _build_oklch_c_max_table(locus)
    return _OKLCH_CMAX_TABLE_CACHE[key]


def _c_max_lookup(
    L: np.ndarray, h: np.ndarray,
    L_grid: np.ndarray, h_grid: np.ndarray, C_max_table: np.ndarray,
) -> np.ndarray:
    """Bilinear lookup of C_max(L, h)."""
    L = np.clip(L, L_grid[0], L_grid[-1])
    h_step = h_grid[1] - h_grid[0]
    h_idx = (h - h_grid[0]) / h_step
    h_lo = np.floor(h_idx).astype(int) % len(h_grid)
    h_hi = (h_lo + 1) % len(h_grid)
    h_frac = h_idx - np.floor(h_idx)

    L_idx = (L - L_grid[0]) / (L_grid[-1] - L_grid[0]) * (len(L_grid) - 1)
    L_lo = np.clip(np.floor(L_idx).astype(int), 0, len(L_grid) - 2)
    L_hi = L_lo + 1
    L_frac = L_idx - L_lo

    v00 = C_max_table[L_lo, h_lo]
    v01 = C_max_table[L_lo, h_hi]
    v10 = C_max_table[L_hi, h_lo]
    v11 = C_max_table[L_hi, h_hi]
    return (
        v00 * (1 - L_frac) * (1 - h_frac)
        + v01 * (1 - L_frac) * h_frac
        + v10 * L_frac * (1 - h_frac)
        + v11 * L_frac * h_frac
    )


def compress_oklch_chroma(
    xy: np.ndarray,
    white_xy: np.ndarray,  # noqa: ARG001 — unused; kept for API symmetry
    *,
    threshold: float,
    limit: float,
    power: float,
    locus: np.ndarray | None = None,
) -> np.ndarray:
    """CSS-Color-4-style chroma reduction in Oklch.

    Convert xy (at Y = 1) → OkLab → Oklch. Compress C only, keeping L
    and h fixed. Perceptual hue and lightness are preserved; only the
    perceived chroma shrinks. Returns the new xy.
    """
    if locus is None:
        locus = spectral_locus_xy()
    c_max_lookup_table = _get_oklch_c_max_table(locus)

    xy = np.asarray(xy, dtype=float)
    xyz = _xy_to_xyz_unit_y(xy)
    lab = np.asarray(colour.XYZ_to_Oklab(xyz))
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    C = np.hypot(a, b)
    h = np.arctan2(b, a)

    C_max = _c_max_lookup(L, h, *c_max_lookup_table)
    safe_C_max = np.fmax(C_max, 1e-9)
    d_norm = C / safe_C_max
    d_compressed = reinhard_knee(
        d_norm, threshold=threshold, limit=limit, power=power,
    )
    C_new = d_compressed * safe_C_max
    a_new = C_new * np.cos(h)
    b_new = C_new * np.sin(h)
    lab_new = np.stack([L, a_new, b_new], axis=-1)
    xyz_new = np.asarray(colour.Oklab_to_XYZ(lab_new))
    return _xyz_to_xy(xyz_new)


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------


def compress_xy(
    xy: np.ndarray,
    white_xy: np.ndarray,
    spec: GamutCompressSpec,
    *,
    locus: np.ndarray | None = None,
) -> np.ndarray:
    """Apply the compression specified by ``spec`` to CIE xy values.

    Parameters
    ----------
    xy :
        Array of CIE xy values, shape ``(..., 2)``.
    white_xy :
        The achromatic axis around which the compression operates —
        in the spektrafilm runtime, this is the film's reference
        illuminant xy.
    spec :
        Configuration. With ``spec.mode == "off"`` returns ``xy``
        unchanged.
    locus :
        Optional spectral locus polygon override. Defaults to
        :func:`spectral_locus_xy` (CIE 1931 2° at 5 nm sampling).
    """
    if spec.mode == "off":
        return np.asarray(xy, dtype=float)
    threshold, limit, power = spec.knee
    if spec.algorithm == "xy":
        return compress_xy_radial(
            xy, white_xy,
            threshold=threshold, limit=limit, power=power, locus=locus,
        )
    if spec.algorithm == "oklch":
        return compress_oklch_chroma(
            xy, white_xy,
            threshold=threshold, limit=limit, power=power, locus=locus,
        )
    raise ValueError(f"unknown algorithm {spec.algorithm!r}")


# ---------------------------------------------------------------------------
# Output-side: per-channel ACES RGC in destination RGB
# ---------------------------------------------------------------------------


def compress_rgb_aces_rgc(
    rgb: np.ndarray,
    *,
    threshold: float,
    limit: float,
    power: float,
) -> np.ndarray:
    """ACES Reference Gamut Compression v1.3 in its native form.

    For each pixel, compute the achromatic value ``ach = max(R, G, B)``
    and per-channel distance ``d = (ach - c) / ach``. ``d >= 0`` for
    every channel; ``d > 1`` exactly when ``c < 0`` (the channel is
    "more saturated than the achromatic envelope"). Apply the Reinhard
    knee to each per-channel distance, then reconstruct:
    ``c' = ach * (1 - d')``.

    With the default ``limit = 1.0``, the knee asymptotes at ``d = 1``,
    so negative channels (which had ``d > 1``) are pulled to exactly
    ``c' = 0`` — the cube boundary. Positive channels inside the
    threshold ``t`` are unchanged. Hue is preserved in the colorist
    sense (the channel-mixture ratios stay coherent rather than the
    dominant-wavelength chromaticity).

    Notes on amplitude
    ------------------
    This operation does *not* touch the achromatic value itself, so
    pixels with ``ach > 1`` retain ``ach > 1`` after compression. That
    high-amplitude case is handled by the existing
    ``params.io.gamut_clip`` safety net downstream (per-channel
    soft-plus or ``np.clip(0, 1)``) — the LUT cube's [0, 1] invariant
    is preserved by the combination.

    References
    ----------
    AMPAS Gamut Mapping Virtual Working Group, *ACES Reference Gamut
    Compression v1.3*, 2020. Same per-channel formulation as OCIO's
    ``FixedFunctionTransform(style=ACES_GamutComp13)``; knee math
    A/B-validated in
    ``spektrafilm-research/studies/a40_lut_system/
    validate_compression_against_references.py``.
    """
    rgb = np.asarray(rgb, dtype=float)
    # Achromatic envelope. For all-non-positive pixels (extreme shadows)
    # we fall back to identity — no meaningful chromaticity to compress.
    ach = np.max(rgb, axis=-1)
    safe_ach = np.where(ach > 1e-12, ach, 1.0)

    d = (ach[..., None] - rgb) / safe_ach[..., None]
    d_compressed = reinhard_knee(
        d, threshold=threshold, limit=limit, power=power,
    )
    rgb_compressed = ach[..., None] * (1.0 - d_compressed)
    # Pixels with ach <= 0 keep their original (near-black) values.
    return np.where(ach[..., None] > 1e-12, rgb_compressed, rgb)


# ---------------------------------------------------------------------------
# Output-side: OkLch chroma reduction to the output primaries cube.
# Mirrors the input-side compress_oklch_chroma but with the boundary swapped
# from the visible spectral locus (a chromaticity polygon) to the destination
# RGB cube (the output primaries' [0, 1]³ in linear RGB).
# ---------------------------------------------------------------------------


_OKLCH_OUTPUT_CMAX_CACHE: dict[
    str, tuple[np.ndarray, np.ndarray, np.ndarray]
] = {}


def _build_oklch_output_c_max_table(
    output_color_space: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bisect to find max Oklch chroma at each (L, h) such that the
    resulting linear RGB in ``output_color_space`` is inside [0, 1]^3.

    Per output color space; cached after the first call. Sampling
    matches the input-side ``_build_oklch_c_max_table`` (64 × 720)
    so resolution and per-cell error characteristics are consistent.
    """
    cs = colour.RGB_COLOURSPACES[output_color_space]
    white = np.asarray(cs.whitepoint, dtype=float)

    n_L = _OKLCH_CMAX_TABLE_N_L
    n_h = _OKLCH_CMAX_TABLE_N_H
    n_bisect = _OKLCH_CMAX_TABLE_N_BISECT

    L_grid = np.linspace(0.02, 1.0, n_L)
    h_grid = np.linspace(-np.pi, np.pi, n_h, endpoint=False)
    L_mesh, h_mesh = np.meshgrid(L_grid, h_grid, indexing="ij")

    lo = np.zeros_like(L_mesh)
    hi = np.full_like(L_mesh, 0.5)  # 0.5 covers all realistic chromas

    for _ in range(n_bisect):
        mid = (lo + hi) * 0.5
        a = mid * np.cos(h_mesh)
        b = mid * np.sin(h_mesh)
        lab = np.stack([L_mesh, a, b], axis=-1).reshape(-1, 3)
        xyz = np.asarray(colour.Oklab_to_XYZ(lab))
        rgb = np.asarray(colour.XYZ_to_RGB(
            xyz, colourspace=output_color_space,
            illuminant=white, apply_cctf_encoding=False,
        ))
        # In-gamut iff every channel is in [0, 1]. Small slack absorbs
        # the matrix-inverse floating-point noise that would otherwise
        # leave the largest in-gamut chroma slightly conservative.
        in_gamut = np.all(
            (rgb >= -1e-6) & (rgb <= 1.0 + 1e-6), axis=-1,
        ).reshape(L_mesh.shape)
        lo = np.where(in_gamut, mid, lo)
        hi = np.where(in_gamut, hi, mid)
    return L_grid, h_grid, lo


def _get_oklch_output_c_max_table(
    output_color_space: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if output_color_space not in _OKLCH_OUTPUT_CMAX_CACHE:
        _OKLCH_OUTPUT_CMAX_CACHE[output_color_space] = (
            _build_oklch_output_c_max_table(output_color_space)
        )
    return _OKLCH_OUTPUT_CMAX_CACHE[output_color_space]


def compress_rgb_oklch_chroma(
    rgb: np.ndarray,
    output_color_space: str,
    *,
    threshold: float,
    limit: float,
    power: float,
) -> np.ndarray:
    """OkLch chroma reduction to the output RGB cube.

    For each pixel, convert linear ``output_color_space`` RGB → XYZ →
    OkLab → OkLch (L, C, h). Look up the maximum in-gamut chroma
    ``C_max(L, h)`` for the destination RGB cube and apply the Reinhard
    knee on ``C / C_max``. Reconstruct OkLch → OkLab → XYZ → RGB.

    L (perceptual lightness) and h (perceptual hue) are preserved by
    construction; only the perceptual chroma shrinks. With
    ``limit = 1.0`` the knee asymptotes at ``C / C_max = 1``, i.e. the
    cube boundary itself — outputs are guaranteed inside the RGB cube
    by the OkLch math, no final clip needed for the chroma direction
    (the achromatic lightness axis is unaffected and the cube's
    [0, 1] amplitude bound is preserved by the OkLab transform when
    L ∈ [0, 1]).

    Heavier per-pixel than :func:`compress_rgb_aces_rgc`: each call
    runs RGB ↔ XYZ ↔ OkLab, a hypot + atan2, a bilinear table lookup,
    a knee, and cos/sin reconstruction. The OkLch C_max table is
    cached per output color space (one build per illuminant), so
    repeated bakes against the same output space are fast.
    """
    rgb = np.asarray(rgb, dtype=float)
    cs = colour.RGB_COLOURSPACES[output_color_space]
    white = np.asarray(cs.whitepoint, dtype=float)

    # RGB → XYZ → OkLab → OkLch (L, C, h).
    xyz = np.asarray(colour.RGB_to_XYZ(
        rgb, colourspace=output_color_space,
        illuminant=white, apply_cctf_decoding=False,
    ))
    lab = np.asarray(colour.XYZ_to_Oklab(xyz))
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    C = np.hypot(a, b)
    h = np.arctan2(b, a)

    # Compress C against the per-output-space C_max(L, h).
    c_max_lookup_table = _get_oklch_output_c_max_table(output_color_space)
    C_max = _c_max_lookup(L, h, *c_max_lookup_table)
    safe_C_max = np.fmax(C_max, 1e-9)
    d_norm = C / safe_C_max
    d_compressed = reinhard_knee(
        d_norm, threshold=threshold, limit=limit, power=power,
    )
    C_new = d_compressed * safe_C_max

    # OkLch → OkLab → XYZ → RGB.
    a_new = C_new * np.cos(h)
    b_new = C_new * np.sin(h)
    lab_new = np.stack([L, a_new, b_new], axis=-1)
    xyz_new = np.asarray(colour.Oklab_to_XYZ(lab_new))
    rgb_new = np.asarray(colour.XYZ_to_RGB(
        xyz_new, colourspace=output_color_space,
        illuminant=white, apply_cctf_encoding=False,
    ))
    return rgb_new


def compress_rgb(
    rgb: np.ndarray,
    spec: "OutputGamutCompressSpec",
    *,
    output_color_space: str | None = None,
) -> np.ndarray:
    """Apply output gamut compression to RGB values per ``spec``.

    Parameters
    ----------
    rgb :
        RGB array in the destination output primaries (linear),
        shape ``(..., 3)``.
    spec :
        Output compression configuration. ``spec.mode == "off"``
        returns ``rgb`` unchanged.
    output_color_space :
        Name of the destination color space (e.g. ``"sRGB"``).
        Required when ``spec.algorithm == "oklch"`` because that
        algorithm needs to build / look up the per-color-space
        ``C_max(L, h)`` table. Ignored for ``"aces_rgc"``, which
        operates purely in destination RGB.
    """
    if spec.mode == "off":
        return np.asarray(rgb, dtype=float)
    threshold, limit, power = spec.knee
    if spec.algorithm == "aces_rgc":
        return compress_rgb_aces_rgc(
            rgb, threshold=threshold, limit=limit, power=power,
        )
    if spec.algorithm == "oklch":
        if output_color_space is None:
            raise ValueError(
                "output_color_space is required when algorithm='oklch'"
            )
        return compress_rgb_oklch_chroma(
            rgb, output_color_space=output_color_space,
            threshold=threshold, limit=limit, power=power,
        )
    raise ValueError(f"unknown output algorithm {spec.algorithm!r}")


# ---------------------------------------------------------------------------
# TC LUT remap-resample (per n100 §3.1)
# ---------------------------------------------------------------------------


def remap_tc_lut_for_compression(
    tc_lut: np.ndarray,
    reference_illuminant_xy: np.ndarray,
    spec: GamutCompressSpec,
    *,
    locus: np.ndarray | None = None,
) -> np.ndarray:
    """Bake the compression into a 128×128×3 tc_lut.

    The runtime lookup path is RGB → CIE xy → tri2quad → tc → bilinear
    sample of ``tc_lut`` → raw. We do **not** want to inject a
    per-sample compression call into that path; instead we remap the
    LUT once at build time so the on-disk LUT internally absorbs the
    compression:

        new_lut[xy] = old_lut[compress(xy)]

    Concretely, for each grid cell of the new LUT we:
      1. Decode its tc index back to a CIE xy via ``_quad2tri``.
      2. Run that xy through the compressor.
      3. Re-encode the compressed xy to tc via ``_tri2quad``.
      4. Bilinearly sample the original LUT at that tc.

    Per-channel bilinear sampling via ``scipy.ndimage.map_coordinates``
    (order=1, ``mode="nearest"`` boundary so out-of-grid tc values get
    the closest-edge LUT value rather than wrapping or extrapolating
    past 0/1 in raw RGB).

    Parameters
    ----------
    tc_lut :
        The per-film ``compute_hanatos2025_tc_lut`` output, shape
        ``(H, W, 3)``.
    reference_illuminant_xy :
        The film's reference illuminant xy (the compression's
        achromatic axis). Must match the illuminant used inside
        ``_rgb_to_tc_b`` so the compression operates around the same
        white the runtime evaluates against.
    spec :
        Compression configuration. ``spec.mode == "off"`` returns
        ``tc_lut`` unchanged.
    locus :
        Optional spectral locus override (see :func:`compress_xy`).
    """
    if spec.mode == "off":
        return tc_lut

    # Import here to avoid a circular module-load between
    # spectral_upsampling.py and gamut_compression.py.
    from spektrafilm.utils.spectral_upsampling import _quad2tri, _tri2quad

    H, W, C = tc_lut.shape
    assert C == 3, f"tc_lut must have 3 channels, got {C}"

    # Grid of LUT cell positions in tc space (the LUT's own indexing).
    # Cell (i, j) corresponds to tc = (i / (H-1), j / (W-1)).
    i_idx, j_idx = np.meshgrid(
        np.arange(H, dtype=float),
        np.arange(W, dtype=float),
        indexing="ij",
    )
    tc_cells = np.stack([i_idx / (H - 1), j_idx / (W - 1)], axis=-1)

    # Step 1: tc → CIE xy via _quad2tri (LUT's inverse coordinate map).
    xy_cells = _quad2tri(tc_cells)

    # Step 2: apply compression.
    xy_compressed = compress_xy(
        xy_cells.reshape(-1, 2),
        np.asarray(reference_illuminant_xy, dtype=float),
        spec,
        locus=locus,
    ).reshape(H, W, 2)

    # Step 3: CIE xy → tc via _tri2quad (LUT's forward coordinate map).
    tc_compressed = _tri2quad(xy_compressed)

    # Step 4: bilinear sample old LUT at tc_compressed. map_coordinates
    # expects coordinates in *grid index* space (not [0, 1] normalized),
    # so convert tc ∈ [0, 1] to indices ∈ [0, H-1] / [0, W-1].
    coord_i = tc_compressed[..., 0] * (H - 1)
    coord_j = tc_compressed[..., 1] * (W - 1)
    coords = np.stack([coord_i.ravel(), coord_j.ravel()], axis=0)

    new_lut = np.empty_like(tc_lut)
    for ch in range(C):
        sampled = map_coordinates(
            tc_lut[..., ch],
            coords,
            order=1,
            mode="nearest",
        )
        new_lut[..., ch] = sampled.reshape(H, W)
    return new_lut
