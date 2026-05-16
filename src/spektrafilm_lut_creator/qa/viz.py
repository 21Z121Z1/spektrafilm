"""Plot library for QA results.

Every public function returns a ``matplotlib.figure.Figure``; the test
functions save the figure to disk and close it. Plot styling is
opinionated and consistent across the suite — dark background, a
fixed palette, visible 3D axes.

Visibility note (n080 follow-up): the cube and OkLab 3D plots used
panel edges at α=0.06, which was right at the threshold of visibility.
Bumped to α=0.22 and added a faint axis-aligned grid; the depth cues
read clearly without distracting from the data.
"""
from __future__ import annotations

import colour
import numpy as np
from matplotlib.figure import Figure
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# Palette.
# ---------------------------------------------------------------------------
BG = "#0a0a0a"
FG = "#cccccc"
HI = "#ffffff"
DIM = "#666666"
RED, GREEN, BLUE = "#ff5050", "#50ff80", "#5080ff"
WARN = "#ffd060"

PANE_EDGE_RGBA = (1.0, 1.0, 1.0, 0.22)
GRID_RGBA = (1.0, 1.0, 1.0, 0.12)


def _setup_3d(ax) -> None:
    """Apply the project's consistent 3D-axis styling.

    The fix for the "axis lines barely visible" issue: pane edges at
    α=0.22 and a faint grid line set provide depth cues without
    overwhelming the data points.
    """
    for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
        axis.pane.fill = False
        axis.pane.set_edgecolor(PANE_EDGE_RGBA)
        axis._axinfo["grid"]["color"] = GRID_RGBA
        axis._axinfo["grid"]["linewidth"] = 0.5
        for lbl in axis.get_ticklabels():
            lbl.set_color(FG)
    ax.grid(True)


def _setup_2d(ax) -> None:
    """Consistent 2D axis styling."""
    ax.tick_params(colors=FG)
    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.grid(True, alpha=0.12, color=HI)


def _fill_3d(fig, *, has_cbar: bool = False, top: float = 0.94,
             bottom: float = 0.02, wspace: float = 0.0) -> None:
    """Push 3D axes to fill the figure canvas.

    matplotlib 3D axes default to a generous interior margin; for the
    plots we ship that leaves the data sitting in the middle 50–60% of
    the figure with a lot of dead black background around it. We pull
    the axes box outward with subplots_adjust; ``bbox_inches="tight"``
    at save time then trims off whatever tick decorations stick out.
    """
    right = 0.92 if has_cbar else 1.0
    fig.subplots_adjust(left=0.0, right=right,
                        bottom=bottom, top=top, wspace=wspace)


def _to_oklab(rgb: np.ndarray, cs_name: str) -> np.ndarray:
    """RGB encoded in ``cs_name`` → OkLab via XYZ.

    Used by every plot that overlays OkLab structure on LUT output.
    """
    from spektrafilm_lut_creator.color_spaces import to_xyz

    xyz = to_xyz(np.asarray(rgb, dtype=float), cs_name)
    return np.asarray(colour.XYZ_to_Oklab(xyz), dtype=float)


def _gamut_triangle_xy(cs_name: str) -> np.ndarray:
    """Closed (R, G, B, R) chromaticity triangle for the registry entry's primaries."""
    from spektrafilm_lut_creator.color_spaces import get as get_cs

    entry = get_cs(cs_name)
    primaries = np.asarray(
        colour.RGB_COLOURSPACES[entry.primaries].primaries, dtype=float
    )
    return np.vstack([primaries, primaries[:1]])


# ---------------------------------------------------------------------------
# Cube views (3D scatters of the LUT in input or output coordinates).
# ---------------------------------------------------------------------------

def cube_sculpture(
    grid_input: np.ndarray,
    grid_output: np.ndarray,
    *,
    color_by: np.ndarray | None = None,
    color_label: str = "",
    cmap: str = "magma",
    title: str = "LUT cube — cells colored by output RGB",
) -> Figure:
    """3D scatter of the cube in input coordinates.

    If ``color_by`` is None, points are colored by their output RGB —
    the LUT renders itself. If ``color_by`` is provided (e.g., ΔITP
    per cell), points are colored by that scalar via ``cmap``.
    """
    fig = plt.figure(figsize=(11, 9), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d", facecolor=BG)
    if color_by is None:
        colors = np.clip(grid_output, 0.0, 1.0)
        sc = ax.scatter(
            grid_input[:, 0], grid_input[:, 1], grid_input[:, 2],
            c=colors, s=22, alpha=0.92, edgecolors="none", depthshade=False,
        )
    else:
        sc = ax.scatter(
            grid_input[:, 0], grid_input[:, 1], grid_input[:, 2],
            c=np.asarray(color_by).ravel(), cmap=cmap,
            s=22, alpha=0.92, edgecolors="none", depthshade=False,
        )
        cbar = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.12)
        cbar.set_label(color_label or "scalar", color=FG)
        cbar.ax.tick_params(colors=FG)
        cbar.outline.set_edgecolor("#555555")
    ax.set_xlabel("R in", color=FG, labelpad=8)
    ax.set_ylabel("G in", color=FG, labelpad=8)
    ax.set_zlabel("B in", color=FG, labelpad=8)
    ax.set_title(title, color=HI, pad=20, fontsize=14)
    _setup_3d(ax)
    ax.view_init(elev=22, azim=-58)
    _fill_3d(fig, has_cbar=color_by is not None)
    return fig


def cube_deformation(
    grid_input: np.ndarray, grid_output: np.ndarray
) -> Figure:
    """Side-by-side: input-position cube vs output-position cube.

    The gap between the two is the LUT's deformation. Both panels use
    output RGB as the point color, so chromatic location is consistent
    across the comparison.
    """
    colors = np.clip(grid_output, 0.0, 1.0)
    fig = plt.figure(figsize=(15, 7), facecolor=BG)
    ax1 = fig.add_subplot(121, projection="3d", facecolor=BG)
    ax1.scatter(grid_input[:, 0], grid_input[:, 1], grid_input[:, 2],
                c=colors, s=18, alpha=0.9, edgecolors="none", depthshade=False)
    ax1.set_title("input positions", color=HI, pad=14, fontsize=12)
    ax2 = fig.add_subplot(122, projection="3d", facecolor=BG)
    ax2.scatter(colors[:, 0], colors[:, 1], colors[:, 2],
                c=colors, s=18, alpha=0.9, edgecolors="none", depthshade=False)
    ax2.set_title("output positions", color=HI, pad=14, fontsize=12)
    for ax in (ax1, ax2):
        ax.set_xlabel("R", color=FG, labelpad=6)
        ax.set_ylabel("G", color=FG, labelpad=6)
        ax.set_zlabel("B", color=FG, labelpad=6)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
        _setup_3d(ax)
        ax.view_init(elev=22, azim=-58)
    fig.suptitle("LUT deformation: where does each input land?",
                 color=HI, fontsize=14, y=0.98)
    _fill_3d(fig, has_cbar=False)
    return fig


def cube_edges(
    table: np.ndarray, grid_input: np.ndarray, n: int
) -> Figure:
    """Trace the 12 saturated cube edges in input vs output coordinates."""
    sweep = np.arange(n)
    pin_pairs = [(0, 0), (0, n - 1), (n - 1, 0), (n - 1, n - 1)]
    edges: list[np.ndarray] = []
    for b, g in pin_pairs:
        edges.append(np.stack([np.full(n, b), np.full(n, g), sweep], axis=-1))
    for b, r in pin_pairs:
        edges.append(np.stack([np.full(n, b), sweep, np.full(n, r)], axis=-1))
    for g, r in pin_pairs:
        edges.append(np.stack([sweep, np.full(n, g), np.full(n, r)], axis=-1))

    flat_table = table.reshape(n ** 3, 3)
    def flat_idx(bgr):
        return bgr[..., 0] * n * n + bgr[..., 1] * n + bgr[..., 2]

    fig = plt.figure(figsize=(15, 7), facecolor=BG)
    ax1 = fig.add_subplot(121, projection="3d", facecolor=BG)
    ax2 = fig.add_subplot(122, projection="3d", facecolor=BG)
    for edge in edges:
        idx = flat_idx(edge)
        in_pos = grid_input[idx]
        out_pos = np.clip(flat_table[idx], 0.0, 1.0)
        ax1.plot(in_pos[:, 0], in_pos[:, 1], in_pos[:, 2],
                 color="#aaaaaa", lw=0.8, alpha=0.6)
        ax1.scatter(in_pos[:, 0], in_pos[:, 1], in_pos[:, 2],
                    c=out_pos, s=22, alpha=0.95, edgecolors="none",
                    depthshade=False)
        ax2.plot(out_pos[:, 0], out_pos[:, 1], out_pos[:, 2],
                 color="#aaaaaa", lw=0.8, alpha=0.6)
        ax2.scatter(out_pos[:, 0], out_pos[:, 1], out_pos[:, 2],
                    c=out_pos, s=22, alpha=0.95, edgecolors="none",
                    depthshade=False)
    ax1.set_title("cube edges — input coordinates", color=HI, pad=14, fontsize=12)
    ax2.set_title("cube edges — output coordinates", color=HI, pad=14, fontsize=12)
    for ax in (ax1, ax2):
        ax.set_xlabel("R", color=FG, labelpad=6)
        ax.set_ylabel("G", color=FG, labelpad=6)
        ax.set_zlabel("B", color=FG, labelpad=6)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
        _setup_3d(ax)
        ax.view_init(elev=22, azim=-58)
    fig.suptitle("Saturated cube edges — the canonical hue+saturation cycle",
                 color=HI, fontsize=14, y=0.98)
    _fill_3d(fig, has_cbar=False)
    return fig


# ---------------------------------------------------------------------------
# Transfer-curve views (1D per-axis slices of the cube table).
# ---------------------------------------------------------------------------

def transfer_curves(
    table: np.ndarray, n: int,
    *,
    violation_marks: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
) -> Figure:
    """Per-axis transfer curves through the cube center.

    Each panel sweeps one input channel with the other two held at
    0.5, plotting R/G/B output. If ``violation_marks`` is provided
    (one boolean array per panel, length n-1), monotonicity violations
    are marked in red.
    """
    mid = n // 2
    axis_codes = np.linspace(0.0, 1.0, n)
    setups = [
        ("R", table[mid, mid, :, :], RED),
        ("G", table[mid, :, mid, :], GREEN),
        ("B", table[:, mid, mid, :], BLUE),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor=BG, layout="constrained")
    for i, (ax, (label, samples, axis_color)) in enumerate(zip(axes, setups)):
        ax.set_facecolor(BG)
        ax.plot(axis_codes, samples[:, 0], color=RED, lw=2.2, label="R out")
        ax.plot(axis_codes, samples[:, 1], color=GREEN, lw=2.2, label="G out")
        ax.plot(axis_codes, samples[:, 2], color=BLUE, lw=2.2, label="B out")
        ax.plot([0, 1], [0, 1], color="#444444", lw=1, ls="--", label="identity")
        if violation_marks is not None:
            mask = violation_marks[i]
            if mask.any():
                xs = axis_codes[1:][mask]
                ys = samples[1:, i][mask]
                ax.scatter(xs, ys, s=60, marker="x", color="#ff3366",
                           label="monotonicity violation", zorder=5)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel(f"{label} in  (other channels = 0.5)", color=FG)
        ax.set_ylabel("output", color=FG)
        ax.set_title(f"{label} sweep", color=axis_color, fontsize=13, pad=8)
        _setup_2d(ax)
        ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                  loc="upper left", fontsize=9)
    fig.suptitle("Per-axis transfer curves through the cube center",
                 color=HI, fontsize=14)
    return fig


def density_transfer_curves(table: np.ndarray, n: int) -> Figure:
    """Density-domain transfer curves: per-axis sweeps + the neutral ramp.

    Four panels in a 2×2 grid:

    - **Top row** (R, G, B sweeps): vary one input channel while the
      other two are held at 0.5. Diagnostic of channel-isolated
      behavior — what does pushing R alone do to the system?
    - **Bottom row** (neutral sweep): vary R=G=B together; this is
      the **canonical film characteristic curve** colorists recognize
      from datasheets. The shoulder, linear segment, and toe shape
      are all visible here in a way the per-axis panels obscure
      (especially for log inputs, where pinning other channels at
      0.5 already sits above scene gray and crushes the visible
      range of the sweep).

    Density convention: D = -log₁₀(output) with the Y axis inverted
    so D=0 (white) sits at top and high D (black) sits at the bottom,
    matching film datasheet conventions.
    """
    mid = n // 2
    axis_codes = np.linspace(0.0, 1.0, n)
    floor = 1.0e-4
    # Neutral diagonal: stack the R=G=B samples one per diagonal cell.
    neutral_samples = np.stack([table[i, i, i, :] for i in range(n)], axis=0)
    setups = [
        ("R", table[mid, mid, :, :], RED, "other channels = 0.5"),
        ("G", table[mid, :, mid, :], GREEN, "other channels = 0.5"),
        ("B", table[:, mid, mid, :], BLUE, "other channels = 0.5"),
        ("neutral (R=G=B)", neutral_samples, HI, "the canonical D-vs-input curve"),
    ]
    fig, axes_2d = plt.subplots(2, 2, figsize=(13, 10), facecolor=BG, layout="constrained")
    axes = axes_2d.flat
    # Compute a shared Y range across all panels so the curves are
    # visually comparable.
    all_densities = []
    for _, samples, _, _ in setups:
        d = -np.log10(np.clip(samples, floor, 1.0))
        all_densities.append(d)
    y_max = max(3.5, float(max(d.max() for d in all_densities)) * 1.05)

    for ax, (label, samples, axis_color, subtitle) in zip(axes, setups):
        ax.set_facecolor(BG)
        density = -np.log10(np.clip(samples, floor, 1.0))
        ax.plot(axis_codes, density[:, 0], color=RED, lw=2.2, label="D-R")
        ax.plot(axis_codes, density[:, 1], color=GREEN, lw=2.2, label="D-G")
        ax.plot(axis_codes, density[:, 2], color=BLUE, lw=2.2, label="D-B")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, y_max)
        ax.invert_yaxis()
        ax.set_xlabel(f"{label} input code   ({subtitle})", color=FG)
        ax.set_ylabel("D = -log₁₀(output)", color=FG)
        ax.set_title(f"{label} sweep", color=axis_color, fontsize=13, pad=8)
        _setup_2d(ax)
        ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                  loc="upper right", fontsize=9)
    fig.suptitle("Density-domain transfer curves",
                 color=HI, fontsize=14)
    return fig


def rg_plane_slices(table: np.ndarray, n: int) -> Figure:
    """R-G plane slices through the cube at varying B values."""
    n_slices = min(8, n)
    indices = np.linspace(0, n - 1, n_slices, dtype=int)
    fig, axes = plt.subplots(1, n_slices, figsize=(2.0 * n_slices, 2.7),
                             facecolor=BG, layout="constrained")
    axes = np.atleast_1d(axes)
    for idx, ax in zip(indices, axes):
        slice_img = np.clip(table[idx, :, :, :], 0.0, 1.0)
        ax.imshow(slice_img, origin="lower", extent=(0, 1, 0, 1), interpolation="bilinear")
        ax.set_title(f"B = {idx / (n - 1):.2f}", color=FG, fontsize=10)
        ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
        ax.tick_params(colors=FG, length=2)
        for spine in ax.spines.values():
            spine.set_color("#555555")
    axes[0].set_xlabel("R", color=FG)
    axes[0].set_ylabel("G", color=FG)
    fig.suptitle("R-G plane slices through the cube", color=HI, fontsize=14)
    return fig


# ---------------------------------------------------------------------------
# Diagnostics.
# ---------------------------------------------------------------------------

def jacobian_condition_3d(
    log_cond_field: np.ndarray, n: int
) -> Figure:
    """3D scatter of interior cube cells colored by log10(cond J)."""
    interior = np.linspace(0.0, 1.0, n)[1:-1]
    BB, GG, RR = np.meshgrid(interior, interior, interior, indexing="ij")
    fig = plt.figure(figsize=(11, 9), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d", facecolor=BG)
    sc = ax.scatter(RR.ravel(), GG.ravel(), BB.ravel(),
                    c=log_cond_field.ravel(), cmap="magma",
                    s=14, alpha=0.85, edgecolors="none", depthshade=False)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.55, pad=0.12)
    cbar.set_label("log₁₀(cond J)", color=FG)
    cbar.ax.tick_params(colors=FG)
    cbar.outline.set_edgecolor("#555555")
    ax.set_xlabel("R in", color=FG, labelpad=8)
    ax.set_ylabel("G in", color=FG, labelpad=8)
    ax.set_zlabel("B in", color=FG, labelpad=8)
    ax.set_title("Local Jacobian condition number (cube smoothness)",
                 color=HI, pad=20, fontsize=14)
    _setup_3d(ax)
    ax.view_init(elev=22, azim=-58)
    _fill_3d(fig, has_cbar=True)
    return fig


def output_histograms(grid_output: np.ndarray) -> Figure:
    """Per-channel output distributions with clipping markers and CDF overlay."""
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), facecolor=BG, layout="constrained")
    for ax, ch, col, name in zip(axes, range(3), (RED, GREEN, BLUE), ("R", "G", "B")):
        ax.set_facecolor(BG)
        values = grid_output[:, ch]
        ax.hist(values, bins=80, range=(-0.02, 1.02),
                color=col, alpha=0.85, edgecolor="none")
        clipped_lo = int(np.sum(values <= 1e-6))
        clipped_hi = int(np.sum(values >= 1.0 - 1e-6))
        ax.axvline(0.0, color=WARN, lw=1.0, ls=":")
        ax.axvline(1.0, color=WARN, lw=1.0, ls=":")
        ax2 = ax.twinx()
        sorted_vals = np.sort(values)
        ax2.plot(sorted_vals, np.linspace(0, 1, sorted_vals.size),
                 color="#ffffff", lw=1.0, alpha=0.8)
        ax2.set_ylim(0, 1)
        ax2.set_ylabel("CDF", color="#cccccc", fontsize=9)
        ax2.tick_params(colors="#cccccc", labelsize=8)
        for spine in ax2.spines.values():
            spine.set_color("#555555")
        ax.set_xlim(-0.02, 1.02)
        ax.set_xlabel(f"{name} output", color=FG)
        ax.set_ylabel("count", color=FG)
        ax.set_title(f"{name}    clipped lo: {clipped_lo}   hi: {clipped_hi}",
                     color=col, fontsize=12, pad=6)
        _setup_2d(ax)
    fig.suptitle("Per-channel output distributions (with CDF + clipping markers)",
                 color=HI, fontsize=13)
    return fig


# ---------------------------------------------------------------------------
# OkLab / perceptual views.
# ---------------------------------------------------------------------------

def oklab_gamut_compare(
    grid_input: np.ndarray, grid_output: np.ndarray,
    in_cs: str, out_cs: str,
) -> Figure:
    """Side-by-side OkLab point clouds for the input and output cubes.

    Both panels share axis limits chosen to frame the **output cube**
    with a 30% margin. Input samples that fall outside this frame
    (common with wide input gamuts like V-Gamut whose primaries lie
    outside the visible spectral locus) get clipped from display —
    OkLab is calibrated for in-locus colors, so those out-of-frame
    coordinates wouldn't be meaningful anyway. The framing makes the
    compression magnitude visually comparable across input spaces.
    """
    lab_in = _to_oklab(grid_input, in_cs)
    lab_out = _to_oklab(grid_output, out_cs)
    colors_in = np.clip(grid_input, 0.0, 1.0)
    colors_out = np.clip(grid_output, 0.0, 1.0)
    fig = plt.figure(figsize=(15, 7), facecolor=BG)
    ax1 = fig.add_subplot(121, projection="3d", facecolor=BG)
    ax2 = fig.add_subplot(122, projection="3d", facecolor=BG)
    ax1.scatter(lab_in[:, 1], lab_in[:, 2], lab_in[:, 0],
                c=colors_in, s=10, alpha=0.7, edgecolors="none", depthshade=False)
    ax2.scatter(lab_out[:, 1], lab_out[:, 2], lab_out[:, 0],
                c=colors_out, s=10, alpha=0.7, edgecolors="none", depthshade=False)
    # In-axes labels rather than pad-above titles to avoid colliding
    # with the multi-line suptitle.
    ax1.text2D(0.02, 0.97, f"input  ({in_cs})",
               transform=ax1.transAxes, color=HI, fontsize=12,
               ha="left", va="top")
    ax2.text2D(0.02, 0.97, f"output  ({out_cs})",
               transform=ax2.transAxes, color=HI, fontsize=12,
               ha="left", va="top")

    # Frame on the OUTPUT cube + 30% margin per axis. Output is bounded
    # by the chosen output color space (sRGB, Rec.2020, …) and always
    # lives at meaningful OkLab coordinates; framing on input fails
    # whenever the input gamut extends outside the visible locus.
    margin_frac = 0.30
    out_a_min, out_a_max = float(lab_out[:, 1].min()), float(lab_out[:, 1].max())
    out_b_min, out_b_max = float(lab_out[:, 2].min()), float(lab_out[:, 2].max())
    out_L_min, out_L_max = float(lab_out[:, 0].min()), float(lab_out[:, 0].max())
    a_pad = margin_frac * max(out_a_max - out_a_min, 1e-3)
    b_pad = margin_frac * max(out_b_max - out_b_min, 1e-3)
    L_pad = margin_frac * max(out_L_max - out_L_min, 1e-3)
    a_lo, a_hi = out_a_min - a_pad, out_a_max + a_pad
    b_lo, b_hi = out_b_min - b_pad, out_b_max + b_pad
    L_lo, L_hi = out_L_min - L_pad, out_L_max + L_pad

    # If input is much wider than the output, compute how many input
    # samples land outside the displayed frame — useful disclosure when
    # the input gamut extends beyond the visible locus.
    in_a, in_b, in_L = lab_in[:, 1], lab_in[:, 2], lab_in[:, 0]
    in_in_frame = (
        (in_a >= a_lo) & (in_a <= a_hi)
        & (in_b >= b_lo) & (in_b <= b_hi)
        & (in_L >= L_lo) & (in_L <= L_hi)
    )
    n_out = int((~in_in_frame).sum())
    suptitle = "LUT gamut compression in OkLab  (frame: output cube + 30%)"
    if n_out > 0:
        suptitle += f"\n{n_out} / {len(in_in_frame)} input samples outside frame (clipped from view)"

    for ax in (ax1, ax2):
        ax.set_xlabel("a*", color=FG, labelpad=6)
        ax.set_ylabel("b*", color=FG, labelpad=6)
        ax.set_zlabel("L*", color=FG, labelpad=6)
        ax.set_xlim(a_lo, a_hi); ax.set_ylim(b_lo, b_hi); ax.set_zlim(L_lo, L_hi)
        _setup_3d(ax)
        ax.view_init(elev=18, azim=-58)
    fig.suptitle(suptitle, color=HI, fontsize=13, y=0.98)
    _fill_3d(fig, has_cbar=False, top=0.91 if n_out > 0 else 0.94)
    return fig


def oklab_ab_slices(grid_output: np.ndarray, out_cs: str) -> Figure:
    """LUT output projected into OkLab, binned by L* (8 panels)."""
    lab = _to_oklab(grid_output, out_cs)
    L = lab[:, 0]
    colors = np.clip(grid_output, 0.0, 1.0)
    n_bins = 8
    L_edges = np.linspace(L.min(), L.max(), n_bins + 1)
    fig, axes = plt.subplots(2, 4, figsize=(16, 8), facecolor=BG, layout="constrained")
    for i, ax in enumerate(axes.flat):
        ax.set_facecolor(BG)
        lo, hi = L_edges[i], L_edges[i + 1]
        mask = (L >= lo) & (L < hi if i < n_bins - 1 else L <= hi)
        if np.any(mask):
            ax.scatter(lab[mask, 1], lab[mask, 2],
                       c=colors[mask], s=8, alpha=0.7, edgecolors="none")
        ax.axhline(0, color="#555555", lw=0.6)
        ax.axvline(0, color="#555555", lw=0.6)
        ax.set_xlim(-0.4, 0.4); ax.set_ylim(-0.4, 0.4); ax.set_aspect("equal")
        ax.set_title(f"L* ∈ [{lo:.2f}, {hi:.2f}]", color=FG, fontsize=10)
        ax.tick_params(colors=FG, labelsize=8)
        for spine in ax.spines.values():
            spine.set_color("#555555")
    fig.suptitle("OkLab a*–b* slices of the LUT output",
                 color=HI, fontsize=14)
    fig.supxlabel("a* (red–green)", color=FG)
    fig.supylabel("b* (yellow–blue)", color=FG)
    return fig


def hue_twist_oklab(
    grid_input: np.ndarray, grid_output: np.ndarray,
    in_cs: str, out_cs: str,
) -> Figure:
    """Input vs output OkLab hue diagram, binned by input chroma."""
    lab_in = _to_oklab(grid_input, in_cs)
    lab_out = _to_oklab(grid_output, out_cs)
    h_in = np.degrees(np.arctan2(lab_in[:, 2], lab_in[:, 1]))
    h_out = np.degrees(np.arctan2(lab_out[:, 2], lab_out[:, 1]))
    c_in = np.sqrt(lab_in[:, 1] ** 2 + lab_in[:, 2] ** 2)
    c_max = float(c_in.max()) if c_in.size else 0.0
    if c_max <= 0.0:
        c_max = 1.0
    bands = [(0.20, 0.35), (0.35, 0.50), (0.50, 0.70), (0.70, 1.001)]
    band_colors = plt.cm.plasma(np.linspace(0.2, 0.95, len(bands)))
    fig, ax = plt.subplots(figsize=(9, 9), facecolor=BG, layout="constrained")
    ax.set_facecolor(BG)
    ax.plot([-180, 180], [-180, 180], color="#555555", lw=1.0, ls="--", label="identity")
    ax.plot([-180, 180], [180, 540], color="#333333", lw=0.6, ls=":")
    ax.plot([-180, 180], [-540, -180], color="#333333", lw=0.6, ls=":")
    for (lo, hi), col in zip(bands, band_colors):
        mask = (c_in >= lo * c_max) & (c_in < hi * c_max)
        if not np.any(mask):
            continue
        ax.scatter(h_in[mask], h_out[mask], color=[col],
                   s=10, alpha=0.55, edgecolors="none",
                   label=f"chroma {lo * c_max:.02f}–{hi * c_max:.02f}")
    ax.set_xlim(-180, 180); ax.set_ylim(-180, 180)
    ax.set_xticks(np.arange(-180, 181, 60))
    ax.set_yticks(np.arange(-180, 181, 60))
    ax.set_xlabel("input hue (OkLab)  [°]", color=FG)
    ax.set_ylabel("output hue (OkLab)  [°]", color=FG)
    ax.set_title("Hue-twist diagram (OkLab)", color=HI, fontsize=14, pad=10)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper left", fontsize=9)
    ax.set_aspect("equal")
    return fig


def oklab_displacement(
    grid_input: np.ndarray, grid_output: np.ndarray,
    in_cs: str, out_cs: str,
) -> Figure:
    """Quiver of OkLab a*-b* displacement at three lightness bands."""
    lab_in = _to_oklab(grid_input, in_cs)
    lab_out = _to_oklab(grid_output, out_cs)
    L_mid = 0.5 * (lab_in[:, 0] + lab_out[:, 0])
    L_lo, L_hi = float(L_mid.min()), float(L_mid.max())
    if L_hi <= L_lo:
        L_hi = L_lo + 1e-6
    edges = np.linspace(L_lo, L_hi, 4)
    band_titles = (
        f"L* ∈ [{edges[0]:.2f}, {edges[1]:.2f}]   (shadows)",
        f"L* ∈ [{edges[1]:.2f}, {edges[2]:.2f}]   (midtones)",
        f"L* ∈ [{edges[2]:.2f}, {edges[3]:.2f}]   (highlights)",
    )
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), facecolor=BG, layout="constrained")
    for i, (ax, title) in enumerate(zip(axes, band_titles)):
        ax.set_facecolor(BG)
        lo, hi = edges[i], edges[i + 1]
        mask = (L_mid >= lo) & (L_mid <= hi)
        if np.any(mask):
            u = lab_out[mask, 1] - lab_in[mask, 1]
            v = lab_out[mask, 2] - lab_in[mask, 2]
            colors = np.clip(grid_output[mask], 0.0, 1.0)
            ax.quiver(lab_in[mask, 1], lab_in[mask, 2], u, v,
                      color=colors, angles="xy", scale_units="xy", scale=1.0,
                      width=0.0035, alpha=0.78)
        ax.axhline(0, color="#555555", lw=0.6)
        ax.axvline(0, color="#555555", lw=0.6)
        ax.set_xlim(-0.4, 0.4); ax.set_ylim(-0.4, 0.4); ax.set_aspect("equal")
        ax.set_title(title, color=FG, fontsize=11)
        ax.set_xlabel("a*  (red–green)", color=FG)
        ax.set_ylabel("b*  (yellow–blue)", color=FG)
        _setup_2d(ax)
    fig.suptitle("OkLab displacement: where the LUT sends each input chromaticity",
                 color=HI, fontsize=14)
    return fig


def chromaticity_1931(
    grid_output: np.ndarray, in_cs: str, out_cs: str,
    *, locus_xy: np.ndarray | None = None,
) -> Figure:
    """CIE 1931 chromaticity with spectral locus, gamut triangles, LUT footprint."""
    from spektrafilm_lut_creator.color_spaces import to_xyz

    xyz = to_xyz(grid_output, out_cs)
    xy = np.asarray(colour.XYZ_to_xy(xyz), dtype=float)
    if locus_xy is None:
        cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
        wavelengths = np.arange(380, 781, 1)
        locus_xyz = np.asarray(cmfs[wavelengths], dtype=float)
        locus_xy = np.asarray(colour.XYZ_to_xy(locus_xyz), dtype=float)
    in_tri = _gamut_triangle_xy(in_cs)
    out_tri = _gamut_triangle_xy(out_cs)

    fig, ax = plt.subplots(figsize=(9, 9), facecolor=BG, layout="constrained")
    ax.set_facecolor(BG)
    ax.plot(locus_xy[:, 0], locus_xy[:, 1], color="#aaaaaa", lw=1.4, zorder=2)
    ax.plot([locus_xy[-1, 0], locus_xy[0, 0]],
            [locus_xy[-1, 1], locus_xy[0, 1]],
            color="#777777", lw=1.0, ls="--", zorder=2)
    ax.plot(in_tri[:, 0], in_tri[:, 1], color="#66ffee", lw=1.4, ls="--",
            alpha=0.85, zorder=3, label=f"input gamut: {in_cs}")
    ax.plot(out_tri[:, 0], out_tri[:, 1], color="#ffee66", lw=1.6, alpha=0.95,
            zorder=3, label=f"output gamut: {out_cs}")
    ax.scatter(xy[:, 0], xy[:, 1], c=np.clip(grid_output, 0.0, 1.0),
               s=8, alpha=0.65, edgecolors="none", zorder=4)
    ax.set_xlim(-0.05, 0.85); ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=FG); ax.set_ylabel("y", color=FG)
    ax.set_title("CIE 1931 chromaticity — LUT output footprint",
                 color=HI, fontsize=14, pad=12)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper right", fontsize=9)
    return fig


# ---------------------------------------------------------------------------
# Diagnostic plots specific to model-side tests.
# ---------------------------------------------------------------------------

def offgrid_error_scatter(
    samples_encoded: np.ndarray,
    delta_field: np.ndarray,
    *, title: str = "Off-grid ΔITP", cbar_label: str = "ΔITP",
) -> Figure:
    """3D scatter of off-grid samples colored by per-sample error.

    Highlights the cube regions where the LUT's interpolated value
    drifts most from the reference pipeline.
    """
    fig = plt.figure(figsize=(11, 9), facecolor=BG)
    ax = fig.add_subplot(111, projection="3d", facecolor=BG)
    sc = ax.scatter(samples_encoded[:, 0], samples_encoded[:, 1], samples_encoded[:, 2],
                    c=delta_field, cmap="viridis",
                    s=4, alpha=0.55, edgecolors="none", depthshade=False)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.6, pad=0.12)
    # Scatter dots are semi-transparent so overlapping samples read; the
    # colorbar should NOT inherit that alpha — restore full saturation
    # so the legend's hue mapping is unambiguous.
    cbar.solids.set_alpha(1.0)
    cbar.solids.set_edgecolor("face")
    cbar.set_label(cbar_label, color=FG)
    cbar.ax.tick_params(colors=FG)
    cbar.outline.set_edgecolor("#555555")
    ax.set_xlabel("R in", color=FG, labelpad=8)
    ax.set_ylabel("G in", color=FG, labelpad=8)
    ax.set_zlabel("B in", color=FG, labelpad=8)
    ax.set_title(title, color=HI, pad=20, fontsize=14)
    _setup_3d(ax)
    ax.view_init(elev=22, azim=-58)
    _fill_3d(fig, has_cbar=True)
    return fig


def planckian_path(
    cct: np.ndarray, xy_out: np.ndarray, locus_xy: np.ndarray, out_cs: str,
) -> Figure:
    """The Planckian / daylight sweep traced on the 1931 chromaticity plot."""
    fig, ax = plt.subplots(figsize=(9, 9), facecolor=BG, layout="constrained")
    ax.set_facecolor(BG)
    ax.plot(locus_xy[:, 0], locus_xy[:, 1], color="#888888", lw=1.2)
    ax.plot([locus_xy[-1, 0], locus_xy[0, 0]],
            [locus_xy[-1, 1], locus_xy[0, 1]],
            color="#666666", lw=1.0, ls="--")
    out_tri = _gamut_triangle_xy(out_cs)
    ax.plot(out_tri[:, 0], out_tri[:, 1], color="#ffee66", lw=1.6, alpha=0.95,
            label=f"output gamut: {out_cs}")
    sc = ax.scatter(xy_out[:, 0], xy_out[:, 1], c=cct, cmap="plasma",
                    s=60, edgecolors="white", linewidths=0.5, zorder=4)
    ax.plot(xy_out[:, 0], xy_out[:, 1], color="#cccccc", lw=0.8, alpha=0.6, zorder=3)
    cbar = fig.colorbar(sc, ax=ax, shrink=0.7, pad=0.04)
    cbar.set_label("CCT [K]", color=FG)
    cbar.ax.tick_params(colors=FG)
    cbar.outline.set_edgecolor("#555555")
    ax.set_xlim(-0.05, 0.85); ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=FG); ax.set_ylabel("y", color=FG)
    ax.set_title("Planckian / daylight sweep — output chromaticity per CCT",
                 color=HI, fontsize=14, pad=12)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper right", fontsize=9)
    return fig


def highlight_rolloff_curves(
    in_codes: np.ndarray,
    out_per_channel: list[np.ndarray],
    *, title: str = "Highlight rolloff",
) -> Figure:
    """Three panels: per-channel transfer curve + 2nd derivative beneath.

    ``out_per_channel`` is a list of three arrays of shape ``(n, 3)``
    — one per swept input channel — containing the encoded RGB output
    at each ramp sample.
    """
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), facecolor=BG,
                             gridspec_kw={"height_ratios": [3, 1]},
                             layout="constrained", sharex="col")
    for col, (label, out, axis_color) in enumerate(zip(
            ("R", "G", "B"), out_per_channel, (RED, GREEN, BLUE))):
        top, bot = axes[0, col], axes[1, col]
        top.set_facecolor(BG); bot.set_facecolor(BG)
        top.plot(in_codes, out[:, 0], color=RED, lw=2.0, label="R out")
        top.plot(in_codes, out[:, 1], color=GREEN, lw=2.0, label="G out")
        top.plot(in_codes, out[:, 2], color=BLUE, lw=2.0, label="B out")
        top.set_xlim(in_codes[0], in_codes[-1])
        top.set_ylim(0, 1.05)
        top.set_xlabel(f"{label} input code", color=FG)
        top.set_ylabel("output", color=FG)
        top.set_title(f"{label} ramp", color=axis_color, fontsize=12, pad=6)
        _setup_2d(top)
        top.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                   loc="lower right", fontsize=8)

        # Second derivative of the swept channel.
        y = out[:, col]
        if y.size >= 3:
            d2 = y[2:] - 2.0 * y[1:-1] + y[:-2]
            bot.plot(in_codes[1:-1], d2, color=axis_color, lw=1.6)
        bot.axhline(0, color="#555555", lw=0.6)
        bot.set_xlim(in_codes[0], in_codes[-1])
        bot.set_xlabel(f"{label} input code", color=FG)
        bot.set_ylabel("d²/dE²", color=FG)
        _setup_2d(bot)
    fig.suptitle(title, color=HI, fontsize=14)
    return fig


def black_toe_curves(
    in_codes: np.ndarray, out_rgb: np.ndarray,
) -> Figure:
    """Linear and log-scale views of the transfer near zero.

    ``in_codes`` shape ``(n,)`` (the neutral ramp from 0 to 0.05).
    ``out_rgb`` shape ``(n, 3)``.
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), facecolor=BG, layout="constrained")
    for ax_idx, (ax, scale) in enumerate(zip(axes, ("linear", "log"))):
        ax.set_facecolor(BG)
        ax.plot(in_codes, out_rgb[:, 0], color=RED, lw=2.0, marker="o", ms=4, label="R out")
        ax.plot(in_codes, out_rgb[:, 1], color=GREEN, lw=2.0, marker="o", ms=4, label="G out")
        ax.plot(in_codes, out_rgb[:, 2], color=BLUE, lw=2.0, marker="o", ms=4, label="B out")
        if scale == "log":
            ax.set_xscale("symlog", linthresh=1e-3)
            ax.set_yscale("symlog", linthresh=1e-3)
        ax.set_xlabel("neutral input code", color=FG)
        ax.set_ylabel("output", color=FG)
        ax.set_title(f"Near-zero transfer ({scale} scale)",
                     color=HI, fontsize=12, pad=8)
        _setup_2d(ax)
        ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                  loc="upper left", fontsize=9)
    fig.suptitle("Black-toe behavior", color=HI, fontsize=14)
    return fig


def dynamic_range_curve(
    stops: np.ndarray,
    output_y: np.ndarray,
    encoded_clip_mask: np.ndarray,
    stats: dict,
    *,
    in_cs: str,
    out_cs: str,
    slope_threshold: float = 0.10,
) -> Figure:
    """Density vs scene-linear log E (stops), the canonical film
    characteristic plot.

    Three layers, top to bottom:

    1. The main curve — output density ``D = -log10(Y)`` vs input
       stops above middle gray. Y axis inverted so D=0 (white) sits
       at the top, high D (black) at the bottom — film datasheet
       convention.
    2. **Encoding-clip vertical lines**: dashed bars marking where
       the input encoding can no longer represent the scene-linear
       value. Stops outside these bars are "the input encoding's
       fault" if rendering is flat.
    3. **Toe / shoulder shading**: light gray bands at the bottom
       and top of the rendered range where slope falls below the
       active threshold. These are the model's compression
       decisions.

    A small text box prints the summary numbers (encoded range,
    active range, collapsed toe/shoulder) so the figure is
    self-contained.
    """
    stops = np.asarray(stops, dtype=float).ravel()
    output_y = np.asarray(output_y, dtype=float).ravel()
    encoded_clip_mask = np.asarray(encoded_clip_mask, dtype=bool).ravel()
    density = -np.log10(np.clip(output_y, 1e-4, None))

    fig, ax = plt.subplots(figsize=(12, 7), facecolor=BG, layout="constrained")
    ax.set_facecolor(BG)

    # Toe / shoulder shading inside the encoded range.
    encoded_ok = ~encoded_clip_mask
    enc_idx = np.where(encoded_ok)[0]
    if enc_idx.size >= 2:
        enc_lo_x, enc_hi_x = stops[enc_idx[0]], stops[enc_idx[-1]]
        toe_n = int(round(stats.get("toe_collapsed_stops", 0.0) /
                          max((stops[1] - stops[0]), 1e-9)))
        shoulder_n = int(round(stats.get("shoulder_collapsed_stops", 0.0) /
                               max((stops[1] - stops[0]), 1e-9)))
        if toe_n > 0:
            toe_hi = stops[min(enc_idx[0] + toe_n, len(stops) - 1)]
            ax.axvspan(enc_lo_x, toe_hi, color="#666666", alpha=0.18,
                       label=f"toe collapse: {stats['toe_collapsed_stops']:.1f} stops")
        if shoulder_n > 0:
            shoulder_lo = stops[max(enc_idx[-1] - shoulder_n, 0)]
            ax.axvspan(shoulder_lo, enc_hi_x, color="#888866", alpha=0.18,
                       label=f"shoulder collapse: {stats['shoulder_collapsed_stops']:.1f} stops")

        # Encoded-range markers.
        ax.axvline(enc_lo_x, color=WARN, lw=1.0, ls="--", alpha=0.7)
        ax.axvline(enc_hi_x, color=WARN, lw=1.0, ls="--", alpha=0.7,
                   label="input encoding clip")

    # Main curve.
    ax.plot(stops, density, color=HI, lw=2.4, zorder=5)
    # Mark where input is clipped — render those segments dimmer.
    if np.any(encoded_clip_mask):
        ax.plot(stops[encoded_clip_mask], density[encoded_clip_mask],
                color=DIM, lw=1.6, marker="x", ms=4, ls="None", zorder=4,
                label="encoded-clipped stops")

    # Reference line at middle gray.
    ax.axvline(0, color="#555555", lw=0.8, alpha=0.6)
    ax.text(0.05, 0.02, "middle gray", color=DIM, fontsize=9,
            transform=ax.get_xaxis_transform())

    ax.set_xlabel("scene-linear stops above middle gray  (log₂(linear / 0.18))",
                  color=FG)
    ax.set_ylabel("D = -log₁₀(output Y)   (film density convention)", color=FG)
    ax.set_ylim(0, max(3.5, float(density.max()) * 1.05))
    ax.invert_yaxis()
    ax.set_xlim(stops[0], stops[-1])
    _setup_2d(ax)

    # Headline summary in the upper-left of the plot — film-datasheet
    # vibe ("Effective: 5.3 stops").
    summary_lines = [
        f"input encoding range:   {stats.get('encoded_range_stops', 0):.1f} stops",
        f"active rendering range: {stats.get('active_range_stops', 0):.1f} stops",
        f"  toe collapsed:        {stats.get('toe_collapsed_stops', 0):.1f} stops",
        f"  shoulder collapsed:   {stats.get('shoulder_collapsed_stops', 0):.1f} stops",
        f"slope threshold:        {slope_threshold} D/stop",
    ]
    ax.text(0.02, 0.98, "\n".join(summary_lines),
            transform=ax.transAxes, color=FG, fontsize=10, family="monospace",
            va="top", ha="left",
            bbox=dict(facecolor="#1a1a1a", edgecolor="#555555",
                      alpha=0.92, boxstyle="round,pad=0.5"))

    ax.set_title(
        f"Dynamic range — {in_cs} → {out_cs}",
        color=HI, fontsize=14, pad=10,
    )
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
              loc="lower right", fontsize=9)
    return fig


def spectral_locus_envelope(
    out_cs: str,
    edges_output_xy: list[np.ndarray],
) -> Figure:
    """Output chromaticity of every input cube edge overlaid on the spectral locus.

    The 12 cube edges form the canonical hue circle in the input
    space; their output chromaticity envelope is the model's
    reachable gamut at maximum saturation. Compared against the
    spectral locus and the output primaries triangle, this reveals
    how much of the visible-color "rim" the model preserves.
    """
    cmfs = colour.MSDS_CMFS["CIE 1931 2 Degree Standard Observer"]
    wavelengths = np.arange(380, 781, 1)
    locus_xyz = np.asarray(cmfs[wavelengths], dtype=float)
    locus_xy = np.asarray(colour.XYZ_to_xy(locus_xyz), dtype=float)
    out_tri = _gamut_triangle_xy(out_cs)

    fig, ax = plt.subplots(figsize=(9, 9), facecolor=BG, layout="constrained")
    ax.set_facecolor(BG)
    ax.plot(locus_xy[:, 0], locus_xy[:, 1], color="#aaaaaa", lw=1.4, label="spectral locus")
    ax.plot([locus_xy[-1, 0], locus_xy[0, 0]],
            [locus_xy[-1, 1], locus_xy[0, 1]],
            color="#777777", lw=1.0, ls="--")
    ax.plot(out_tri[:, 0], out_tri[:, 1], color="#ffee66", lw=1.6, alpha=0.95,
            label=f"output gamut: {out_cs}")
    cmap = plt.cm.hsv(np.linspace(0, 1, len(edges_output_xy)))
    for col, xy in zip(cmap, edges_output_xy):
        ax.plot(xy[:, 0], xy[:, 1], color=col, lw=1.2, alpha=0.85)
    ax.set_xlim(-0.05, 0.85); ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=FG); ax.set_ylabel("y", color=FG)
    ax.set_title("Spectral-locus envelope — cube edges through the LUT",
                 color=HI, fontsize=14, pad=12)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper right", fontsize=9)
    return fig
