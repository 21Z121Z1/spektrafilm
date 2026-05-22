"""The QA suite — 14 tests, one figure each.

Each function takes a :class:`QAContext` and returns a :class:`Result`.
Five tests address **LUT fidelity** (does the cube preserve the
pipeline within industry tolerance), seven address **model diagnostic**
(does the spektrafilm pipeline itself produce sensible output), and
two are **picture-style diagnostics** that render the bundle through
representative stress patterns. All three flavors are necessary for
an industry-grade QA story — see ``studies/a40_lut_system/n080``.

Tests that need the cached pipeline reference (``ctx.reference``) are
LUT-fidelity tests; model-diagnostic tests use their own small
stimulus patterns and invoke the pipeline ad-hoc via
``reference.run_pipeline_at``.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import numpy as np

import colour

from spektrafilm_lut_creator.color_spaces import to_xyz
from spektrafilm_lut_creator.qa import evaluators, metrics, patterns, reference, viz
from spektrafilm_lut_creator.qa.result import Result

if TYPE_CHECKING:
    from spektrafilm_lut_creator.qa.suite import QAContext


def _save(ctx: "QAContext", fig, name: str):
    """Save a figure under ``figures/<name>.png`` and close it.

    Stamps every figure with the producing spektrafilm version (bottom
    center) via :func:`viz.add_footer` so reports remain traceable
    after they leave the bundle directory.
    """
    viz.add_footer(fig, ctx.bundle.meta.provenance.spektrafilm_version)
    path = ctx.figures_dir / f"{name}.png"
    fig.savefig(path, dpi=160, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# LUT fidelity.
# ---------------------------------------------------------------------------

def off_grid_identity(ctx: "QAContext") -> Result:
    """Off-grid ΔE₀₀ between the LUT (trilinear + tetrahedral) and the
    live spektrafilm pipeline.

    The single most load-bearing test in the suite. The exact-grid test
    (already in M4) verifies the bake is self-consistent at corners;
    this test verifies what real users will see — the LUT applied at
    off-grid positions via the same interpolation methods Resolve,
    Nuke, FFmpeg, and OBS actually use.

    Industry tolerances (SDR, CIEDE2000): ``max ≤ 2.0`` and
    ``p99 ≤ 1.0`` for both trilinear and tetrahedral. ΔE₀₀ is the
    metric colorists reference daily; ΔITP (BT.2124) is also computed
    and reported but the pass criterion is ΔE₀₀.

    References
    ----------
    - CIE 142:2001 (CIEDE2000) — the workhorse perceptual metric.
    - ITU-R BT.2124 — HDR-aware perceptual color difference (ΔITP).
    - Kirk, *Tetrahedral Interpolation* (FilmLight Truelight whitepapers).
    - OCIO ``ociochecklut`` — the reference implementation we mirror.
    """
    ref = ctx.reference
    table = ctx.lut.table
    out_cs = ctx.spec.output_color_space

    lut_out_tri = evaluators.apply_trilinear(table, ref.rng_samples_encoded)
    lut_out_tet = evaluators.apply_tetrahedral(table, ref.rng_samples_encoded)

    de_tri = metrics.delta_e_2000(lut_out_tri, ref.pipeline_out_encoded, output_color_space=out_cs)
    de_tet = metrics.delta_e_2000(lut_out_tet, ref.pipeline_out_encoded, output_color_space=out_cs)
    stats_tri = metrics.summary_stats(de_tri)
    stats_tet = metrics.summary_stats(de_tet)

    # Secondary ΔITP for HDR-side comparability; not used for pass/fail
    # while bundles are SDR-dominant.
    itp_tri = metrics.delta_itp(lut_out_tri, ref.pipeline_out_encoded, output_color_space=out_cs)
    stats_itp = metrics.summary_stats(itp_tri)

    summary = {
        "trilinear_dE2000_max": stats_tri["max"],
        "trilinear_dE2000_p99": stats_tri["p99"],
        "trilinear_dE2000_p50": stats_tri["p50"],
        "tetrahedral_dE2000_max": stats_tet["max"],
        "tetrahedral_dE2000_p99": stats_tet["p99"],
        "tetrahedral_dE2000_p50": stats_tet["p50"],
        "trilinear_dITP_max": stats_itp["max"],
        "trilinear_dITP_p99": stats_itp["p99"],
    }
    passed = bool(
        stats_tri["max"] <= 2.0 and stats_tri["p99"] <= 1.0
        and stats_tet["max"] <= 2.0 and stats_tet["p99"] <= 1.0
    )

    fig = viz.offgrid_error_scatter(
        ref.rng_samples_encoded, de_tri,
        title=(f"Off-grid ΔE₀₀ (trilinear) — max={stats_tri['max']:.3f}, "
               f"p99={stats_tri['p99']:.3f}"),
        cbar_label="ΔE₀₀",
    )
    path = _save(ctx, fig, "off_grid_identity")

    return Result(
        name="off_grid_identity",
        summary=summary,
        scalar_field=de_tri,
        figure_path=path,
        units="ΔE₀₀",
        interpretation=(
            "ΔE₀₀ measures perceptual error between the LUT's prediction "
            "(via interpolation in the host's mode — trilinear or "
            "tetrahedral) and the live pipeline at off-grid positions. "
            "Above the visibility threshold users will see interpolation "
            "artifacts the on-grid test cannot detect; remedies are "
            "higher LUT resolution or wire-shaping changes. ΔITP is "
            "reported as a secondary, HDR-aware companion metric."
        ),
        reference_values={
            "trilinear_dE2000_max": "≤ 2.0 — perceptual visibility threshold for graphics work",
            "trilinear_dE2000_p99": "≤ 1.0 — interpolation-quality target across the cube",
            "tetrahedral_dE2000_max": "≤ 2.0 — same threshold under tetrahedral interpolation",
            "tetrahedral_dE2000_p99": "≤ 1.0 — same target under tetrahedral interpolation",
        },
        passed=passed,
    )


def monotonicity(ctx: "QAContext") -> Result:
    """Diagonal axes of the cube must be non-decreasing in their
    matching output channel.

    A negative finite-difference is a fold-back: increasing R input
    decreased R output, which produces non-invertible regions that
    confound grading. Off-diagonal non-monotonicity (e.g. green-in-red
    curve) can be physically legitimate from DIR couplers or crosstalk
    in print chemistry, so we don't count those.

    The cube-wide violation count
    (``metrics.monotonicity_violations``) is the master pass/fail
    statistic. The figure visualizes one informative centerline:
    each panel sweeps one channel with the other two held at the
    input color space's **middle-gray-encoded** value (linear 0.18
    encoded through the input CCTF). This is more honest than the
    cube-midpoint sweep for log-encoded inputs — for V-Log the
    encoded midpoint (0.5) corresponds to mid-bright, not gray;
    pinning at the true middle-gray-encoded position (≈0.42 for
    V-Log, ≈0.46 for sRGB, 0.18 for ACEScg) gives a centerline that
    actually represents the channel's behavior at a neutral gray.

    References
    ----------
    - OCIO v2 design notes on monotonic LUT structure.
    - FilmLight Truelight whitepapers.
    """
    from spektrafilm_lut_creator.color_spaces import encode_cctf

    table = ctx.lut.table
    info = metrics.monotonicity_violations(table)

    # Middle-gray-encoded for the input color space. linear 0.18 (the
    # photographic 18% middle-gray reference) through the input CCTF.
    # Same value for all three channels by definition; one scalar.
    mid_gray_linear = np.full((1, 3), 0.18, dtype=float)
    mid_gray_encoded = encode_cctf(mid_gray_linear, ctx.spec.input_color_space)
    pin = float(np.asarray(mid_gray_encoded).flatten()[0])

    # Sweep each axis at the middle-gray centerline. Density-65 sampling
    # gives a finer curve than the cube's native resolution; trilinear
    # interpolation on the LUT smooths small cube-grid quantization
    # artifacts so the visible violations reflect real fold-backs,
    # not float-precision jitter between cube cells.
    n_samples = 65
    sweep = np.linspace(0.0, 1.0, n_samples)
    pin_arr = np.full(n_samples, pin)
    sweep_inputs = {
        "R": np.stack([sweep, pin_arr, pin_arr], axis=-1),
        "G": np.stack([pin_arr, sweep, pin_arr], axis=-1),
        "B": np.stack([pin_arr, pin_arr, sweep], axis=-1),
    }
    sweep_outputs = tuple(
        evaluators.apply_trilinear(table, np.asarray(samples, dtype=np.float32))
        for samples in sweep_inputs.values()
    )

    # Per-panel violation masks: where the matching output channel's
    # finite-diff is negative along the swept axis.
    masks = (
        np.diff(sweep_outputs[0][:, 0]) < 0.0,
        np.diff(sweep_outputs[1][:, 1]) < 0.0,
        np.diff(sweep_outputs[2][:, 2]) < 0.0,
    )
    centerline_violations = int(sum(int(m.sum()) for m in masks))

    pin_label = f"{pin:.3f} (mid-gray encoded)"
    fig = viz.transfer_curves(
        sweep, sweep_outputs,
        pin_label=pin_label, violation_marks=masks,
        suptitle=(
            f"Per-axis transfer curves through middle-gray "
            f"({ctx.spec.input_color_space} encoded {pin:.3f})"
        ),
    )
    path = _save(ctx, fig, "monotonicity")

    passed = (info["violations"] == 0)
    return Result(
        name="monotonicity",
        summary={
            "violations": int(info["violations"]),
            "worst_negative_diff": float(info["worst_negative_diff"]),
            "centerline_pin_encoded": pin,
            "centerline_violations": centerline_violations,
        },
        figure_path=path,
        units="cells",
        interpretation=(
            "Each diagonal axis-channel pair (R-in vs R-out, etc.) "
            "must be monotonic for the LUT to be invertible without "
            "fold-backs. The `violations` count is cube-wide; the "
            "figure visualizes the centerline sweep through "
            "middle-gray-encoded for honest comparison across input "
            "color spaces (without this, log inputs like V-Log would "
            "be evaluated through their encoded midpoint, which is "
            "mid-bright rather than gray and produces visually "
            "confusing curve shapes). Violations on the centerline "
            "indicate either a model regime that legitimately produces "
            "a fold (DIR couplers in shadows, gamut compression at "
            "the saturation knee) or a bake artifact at the cube "
            "boundary; investigate both before relaxing the test."
        ),
        reference_values={
            "violations": "== 0 — any cube-wide fold-back is a hard invertibility break",
            "worst_negative_diff": "== 0.0 when violations == 0; a tiny negative (≈ -1e-5) on the centerline is bake jitter rather than a real fold",
        },
        passed=passed,
    )


def jacobian_condition(ctx: "QAContext") -> Result:
    """Local 3×3 Jacobian condition number — a smoothness diagnostic.

    Gamut compression and density shoulders produce regions where the
    local linear approximation of the transform is near-singular
    (long thin parallelepipeds in output space). Healthy cube cells
    have log-cond ~ O(1); pathological cells climb above 3 (cond ~
    1000), signaling visible artifacts.

    References
    ----------
    - Siragusano, *The Beauty of Per-Pixel Math* (FilmLight, Vimeo).
    - Hable, filmicworlds.com.
    """
    table = ctx.lut.table
    n = ctx.lut.resolution
    field = metrics.local_jacobian_log_cond(table)
    stats = metrics.summary_stats(field)
    fig = viz.jacobian_condition_3d(field, n)
    path = _save(ctx, fig, "jacobian_condition")

    return Result(
        name="jacobian_condition",
        summary={
            "max_log10_cond": stats["max"],
            "p99_log10_cond": stats["p99"],
            "p50_log10_cond": stats["p50"],
        },
        scalar_field=field,
        figure_path=path,
        units="log10(cond J)",
        interpretation=(
            "Where the cube colors locally compress onto a near-curve "
            "(e.g., the highlight shoulder collapsing chroma), log-cond "
            "rises sharply. Shape of the high-cond region matters more "
            "than its absolute value — a thin shell near the gamut "
            "boundary is expected; a fat interior region is suspicious."
        ),
        passed=None,  # informational — no hard threshold
    )


def total_variation(ctx: "QAContext") -> Result:
    """Per-axis total variation + axial-FFT high-band energy.

    A noisy bake (NaN propagation, numerical instability, bad
    chemistry models) lifts these. Reported informational — typical
    spektrafilm bundles will need baselines before this gates CI.
    """
    table = ctx.lut.table
    tv = metrics.total_variation(table)
    fft = metrics.axial_fft_highband_ratio(table)
    summary = {**tv, **fft}
    fig = viz.output_histograms(ctx.grid_output)
    path = _save(ctx, fig, "total_variation")

    return Result(
        name="total_variation",
        summary=summary,
        figure_path=path,
        units="",
        interpretation=(
            "Total variation is the mean absolute finite-difference of "
            "the cube table — a smoothness scalar. The axial-FFT "
            "high-band ratio adds spectral-domain evidence: a bake with "
            "banding shows lifted energy in the upper half of the "
            "axial spectrum. The histogram plot is a sanity check on "
            "clipping incidence at 0 and 1."
        ),
        passed=None,
    )


def output_gamut_compression(ctx: "QAContext") -> Result:
    """Detect cube-face folds, report gamut compression ratio, and
    visualize the output gamut before/after compression.

    Combines two diagnostics that share the same underlying data
    (LUT cube + an unbounded re-run of the simulation):

    1. **Fold-back metric** — `metrics.gamut_self_intersection_score`
       counts cube-face triangles that flip orientation. Any fold is a
       hard non-invertibility and fails the test.
    2. **Hull volume ratio** — output OkLab convex-hull volume divided
       by input OkLab convex-hull volume. < 1 expected (LUTs compress);
       > 1 means expansion (suspect).
    3. **Gamut compression preview** — a 1x2 figure with the LUT's
       compressed gamut volume (faint cube cloud) and the
       unbounded→compressed rim envelope, shown in OkLab (left) and
       xy chromaticity (right). The xy panel duplicates what the
       standalone preview test used to render; merging the two avoids
       two separate unbounded-pipeline runs.

    References
    ----------
    - ACES Reference Gamut Compression test imagery.
    - Morovic, gamut-mapping CIC papers.
    - spektrafilm-research n110 (output compression design).
    - ACES Reference Gamut Compression v1.3 (AMPAS, 2020).
    """
    from spektrafilm_lut_creator.qa import patterns
    from spektrafilm.utils.gamut_compression import compress_rgb
    from spektrafilm_lut_creator.color_spaces import get as _get_cs

    table = ctx.lut.table
    flips = metrics.gamut_self_intersection_score(table)
    hull = metrics.gamut_hull_volume_ratio(
        ctx.grid_input, ctx.grid_output, ctx.spec.output_color_space,
    )

    # Rim — saturated cube edges — and its unbounded pipeline output.
    rim_samples, rim_segments = patterns.saturated_cube_edges(n=96)
    out_cs_name = ctx.spec.output_color_space
    out_primaries_name = _get_cs(out_cs_name).primaries
    compression_spec = ctx.spec.output_gamut_compress

    rim_unbounded = _run_unbounded_pipeline_for_rim(ctx, rim_samples)
    rim_compressed = (
        compress_rgb(rim_unbounded, compression_spec,
                     output_color_space=out_primaries_name)
        if compression_spec.mode != "off" else rim_unbounded.copy()
    )

    hsv = np.asarray(colour.RGB_to_HSV(rim_samples), dtype=float)
    rim_hues = hsv[..., 0]
    n_per_seg = len(rim_segments[0])
    n_segments = len(rim_segments)

    # Stats for the merged summary (mirror the old preview's numbers).
    ach = rim_unbounded.max(axis=-1)
    bright_mask = ach > 1e-2
    safe_ach = np.where(ach > 1e-6, ach, 1.0)
    d_max = ((ach[..., None] - rim_unbounded) / safe_ach[..., None]).max(axis=-1)
    oog_mask = (d_max > 1.0) & bright_mask
    oog_fraction = float(oog_mask.sum() / max(int(bright_mask.sum()), 1))
    rim_disp = np.linalg.norm(rim_unbounded - rim_compressed, axis=-1)

    summary = {
        "fold_triangles": int(flips["flips"]),
        "fold_fraction": float(flips["fraction"]),
        "input_hull_volume": float(hull["input_hull_volume"]),
        "output_hull_volume": float(hull["output_hull_volume"]),
        "compression_ratio": float(hull["compression_ratio"]),
        "compression_mode": compression_spec.mode,
        "compression_algorithm": compression_spec.algorithm,
        "rim_oog_fraction": oog_fraction,
        "rim_oog_samples": int(oog_mask.sum()),
        "rim_max_displacement":
            float(rim_disp[oog_mask].max()) if oog_mask.any() else 0.0,
        "rim_mean_displacement":
            float(rim_disp[oog_mask].mean()) if oog_mask.any() else 0.0,
    }
    # Hard failure when face folds appear. Compression ratio > 1.05 is
    # suspicious (rare expansion); < 0.05 is suspicious (extreme
    # collapse). Rim displacement/OOG is informational only.
    passed = (flips["flips"] == 0
              and 0.05 <= hull["compression_ratio"] <= 1.05)

    fig = viz.gamut_compression_3d_xy(
        grid_output_compressed=ctx.grid_output,
        rim_unbounded_linear=rim_unbounded,
        rim_compressed_linear=rim_compressed,
        rim_input_hues=rim_hues,
        rim_n_per_segment=n_per_seg,
        rim_n_segments=n_segments,
        in_cs_name=ctx.spec.input_color_space,
        out_cs_name=out_cs_name,
        compression_spec=compression_spec,
    )
    path = _save(ctx, fig, "output_gamut_compression")

    return Result(
        name="output_gamut_compression",
        summary=summary,
        figure_path=path,
        units="",
        interpretation=(
            "Face folds mean the cube surface maps onto itself — a "
            "non-invertible region that breaks grading. The compression "
            "ratio quantifies how much perceptual volume the LUT throws "
            "away; numbers in [0.05, 1.05] are normal, outside means "
            "either degenerate output (very small ratio) or unexpected "
            "expansion (ratio > 1). The figure's left panel shows the "
            "LUT's compressed gamut in OkLab (faint cube cloud) with "
            "the unbounded rim (solid colored lines) and the compressed "
            "rim (dashed) overlaid; the right panel is the canonical "
            "xy-chromaticity preview of the same compression event."
        ),
        reference_values={
            "fold_triangles": "== 0 — any cube-face fold is a hard non-invertibility",
            "compression_ratio": "in [0.05, 1.05] — < 0.05 is extreme collapse, > 1.05 is unexpected expansion",
        },
        passed=passed,
    )


# ---------------------------------------------------------------------------
# Model diagnostic.
# ---------------------------------------------------------------------------

def characteristic_curve(ctx: "QAContext") -> Result:
    """Pipeline response in the density domain — coupler diagnostic.

    Reads complementary to ``monotonicity``: that test measures
    "is the cube invertible?" along the centerline; this one shows
    "how do the channels interact?" by sweeping each channel against
    several constant values of the other two ("pins") and overlaying
    the resulting density curves.

    Pins are picked so the **off-diagonal curves enter each panel at
    target output densities** ``[0.2, 0.4, 0.6, 0.8, 1.0]``. Concretely:
    we build a fine neutral (R=G=B=t) characteristic curve from the
    LUT, invert it once to find the input codes ``t`` whose neutral
    output density equals each target D, and pin the non-swept channels
    at those codes. So in the R panel, at sweep_x=0, the G and B curves
    start near D=0.2/0.4/0.6/0.8/1.0 — the legend value matches what
    you see on the Y-axis at the left edge of the panel. (Not exact —
    pulling the swept channel to 0 perturbs the off-diagonal output via
    chemistry coupling — but well within "about", which is the point of
    the visualization.)

    The vertical spread between same-color curves at different pins is
    the **DIR coupler signature**: if the developer-inhibitor couplers
    in the film simulation are active, pushing one channel's pin level
    shifts the other channels' density response visibly; an uncoupled
    simulation would show all same-color curves stacked.

    The bottom-right panel keeps the canonical neutral (R=G=B) curve
    — the classic film D-vs-input characteristic from datasheets.

    Uses trilinear interpolation on the LUT (the LUT already encodes
    the on-grid pipeline response; we sample at the pins which may not
    align with the cube grid).

    References
    ----------
    - Hunt, *The Reproduction of Colour* — characteristic curves.
    - Any film stock datasheet (Kodak, Fuji) — the canonical D vs
      log E shape this plot is patterned on.
    """
    table = ctx.lut.table
    n = ctx.lut.resolution

    # Build the neutral characteristic curve at fine resolution and
    # invert it to find the pin input codes whose neutral output density
    # equals each target. Use the mean of the three output channels as
    # the density reference — for a calibrated neutral the three channels
    # track closely, and the mean is robust to small per-channel
    # divergence.
    pin_densities = (0.2, 0.4, 0.6, 0.8, 1.0)
    alphas = (0.3, 0.6, 1.0, 0.6, 0.3)
    n_neutral_probe = 257
    t_probe = np.linspace(0.0, 1.0, n_neutral_probe).astype(np.float32)
    neutral_probe_in = np.stack([t_probe, t_probe, t_probe], axis=-1)
    neutral_probe_out = np.asarray(
        evaluators.apply_trilinear(table, neutral_probe_in), dtype=float,
    )
    neutral_d = -np.log10(
        np.clip(np.mean(neutral_probe_out, axis=-1), 1e-4, 1.0),
    )
    # np.interp wants x ascending; density is monotonically decreasing in
    # t (more input → less density on a print), so flip both vectors.
    pin_codes = tuple(
        float(np.interp(d, neutral_d[::-1], t_probe[::-1].astype(float)))
        for d in pin_densities
    )

    # Trilinear-sampled sweeps at finer-than-cube resolution; gives
    # smooth curves even at low cube resolutions and lets us pin the
    # non-swept channels at exactly the requested values rather than
    # snapping to cube cells.
    n_samples = 65
    sweep_x = np.linspace(0.0, 1.0, n_samples)
    r_sweep_data: list[tuple[float, np.ndarray, float]] = []
    g_sweep_data: list[tuple[float, np.ndarray, float]] = []
    b_sweep_data: list[tuple[float, np.ndarray, float]] = []
    for pin_d, pin_code, alpha in zip(pin_densities, pin_codes, alphas):
        pin_arr = np.full(n_samples, pin_code)
        r_in = np.stack([sweep_x, pin_arr, pin_arr], axis=-1).astype(np.float32)
        g_in = np.stack([pin_arr, sweep_x, pin_arr], axis=-1).astype(np.float32)
        b_in = np.stack([pin_arr, pin_arr, sweep_x], axis=-1).astype(np.float32)
        # The pin value in the data tuple is the *density* — used for
        # legend labels in viz.density_transfer_curves so the label
        # units match the panel's Y-axis.
        r_sweep_data.append((pin_d, evaluators.apply_trilinear(table, r_in), alpha))
        g_sweep_data.append((pin_d, evaluators.apply_trilinear(table, g_in), alpha))
        b_sweep_data.append((pin_d, evaluators.apply_trilinear(table, b_in), alpha))

    # Neutral R=G=B sweep — the canonical D-vs-input curve.
    neutral_in = np.stack([sweep_x, sweep_x, sweep_x], axis=-1).astype(np.float32)
    neutral_samples = evaluators.apply_trilinear(table, neutral_in)

    fig = viz.density_transfer_curves(
        sweep_x,
        r_sweep_data, g_sweep_data, b_sweep_data,
        neutral_samples,
    )
    path = _save(ctx, fig, "characteristic_curve")

    # Quantify the system gamma at the midpoint of the neutral ramp:
    # slope of log10(output) vs log10(input) at index n//2.
    mid = n // 2
    axis_codes = np.linspace(1e-6, 1.0, n)
    neutral_out = np.array([table[i, i, i, :] for i in range(n)])
    log_in = np.log10(axis_codes)
    log_out = np.log10(np.clip(np.mean(neutral_out, axis=-1), 1e-4, 1.0))
    # Local slope at mid via central difference.
    gamma_mid = float((log_out[mid + 1] - log_out[mid - 1]) /
                      (log_in[mid + 1] - log_in[mid - 1]))

    # Channel divergence at mid: how far the three CMY densities spread.
    densities = -np.log10(np.clip(neutral_out, 1e-4, 1.0))
    spread = float(np.max(np.ptp(densities, axis=-1)))

    return Result(
        name="characteristic_curve",
        summary={
            "system_gamma_at_mid": gamma_mid,
            "max_channel_density_spread": spread,
        },
        figure_path=path,
        units="density",
        interpretation=(
            "The system's response to neutral input should be smooth, "
            "with the three channels tracking each other (small spread). "
            "Big channel divergence on a neutral ramp is a calibration "
            "or chemistry-model bug, not a LUT bug; check the print "
            "chemistry's neutral handling."
        ),
        passed=None,
    )


def planckian_sweep(ctx: "QAContext") -> Result:
    """Pipeline response to white surfaces under daylight illuminants.

    A spektrafilm bundle should send "white under D55", "white under
    D65", "white under D75", etc. to a smooth, monotonic curve in
    output chromaticity. Kinks or fold-backs reveal white-balance
    handling bugs.

    References
    ----------
    - CIE 15:2018 (daylight illuminants).
    - Poynton, *Color FAQ* — white-point handling.
    """
    spec = ctx.spec
    samples_encoded, cct = patterns.planckian_sweep(spec.input_color_space, n=16)

    # Apply the LUT (cheap) — that's what users will see.
    lut_out_encoded = evaluators.apply_trilinear(ctx.lut.table, samples_encoded)
    out_xyz = to_xyz(lut_out_encoded, spec.output_color_space)
    out_xy = np.asarray(colour.XYZ_to_xy(out_xyz), dtype=float)

    # Smoothness: max angular deviation of consecutive sweep segments
    # from a straight line through the cloud (a sanity proxy for
    # monotone smoothness without imposing a specific curve shape).
    diffs = np.diff(out_xy, axis=0)
    norms = np.linalg.norm(diffs, axis=1) + 1e-12
    cos_theta = np.sum(diffs[:-1] * diffs[1:], axis=1) / (norms[:-1] * norms[1:])
    cos_theta = np.clip(cos_theta, -1.0, 1.0)
    bend_angle_deg = np.degrees(np.arccos(cos_theta))
    max_bend = float(bend_angle_deg.max()) if bend_angle_deg.size else 0.0

    locus_xy = patterns.spectral_locus_chromaticities()
    fig = viz.planckian_path(cct, out_xy, locus_xy, spec.output_color_space)
    path = _save(ctx, fig, "planckian_sweep")

    # > 30 deg between consecutive segments on a daylight sweep is
    # surprising; pure monotone smoothness would give ~0 deg.
    passed = max_bend <= 30.0

    return Result(
        name="planckian_sweep",
        summary={
            "max_bend_angle_deg": max_bend,
            "cct_range_k": f"{int(cct[0])}-{int(cct[-1])}",
        },
        figure_path=path,
        units="degrees",
        interpretation=(
            "White points across the daylight CCT range should map to a "
            "smooth curve in output chromaticity. Sharp bends suggest "
            "the model is doing something discontinuous to chromatic "
            "adaptation — worth investigating the scan illuminant "
            "handling and the print's spectral response curves."
        ),
        reference_values={
            "max_bend_angle_deg": "≤ 30° — daylight CCT sweep should map to a smooth curve; pure monotone smoothness gives ~0°",
        },
        passed=passed,
    )


def hue_twist_oklab(ctx: "QAContext") -> Result:
    """Maximum hue rotation per saturation band, in OkLab.

    Reported as **informational** for v1: spektrafilm is a film
    simulation and film simulations legitimately rotate hue
    (yellow-green shift, red darkening, etc.) — a "pass/fail"
    threshold without per-stock baselines is just noise. The numbers
    are meant for tracking drift vs. previous bakes, and once the
    baselines work from n080 §10 ships, this becomes a gated test.

    Filtering: input samples with OkLab chroma > 0.6 are dropped
    (they lie outside the visible spectral locus — V-Gamut and
    ProPhoto primaries extend there — and don't have meaningful hue
    coordinates).

    References
    ----------
    - Ottosson, *OkLab*, https://bottosson.github.io/posts/oklab/.
    - Yedlin, *Display Prep Demo*, yedlin.net.
    - Sobotka, *AgX*, github.com/sobotka/AgX.
    """
    in_cs = ctx.spec.input_color_space
    out_cs = ctx.spec.output_color_space
    lab_in_all = viz._to_oklab(ctx.grid_input, in_cs)
    lab_out_all = viz._to_oklab(ctx.grid_output, out_cs)

    # Drop out-of-locus inputs (V-Gamut, ProPhoto extremes, etc.).
    # OkLab chroma > 0.6 corresponds to colors well outside any
    # physically realizable gamut; hue at those coordinates is an
    # extrapolation artifact rather than a meaningful measurement.
    c_in_all = np.sqrt(lab_in_all[:, 1] ** 2 + lab_in_all[:, 2] ** 2)
    in_locus = c_in_all <= 0.6
    n_filtered = int((~in_locus).sum())
    lab_in = lab_in_all[in_locus]
    lab_out = lab_out_all[in_locus]
    grid_in_filt = ctx.grid_input[in_locus]
    grid_out_filt = ctx.grid_output[in_locus]

    info = dict(metrics.hue_rotation_per_band(lab_in, lab_out))
    info["samples_in_locus"] = int(in_locus.sum())
    info["samples_filtered_out_of_locus"] = n_filtered

    fig = viz.hue_twist_oklab(grid_in_filt, grid_out_filt, in_cs, out_cs)
    path = _save(ctx, fig, "hue_twist_oklab")

    return Result(
        name="hue_twist_oklab",
        summary=info,
        figure_path=path,
        units="degrees",
        interpretation=(
            "Hue rotation as a function of input chroma is the single "
            "thing colorists notice without instrumentation. Some "
            "rotation is part of the look (a film simulation IS a hue "
            "rotation in places); the magnitude is stock-specific. "
            "Use this number to track drift between bakes of the same "
            "stock — large jumps signal a model-side regression. "
            "Per-stock pass/fail thresholds wait on the baselines work "
            "(n080 §10)."
        ),
        passed=None,  # informational; no absolute threshold pre-baselines
    )


def dynamic_range_usage(ctx: "QAContext") -> Result:
    """How many input stops does the LUT actually render — in the
    colorist's unit (scene-linear stops above middle gray).

    Generates a neutral ramp uniform in **scene-linear log2 stops**
    across ``[-8, +8]`` EV (range that covers most practical
    cameras), CCTF-encodes it for the input space, clips to the LUT
    input domain ``[0, 1]``, applies the LUT, and decodes the
    output's CCTF to get scene-linear output luminance. The
    resulting D vs log E curve is the **canonical film characteristic
    plot** every film datasheet ships.

    Separates two sources of range loss:

    - **Encoding clip**: stops outside what the input encoding can
      represent (e.g., sRGB caps at ~+2.5 EV above middle gray; V-Log
      reaches +8 EV). Not the LUT's fault.
    - **Toe / shoulder collapse**: stops within the encoded range
      where output slope falls below 0.10 density per stop — the
      LUT's rendering decision to compress shadows or highlights.

    Reported informational for v1 — there's no universal "correct"
    answer for how many stops a film simulation should preserve, but
    knowing the number is a colorist staple.

    References
    ----------
    - Hunt, *The Reproduction of Colour* — characteristic curves.
    - ARRI K1S0-057 LogC whitepaper.
    - ANSI/SMPTE RP 180 (18% middle gray).
    """
    in_cs = ctx.spec.input_color_space
    out_cs = ctx.spec.output_color_space
    stops, encoded_in, encoded_clip_mask = patterns.dynamic_range_neutral_ramp(in_cs)

    # Apply the LUT (already composed if 2-LUT) at the encoded inputs.
    lut_out_encoded = evaluators.apply_trilinear(ctx.lut.table, encoded_in)

    # Decode the output's CCTF to get scene-linear and take the Y
    # (luminance) component via XYZ. `to_xyz` handles the CCTF decode
    # plus primaries-to-XYZ transform.
    xyz_out = to_xyz(lut_out_encoded, out_cs)
    y_out = np.asarray(xyz_out[:, 1], dtype=float)
    # Some output spaces' linear Y can dip very slightly negative on
    # extreme gamut edges (numerical) — clip the floor.
    y_out = np.clip(y_out, 1e-6, None)

    stats = metrics.dynamic_range_stats(stops, y_out, encoded_clip_mask)
    fig = viz.dynamic_range_curve(
        stops, y_out, encoded_clip_mask, stats,
        in_cs=in_cs, out_cs=out_cs,
    )
    path = _save(ctx, fig, "dynamic_range_usage")

    return Result(
        name="dynamic_range_usage",
        summary=stats,
        figure_path=path,
        units="stops",
        interpretation=(
            "The 'active rendering range' is how many input stops the "
            "LUT distinguishes — slope above 0.10 D/stop. Below that "
            "threshold, an input stop change barely moves the output, "
            "so the stop is effectively collapsed. The 'input encoding "
            "range' is a property of the input color space (sRGB ~2.5 "
            "EV above middle gray, V-Log ~8 EV), not the LUT. Toe and "
            "shoulder collapsed stops sit *within* the encoded range — "
            "they're rendering decisions, not encoding limits."
        ),
        passed=None,
    )


def spectral_locus_envelope(ctx: "QAContext") -> Result:
    """Full chromaticity map of the LUT cube — every cube cell as a
    dot in xy, colored by its actual output RGB.

    The shipped LUT already contains the output color for every input
    cube cell. Projecting all of them to xy and coloring each dot by
    its own rendered RGB shows the simulation's complete chromaticity
    footprint at once: where in xy the LUT maps colors, how densely
    each region is sampled, and what color you'd actually see at each
    location.

    Density is conveyed by alpha blending: small markers at low alpha
    accumulate visually in regions where many cube cells project to
    similar chromaticities (the dye-gamut "shoulders" and the
    achromatic core), and fade to single dots in the sparse rim.

    Replaces the older rim-only envelope plot — the rim envelope's
    "where does the gamut reach" role is now covered by the right
    panel of ``output_gamut_compression``; this plot answers the
    complementary "what does the full LUT *look* like in xy" question.

    References
    ----------
    - Mansencal (@KelSolaar), colour-science visualizations.
    - ACES Reference Gamut Compression.
    """
    out_cs = ctx.spec.output_color_space

    # 1) Every cube cell as a sample, flattened to (N³, 3).
    cube = ctx.lut.table  # encoded output RGB, shape (N, N, N, 3) in [0, 1]
    n = cube.shape[0]
    rgb_encoded = np.asarray(cube, dtype=float).reshape(-1, 3)

    # 2) Project each cell to xy in the output color space's frame.
    #    to_xyz takes encoded RGB and handles the CCTF + matrix.
    xyz = to_xyz(rgb_encoded, out_cs)
    xy = np.asarray(colour.XYZ_to_xy(xyz), dtype=float)

    # 3) Skip degenerate (near-black) samples whose xy is unreliable.
    Y = np.asarray(xyz[:, 1], dtype=float)
    valid = (Y > 1e-4) & np.all(np.isfinite(xy), axis=-1)

    # 4) Output primaries + white for the reference frame.
    out_primaries = colour.RGB_COLOURSPACES[
        __import__("spektrafilm_lut_creator.color_spaces", fromlist=["get"])
            .get(out_cs).primaries
    ]
    out_white = np.asarray(out_primaries.whitepoint, dtype=float)
    out_tri = np.asarray(out_primaries.primaries, dtype=float)

    # 5) Spectral locus for the outer reference.
    from spektrafilm.utils.gamut_compression import spectral_locus_xy
    locus = spectral_locus_xy()

    # ``accent`` is the yellow-ish color used for the input-gamut
    # triangle overlay (visible against the dark BG); titles use the
    # shared viz.HI white so they match the rest of the report.
    bg, fg, accent, dim = "#0a0a0a", "#cccccc", "#ffee66", "#888888"

    fig, ax = plt.subplots(figsize=(10, 10), facecolor=bg, layout="constrained")
    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.tick_params(colors=fg)
    ax.grid(True, alpha=0.08, color=accent)

    # Reference frame — drawn before scatter so dots sit on top.
    ax.plot(locus[:, 0], locus[:, 1], color=dim, lw=1.0, alpha=0.5,
            label="visible spectral locus")
    locus_fill = plt.Polygon(
        locus, closed=True, facecolor="#cccccc",
        alpha=0.015, edgecolor="none",
    )
    ax.add_patch(locus_fill)

    tri = np.vstack([out_tri, out_tri[:1]])
    ax.plot(tri[:, 0], tri[:, 1], color=fg, lw=1.6, alpha=0.85,
            label=f"{out_cs} gamut")
    primary_colors = ["#ff5566", "#66ff88", "#5599ff"]
    primary_labels = ["R", "G", "B"]
    for (px, py), pcol, plab in zip(out_tri, primary_colors, primary_labels):
        ax.plot(px, py, "o", color=pcol, markersize=10,
                markeredgecolor=bg, markeredgewidth=1.5, zorder=4)
        offset = np.array([px, py]) - out_white
        norm = np.linalg.norm(offset) + 1e-9
        lx, ly = np.array([px, py]) + 0.035 * offset / norm
        ax.text(lx, ly, plab, color=pcol, ha="center", va="center",
                fontsize=12, fontweight="bold", zorder=5)
    ax.plot(out_white[0], out_white[1], "D", color=fg, markersize=9,
            markeredgecolor=bg, markeredgewidth=1.2,
            label=f"{out_cs} white", zorder=4)

    # The main event — every cube cell as a dot at its xy position,
    # colored by its own encoded output RGB. Two layers:
    #   * a fatter, very-low-alpha layer for a soft "glow" where many
    #     cells overlap
    #   * a tighter, slightly-stronger layer for individual dot legibility
    # Together they read as "rendered color in chromaticity space."
    rgb_color = np.clip(rgb_encoded[valid], 0.0, 1.0)
    xy_valid = xy[valid]

    # Marker sizes / alphas scale gently with cube size so 17³ and 33³
    # look comparable. Empirically chosen.
    n_pts = len(xy_valid)
    if n_pts > 0:
        # Glow layer: large markers, very low alpha → density bloom.
        s_glow = max(8.0, 80.0 / np.sqrt(n / 17.0))
        a_glow = 0.10
        # Dot layer: small markers, moderate alpha → individual cells.
        s_dot = max(2.0, 12.0 / np.sqrt(n / 17.0))
        a_dot = 0.55
        ax.scatter(
            xy_valid[:, 0], xy_valid[:, 1],
            c=rgb_color, s=s_glow, alpha=a_glow,
            edgecolors="none", zorder=2.5,
        )
        ax.scatter(
            xy_valid[:, 0], xy_valid[:, 1],
            c=rgb_color, s=s_dot, alpha=a_dot,
            edgecolors="none", zorder=3,
        )

    # Stats — quantify how much of the cube ends up where.
    inside_tri = _in_triangle(xy_valid, out_tri)
    n_total = int(n_pts)
    n_inside = int(inside_tri.sum())
    inside_fraction = n_inside / max(n_total, 1)

    # Rim fraction — fraction of valid samples within `on_locus_eps`
    # of the spectral locus polyline. Kept for backwards compatibility
    # with the prior summary dict.
    on_locus_eps = 0.02
    if n_pts > 0:
        dist_to_locus = np.min(
            np.linalg.norm(
                xy_valid[:, None, :] - locus[None, :, :], axis=-1,
            ),
            axis=1,
        )
        rim_fraction = float(np.mean(dist_to_locus < on_locus_eps))
    else:
        rim_fraction = 0.0

    text = (
        f"input:     {ctx.spec.input_color_space}\n"
        f"output:    {out_cs}\n"
        f"film:      {ctx.spec.film_profile}\n"
        f"paper:     {ctx.paper_name}\n"
        f"\n"
        f"cube res:  {n}³ = {n**3} cells\n"
        f"valid:     {n_total} ({n_total/max(n**3,1):.0%})\n"
        f"inside gamut: {inside_fraction:.1%}\n"
        f"near locus:   {rim_fraction:.1%}"
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
    ax.set_title(
        f"LUT chromaticity map — {ctx.spec.input_color_space} → {out_cs}",
        color=viz.HI, fontsize=viz.SUPTITLE_FS, pad=viz.SUPTITLE_PAD,
    )

    path = _save(ctx, fig, "spectral_locus_envelope")

    return Result(
        name="spectral_locus_envelope",
        summary={
            "cube_resolution": int(n),
            "cube_cells": int(n ** 3),
            "valid_cells": int(n_total),
            "inside_output_gamut_fraction": float(inside_fraction),
            "near_locus_fraction": float(rim_fraction),
        },
        figure_path=path,
        units="",
        interpretation=(
            "Every cube cell projected to xy and rendered at its own "
            "output RGB color. Density variations show where the LUT "
            "concentrates color reproduction (achromatic core dense, "
            "saturated rim sparse). `inside_output_gamut_fraction` "
            "near 1.0 confirms output gamut compression is keeping "
            "the simulation inside the output primaries triangle as "
            "intended. The complementary `output_gamut_compression` "
            "figure shows the rim envelope and the compression's "
            "effect explicitly."
        ),
        passed=None,
    )


def _in_triangle(xy: np.ndarray, tri: np.ndarray) -> np.ndarray:
    """Vectorized point-in-triangle test for the output primaries triangle."""
    from matplotlib.path import Path as MplPath
    path = MplPath(np.vstack([tri, tri[:1]]))
    return path.contains_points(xy)


# ---------------------------------------------------------------------------
# The ordered default test list.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Input gamut compression diagnostics. Two informational plots shipped in
# every bundle's qa/ folder so colorists can see exactly what the input
# gamut compression is doing for their input space (compression preview)
# and confirm the compression is smooth (circumferential probe). Driven
# by ctx.spec.input_gamut_compress; with mode="off" both tests still
# produce a figure but it just says "compression disabled".
# ---------------------------------------------------------------------------


def _cube_xy_in_film_frame(ctx: "QAContext", reference_illuminant: str):
    """Project the QA cube's input samples to CIE xy in the film's
    reference-illuminant frame — same path ``_rgb_to_tc_b`` runs at
    runtime, minus the LUT lookup.

    Returns ``(xy, b)`` where ``xy`` is shape ``(N, 2)`` and ``b`` is
    ``X+Y+Z`` (for the brightness threshold).
    """
    from spektrafilm_lut_creator.color_spaces import get as get_cs
    in_cs = get_cs(ctx.spec.input_color_space)
    rgb = ctx.grid_input  # encoded; ctx.reference uses encoded inputs too
    # Decode to linear if the input space has a CCTF.
    if in_cs.cctf is not None:
        rgb_linear = np.asarray(
            colour.cctf_decoding(rgb, function=in_cs.cctf), dtype=float,
        )
    else:
        rgb_linear = np.asarray(rgb, dtype=float)
    ref_xy = np.asarray(
        colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"][
            reference_illuminant
        ], dtype=float,
    )
    xyz = colour.RGB_to_XYZ(
        rgb_linear,
        colourspace=in_cs.primaries,
        apply_cctf_decoding=False,
        illuminant=ref_xy,
        chromatic_adaptation_transform="CAT02",
    )
    b = np.asarray(xyz, dtype=float).sum(axis=-1)
    safe_b = np.where(b > 1e-12, b, 1.0)
    xy = xyz[..., :2] / safe_b[..., None]
    return np.asarray(xy, dtype=float), b


def _film_reference_illuminant(ctx: "QAContext") -> str:
    """Resolve the film's reference illuminant by loading its profile.

    The film profile carries the illuminant the spectral sensitivities
    were measured under — and the spektrafilm runtime CAT02-adapts
    input chromaticities to this illuminant before feeding the Hanatos
    LUT. The compression in the baked LUT operates in this same frame,
    so the QA plot must too. Falls back to ``"D55"`` if anything goes
    wrong (most film profiles).
    """
    try:
        from spektrafilm.profiles.io import load_profile
        profile = load_profile(ctx.spec.film_profile)
        ref = profile.info.reference_illuminant
        return str(ref) if ref else "D55"
    except Exception:
        return "D55"


def input_gamut_compression_preview(ctx: "QAContext") -> Result:
    """Visualize what the input gamut compression does for this bundle.

    For the bundle's input color space, we project the QA cube to CIE
    xy in the film's reference-illuminant frame (the same projection
    the runtime does just before the Hanatos LUT lookup), identify
    out-of-locus samples, and draw arrows from each OOG sample to its
    compressed destination. The figure is informational — the
    compression itself is correct by construction; this lets a colorist
    see at a glance how much of their input cube gets modified.

    Styling mirrors spektrafilm-research/studies/a40_lut_system/
    tune_input_gamut_compression.py ``plot_compression_preview`` so the
    QA artifact reads the same way as the study figures.

    References
    ----------
    - ACES Reference Gamut Compression v1.3 (AMPAS, 2020).
    - Hanatos et al., *Sigmoidal Compression for Reflectance Manifold* (2025).
    - spektrafilm-research n100 §5.
    """
    from spektrafilm.utils.gamut_compression import (
        compress_xy, spectral_locus_xy,
    )
    from matplotlib.path import Path as MplPath

    # Palette matches the tuning script (BG/FG/HI/DIM and the
    # OOG/compressed/arrow colors). Keeping these inline rather than
    # importing from the research tree keeps QA self-contained.
    # ``accent`` is the yellow-ish color used for the input-gamut
    # triangle overlay (visible against the dark BG); titles use the
    # shared viz.HI white so they match the rest of the report.
    bg, fg, accent, dim = "#0a0a0a", "#cccccc", "#ffee66", "#888888"
    ok_color = "#66cc99"
    oog_color = "#ff6666"
    moved_color = "#66ccff"
    arrow_color = "#ffaa55"

    spec = ctx.spec.input_gamut_compress
    ref_illuminant = _film_reference_illuminant(ctx)
    ref_xy_arr = np.asarray(
        colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"][
            ref_illuminant
        ], dtype=float,
    )

    xy, b = _cube_xy_in_film_frame(ctx, ref_illuminant)
    locus = spectral_locus_xy()

    # Match the tuning script's brightness gates so the numbers here
    # are directly comparable to its OOG figures.
    bright_mask = b > 1e-2
    degenerate_mask = b <= 1e-4
    in_locus = MplPath(locus).contains_points(xy)
    oog_mask = (~in_locus) & (~degenerate_mask)
    oog_bright_mask = oog_mask & bright_mask
    valid = ~degenerate_mask
    oog_fraction = float(oog_mask.sum() / max(int(valid.sum()), 1))

    # Compress the entire cube once; we'll only draw arrows on the
    # bright OOG subset (the population the knee was sized for).
    if spec.mode != "off":
        xy_out = compress_xy(xy, ref_xy_arr, spec)
    else:
        xy_out = xy.copy()

    fig, ax = plt.subplots(figsize=(9, 9), facecolor=bg, layout="constrained")
    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.tick_params(colors=fg)
    ax.grid(True, alpha=0.12, color=accent)

    # Spectral locus.
    ax.plot(locus[:, 0], locus[:, 1], color=fg, lw=1.3, alpha=0.95,
            label="spectral locus")

    # Input gamut triangle (native primaries, native white).
    try:
        from spektrafilm_lut_creator.color_spaces import get as _get_cs
        in_entry = _get_cs(ctx.spec.input_color_space)
        in_cs_obj = colour.RGB_COLOURSPACES[in_entry.primaries]
        pri = np.asarray(in_cs_obj.primaries, dtype=float)
        tri = np.vstack([pri, pri[:1]])
        ax.plot(tri[:, 0], tri[:, 1], color=accent, lw=1.4, alpha=0.7,
                label=f"{ctx.spec.input_color_space} gamut")
        ax.fill(tri[:, 0], tri[:, 1], color=accent, alpha=0.04)
    except Exception:
        pass

    # Reference illuminant marker.
    ax.plot(ref_xy_arr[0], ref_xy_arr[1], "D", color=dim, markersize=8,
            markeredgecolor=fg, markeredgewidth=0.8,
            label=f"film ref illum ({ref_illuminant})")

    # Background: in-locus samples (faint), then OOG originals (red),
    # then compressed positions (cyan), then arrows on top.
    in_locus_valid = in_locus & valid
    if in_locus_valid.any():
        ax.scatter(xy[in_locus_valid, 0], xy[in_locus_valid, 1],
                   c=ok_color, s=2, alpha=0.25, edgecolors="none",
                   zorder=2)
    if oog_mask.any():
        ax.scatter(xy[oog_mask, 0], xy[oog_mask, 1], c=oog_color,
                   s=4, alpha=0.45, edgecolors="none", zorder=3,
                   label="OOG (original)")
    if oog_bright_mask.any() and spec.mode != "off":
        ax.scatter(xy_out[oog_bright_mask, 0], xy_out[oog_bright_mask, 1],
                   c=moved_color, s=5, alpha=0.85, edgecolors="none",
                   zorder=4, label="compressed")
        # Displacement arrows on bright OOG only, capped at 400 for
        # legibility on dense V-Gamut-like inputs.
        bright_idx = np.flatnonzero(oog_bright_mask)
        n_arrows = min(len(bright_idx), 400)
        rng = np.random.default_rng(0)
        pick = rng.choice(bright_idx, size=n_arrows, replace=False)
        x0 = xy[pick, 0]; y0 = xy[pick, 1]
        x1 = xy_out[pick, 0]; y1 = xy_out[pick, 1]
        ax.quiver(
            x0, y0, x1 - x0, y1 - y0,
            color=arrow_color, alpha=0.55,
            angles="xy", scale_units="xy", scale=1.0,
            width=0.0025, headwidth=4, headlength=5, zorder=3.5,
        )

    # Stats panel in the upper left, monospace so the columns line up.
    if oog_bright_mask.any() and spec.mode != "off":
        disp = np.linalg.norm(
            xy_out[oog_bright_mask] - xy[oog_bright_mask], axis=-1,
        )
        text = (
            f"algorithm:    {spec.algorithm}\n"
            f"mode:         {spec.mode}\n"
            f"threshold:    {spec.knee[0]}\n"
            f"limit:        {spec.knee[1]}\n"
            f"power:        {spec.knee[2]}\n"
            f"\n"
            f"input:        {ctx.spec.input_color_space}\n"
            f"OOG fraction: {oog_fraction:.1%}\n"
            f"OOG (bright): {int(oog_bright_mask.sum())}\n"
            f"max disp:     {disp.max():.4f}\n"
            f"p99 disp:     {np.percentile(disp, 99):.4f}\n"
            f"mean disp:    {disp.mean():.4f}"
        )
    elif spec.mode == "off":
        text = (
            f"algorithm:    {spec.algorithm}\n"
            f"mode:         off\n"
            f"\n"
            f"input:        {ctx.spec.input_color_space}\n"
            f"OOG fraction: {oog_fraction:.1%}\n"
            f"(compression disabled — OOG samples passed through unchanged)"
        )
    else:
        text = (
            f"algorithm:    {spec.algorithm}\n"
            f"threshold:    {spec.knee[0]}\n"
            f"limit:        {spec.knee[1]}\n"
            f"power:        {spec.knee[2]}\n"
            f"\n(no bright OOG samples — nothing to compress)"
        )
    ax.text(
        0.02, 0.98, text,
        transform=ax.transAxes, va="top", ha="left",
        color=fg, family="monospace", fontsize=9,
        bbox=dict(facecolor="#1a1a1a", edgecolor="#555555",
                  alpha=0.92, boxstyle="round,pad=0.5"),
    )

    ax.set_xlim(-0.05, 0.85)
    ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=fg)
    ax.set_ylabel("y", color=fg)
    ax.set_aspect("equal")
    ax.set_title(
        f"compression preview — {ctx.spec.input_color_space} via "
        f"{spec.algorithm} (t={spec.knee[0]}, l={spec.knee[1]}, "
        f"p={spec.knee[2]})",
        color=viz.HI, fontsize=viz.SUPTITLE_FS, pad=viz.SUPTITLE_PAD,
    )
    ax.legend(facecolor="#1a1a1a", labelcolor=fg, framealpha=0.9,
              loc="upper right", fontsize=8)

    path = _save(ctx, fig, "input_gamut_compression_preview")

    return Result(
        name="input_gamut_compression_preview",
        summary={
            "mode": spec.mode,
            "algorithm": spec.algorithm,
            "knee_threshold": float(spec.knee[0]),
            "knee_limit": float(spec.knee[1]),
            "knee_power": float(spec.knee[2]),
            "oog_fraction": oog_fraction,
            "n_oog_samples": int(oog_mask.sum()),
            "n_oog_bright": int(oog_bright_mask.sum()),
            "reference_illuminant": ref_illuminant,
        },
        figure_path=path,
        units="",
        interpretation=(
            "Shows which cube samples fall outside the visible spectral "
            "locus (where Hanatos 2025 spectral upsampling is well "
            "defined) and where the compression maps them. Red = input "
            "OOG, cyan = compressed destination, orange arrows = "
            "displacement (bright OOG subset only, capped at 400 for "
            "legibility). Samples in the locus pass through unchanged. "
            "The compression is baked into the per-film tc_lut at build "
            "time (n100 §3.1); this plot is the build's audit trail. "
            "Informational only — no pass/fail."
        ),
        passed=None,
    )


def input_gamut_compression_smoothness(ctx: "QAContext") -> Result:
    """Probe the compression's smoothness on a circumferential ring.

    A circle around the film reference illuminant that crosses the
    spectral locus in several places. After compression the output
    should be a smooth closed curve, color-coded uniformly with input
    angle (HSV hue → input azimuth). Visible kinks, bunching, or color
    jumps reveal hue smoothness issues.

    Styling mirrors spektrafilm-research/studies/a40_lut_system/
    tune_input_gamut_compression.py ``plot_smoothness_circumferential``
    so the QA artifact reads identically to the study figure.

    References
    ----------
    - spektrafilm-research n100 §5.1 (smoothness probes).
    - ``tune_input_gamut_compression.py`` ``plot_smoothness_circumferential``.
    """
    from spektrafilm.utils.gamut_compression import (
        compress_xy, spectral_locus_xy,
    )

    # ``accent`` is the yellow-ish color used for the input-gamut
    # triangle overlay (visible against the dark BG); titles use the
    # shared viz.HI white so they match the rest of the report.
    bg, fg, accent, dim = "#0a0a0a", "#cccccc", "#ffee66", "#888888"

    spec = ctx.spec.input_gamut_compress
    ref_illuminant = _film_reference_illuminant(ctx)
    ref_xy_arr = np.asarray(
        colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"][
            ref_illuminant
        ], dtype=float,
    )

    # Radius matches the tuning script default (0.30 puts about half the
    # circle in OOG territory for D55-centred rings — comfortable for
    # showing the knee in action without sweeping into unphysical xy).
    radius = 0.30
    n_samples = 720
    angles = np.linspace(0.0, 2.0 * np.pi, n_samples, endpoint=False)
    direction = np.stack([np.cos(angles), np.sin(angles)], axis=-1)
    probe_input = ref_xy_arr[None, :] + direction * radius
    angles_deg = np.degrees(angles)

    probe_output = compress_xy(probe_input, ref_xy_arr, spec)
    locus = spectral_locus_xy()

    # Try to draw the input gamut triangle in the background — useful
    # context for "which directions cross the gamut edge first".
    pri = None
    try:
        from spektrafilm_lut_creator.color_spaces import get as _get_cs
        in_entry = _get_cs(ctx.spec.input_color_space)
        in_cs_obj = colour.RGB_COLOURSPACES[in_entry.primaries]
        pri = np.asarray(in_cs_obj.primaries, dtype=float)
    except Exception:
        pass

    # Smoothness metric: ratio of worst inter-sample step to median.
    # Close to 1 = perfectly even hue spacing; >>1 = a discontinuity.
    diffs = np.diff(probe_output, axis=0)
    step_lengths = np.linalg.norm(diffs, axis=-1)
    worst_step = float(step_lengths.max())
    median_step = float(np.median(step_lengths))
    ratio = worst_step / max(median_step, 1e-9)

    fig, ax = plt.subplots(figsize=(7, 7), facecolor=bg, layout="constrained")
    ax.set_facecolor(bg)
    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.tick_params(colors=fg)
    ax.grid(True, alpha=0.12, color=accent)

    # Spectral locus.
    ax.plot(locus[:, 0], locus[:, 1], color=fg, lw=1.0, alpha=0.85,
            label="spectral locus")

    # Input gamut triangle.
    if pri is not None:
        tri = np.vstack([pri, pri[:1]])
        ax.plot(tri[:, 0], tri[:, 1], color=accent, lw=1.0, alpha=0.5,
                label=f"{ctx.spec.input_color_space} gamut")

    # Input circle as a dashed reference.
    ax.plot(probe_input[:, 0], probe_input[:, 1], color=dim, lw=0.6,
            ls="--", alpha=0.5)

    # Compressed output colored by input angle — the visual signature of
    # smoothness is a clean rainbow ring with no color discontinuities.
    ax.scatter(probe_output[:, 0], probe_output[:, 1],
               c=angles_deg, cmap=plt.cm.hsv, s=6, alpha=0.95,
               edgecolors="none")

    # Reference illuminant.
    ax.plot(ref_xy_arr[0], ref_xy_arr[1], "D", color=dim, markersize=7,
            markeredgecolor=fg, markeredgewidth=0.7,
            label=f"film ref ({ref_illuminant})")

    ax.set_xlim(-0.05, 0.85)
    ax.set_ylim(-0.05, 0.95)
    ax.set_xlabel("x", color=fg)
    ax.set_ylabel("y", color=fg)
    ax.set_aspect("equal")
    ax.set_title(
        f"circumferential smoothness probe — "
        f"{ctx.spec.input_color_space} via {spec.algorithm} "
        f"(t={spec.knee[0]}, l={spec.knee[1]}, p={spec.knee[2]})\n"
        f"r = {radius} from {ref_illuminant}    "
        f"worst/median step {ratio:.2f}",
        color=viz.HI, fontsize=viz.SUPTITLE_FS, pad=viz.SUPTITLE_PAD,
    )
    leg = ax.legend(loc="upper right", fontsize=8,
                    facecolor="#1a1a1a", edgecolor="#555555",
                    labelcolor=fg)
    leg.get_frame().set_alpha(0.9)

    path = _save(ctx, fig, "input_gamut_compression_smoothness")

    return Result(
        name="input_gamut_compression_smoothness",
        summary={
            "mode": spec.mode,
            "algorithm": spec.algorithm,
            "knee_threshold": float(spec.knee[0]),
            "knee_limit": float(spec.knee[1]),
            "knee_power": float(spec.knee[2]),
            "probe_radius": float(radius),
            "probe_samples": int(n_samples),
            "worst_step": worst_step,
            "median_step": median_step,
            "worst_over_median_step": ratio,
            "reference_illuminant": ref_illuminant,
        },
        figure_path=path,
        units="",
        interpretation=(
            "A ring of input chromaticities around the film reference "
            "illuminant runs through the compression and emerges as a "
            "rainbow ring of output points. A smooth, evenly-spaced "
            "ring means the compression is hue-uniform; bunching or "
            "color jumps reveal hue discontinuities that would translate "
            "into banding in the baked LUT. `worst_over_median_step` "
            "near 1 is ideal; >>1 indicates a kink. Informational only — "
            "no pass/fail."
        ),
        passed=None,
    )


# ---------------------------------------------------------------------------
# The ordered default test list.
# ---------------------------------------------------------------------------

def _run_unbounded_pipeline_for_rim(
    ctx: "QAContext", samples_encoded: np.ndarray,
) -> np.ndarray:
    """Run a one-off pipeline with output gamut compression *off* to
    capture the simulation's unbounded reach in output-primaries linear
    RGB.

    The shipped LUT bake has compression baked in (via scanning.py);
    that's the "after" state. To visualize the "before" we need to
    re-run the same pipeline once with compression disabled. Per-call
    cost is small (cube-rim sample count, hundreds of samples).
    """
    from spektrafilm.runtime.params_builder import digest_params, init_params
    from spektrafilm.runtime.pipeline import SimulationPipeline
    from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec
    from spektrafilm_lut_creator.color_spaces import (
        decode_cctf, get as get_color_space,
    )

    spec = ctx.spec
    in_entry = get_color_space(spec.input_color_space)
    out_entry = get_color_space(spec.output_color_space)
    paper = (
        ctx.bundle.meta.stocks.prints[ctx.paper_index]
        if ctx.bundle.meta.stocks else spec.print_profiles[ctx.paper_index]
    )

    params = init_params(film_profile=spec.film_profile, print_profile=paper)
    params.debug.lut_mode = True
    params.io.input_primaries = in_entry.primaries
    params.io.output_primaries = out_entry.primaries
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = False
    # Disable both the soft-plus and the final [0,1] clip so we can
    # actually see the simulation's unbounded reach. The shipping bake
    # always clips; this is QA-only.
    params.io.gamut_clip = "off"
    params.io.input_gamut_compress = spec.input_gamut_compress
    params.io.output_gamut_compress = OutputGamutCompressSpec(mode="off")
    params = digest_params(params)
    pipeline = SimulationPipeline(params)

    samples_linear = decode_cctf(samples_encoded, spec.input_color_space)
    image_in = samples_linear.reshape(1, -1, 3).astype(np.float32)
    image_out = np.asarray(pipeline.process(image_in), dtype=float)
    return image_out.reshape(-1, 3)


# ---------------------------------------------------------------------------
# Gamut edge stress + R-G plane slices — picture-style diagnostics.
# ---------------------------------------------------------------------------

def _build_gamut_edge_stress_panel(
    target_cs: str,
    in_cs: str,
    out_cs: str,
    pipeline,
    *,
    width: int = 768,
    height: int = 256,
) -> tuple[np.ndarray, dict]:
    """Build one Granger-style RGB stress panel.

    Each column is a continuous tent gradient built in the **target
    space's CCTF-encoded RGB** (Mononodes LUT-Inspector convention —
    ramps are perceptually uniform in encoded RGB, not linear):

    - top row:    white ``(1, 1, 1)``
    - mid row:    a saturated point on the RGB-cube edge in encoded
                  RGB (R → Y → G → C → B → M → R across columns)
    - bottom row: black ``(0, 0, 0)``

    Within a column the encoded value is linearly interpolated:
    ``pixel_enc = w_white·(1,1,1) + w_sat·C(hue) + w_black·(0,0,0)``,
    with tent weights ``w_white = max(0, 1-2v)``,
    ``w_sat = 1 - |2v-1|``, ``w_black = max(0, 2v-1)`` for
    ``v ∈ [0, 1]`` top→bottom.

    The encoded image is CCTF-decoded to target linear, CAT-adapted
    into the bundle's input primaries (no clipping — saturated rim
    pixels keep their negative components), and pushed through the
    actual runtime pipeline. This is what a real workflow does: the
    runtime's input gamut compression handles chromaticities inside
    the visible locus directly via spectral upsampling, so there's no
    need to force the input through the LUT's [0, 1]³ cube boundary
    via hard clipping. The LUT is *not* used for this test — running
    the runtime is the honest answer for stress-test inputs whose
    chromaticities sit outside the bundle's declared input primaries.

    Output goes through the runtime's output gamut compression (toward
    the bundle's output primaries, baked into the pipeline). The
    result is then CAT'd to sRGB linear and hard-clipped to ``[0, 1]``
    for display — the runtime's output gamut compression is expected
    to have already pulled values inside the cube, so the clip should
    be near-identity in well-behaved bundles. Any visible clip cliff
    here is a bake-time disclosure that the bundle's compression
    didn't fully contain the simulation's reach for this target.

    The ``oog_fraction_*`` stats report how many pixels of the
    target-space gradient lie outside the bundle's input-primaries
    cube — a diagnostic of "how much of this source the bundle can't
    natively represent in its declared input gamut," kept even though
    the pipeline handles those pixels without clipping.
    """
    from spektrafilm_lut_creator.color_spaces import (
        decode_cctf, get as get_cs,
    )

    W, H = width, height

    # Saturated-edge color per column. 6 segments around the RGB cube:
    # R → Y → G → C → B → M → R.
    t = np.linspace(0.0, 6.0, W, endpoint=False)
    seg = np.floor(t).astype(int) % 6
    f = (t - np.floor(t)).astype(float)
    sat = np.zeros((W, 3), dtype=float)
    builders = (
        lambda f: np.stack([np.ones_like(f),  f,                  np.zeros_like(f)], axis=-1),
        lambda f: np.stack([1.0 - f,          np.ones_like(f),    np.zeros_like(f)], axis=-1),
        lambda f: np.stack([np.zeros_like(f), np.ones_like(f),    f                ], axis=-1),
        lambda f: np.stack([np.zeros_like(f), 1.0 - f,            np.ones_like(f) ], axis=-1),
        lambda f: np.stack([f,                np.zeros_like(f),   np.ones_like(f) ], axis=-1),
        lambda f: np.stack([np.ones_like(f),  np.zeros_like(f),   1.0 - f         ], axis=-1),
    )
    for s, build in enumerate(builders):
        m = (seg == s)
        if m.any():
            sat[m] = build(f[m])

    # Tent weights down the column: white at v=0, saturated at v=0.5,
    # black at v=1. Applied to the target space's CCTF-encoded RGB so
    # the ramp is perceptually uniform — the LUT-Inspector convention.
    v = np.linspace(0.0, 1.0, H)
    w_white = np.maximum(0.0, 1.0 - 2.0 * v).reshape(H, 1, 1)
    w_sat   = (1.0 - np.abs(2.0 * v - 1.0)).reshape(H, 1, 1)
    # w_black contributes zero so omitted.
    image_target_encoded = w_white + w_sat * sat[None, :, :]

    target_entry = get_cs(target_cs)
    in_entry = get_cs(in_cs)
    out_entry = get_cs(out_cs)

    # CCTF-decode to target linear, CAT to bundle-input linear. No
    # clipping at this boundary — the pipeline will handle any negative
    # components via input gamut compression toward the spectral locus.
    image_linear = decode_cctf(image_target_encoded, target_cs)
    input_linear = np.asarray(
        colour.RGB_to_RGB(
            image_linear,
            target_entry.primaries,
            in_entry.primaries,
            chromatic_adaptation_transform="CAT02",
        ), dtype=float,
    )

    # OOG-to-input diagnostic: how much of the target gradient sits
    # outside the bundle's declared input primaries cube. Computed
    # purely for the stat; the pipeline doesn't need it.
    oog_mask = np.any(
        (input_linear < 0.0) | (input_linear > 1.0), axis=-1,
    )

    # Run the gradient through the actual runtime pipeline. Pipeline
    # expects (H, W, 3); lut_mode disables every spatial effect so the
    # layout is purely a performance knob. Output is linear RGB in the
    # bundle's output primaries.
    image_in = input_linear.reshape(1, H * W, 3).astype(np.float32)
    image_out_linear = np.asarray(
        pipeline.process(image_in), dtype=float,
    ).reshape(H, W, 3)

    # Display conversion: CAT from bundle output primaries to sRGB
    # linear, then a hard clip to [0, 1] before sRGB-encoding. This
    # step used to be an OkLch chroma reduction toward sRGB, but OkLab's
    # well-known blue hue rotation produced a visible cyan↔magenta seam
    # at the deep-blue corner — visible in the saturated row of the
    # strip. A hard clip keeps the test "honest about" what the bundle
    # actually delivers: any value the runtime's output gamut
    # compression didn't already pull inside [0, 1]³ now clips at the
    # cube boundary, exactly as a downstream consumer would see it.
    srgb_linear = np.asarray(
        colour.RGB_to_RGB(
            image_out_linear,
            out_entry.primaries,
            "sRGB",
            chromatic_adaptation_transform="CAT02",
        ), dtype=float,
    )
    srgb_encoded = np.asarray(
        colour.cctf_encoding(np.clip(srgb_linear, 0.0, 1.0), function="sRGB"),
        dtype=float,
    )
    srgb_encoded = np.clip(srgb_encoded, 0.0, 1.0)

    mid_band = slice(max(0, H // 2 - H // 16), H // 2 + H // 16)
    stats = {
        "oog_fraction_total": float(oog_mask.mean()),
        "oog_fraction_saturated_row": float(oog_mask[mid_band].mean()),
    }
    return srgb_encoded, stats


def output_gamut_edge_stress(ctx: "QAContext") -> Result:
    """Granger-style RGB stress chart at the edges of three target
    color spaces, rendered through the actual runtime pipeline.

    For each target space (Rec.709, DCI-P3, Rec.2020) we build a
    vertical linear-RGB gradient — white at the top, the saturated
    edge of the target's RGB cube in the middle (hue cycle across
    columns), black at the bottom — CAT-adapt it into the bundle's
    input primaries (no clipping), and process it through the runtime
    pipeline rather than the baked LUT. The runtime handles
    chromaticities outside the bundle's declared input cube directly:
    spectral upsampling works anywhere inside the visible locus, and
    the bundle's input gamut compression (toward the locus) handles
    anything beyond. Output goes through the bundle's output gamut
    compression and is rendered to sRGB for display via OkLch chroma
    reduction toward the sRGB primaries.

    Why the runtime and not the LUT: the LUT is sampled in
    ``[0, 1]^3`` of the bundle's input encoded cube; saturated rim
    pixels in a wider target space (P3, Rec.2020) lie outside that
    cube and the LUT physically can't evaluate them without first
    clipping them in — which is exactly the artifact the test is
    supposed to surface. Running the runtime is the honest answer
    for "what would the bundle produce if applied to this source."

    Visible bands, kinks, hue jumps, or posterization in the rendered
    gradient signal model-side pathology at saturated input — a
    regime the rest of the suite probes only statistically.

    References
    ----------
    - Mononodes LUT Inspector — Granger-style RGB stress chart,
      https://mononodes.com/lut-inspector/.
    - Mononodes Cube Slice DCTL — RGB cube face gradients.
    """
    from spektrafilm.runtime.params_builder import digest_params, init_params
    from spektrafilm.runtime.pipeline import SimulationPipeline
    from spektrafilm_lut_creator.color_spaces import get as get_color_space

    spec = ctx.spec
    in_cs = spec.input_color_space
    out_cs = spec.output_color_space
    in_entry = get_color_space(in_cs)
    out_entry = get_color_space(out_cs)
    paper = (
        ctx.bundle.meta.stocks.prints[ctx.paper_index]
        if ctx.bundle.meta.stocks else spec.print_profiles[ctx.paper_index]
    )

    # Build the runtime pipeline once and share it across the three
    # target gradients. lut_mode disables spatial effects; the
    # gamut_clip / input_gamut_compress / output_gamut_compress
    # settings mirror the bundle's bake-time configuration so the
    # stress test renders what the bundle would actually produce.
    params = init_params(film_profile=spec.film_profile, print_profile=paper)
    params.debug.lut_mode = True
    params.io.input_primaries = in_entry.primaries
    params.io.output_primaries = out_entry.primaries
    params.io.input_cctf_decoding = False
    params.io.output_cctf_encoding = False
    params.io.gamut_clip = spec.gamut_clip
    params.io.input_gamut_compress = spec.input_gamut_compress
    params.io.output_gamut_compress = spec.output_gamut_compress
    params = digest_params(params)
    pipeline = SimulationPipeline(params)

    target_spaces = ["Rec.709", "DCI-P3", "Rec.2020"]
    panels: list[tuple[str, np.ndarray, dict]] = []
    summary: dict[str, float] = {}
    for cs in target_spaces:
        img, stats = _build_gamut_edge_stress_panel(cs, in_cs, out_cs, pipeline)
        panels.append((cs, img, stats))
        summary[f"{cs}_oog_fraction_saturated_row"] = stats["oog_fraction_saturated_row"]

    fig = viz.gamut_edge_stress(panels, in_cs=in_cs, out_cs=out_cs)
    path = _save(ctx, fig, "output_gamut_edge_stress")

    return Result(
        name="output_gamut_edge_stress",
        summary=summary,
        figure_path=path,
        units="",
        interpretation=(
            "Each panel is a Granger-style RGB stress chart at the "
            "edges of one target RGB space: each column is a tent "
            "white → saturated_edge(hue) → black in target-cs encoded "
            "RGB. The image is CAT-adapted into the bundle's input "
            "primaries (no clipping) and pushed through the runtime "
            "pipeline, which handles chromaticities outside the "
            "bundle's input cube via spectral upsampling + input "
            "gamut compression toward the visible locus. Output is "
            "rendered to sRGB for viewing via CAT + a hard clip to "
            "[0, 1] (the runtime's own output gamut compression is "
            "expected to have already done the cube containment). "
            "The gradient should be continuous and smooth from top to "
            "bottom; visible bands, hue jumps, or posterization "
            "reveal model-side pathology at saturated input. "
            "`oog_fraction_*` reports how many pixels lie outside the "
            "bundle's input primaries cube — a diagnostic of how much "
            "of each target's saturated rim the bundle has to handle "
            "as out-of-input-gamut input (the pipeline still renders "
            "them, but they're physically outside the bundle's "
            "declared input gamut)."
        ),
        passed=None,
    )


def rg_plane_slices(ctx: "QAContext") -> Result:
    """R-G cube slices at evenly-spaced B-input values, displayed in sRGB.

    Each panel shows the LUT's R-G response at one B input level. The
    slice is in the bundle's output color space; we decode to linear,
    chromatically adapt to sRGB, sRGB-encode, and hard-clip — so the
    rendered colors are visually accurate on an sRGB display
    regardless of the bundle's output space.
    """
    fig = viz.rg_plane_slices(
        ctx.lut.table, ctx.lut.resolution, ctx.spec.output_color_space,
    )
    path = _save(ctx, fig, "rg_plane_slices")

    return Result(
        name="rg_plane_slices",
        summary={
            "n_slices": int(min(9, ctx.lut.resolution)),
            "cube_resolution": int(ctx.lut.resolution),
        },
        figure_path=path,
        units="",
        interpretation=(
            "Cube cross-sections at constant input B, displayed in "
            "sRGB (hard-clipped). Smooth color gradation across the "
            "panels indicates a well-behaved cube along B; abrupt "
            "changes between adjacent slices point at low-resolution "
            "or noisy regions. Within each panel the gradient runs R "
            "left→right, G bottom→top — corner colors are the LUT's "
            "renderings of input (R, G, B) corners at that B."
        ),
        passed=None,
    )


DEFAULT_TESTS = (
    off_grid_identity,
    monotonicity,
    jacobian_condition,
    total_variation,
    output_gamut_compression,
    characteristic_curve,
    dynamic_range_usage,
    planckian_sweep,
    hue_twist_oklab,
    spectral_locus_envelope,
    input_gamut_compression_preview,
    input_gamut_compression_smoothness,
    output_gamut_edge_stress,
    rg_plane_slices,
)
