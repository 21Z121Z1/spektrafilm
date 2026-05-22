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

# ---------------------------------------------------------------------------
# Canonical typography (n090 §3 trust signals — figures of-a-piece).
# Suptitle = figure-level title; PANEL = inner-panel title.
# ---------------------------------------------------------------------------
SUPTITLE_FS = 14
PANEL_TITLE_FS = 12
SUPTITLE_PAD = 10
PANEL_TITLE_PAD = 8
IDENTITY_COLOR = "#555555"
IDENTITY_ALPHA = 0.7
FOOTER_FS = 8
FOOTER_COLOR = DIM
FOOTER_BAND_FRAC = 0.04
"""Fraction of figure height reserved for the version footer.

Sized so x-axis tick labels of the bottom subplot row can't bleed into
the band: at the suite's typical 9–10 inch tall figures and 160 DPI,
0.04 ≈ 0.4 inch ≈ 60 px of clear space — enough for a centered 8pt
footer with breathing room on either side."""
HEADER_BAND_FRAC = 0.08
"""Fraction of figure height reserved at the top for the suptitle.

When :func:`add_footer` clamps the constrained-layout rect to leave a
band free at the bottom for the version footer, the same rect's *top*
needs to be set explicitly too — otherwise matplotlib treats the rect
as the working area and tries to fit the suptitle inside it, with
nowhere to go above. The suptitle ends up flush with the figure's top
edge and overlaps with panel titles.

0.08 is sized to accommodate the suite's largest suptitle (two lines
at 14pt) on figures down to ~5 inches tall. Single-line suptitles
waste a couple of percent of the figure to whitespace, which is the
acceptable price for not having to thread "is your suptitle one or
two lines" through every viz function."""


def _identity_line(ax, *, label: str | None = "identity",
                   lo: float = 0.0, hi: float = 1.0) -> None:
    """Standard y=x reference line for 2D transfer plots.

    Centralizing the styling so every figure uses the same gray /
    dash style — no more drift between ``#444444`` and ``#555555``.
    """
    ax.plot([lo, hi], [lo, hi], color=IDENTITY_COLOR, lw=1.0, ls="--",
            alpha=IDENTITY_ALPHA, label=label, zorder=1)


def add_footer(fig, version: str) -> None:
    """Stamp the canonical ``spektrafilm <version>`` footer on a figure.

    Reserves :data:`FOOTER_BAND_FRAC` of the figure height as a clear
    band at the bottom, then places the version text centered in it.
    The reserve is applied through whichever layout system the figure
    uses:

    - **Constrained-layout figures** (every 2D figure in this module)
      have their layout engine's ``rect`` clamped to leave the bottom
      band free — subplots reflow upward and tick labels stop at the
      band's top edge instead of bleeding into the footer.
    - **Manually-laid-out figures** (the 3D scatters, which call
      :func:`_fill_3d`) get a bumped ``subplots_adjust(bottom=...)``
      instead, preserving the other margins ``_fill_3d`` set.

    Called from :func:`spektrafilm_lut_creator.qa.tests._save` so every
    saved figure carries the producing version automatically — a
    trust signal that survives the figure leaving its bundle (n090 §3).
    """
    engine = fig.get_layout_engine()
    if engine is not None:
        # Constrained layout: clamp the subplot rect on *both* sides so
        # neither the footer band nor the suptitle gets eaten. The top
        # bound is the load-bearing one — without it constrained-layout
        # tries to fit the suptitle inside the working area and the
        # title ends up flush with the figure's top edge, colliding
        # with panel titles.
        engine.set(rect=(0.0, FOOTER_BAND_FRAC, 1.0, 1.0 - HEADER_BAND_FRAC))
    elif fig.subplotpars.bottom < FOOTER_BAND_FRAC:
        # Manual layout (the _fill_3d path): widen the bottom margin
        # only if it's currently tighter than the band. Other margins
        # set by _fill_3d are preserved.
        fig.subplots_adjust(bottom=FOOTER_BAND_FRAC)
    # Text centered vertically within the band.
    fig.text(0.5, FOOTER_BAND_FRAC / 2.0, f"spektrafilm {version}",
             color=FOOTER_COLOR, fontsize=FOOTER_FS,
             ha="center", va="center", alpha=0.85)


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


def _fill_3d(fig, *, has_cbar: bool = False, top: float | None = None,
             bottom: float | None = None, wspace: float = 0.0) -> None:
    """Push 3D axes to fill the figure canvas.

    matplotlib 3D axes default to a generous interior margin; for the
    plots we ship that leaves the data sitting in the middle 50–60% of
    the figure with a lot of dead black background around it. We pull
    the axes box outward with subplots_adjust; ``bbox_inches="tight"``
    at save time then trims off whatever tick decorations stick out.

    ``top`` / ``bottom`` default to :data:`HEADER_BAND_FRAC` /
    :data:`FOOTER_BAND_FRAC` complements so the suptitle and version
    footer have the same reserved bands as the constrained-layout
    figures. Callers can override for 2-line suptitles that need more
    top space.
    """
    if top is None:
        top = 1.0 - HEADER_BAND_FRAC
    if bottom is None:
        bottom = FOOTER_BAND_FRAC
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
    ax.set_title(title, color=HI, pad=SUPTITLE_PAD, fontsize=SUPTITLE_FS)
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
    ax1.set_title("input positions", color=HI, pad=PANEL_TITLE_PAD, fontsize=PANEL_TITLE_FS)
    ax2 = fig.add_subplot(122, projection="3d", facecolor=BG)
    ax2.scatter(colors[:, 0], colors[:, 1], colors[:, 2],
                c=colors, s=18, alpha=0.9, edgecolors="none", depthshade=False)
    ax2.set_title("output positions", color=HI, pad=PANEL_TITLE_PAD, fontsize=PANEL_TITLE_FS)
    for ax in (ax1, ax2):
        ax.set_xlabel("R", color=FG, labelpad=6)
        ax.set_ylabel("G", color=FG, labelpad=6)
        ax.set_zlabel("B", color=FG, labelpad=6)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
        _setup_3d(ax)
        ax.view_init(elev=22, azim=-58)
    fig.suptitle("LUT deformation: where does each input land?",
                 color=HI, fontsize=SUPTITLE_FS)
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
    ax1.set_title("cube edges — input coordinates", color=HI, pad=PANEL_TITLE_PAD, fontsize=PANEL_TITLE_FS)
    ax2.set_title("cube edges — output coordinates", color=HI, pad=PANEL_TITLE_PAD, fontsize=PANEL_TITLE_FS)
    for ax in (ax1, ax2):
        ax.set_xlabel("R", color=FG, labelpad=6)
        ax.set_ylabel("G", color=FG, labelpad=6)
        ax.set_zlabel("B", color=FG, labelpad=6)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.set_zlim(0, 1)
        _setup_3d(ax)
        ax.view_init(elev=22, azim=-58)
    fig.suptitle("Saturated cube edges — the canonical hue+saturation cycle",
                 color=HI, fontsize=SUPTITLE_FS)
    _fill_3d(fig, has_cbar=False)
    return fig


# ---------------------------------------------------------------------------
# Transfer-curve views (1D per-axis slices of the cube table).
# ---------------------------------------------------------------------------

def transfer_curves(
    sweep_x: np.ndarray,
    samples: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    pin_label: str,
    violation_marks: tuple[np.ndarray, np.ndarray, np.ndarray] | None = None,
    suptitle: str = "Per-axis transfer curves through middle-gray",
) -> Figure:
    """Per-axis transfer curves through a chosen centerline.

    Each panel sweeps one input channel from 0 to 1 with the other two
    held at a fixed encoded value, plotting R/G/B output. The caller
    computes the LUT samples via trilinear interpolation, so the
    centerline can be placed at any encoded value (not just the cube
    midpoint) — critical for log-encoded input spaces where the
    encoded midpoint isn't perceptually meaningful.

    Parameters
    ----------
    sweep_x :
        Shape ``(N,)`` — the input encoded values being swept (typically
        ``np.linspace(0, 1, N)``). Same x-axis for all three panels.
    samples :
        Three arrays of shape ``(N, 3)`` for the R-sweep, G-sweep, and
        B-sweep respectively. Each row is the LUT's encoded RGB output
        at that sweep point.
    pin_label :
        Human-readable label for what the "other channels" are pinned
        to (e.g. ``"0.46 (middle gray)"``). Shown on each panel's
        x-axis label so the figure is self-explanatory across input
        color spaces.
    violation_marks :
        Optional ``(R_mask, G_mask, B_mask)`` of monotonicity violations
        (each ``(N-1,)`` boolean), marked in red on the matching
        channel's curve.
    suptitle :
        Figure-level title. Default reflects the new
        middle-gray-centerline behavior.
    """
    setups = [
        ("R", samples[0], RED),
        ("G", samples[1], GREEN),
        ("B", samples[2], BLUE),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5), facecolor=BG, layout="constrained")
    for i, (ax, (label, axis_samples, axis_color)) in enumerate(zip(axes, setups)):
        ax.set_facecolor(BG)
        ax.plot(sweep_x, axis_samples[:, 0], color=RED, lw=2.2, label="R out")
        ax.plot(sweep_x, axis_samples[:, 1], color=GREEN, lw=2.2, label="G out")
        ax.plot(sweep_x, axis_samples[:, 2], color=BLUE, lw=2.2, label="B out")
        _identity_line(ax)
        if violation_marks is not None:
            mask = violation_marks[i]
            if mask.any():
                xs = sweep_x[1:][mask]
                ys = axis_samples[1:, i][mask]
                ax.scatter(xs, ys, s=60, marker="x", color="#ff3366",
                           label="monotonicity violation", zorder=5)
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.set_xlabel(f"{label} in  (other channels = {pin_label})", color=FG)
        ax.set_ylabel("output", color=FG)
        ax.set_title(f"{label} sweep", color=axis_color, fontsize=PANEL_TITLE_FS, pad=PANEL_TITLE_PAD)
        _setup_2d(ax)
        ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                  loc="upper left", fontsize=9)
    fig.suptitle(suptitle, color=HI, fontsize=SUPTITLE_FS)
    return fig


def density_transfer_curves(
    sweep_x: np.ndarray,
    r_sweep: list[tuple[float, np.ndarray, float]],
    g_sweep: list[tuple[float, np.ndarray, float]],
    b_sweep: list[tuple[float, np.ndarray, float]],
    neutral_samples: np.ndarray,
    *,
    title: str = "Density-domain transfer curves — coupler diagnostic",
) -> Figure:
    """Density-domain transfer curves — coupler diagnostic.

    Four panels in a 2×2 grid:

    - **Top row** (R, G, B sweeps): each panel sweeps one input channel
      and shows D-R, D-G, D-B output as a *family* of curves taken at
      several constant values of the other channels (the "pins"). The
      spread between curves at different pins IS the coupler signature:
      DIR couplers in the film simulation make the output channels
      respond to inputs they otherwise shouldn't, and that cross-talk
      shows up as a visible vertical gap between same-color curves at
      different pins. The center pin (typically 0.5) is drawn at full
      alpha; outer pins fade so the eye reads the family as a textured
      band rather than a tangle of equally-weighted lines.
    - **Bottom right** (neutral sweep): vary R=G=B together. The
      canonical film characteristic curve from datasheets — toe,
      linear segment, shoulder all visible.

    Density convention: D = -log₁₀(output) with the Y axis inverted
    so D=0 (white) sits at top and high D (black) sits at the bottom,
    matching film datasheet conventions.

    Parameters
    ----------
    sweep_x :
        Shape ``(N,)`` — the input encoded values being swept (same
        x-axis for all panels). The caller computes this; typically
        ``np.linspace(0, 1, N)``.
    r_sweep, g_sweep, b_sweep :
        Lists of ``(pin_density, samples, alpha)`` triples. ``samples``
        is shape ``(N, 3)`` of LUT output at the sweep points with the
        non-swept channels pinned. ``pin_density`` is the *output*
        density the off-diagonal curves are expected to start at on the
        Y-axis — the caller picked the actual input-code pins by
        inverting the neutral characteristic curve so the off-diagonals
        enter each panel at ``pin_density``. Used only for the axis
        label. ``alpha`` controls the line transparency for that pin's
        curves.
    neutral_samples :
        Shape ``(N, 3)`` of LUT output along the neutral diagonal
        (R=G=B=sweep_x). Drawn at full alpha in the bottom-right panel.
    title :
        Figure suptitle.
    """
    floor = 1.0e-4

    # Shared Y range across all 4 panels (so D values are visually
    # comparable across the R / G / B / neutral sweeps). Top stays at
    # D=0 (white); bottom sits just past the deepest observed density
    # — no snapping to round numbers, the plot surface is for the data.
    all_densities = []
    for sweep_data in (r_sweep, g_sweep, b_sweep):
        for _, samples, _ in sweep_data:
            d = -np.log10(np.clip(samples, floor, 1.0))
            all_densities.append(d)
    neutral_d = -np.log10(np.clip(neutral_samples, floor, 1.0))
    all_densities.append(neutral_d)
    observed_max = float(max(d.max() for d in all_densities))
    y_max = observed_max * 1.05

    fig, axes_2d = plt.subplots(2, 2, figsize=(13, 10), facecolor=BG,
                                layout="constrained")
    # Materialize as a list — zip() on a flatiter advances it past the
    # zipped count when the other iterable exhausts first, leaving
    # nothing for the neutral panel below.
    axes = list(axes_2d.flat)

    setups = [
        ("R", r_sweep, RED),
        ("G", g_sweep, GREEN),
        ("B", b_sweep, BLUE),
    ]
    for ax, (label, sweep_data, axis_color) in zip(axes[:3], setups):
        ax.set_facecolor(BG)
        # Plot every (pin, samples) family in the panel. The matching
        # channel's center-pin curve sits on top of the stack so it's
        # visually dominant.
        for pin, samples, alpha in sweep_data:
            density = -np.log10(np.clip(samples, floor, 1.0))
            ax.plot(sweep_x, density[:, 0], color=RED, lw=2.0,
                    alpha=alpha, zorder=2 + alpha)
            ax.plot(sweep_x, density[:, 1], color=GREEN, lw=2.0,
                    alpha=alpha, zorder=2 + alpha)
            ax.plot(sweep_x, density[:, 2], color=BLUE, lw=2.0,
                    alpha=alpha, zorder=2 + alpha)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, y_max)
        ax.invert_yaxis()
        pin_densities = sorted({pin for pin, _, _ in sweep_data})
        pins_text = ", ".join(f"{p:g}" for p in pin_densities)
        ax.set_xlabel(
            f"{label} input code   (other channels start at D ≈ {{{pins_text}}})",
            color=FG, fontsize=9,
        )
        ax.set_ylabel("D = -log₁₀(output)", color=FG)
        ax.set_title(f"{label} sweep", color=axis_color, fontsize=PANEL_TITLE_FS, pad=PANEL_TITLE_PAD)
        _setup_2d(ax)
        # Legend uses three full-alpha proxies so the swatch is readable
        # against the multi-alpha lines actually drawn.
        from matplotlib.lines import Line2D
        proxies = [
            Line2D([0], [0], color=RED, lw=2.0, label="D-R"),
            Line2D([0], [0], color=GREEN, lw=2.0, label="D-G"),
            Line2D([0], [0], color=BLUE, lw=2.0, label="D-B"),
        ]
        ax.legend(handles=proxies, facecolor="#1a1a1a", labelcolor=FG,
                  framealpha=0.85, loc="upper right", fontsize=9)

    # Neutral diagonal panel — single full-alpha family, the canonical
    # film D-vs-input curve.
    ax_n = axes[3]
    ax_n.set_facecolor(BG)
    ax_n.plot(sweep_x, neutral_d[:, 0], color=RED, lw=2.2, label="D-R")
    ax_n.plot(sweep_x, neutral_d[:, 1], color=GREEN, lw=2.2, label="D-G")
    ax_n.plot(sweep_x, neutral_d[:, 2], color=BLUE, lw=2.2, label="D-B")
    ax_n.set_xlim(0, 1)
    ax_n.set_ylim(0, y_max)
    ax_n.invert_yaxis()
    ax_n.set_xlabel(
        "neutral (R=G=B) input code   (the canonical D-vs-input curve)",
        color=FG, fontsize=9,
    )
    ax_n.set_ylabel("D = -log₁₀(output)", color=FG)
    ax_n.set_title("neutral (R=G=B) sweep", color=HI, fontsize=PANEL_TITLE_FS, pad=PANEL_TITLE_PAD)
    _setup_2d(ax_n)
    ax_n.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.85,
                loc="upper right", fontsize=9)

    fig.suptitle(title, color=HI, fontsize=SUPTITLE_FS)
    return fig


def rg_plane_slices(
    table: np.ndarray, n: int, out_cs: str, *, n_slices: int = 9,
) -> Figure:
    """R-G plane slices through the cube at varying B-input values,
    rendered as **sRGB display images** (hard-clipped).

    The cube table is encoded in the bundle's output color space. A
    naive imshow would treat those values as if they were sRGB-encoded,
    which produces visibly wrong colors for any non-sRGB output
    (Rec.2020, DCI-P3, P3-D65 PQ, …). Each slice is decoded to linear
    in the output primaries, chromatically adapted to sRGB primaries,
    sRGB-encoded, and hard-clipped — so what's on screen is the LUT's
    R-G response at that B as it would appear on an sRGB display.
    """
    from spektrafilm_lut_creator.color_spaces import (
        decode_cctf, get as get_cs,
    )
    # Fixed 3x3 grid; default 9 slices fills it exactly. If the cube
    # resolution is too small for 9 slices we use as many as fit and
    # leave the trailing axes blank.
    n_slices = min(n_slices, n)
    grid_cols = 3
    grid_rows = int(np.ceil(n_slices / grid_cols))
    indices = np.linspace(0, n - 1, n_slices, dtype=int)
    out_entry = get_cs(out_cs)

    fig, axes_2d = plt.subplots(
        grid_rows, grid_cols,
        figsize=(2.4 * grid_cols, 2.6 * grid_rows + 0.4),
        facecolor=BG, layout="constrained",
    )
    axes = np.atleast_1d(axes_2d).reshape(grid_rows, grid_cols).flatten()
    for i, ax in enumerate(axes):
        if i >= n_slices:
            ax.axis("off")
            continue
        idx = indices[i]
        slice_encoded = np.asarray(table[idx, :, :, :], dtype=float)
        slice_linear = decode_cctf(slice_encoded, out_cs)
        srgb_linear = np.asarray(
            colour.RGB_to_RGB(
                slice_linear,
                out_entry.primaries,
                "sRGB",
                chromatic_adaptation_transform="CAT02",
            ), dtype=float,
        )
        srgb_encoded = np.asarray(
            colour.cctf_encoding(np.clip(srgb_linear, 0.0, 1.0), function="sRGB"),
            dtype=float,
        )
        ax.imshow(np.clip(srgb_encoded, 0.0, 1.0),
                  origin="lower", extent=(0, 1, 0, 1), interpolation="bilinear")
        b_val = idx / (n - 1)
        ax.set_title(f"B = {b_val:.2f}", color=FG, fontsize=10)
        ax.set_xticks([0, 1]); ax.set_yticks([0, 1])
        ax.tick_params(colors=FG, length=2)
        for spine in ax.spines.values():
            spine.set_color("#555555")
        # Only the leftmost column gets a G label; only the bottom
        # row gets an R label — keeps the grid uncluttered.
        row, col = i // grid_cols, i % grid_cols
        if col == 0:
            ax.set_ylabel("G in", color=FG, fontsize=8)
        if row == grid_rows - 1 or (i + grid_cols) >= n_slices:
            ax.set_xlabel("R in", color=FG, fontsize=8)
    fig.suptitle(
        f"R-G cube slices at varying B   (output {out_cs} → sRGB display, hard-clipped)",
        color=HI, fontsize=SUPTITLE_FS,
    )
    return fig


def gamut_edge_stress(
    panels: list[tuple[str, np.ndarray, dict]],
    *,
    in_cs: str,
    out_cs: str,
) -> Figure:
    """Granger-style RGB stress chart panels.

    Each panel is a vertical linear-RGB gradient (white at the top,
    saturated RGB-cube edge in the middle as the hue cycles across
    columns, black at the bottom) generated in one target RGB color
    space, CAT-adapted into the bundle's input encoding, pushed
    through the LUT, and displayed in sRGB (hard-clipped). Pixels
    whose target-space color does not fit the bundle's input encoding
    are left black.

    ``panels`` is ``[(target_cs_name, srgb_image (H,W,3), stats_dict)]``.
    """
    # Panel aspect is 3:1 (width:height) to match Mononodes-style charts —
    # the gradient image itself is built at 3:1 too, so aspect="equal"
    # honors that and avoids the very-long banner shape.
    n_panels = len(panels)
    panel_width = 9.0
    fig, axes = plt.subplots(
        n_panels, 1,
        figsize=(panel_width, (panel_width / 3.0) * n_panels + 0.8),
        facecolor=BG, layout="constrained",
    )
    axes = np.atleast_1d(axes)
    for ax, (cs_name, img, stats) in zip(axes, panels):
        ax.imshow(img, aspect="equal", origin="upper", interpolation="nearest")
        oog_sat = stats.get("oog_fraction_saturated_row", 0.0)
        ax.set_title(
            f"target: {cs_name}   ·   saturated-row OOG vs {in_cs}: {oog_sat:.1%}",
            color=FG, fontsize=11, pad=4,
        )
        ax.set_xticks([]); ax.set_yticks([])
        for spine in ax.spines.values():
            spine.set_color("#555555")
    # The per-column gradient construction (white → saturated edge →
    # black, OOG pixels black) is documented in the QA report; keeping
    # the suptitle to one line avoids stomping on the top panel.
    fig.suptitle(
        f"Gamut-edge stress test — {in_cs} → {out_cs}",
        color=HI, fontsize=SUPTITLE_FS,
    )
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
                 color=HI, pad=SUPTITLE_PAD, fontsize=SUPTITLE_FS)
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
                     color=col, fontsize=PANEL_TITLE_FS, pad=PANEL_TITLE_PAD)
        _setup_2d(ax)
    fig.suptitle("Per-channel output distributions (with CDF + clipping markers)",
                 color=HI, fontsize=SUPTITLE_FS)
    return fig


# ---------------------------------------------------------------------------
# OkLab / perceptual views.
# ---------------------------------------------------------------------------

def gamut_compression_3d_xy(
    *,
    grid_output_compressed: np.ndarray,
    rim_unbounded_linear: np.ndarray,
    rim_compressed_linear: np.ndarray,
    rim_input_hues: np.ndarray,
    rim_n_per_segment: int,
    rim_n_segments: int,
    in_cs_name: str,
    out_cs_name: str,
    compression_spec,
) -> Figure:
    """1x2 figure: 3D OkLab gamut (cube cloud + rim before/after) and 2D xy
    chromaticity preview of the same compression event.

    Left panel — perceptual volume + rim envelope:
      - Faint scatter of the LUT's compressed output cube (= what the
        LUT actually delivers) for volume context, colored by the
        cube's input RGB.
      - Bright colored polylines tracing the **unbounded rim** — the
        chromaticities the simulation would reach with output gamut
        compression disabled — overlaid on top.
      - Dimmer dashed polylines for the **compressed rim** so the eye
        can follow each cube-edge's displacement under compression.
      - Sparse displacement arrows on the OOG subset (when there is
        out-of-gamut content to show).

    Right panel — the canonical xy chromaticity preview:
      - Spectral locus + output gamut triangle.
      - Unbounded rim (rainbow scatter) → compressed rim (faded
        inner ring) → optional displacement arrows.
      - Compact stats panel.

    All RGB inputs for the rim are in the output color space's
    **linear** primaries (no CCTF applied), matching what the runtime's
    unbounded pipeline produces. ``grid_output_compressed`` is the
    shipped LUT's encoded output (matches ``ctx.grid_output``).
    """
    from spektrafilm_lut_creator.color_spaces import get as get_cs

    out_entry = get_cs(out_cs_name)
    out_primaries_name = out_entry.primaries
    out_primaries = colour.RGB_COLOURSPACES[out_primaries_name]
    out_white = np.asarray(out_primaries.whitepoint, dtype=float)
    out_tri = np.asarray(out_primaries.primaries, dtype=float)

    cube_lab = _to_oklab(grid_output_compressed, out_cs_name)
    cube_colors = np.clip(grid_output_compressed, 0.0, 1.0)
    rim_unbounded_lab = _linear_rgb_to_oklab(
        rim_unbounded_linear, out_primaries_name,
    )
    rim_compressed_lab = _linear_rgb_to_oklab(
        rim_compressed_linear, out_primaries_name,
    )
    xy_unbounded = _linear_rgb_to_xy(rim_unbounded_linear, out_primaries)
    xy_compressed = _linear_rgb_to_xy(rim_compressed_linear, out_primaries)

    # ACES RGC "achromatic distance" — how far past the output gamut
    # each rim sample sits, in the same RGB metric the algorithm uses.
    # ach > 1e-2 skips near-black samples whose direction is dominated
    # by noise.
    ach = rim_unbounded_linear.max(axis=-1)
    safe_ach = np.where(ach > 1e-6, ach, 1.0)
    d_per_channel = (ach[..., None] - rim_unbounded_linear) / safe_ach[..., None]
    d_max = d_per_channel.max(axis=-1)
    bright_mask = ach > 1e-2
    oog_mask = (d_max > 1.0) & bright_mask
    oog_fraction = float(oog_mask.sum() / max(int(bright_mask.sum()), 1))
    displacement = np.linalg.norm(
        rim_unbounded_linear - rim_compressed_linear, axis=-1,
    )
    compression_active = (
        getattr(compression_spec, "mode", "off") != "off"
    )

    fig = plt.figure(figsize=(18, 9), facecolor=BG)
    ax3d = fig.add_subplot(121, projection="3d", facecolor=BG)
    ax2d = fig.add_subplot(122, facecolor=BG)
    _render_oklab_gamut_3d(
        ax3d,
        cube_lab=cube_lab,
        cube_colors=cube_colors,
        rim_unbounded_lab=rim_unbounded_lab,
        rim_compressed_lab=rim_compressed_lab,
        rim_hues=rim_input_hues,
        rim_n_per_segment=rim_n_per_segment,
        rim_n_segments=rim_n_segments,
        rim_bright_mask=bright_mask,
        rim_oog_mask=oog_mask,
        compression_active=compression_active,
        out_cs_name=out_cs_name,
    )
    _render_xy_compression_panel(
        ax2d,
        xy_unbounded=xy_unbounded,
        xy_compressed=xy_compressed,
        rim_hues=rim_input_hues,
        rim_n_per_segment=rim_n_per_segment,
        rim_n_segments=rim_n_segments,
        rim_bright_mask=bright_mask,
        rim_oog_mask=oog_mask,
        out_tri=out_tri,
        out_white=out_white,
        out_cs_name=out_cs_name,
        in_cs_name=in_cs_name,
        compression_spec=compression_spec,
        compression_active=compression_active,
        oog_fraction=oog_fraction,
        displacement=displacement,
    )

    algorithm_label = {
        "oklch": "OkLch chroma reduction",
        "aces_rgc": "ACES RGC v1.3",
    }.get(getattr(compression_spec, "algorithm", ""),
          getattr(compression_spec, "algorithm", ""))
    fig.suptitle(
        f"output gamut compression — {in_cs_name} → {out_cs_name}   "
        f"via {algorithm_label}",
        color=HI, fontsize=SUPTITLE_FS,
    )
    fig.subplots_adjust(left=0.02, right=0.98, top=1.0 - HEADER_BAND_FRAC,
                       bottom=FOOTER_BAND_FRAC, wspace=0.05)
    return fig


def _linear_rgb_to_oklab(rgb_linear: np.ndarray, primaries_name: str) -> np.ndarray:
    """Output-primaries linear RGB → OkLab via XYZ.

    Parallel to :func:`_to_oklab` but for inputs that have already had
    their CCTF stripped (or never had one applied) — e.g. the unbounded
    pipeline's output.
    """
    primaries = colour.RGB_COLOURSPACES[primaries_name]
    xyz = colour.RGB_to_XYZ(
        np.asarray(rgb_linear, dtype=float),
        colourspace=primaries.name,
        apply_cctf_decoding=False,
        illuminant=primaries.whitepoint,
    )
    return np.asarray(colour.XYZ_to_Oklab(xyz), dtype=float)


def _linear_rgb_to_xy(rgb_linear: np.ndarray, primaries) -> np.ndarray:
    """Linear RGB → xy chromaticity in the given primaries' frame."""
    xyz = colour.RGB_to_XYZ(
        np.asarray(rgb_linear, dtype=float),
        colourspace=primaries.name,
        apply_cctf_decoding=False,
        illuminant=np.asarray(primaries.whitepoint, dtype=float),
    )
    b = xyz.sum(axis=-1, keepdims=True)
    return np.asarray(xyz[..., :2] / np.where(np.abs(b) > 1e-12, b, 1.0),
                       dtype=float)


def _render_oklab_gamut_3d(
    ax,
    *,
    cube_lab: np.ndarray,
    cube_colors: np.ndarray,
    rim_unbounded_lab: np.ndarray,
    rim_compressed_lab: np.ndarray,
    rim_hues: np.ndarray,
    rim_n_per_segment: int,
    rim_n_segments: int,
    rim_bright_mask: np.ndarray,
    rim_oog_mask: np.ndarray,
    compression_active: bool,
    out_cs_name: str,
) -> None:
    """Draw the 3D OkLab cube cloud + before/after rim envelope onto ``ax``.

    Frame is keyed to the cube + unbounded rim's combined extent so the
    out-of-gamut excursion is visible.
    """
    ax.scatter(
        cube_lab[:, 1], cube_lab[:, 2], cube_lab[:, 0],
        c=cube_colors, s=4, alpha=0.18, edgecolors="none",
        depthshade=False, zorder=1.0,
    )

    # Skip the three "lit-white" edges per axis (same convention as
    # the xy panel) — they're saturation sweeps and clutter the rim
    # envelope with lines running into the achromatic axis.
    for k in range(rim_n_segments):
        if k % 4 == 3:
            continue
        s, e = k * rim_n_per_segment, (k + 1) * rim_n_per_segment
        if not rim_bright_mask[s:e].any():
            continue
        seg_hue = rim_hues[s:e]
        col = plt.cm.hsv(
            np.angle(np.exp(1j * 2 * np.pi * np.mean(seg_hue)))
            / (2 * np.pi) % 1.0
        )
        ax.plot(
            rim_unbounded_lab[s:e, 1], rim_unbounded_lab[s:e, 2],
            rim_unbounded_lab[s:e, 0],
            color=col, lw=2.0, alpha=0.95, zorder=3.0,
        )
        if compression_active:
            ax.plot(
                rim_compressed_lab[s:e, 1], rim_compressed_lab[s:e, 2],
                rim_compressed_lab[s:e, 0],
                color=col, lw=1.0, alpha=0.65, ls="--", zorder=2.8,
            )

    # Sparse displacement arrows on a brightest-OOG subset (3D quiver).
    if compression_active and rim_oog_mask.any():
        oog_idx = np.flatnonzero(rim_oog_mask)
        n_arrows = min(len(oog_idx), 80)
        if n_arrows > 0:
            rng = np.random.default_rng(0)
            pick = rng.choice(oog_idx, size=n_arrows, replace=False)
            u = rim_compressed_lab[pick, 1] - rim_unbounded_lab[pick, 1]
            v = rim_compressed_lab[pick, 2] - rim_unbounded_lab[pick, 2]
            w = rim_compressed_lab[pick, 0] - rim_unbounded_lab[pick, 0]
            ax.quiver(
                rim_unbounded_lab[pick, 1], rim_unbounded_lab[pick, 2],
                rim_unbounded_lab[pick, 0],
                u, v, w,
                color="#ffaa55", alpha=0.55,
                arrow_length_ratio=0.18, linewidth=0.9, zorder=3.5,
            )

    # Frame on the union of cube + unbounded rim. The unbounded rim
    # extends past the cube along OOG directions, which is the point
    # of the visualization — show it.
    pts = np.vstack([cube_lab, rim_unbounded_lab[rim_bright_mask]])
    a_lo, a_hi = float(pts[:, 1].min()), float(pts[:, 1].max())
    b_lo, b_hi = float(pts[:, 2].min()), float(pts[:, 2].max())
    L_lo, L_hi = float(pts[:, 0].min()), float(pts[:, 0].max())
    pad = 0.10
    a_pad = pad * max(a_hi - a_lo, 1e-3)
    b_pad = pad * max(b_hi - b_lo, 1e-3)
    L_pad = pad * max(L_hi - L_lo, 1e-3)
    ax.set_xlim(a_lo - a_pad, a_hi + a_pad)
    ax.set_ylim(b_lo - b_pad, b_hi + b_pad)
    ax.set_zlim(L_lo - L_pad, L_hi + L_pad)
    ax.set_xlabel("a*", color=FG, labelpad=6)
    ax.set_ylabel("b*", color=FG, labelpad=6)
    ax.set_zlabel("L*", color=FG, labelpad=6)
    _setup_3d(ax)
    ax.view_init(elev=18, azim=-58)
    ax.text2D(
        0.02, 0.97,
        f"OkLab gamut  ({out_cs_name})\n"
        f"cloud = compressed LUT cube · rim solid = unbounded · "
        f"rim dashed = compressed",
        transform=ax.transAxes, color=HI, fontsize=10,
        ha="left", va="top",
    )


def _render_xy_compression_panel(
    ax,
    *,
    xy_unbounded: np.ndarray,
    xy_compressed: np.ndarray,
    rim_hues: np.ndarray,
    rim_n_per_segment: int,
    rim_n_segments: int,
    rim_bright_mask: np.ndarray,
    rim_oog_mask: np.ndarray,
    out_tri: np.ndarray,
    out_white: np.ndarray,
    out_cs_name: str,
    in_cs_name: str,
    compression_spec,
    compression_active: bool,
    oog_fraction: float,
    displacement: np.ndarray,
) -> None:
    """Draw the xy chromaticity compression preview onto ``ax``.

    Spectral locus + output primaries triangle + unbounded vs
    compressed rim envelope, with displacement arrows on the
    out-of-gamut subset and a compact stats panel.
    """
    from spektrafilm.utils.gamut_compression import spectral_locus_xy

    bg, fg, accent, dim = BG, FG, "#ffee66", "#888888"
    locus = spectral_locus_xy()

    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.tick_params(colors=fg)
    ax.grid(True, alpha=0.12, color=accent)

    ax.plot(locus[:, 0], locus[:, 1], color=dim, lw=1.0, alpha=0.45,
            label="visible spectral locus")
    locus_path = plt.Polygon(locus, closed=True, facecolor="#cccccc",
                             alpha=0.025, edgecolor="none")
    ax.add_patch(locus_path)

    tri = np.vstack([out_tri, out_tri[:1]])
    ax.fill(tri[:, 0], tri[:, 1], color="#ffffff", alpha=0.04, zorder=1.5)
    ax.plot(tri[:, 0], tri[:, 1], color=fg, lw=2.0, alpha=0.95,
            label=f"{out_cs_name} gamut", zorder=2)
    primary_colors = ["#ff5566", "#66ff88", "#5599ff"]
    primary_labels = ["R", "G", "B"]
    for (px, py), pcol, plab in zip(out_tri, primary_colors, primary_labels):
        ax.plot(px, py, "o", color=pcol, markersize=11,
                markeredgecolor=bg, markeredgewidth=1.5, zorder=4)
        offset = np.array([px, py]) - out_white
        n = np.linalg.norm(offset) + 1e-9
        lx, ly = np.array([px, py]) + 0.035 * offset / n
        ax.text(lx, ly, plab, color=pcol, ha="center", va="center",
                fontsize=12, fontweight="bold", zorder=5)
    ax.plot(out_white[0], out_white[1], "D", color=fg, markersize=10,
            markeredgecolor=bg, markeredgewidth=1.2,
            label=f"{out_cs_name} white", zorder=4)

    bright_idx = np.flatnonzero(rim_bright_mask)
    for k in range(rim_n_segments):
        if k % 4 == 3:
            continue
        s, e = k * rim_n_per_segment, (k + 1) * rim_n_per_segment
        if not rim_bright_mask[s:e].any():
            continue
        seg_hue = rim_hues[s:e]
        col = plt.cm.hsv(
            np.angle(np.exp(1j * 2 * np.pi * np.mean(seg_hue)))
            / (2 * np.pi) % 1.0
        )
        ax.plot(xy_unbounded[s:e, 0], xy_unbounded[s:e, 1],
                color=col, lw=4.0, alpha=0.25, zorder=2.6)
        ax.plot(xy_unbounded[s:e, 0], xy_unbounded[s:e, 1],
                color=col, lw=1.6, alpha=0.95, zorder=2.7)
        if compression_active:
            ax.plot(xy_compressed[s:e, 0], xy_compressed[s:e, 1],
                    color=col, lw=1.0, alpha=0.7, ls="--", zorder=2.65)

    ax.scatter(
        xy_unbounded[bright_idx, 0], xy_unbounded[bright_idx, 1],
        c=rim_hues[bright_idx], cmap=plt.cm.hsv, s=20, alpha=0.95,
        edgecolors="none", zorder=3, label="unbounded rim",
    )
    if compression_active and rim_oog_mask.any():
        ax.scatter(
            xy_compressed[bright_idx, 0], xy_compressed[bright_idx, 1],
            c=rim_hues[bright_idx], cmap=plt.cm.hsv, s=10, alpha=0.7,
            edgecolors="none", zorder=3.5, label="compressed rim",
        )
        oog_bright_idx = np.flatnonzero(rim_oog_mask)
        n_arrows = min(len(oog_bright_idx), 120)
        if n_arrows > 0:
            rng = np.random.default_rng(0)
            pick = rng.choice(oog_bright_idx, size=n_arrows, replace=False)
            ax.quiver(
                xy_unbounded[pick, 0], xy_unbounded[pick, 1],
                xy_compressed[pick, 0] - xy_unbounded[pick, 0],
                xy_compressed[pick, 1] - xy_unbounded[pick, 1],
                color="#ffaa55", alpha=0.5,
                angles="xy", scale_units="xy", scale=1.0,
                width=0.0022, headwidth=4, headlength=5, zorder=3.7,
            )

    if compression_active and rim_oog_mask.any():
        text = (
            f"algorithm:    {compression_spec.algorithm}\n"
            f"mode:         {compression_spec.mode}\n"
            f"threshold:    {compression_spec.knee[0]}\n"
            f"limit:        {compression_spec.knee[1]}\n"
            f"power:        {compression_spec.knee[2]}\n"
            f"\n"
            f"input:        {in_cs_name}\n"
            f"output:       {out_cs_name}\n"
            f"OOG fraction: {oog_fraction:.1%}\n"
            f"OOG samples:  {int(rim_oog_mask.sum())}\n"
            f"max disp:     {displacement[rim_oog_mask].max():.4f}\n"
            f"p99 disp:     "
            f"{np.percentile(displacement[rim_oog_mask], 99):.4f}\n"
            f"mean disp:    {displacement[rim_oog_mask].mean():.4f}"
        )
    elif not compression_active:
        text = (
            f"algorithm:    {compression_spec.algorithm}\n"
            f"mode:         OFF\n"
            f"\n"
            f"input:        {in_cs_name}\n"
            f"output:       {out_cs_name}\n"
            f"OOG fraction: {oog_fraction:.1%}\n"
            f"(compression disabled — rim shown as-is)"
        )
    else:
        text = (
            f"algorithm:    {compression_spec.algorithm}\n"
            f"\n(no bright OOG samples — the simulation's rim is\n"
            f" already inside the output gamut for this input)"
        )
    ax.text(
        0.02, 0.98, text,
        transform=ax.transAxes, va="top", ha="left",
        color=fg, family="monospace", fontsize=9,
        bbox=dict(facecolor="#1a1a1a", edgecolor="#555555",
                  alpha=0.92, boxstyle="round,pad=0.5"),
        zorder=10,
    )

    leg = ax.legend(loc="upper right", fontsize=8,
                    facecolor="#1a1a1a", edgecolor="#555555",
                    labelcolor=fg)
    leg.get_frame().set_alpha(0.9)

    ax.set_xlim(-0.05, 0.85)
    ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=fg)
    ax.set_ylabel("y", color=fg)
    ax.set_aspect("equal")


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
                 color=HI, fontsize=SUPTITLE_FS)
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
    _identity_line(ax, lo=-180, hi=180)
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
    ax.set_title("Hue-twist diagram (OkLab)", color=HI, fontsize=SUPTITLE_FS, pad=SUPTITLE_PAD)
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
                 color=HI, fontsize=SUPTITLE_FS)
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
                 color=HI, fontsize=SUPTITLE_FS, pad=SUPTITLE_PAD)
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
    ax.set_title(title, color=HI, pad=SUPTITLE_PAD, fontsize=SUPTITLE_FS)
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
                 color=HI, fontsize=SUPTITLE_FS, pad=SUPTITLE_PAD)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper right", fontsize=9)
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

    Four layers:

    1. The main curve — output density ``D = -log10(Y)`` vs input
       stops above middle gray. Y axis inverted so D=0 (white) sits
       at the top, high D (black) at the bottom — film datasheet
       convention.
    2. **Encoding-clip shading + dashed bars**: warm-tinted shaded
       regions covering the *full extent* of stops the input encoding
       can't represent (clipped to 0 or 1 at the input), with a dashed
       vertical line at each clip threshold for precise reading. Stops
       inside these shaded regions are "the input encoding's fault" —
       the LUT was fed the same clip-boundary value for every stop in
       that range, so the curve is necessarily flat there.
    3. **Toe / shoulder shading**: light gray bands at the bottom
       and top of the rendered range where slope falls below the
       active threshold. These are the model's compression decisions.
    4. **'x' markers** on the clipped-stop samples to make the flat
       segment legible even where it overlaps with shading.

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

    # Toe / shoulder shading inside the encoded range, plus encoding-clip
    # shading outside it so the *full extent* of clipped stops is visible
    # at a glance (the "x" markers alone made the clip range easy to miss).
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

        # Encoding-clip shading: full vertical extent of the clipped
        # stops, one span on each side that actually clips. Each
        # carries its own count so the legend describes the situation
        # asymmetric SDR inputs typically produce (no shadow clip in
        # the ramp range, large highlight clip).
        if enc_lo_x > stops[0]:
            lo_stops = stops[enc_idx[0]] - stops[0]
            ax.axvspan(stops[0], enc_lo_x, color=WARN, alpha=0.12,
                       label=f"encoding clip: {lo_stops:.1f} stops (shadows)")
        if enc_hi_x < stops[-1]:
            hi_stops = stops[-1] - stops[enc_idx[-1]]
            ax.axvspan(enc_hi_x, stops[-1], color=WARN, alpha=0.12,
                       label=f"encoding clip: {hi_stops:.1f} stops (highlights)")

        # Boundary markers — kept as a precise visual anchor at the
        # exact clip threshold (the shading shows extent; the dashed
        # line shows where the encoding starts to clip).
        ax.axvline(enc_lo_x, color=WARN, lw=1.0, ls="--", alpha=0.7)
        ax.axvline(enc_hi_x, color=WARN, lw=1.0, ls="--", alpha=0.7)

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
    ax.set_ylim(0, float(density.max()) * 1.05)
    ax.invert_yaxis()
    # Frame on the input encoding's representable range — the stops the
    # LUT actually sees as distinct values. Outside this range the input
    # encoding clipped to 0 or 1 and the curve is necessarily flat, so
    # including it just compresses the meaningful portion of the plot.
    enc_idx_all = np.where(~encoded_clip_mask)[0]
    if enc_idx_all.size >= 2:
        ax.set_xlim(stops[enc_idx_all[0]], stops[enc_idx_all[-1]])
    else:
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
        color=HI, fontsize=SUPTITLE_FS, pad=SUPTITLE_PAD,
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
                 color=HI, fontsize=SUPTITLE_FS, pad=SUPTITLE_PAD)
    _setup_2d(ax)
    ax.legend(facecolor="#1a1a1a", labelcolor=FG, framealpha=0.9,
              loc="upper right", fontsize=9)
    return fig
