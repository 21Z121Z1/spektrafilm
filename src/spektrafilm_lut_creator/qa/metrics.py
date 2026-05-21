"""Scientific metrics for LUT QA.

Each function takes input/output arrays and returns scalars (or scalar
fields) suitable for the ``Result.summary`` dictionary. Implementations
favor clarity over micro-optimization — these run once per QA pass.

References are inline. The default tolerances cited come from the
named standard; per-test thresholds live in ``tests.py``.
"""
from __future__ import annotations

import numpy as np

import colour


# ---------------------------------------------------------------------------
# Perceptual color differences.
# ---------------------------------------------------------------------------

def delta_itp(rgb_a: np.ndarray, rgb_b: np.ndarray, *, output_color_space: str) -> np.ndarray:
    """ITU-R BT.2124 ΔITP between two RGB arrays.

    ΔITP is the HDR-aware perceptual color difference used by
    Dolby and SMPTE for HDR/SDR encoding QA. Unit: just-noticeable
    difference (1 JND = imperceptible by BT.2124 definition).

    Parameters
    ----------
    rgb_a, rgb_b
        Shape ``(M, 3)``. *Encoded* RGB in the output color space (the
        wire form a LUT produces).
    output_color_space
        Registry name for ``rgb_a`` / ``rgb_b`` (e.g. ``"sRGB"``).
        Used to CCTF-decode to linear before the conversion.

    Returns
    -------
    np.ndarray
        Shape ``(M,)`` of ΔITP values. Aggregate with
        :func:`summary_stats`.

    References
    ----------
    - ITU-R BT.2124 "Objective metric for the assessment of the
      potential visibility of colour differences in television".
    """
    from spektrafilm_lut_creator.color_spaces import to_xyz

    xyz_a = to_xyz(rgb_a, output_color_space)
    xyz_b = to_xyz(rgb_b, output_color_space)
    # colour-science ICtCp expects normalized XYZ. BT.2124 normalizes
    # to a reference luminance; for SDR outputs the standard convention
    # is XYZ already in [0,1] reflectance units, which matches what
    # spektrafilm's scan produces (Y <= 1 by physics, see n070 §1.5).
    ictcp_a = colour.XYZ_to_ICtCp(xyz_a)
    ictcp_b = colour.XYZ_to_ICtCp(xyz_b)
    return np.asarray(colour.delta_E(ictcp_a, ictcp_b, method="ITP"), dtype=float)


def delta_e_2000(
    rgb_a: np.ndarray, rgb_b: np.ndarray, *, output_color_space: str
) -> np.ndarray:
    """CIE ΔE₀₀ (CIEDE2000) between two RGB arrays.

    The classic perceptual delta. Still load-bearing in print and
    photography. Less HDR-aware than ΔITP.
    """
    from spektrafilm_lut_creator.color_spaces import to_xyz

    xyz_a = to_xyz(rgb_a, output_color_space)
    xyz_b = to_xyz(rgb_b, output_color_space)
    lab_a = colour.XYZ_to_Lab(xyz_a)
    lab_b = colour.XYZ_to_Lab(xyz_b)
    return np.asarray(colour.delta_E(lab_a, lab_b, method="CIE 2000"), dtype=float)


def oklab_delta(
    rgb_a: np.ndarray, rgb_b: np.ndarray, *, output_color_space: str
) -> np.ndarray:
    """Euclidean OkLab distance between two RGB arrays.

    OkLab is the modern perceptually uniform space from Björn
    Ottosson; better hue uniformity than CIELAB at the cost of less
    established tolerances. Useful as a hue-direction-aware companion
    to ΔITP.

    References
    ----------
    - Ottosson, "A perceptual color space for image processing",
      https://bottosson.github.io/posts/oklab/.
    """
    from spektrafilm_lut_creator.color_spaces import to_xyz

    xyz_a = to_xyz(rgb_a, output_color_space)
    xyz_b = to_xyz(rgb_b, output_color_space)
    lab_a = np.asarray(colour.XYZ_to_Oklab(xyz_a), dtype=float)
    lab_b = np.asarray(colour.XYZ_to_Oklab(xyz_b), dtype=float)
    return np.linalg.norm(lab_a - lab_b, axis=-1)


# ---------------------------------------------------------------------------
# Cube-structural metrics.
# ---------------------------------------------------------------------------

def summary_stats(values: np.ndarray) -> dict[str, float]:
    """``{"max": ..., "p99": ..., "p95": ..., "p50": ..., "mean": ...}``.

    The standard headline tuple. ``p99`` is more honest than ``mean``
    for QA — a few cells with large errors are visible artifacts even
    when mean is tiny.
    """
    values = np.asarray(values, dtype=float).ravel()
    if values.size == 0:
        return {"max": float("nan"), "p99": float("nan"), "p95": float("nan"),
                "p50": float("nan"), "mean": float("nan")}
    return {
        "max":  float(np.max(values)),
        "p99":  float(np.percentile(values, 99)),
        "p95":  float(np.percentile(values, 95)),
        "p50":  float(np.percentile(values, 50)),
        "mean": float(np.mean(values)),
    }


def monotonicity_violations(table: np.ndarray) -> dict[str, int | float]:
    """Count and quantify per-axis monotonicity violations on the cube
    diagonal.

    For each axis ``a`` and the matching output channel ``c == a``, we
    check that ``table[..., c]`` is non-decreasing as we step along
    axis ``a``. A negative finite-difference is a fold-back.

    Off-diagonal non-monotonicity (e.g. green-in-red curve) is
    physically reasonable — DIR couplers, crosstalk in print
    chemistries — so we don't count those. The diagonal must be clean.

    Returns
    -------
    dict
        ``violations``: total count of bad steps across the three
        diagonal axes. ``worst_negative_diff``: most negative
        finite-difference (signed; 0.0 if no violations).
    """
    n = table.shape[0]
    table = np.asarray(table, dtype=float)
    # table indexing is [b, g, r, channel]. The diagonal pairs are:
    #   axis R (last spatial axis) vs channel 0
    #   axis G (middle spatial axis) vs channel 1
    #   axis B (first spatial axis) vs channel 2
    diffs = []
    diffs.append(np.diff(table[..., 0], axis=2))   # along R for channel R
    diffs.append(np.diff(table[..., 1], axis=1))   # along G for channel G
    diffs.append(np.diff(table[..., 2], axis=0))   # along B for channel B
    flat = np.concatenate([d.ravel() for d in diffs])
    violations = int(np.sum(flat < 0.0))
    worst = float(min(0.0, flat.min())) if flat.size else 0.0
    return {"violations": violations, "worst_negative_diff": worst}


def local_jacobian_log_cond(table: np.ndarray) -> np.ndarray:
    """log10 of the local 3x3 Jacobian condition number per interior cell.

    Computed by central differences on the cube table. The Jacobian
    captures local linearization of the transform; its condition number
    is ``sigma_max / sigma_min``, large where the transform is locally
    near-singular (gamut compression, density shoulders).

    Returns the flat array of log10(cond) values, length
    ``(N-2)**3``. Aggregate with :func:`summary_stats`.

    References
    ----------
    - Siragusano, "The Beauty of Per-Pixel Math", FilmLight (Vimeo).
    """
    table = np.asarray(table, dtype=float)
    dR = table[1:-1, 1:-1, 2:, :] - table[1:-1, 1:-1, :-2, :]
    dG = table[1:-1, 2:, 1:-1, :] - table[1:-1, :-2, 1:-1, :]
    dB = table[2:, 1:-1, 1:-1, :] - table[:-2, 1:-1, 1:-1, :]
    J = np.stack([dR, dG, dB], axis=-1)
    svds = np.linalg.svd(J, compute_uv=False)
    cond = svds[..., 0] / np.clip(svds[..., -1], 1e-12, None)
    return np.log10(np.clip(cond, 1.0, None)).ravel()


def total_variation(table: np.ndarray) -> dict[str, float]:
    """Per-axis mean absolute finite-difference of the cube table.

    A simple smoothness scalar. Higher values mean more variation per
    cell — banding-prone bakes show high values relative to their
    "ideal" reconstruction. Reported per output channel for diagnostic
    purposes; the headline ``tv`` is the sum.
    """
    table = np.asarray(table, dtype=float)
    tv_r = float(np.mean(np.abs(np.diff(table, axis=2))))
    tv_g = float(np.mean(np.abs(np.diff(table, axis=1))))
    tv_b = float(np.mean(np.abs(np.diff(table, axis=0))))
    return {"tv": tv_r + tv_g + tv_b, "tv_r": tv_r, "tv_g": tv_g, "tv_b": tv_b}


def axial_fft_highband_ratio(table: np.ndarray, band_frac: float = 0.5) -> dict[str, float]:
    """Fraction of axial-FFT energy living above ``band_frac * Nyquist``.

    For each axis, take 1D FFTs along that axis through every line of
    the cube, sum the magnitude spectrum, and compute the energy ratio
    above ``band_frac * Nyquist``. A bake with banding or aliasing
    artifacts lifts this ratio noticeably.

    ``band_frac=0.5`` is the default — energy in the top half of the
    spectrum is mostly noise / sharp edges, not the smooth color
    curves we expect.
    """
    table = np.asarray(table, dtype=float)
    n = table.shape[0]
    nyq_index = n // 2 + 1
    band_start = max(1, int(band_frac * (n // 2)))

    ratios: list[float] = []
    for axis in range(3):
        # Move the analysis axis to the end and flatten the rest into rows.
        moved = np.moveaxis(table, axis, -1)
        lines = moved.reshape(-1, n)
        spec = np.abs(np.fft.rfft(lines, axis=-1))
        total = spec.sum()
        high = spec[..., band_start:nyq_index].sum()
        ratios.append(float(high / max(total, 1e-12)))
    return {"axial_highband_ratio_r": ratios[0],
            "axial_highband_ratio_g": ratios[1],
            "axial_highband_ratio_b": ratios[2],
            "axial_highband_ratio_mean": float(np.mean(ratios))}


def gamut_hull_volume_ratio(grid_in: np.ndarray, grid_out: np.ndarray,
                             output_color_space: str) -> dict[str, float]:
    """Output OkLab convex-hull volume / input OkLab convex-hull volume.

    A LUT that compresses gamut produces a ratio < 1. A ratio > 1
    likely means the LUT expanded chromaticity, which for a film
    simulation would be physically surprising.

    Compares in OkLab so units are perceptually meaningful. Uses
    ``scipy.spatial.ConvexHull``; large grids are sub-sampled to keep
    the hull computation fast.
    """
    from scipy.spatial import ConvexHull
    from spektrafilm_lut_creator.color_spaces import to_xyz

    rng = np.random.default_rng(0)
    n_sample = min(grid_in.shape[0], 8000)
    idx = rng.choice(grid_in.shape[0], size=n_sample, replace=False)

    in_xyz = to_xyz(grid_in[idx], output_color_space)   # we use the output space
    out_xyz = to_xyz(grid_out[idx], output_color_space)  # for both for an apples-to-apples OkLab projection
    lab_in = np.asarray(colour.XYZ_to_Oklab(in_xyz), dtype=float)
    lab_out = np.asarray(colour.XYZ_to_Oklab(out_xyz), dtype=float)

    hull_in = ConvexHull(lab_in)
    hull_out = ConvexHull(lab_out)
    return {
        "input_hull_volume": float(hull_in.volume),
        "output_hull_volume": float(hull_out.volume),
        "compression_ratio": float(hull_out.volume / max(hull_in.volume, 1e-12)),
    }


def gamut_self_intersection_score(table: np.ndarray) -> dict[str, float]:
    """Detect cube surface folds via signed-volume sign flips.

    A well-behaved LUT preserves the orientation of the cube surface.
    We tessellate the input cube faces, push them through the LUT, and
    count tetrahedra whose signed volume changed sign relative to the
    identity — that flip is a fold-back of the surface onto itself
    (the gamut topology is broken).

    Returns
    -------
    dict
        ``flips``: count of flipped face triangles. ``fraction``:
        flips / total triangles tested.
    """
    n = table.shape[0]
    if n < 3:
        return {"flips": 0, "fraction": 0.0, "triangles": 0}

    axis = np.linspace(0.0, 1.0, n)
    flips = 0
    total = 0
    # Six faces; for each, sweep two non-face axes to form quad cells,
    # split into triangles, compute signed area in some projection.
    # Simpler proxy: for each face, sample a 2D grid and check that
    # the LUT image of opposing edge ordering is preserved.
    # We use the determinant of the local 2x2 partial-derivative matrix
    # of the face in OUTPUT space (any 2 of 3 output channels). A flip
    # in determinant sign signals a local fold.
    for fixed_axis in range(3):
        for fixed_value in (0, n - 1):
            # Build a 2D slice with two free axes (u, v) of length n.
            # output_face has shape (n, n, 3).
            if fixed_axis == 0:
                face = table[fixed_value, :, :, :]
            elif fixed_axis == 1:
                face = table[:, fixed_value, :, :]
            else:
                face = table[:, :, fixed_value, :]
            # Pick the two output channels that aren't equal to fixed_axis
            # as the projection (a heuristic but consistent).
            keep = [c for c in range(3) if c != fixed_axis]
            face2d = face[..., keep]  # shape (n, n, 2)
            du = face2d[1:, :-1, :] - face2d[:-1, :-1, :]
            dv = face2d[:-1, 1:, :] - face2d[:-1, :-1, :]
            det = du[..., 0] * dv[..., 1] - du[..., 1] * dv[..., 0]
            n_cells = det.size
            n_neg = int(np.sum(det < 0))
            n_pos = int(np.sum(det > 0))
            # If the face is supposed to be orientation-preserving, a
            # mix of signs across the face is a problem. We count the
            # minority sign as flips.
            flips += min(n_neg, n_pos)
            total += n_cells
    return {"flips": int(flips), "fraction": float(flips / max(total, 1)), "triangles": int(total)}


def hue_rotation_per_band(grid_in_lab: np.ndarray, grid_out_lab: np.ndarray) -> dict[str, float]:
    """Per-saturation-band maximum hue rotation, in degrees.

    Splits input by chroma into four bands and computes the worst hue
    rotation in each band. Hue rotation in OkLab is the angular
    distance between input and output hue vectors.

    Empty bands (no samples) are skipped silently.
    """
    grid_in_lab = np.asarray(grid_in_lab, dtype=float)
    grid_out_lab = np.asarray(grid_out_lab, dtype=float)
    c_in = np.sqrt(grid_in_lab[:, 1] ** 2 + grid_in_lab[:, 2] ** 2)
    c_max = float(c_in.max()) if c_in.size else 0.0
    if c_max <= 0.0:
        return {"max_hue_rotation_deg": 0.0}
    h_in = np.arctan2(grid_in_lab[:, 2], grid_in_lab[:, 1])
    h_out = np.arctan2(grid_out_lab[:, 2], grid_out_lab[:, 1])
    delta = np.abs(np.degrees(np.angle(np.exp(1j * (h_out - h_in)))))
    bands = [(0.20, 0.35), (0.35, 0.50), (0.50, 0.70), (0.70, 1.001)]
    out = {}
    worst_overall = 0.0
    for lo, hi in bands:
        mask = (c_in >= lo * c_max) & (c_in < hi * c_max)
        if not np.any(mask):
            continue
        max_band = float(delta[mask].max())
        out[f"max_rotation_chroma_{lo:.2f}_{hi:.2f}"] = max_band
        worst_overall = max(worst_overall, max_band)
    out["max_hue_rotation_deg"] = worst_overall
    return out


def second_derivative_max(curve: np.ndarray) -> float:
    """Max absolute discrete second derivative of a 1D sequence.

    Used by highlight-rolloff and log-domain-kink tests to detect
    kinks. Smooth physical curves have small |d^2 y / dx^2|; a kink
    spikes it.
    """
    y = np.asarray(curve, dtype=float).ravel()
    if y.size < 3:
        return 0.0
    d2 = y[2:] - 2.0 * y[1:-1] + y[:-2]
    return float(np.max(np.abs(d2)))


def dynamic_range_stats(
    stops: np.ndarray,
    output_y: np.ndarray,
    encoded_clip_mask: np.ndarray,
    *,
    slope_threshold: float = 0.10,
) -> dict[str, float | int]:
    """Quantify how many input stops the LUT actively renders.

    Parameters
    ----------
    stops
        Input axis in log2 stops (uniform spacing).
    output_y
        Output luminance ``Y`` (scene-linear, post-CCTF-decode of the
        LUT output) at each stop. Shape ``(n,)``.
    encoded_clip_mask
        Boolean ``(n,)``; ``True`` where the input encoding clipped
        the corresponding stop (can't be blamed on the LUT).
    slope_threshold
        Minimum ``|d log10(Y) / d stop|`` for a stop to count as
        "actively rendering." Default ``0.10`` density per stop —
        below this, the output barely moves with input, i.e. the
        stop is being collapsed.

    Returns
    -------
    dict
        ``encoded_range_stops``: stops where the input encoding can
        actually represent the scene-linear value (no clipping).
        ``active_range_stops``: stops where the LUT also renders
        them with above-threshold slope (the "actually usable"
        range). ``toe_collapsed_stops`` / ``shoulder_collapsed_stops``:
        stops within the encoded range where the slope falls below
        threshold at the low / high end respectively (these are
        rendering decisions, not encoding limits).

    References
    ----------
    - Density / log-E characteristic: any film datasheet; Hunt, "The
      Reproduction of Colour"; ARRI K1S0-057 LogC whitepaper for the
      modern equivalent.
    """
    stops = np.asarray(stops, dtype=float).ravel()
    output_y = np.asarray(output_y, dtype=float).ravel()
    encoded_clip_mask = np.asarray(encoded_clip_mask, dtype=bool).ravel()
    if stops.shape != output_y.shape or stops.shape != encoded_clip_mask.shape:
        raise ValueError(
            f"shape mismatch: stops={stops.shape} y={output_y.shape} "
            f"clip={encoded_clip_mask.shape}"
        )

    encoded_ok = ~encoded_clip_mask
    encoded_indices = np.where(encoded_ok)[0]
    if encoded_indices.size < 2:
        return {
            "encoded_range_stops": 0.0,
            "active_range_stops": 0.0,
            "toe_collapsed_stops": 0.0,
            "shoulder_collapsed_stops": 0.0,
        }
    enc_lo, enc_hi = encoded_indices[0], encoded_indices[-1]
    encoded_range_stops = float(stops[enc_hi] - stops[enc_lo])

    # Local density slope per stop: dD/dstop where D = -log10(Y).
    log_y = np.log10(np.clip(output_y, 1e-4, None))
    dlog = np.diff(log_y)
    dstop = np.diff(stops)
    # |dD / dstop| — D = -log10(Y), so dD = -dlog_y; magnitude is
    # symmetric so we just take |dlog_y|.
    slope_per_stop = np.abs(dlog) / np.clip(np.abs(dstop), 1e-9, None)

    # Restrict to the encoded range: indices [enc_lo, enc_hi].
    # Slopes live at midpoints between consecutive stops; index i in
    # `slope_per_stop` corresponds to the segment [stops[i], stops[i+1]].
    seg_within_encoded = (np.arange(slope_per_stop.size) >= enc_lo) & (
        np.arange(slope_per_stop.size) < enc_hi
    )
    active = (slope_per_stop > slope_threshold) & seg_within_encoded
    step = float(np.mean(np.diff(stops)))
    active_range_stops = float(np.sum(active) * step)

    # Toe: contiguous low-slope segments starting from enc_lo.
    toe_n = 0
    for i in range(enc_lo, enc_hi):
        if active[i]:
            break
        toe_n += 1
    toe_collapsed_stops = float(toe_n * step)

    # Shoulder: contiguous low-slope segments ending at enc_hi.
    shoulder_n = 0
    for i in range(enc_hi - 1, enc_lo - 1, -1):
        if active[i]:
            break
        shoulder_n += 1
    shoulder_collapsed_stops = float(shoulder_n * step)

    return {
        "encoded_range_stops": encoded_range_stops,
        "active_range_stops": active_range_stops,
        "toe_collapsed_stops": toe_collapsed_stops,
        "shoulder_collapsed_stops": shoulder_collapsed_stops,
    }


