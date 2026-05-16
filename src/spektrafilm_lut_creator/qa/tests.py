"""The eleven QA tests.

Each function takes a :class:`QAContext` and returns a :class:`Result`.
Five tests address **LUT fidelity** (does the cube preserve the
pipeline within industry tolerance), six address **model diagnostic**
(does the spektrafilm pipeline itself produce sensible output). Both
are necessary for an industry-grade QA story — see
``studies/a40_lut_system/n080``.

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
    """Save a figure under ``figures/<name>.png`` and close it."""
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
            "Failure (max > 2.0) means users will see interpolation "
            "artifacts the on-grid test cannot detect; remedies are "
            "higher LUT resolution or wire-shaping changes. ΔITP is "
            "reported as a secondary, HDR-aware companion metric."
        ),
        references=(
            "CIE 142:2001 (CIEDE2000) — the workhorse perceptual metric",
            "ITU-R BT.2124 — HDR-aware perceptual color difference (ΔITP)",
            "Kirk, Tetrahedral Interpolation (FilmLight Truelight whitepapers)",
            "OCIO ociochecklut",
        ),
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
    """
    table = ctx.lut.table
    n = ctx.lut.resolution
    info = metrics.monotonicity_violations(table)

    # Build per-axis violation masks for the transfer-curve viz: True
    # where the finite-diff along the centerline crosses zero.
    mid = n // 2
    masks = (
        np.diff(table[mid, mid, :, 0]) < 0.0,    # R
        np.diff(table[mid, :, mid, 1]) < 0.0,    # G
        np.diff(table[:, mid, mid, 2]) < 0.0,    # B
    )
    fig = viz.transfer_curves(table, n, violation_marks=masks)
    path = _save(ctx, fig, "monotonicity")

    passed = (info["violations"] == 0)
    return Result(
        name="monotonicity",
        summary={
            "violations": int(info["violations"]),
            "worst_negative_diff": float(info["worst_negative_diff"]),
        },
        figure_path=path,
        units="cells",
        interpretation=(
            "Each diagonal axis-channel pair (R-in vs R-out, etc.) must be "
            "monotonic for the LUT to be invertible without fold-backs. "
            "Violations indicate either a model regime that legitimately "
            "produces a fold (DIR couplers being aggressive enough to "
            "cross zero in the diagonal) or a bake artifact at the "
            "cube boundary; investigate both before relaxing the test."
        ),
        references=(
            "OCIO v2 design notes on monotonic LUT structure",
            "FilmLight Truelight whitepapers",
        ),
        passed=passed,
    )


def jacobian_condition(ctx: "QAContext") -> Result:
    """Local 3×3 Jacobian condition number — a smoothness diagnostic.

    Gamut compression and density shoulders produce regions where the
    local linear approximation of the transform is near-singular
    (long thin parallelepipeds in output space). Healthy cube cells
    have log-cond ~ O(1); pathological cells climb above 3 (cond ~
    1000), signaling visible artifacts.
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
        references=(
            "Siragusano, 'The Beauty of Per-Pixel Math' (FilmLight, Vimeo)",
            "Hable, filmicworlds.com",
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
        references=(),
        passed=None,
    )


def gamut_self_intersection(ctx: "QAContext") -> Result:
    """Detect cube-face folds and report gamut compression ratio.

    Fold-backs of the cube surface indicate a non-orientation-preserving
    transform — a hard failure for any grading workflow. The compression
    ratio (output / input OkLab hull volume) is a separate informational
    number: < 1 expected (LUTs compress); > 1 means expansion (suspect).
    """
    table = ctx.lut.table
    flips = metrics.gamut_self_intersection_score(table)
    hull = metrics.gamut_hull_volume_ratio(
        ctx.grid_input, ctx.grid_output, ctx.spec.output_color_space,
    )

    summary = {
        "fold_triangles": int(flips["flips"]),
        "fold_fraction": float(flips["fraction"]),
        "input_hull_volume": float(hull["input_hull_volume"]),
        "output_hull_volume": float(hull["output_hull_volume"]),
        "compression_ratio": float(hull["compression_ratio"]),
    }
    # Hard failure when face folds appear. Compression ratio > 1.05 is
    # suspicious (rare expansion); < 0.05 is suspicious (extreme
    # collapse).
    passed = (flips["flips"] == 0
              and 0.05 <= hull["compression_ratio"] <= 1.05)

    fig = viz.oklab_gamut_compare(
        ctx.grid_input, ctx.grid_output,
        ctx.spec.input_color_space, ctx.spec.output_color_space,
    )
    path = _save(ctx, fig, "gamut_self_intersection")

    return Result(
        name="gamut_self_intersection",
        summary=summary,
        figure_path=path,
        units="",
        interpretation=(
            "Face folds mean the cube surface maps onto itself — a "
            "non-invertible region that breaks grading. The compression "
            "ratio quantifies how much perceptual volume the LUT throws "
            "away; numbers in [0.05, 1.05] are normal, outside means "
            "either degenerate output (very small ratio) or unexpected "
            "expansion (ratio > 1)."
        ),
        references=(
            "ACES Reference Gamut Compression test imagery",
            "Morovic, gamut mapping CIC papers",
        ),
        passed=passed,
    )


# ---------------------------------------------------------------------------
# Model diagnostic.
# ---------------------------------------------------------------------------

def characteristic_curve(ctx: "QAContext") -> Result:
    """Pipeline response to a neutral input ramp, in the density domain.

    This is the system characteristic curve: D-out vs input code. A
    healthy spektrafilm bundle produces curves that smoothly traverse
    toe / linear / shoulder, with the three CMY densities tracking
    each other for a neutral input. Per-channel divergence at the
    extremes is a model-honesty signal.

    Uses :func:`density_transfer_curves` on the LUT directly (cheaper
    than re-running the pipeline; the LUT already encodes the on-grid
    pipeline response).
    """
    table = ctx.lut.table
    n = ctx.lut.resolution
    fig = viz.density_transfer_curves(table, n)
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
        references=(
            "Hunt, 'The Reproduction of Colour' — characteristic curves",
            "any film stock datasheet (Kodak, Fuji)",
        ),
        passed=None,
    )


def planckian_sweep(ctx: "QAContext") -> Result:
    """Pipeline response to white surfaces under daylight illuminants.

    A spektrafilm bundle should send "white under D55", "white under
    D65", "white under D75", etc. to a smooth, monotonic curve in
    output chromaticity. Kinks or fold-backs reveal white-balance
    handling bugs.
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
        references=(
            "CIE 15:2018 (daylight illuminants)",
            "Poynton, Color FAQ — white-point handling",
        ),
        passed=passed,
    )


def highlight_rolloff(ctx: "QAContext") -> Result:
    """Smoothness of the LUT's per-channel transfer near the top end.

    For log/HDR-friendly input spaces, the upper half of the input
    domain covers many stops above middle gray — exactly where the
    shoulder of the density curves shapes the look. Kinks in the
    second derivative are visible artifacts.
    """
    spec = ctx.spec
    n_per_axis = 64
    pattern = patterns.highlight_ramps_per_channel(spec.input_color_space, n=n_per_axis)
    lut_out = evaluators.apply_trilinear(ctx.lut.table, pattern)
    # Split into the three per-channel ramps.
    per_axis_out = [lut_out[i * n_per_axis:(i + 1) * n_per_axis] for i in range(3)]
    in_codes = np.linspace(0.4, 1.0, n_per_axis)

    # Second-derivative max on the swept channel — kink detector.
    max_d2 = max(
        metrics.second_derivative_max(per_axis_out[c][:, c]) for c in range(3)
    )
    fig = viz.highlight_rolloff_curves(
        in_codes, per_axis_out, title="Highlight rolloff — top-half ramps",
    )
    path = _save(ctx, fig, "highlight_rolloff")

    # Empirical threshold: smooth shoulders give max |d²| < ~0.005 for
    # 64-sample ramps. Set the bar loosely at 0.02 — actual kinks lift
    # by an order of magnitude when present.
    passed = max_d2 <= 0.02

    return Result(
        name="highlight_rolloff",
        summary={"max_abs_second_derivative": max_d2},
        figure_path=path,
        units="output (per-step²)",
        interpretation=(
            "A film's shoulder should be smooth at the resolution of "
            "the LUT. Kinks indicate a model regime change (e.g., a "
            "piecewise function with a discontinuous derivative) or a "
            "bake artifact at the LUT's gamut boundary. Visible in "
            "long exponential ramps as banding or a hard knee."
        ),
        references=(
            "ARRI K1S0-057 LogC curve whitepaper",
            "ACES Output Transform threads (ACEScentral)",
        ),
        passed=passed,
    )


def black_toe(ctx: "QAContext") -> Result:
    """Behavior near zero — slope and channel divergence at code 0.

    Crushed blacks, hue shifts at base+fog, and shadow banding all
    live in the bottom 5% of the input domain. A trustworthy bundle
    has its three channels converging gracefully at zero with a clean
    finite slope.
    """
    spec = ctx.spec
    pattern = patterns.near_zero_patches(spec.input_color_space, n=48)
    lut_out = evaluators.apply_trilinear(ctx.lut.table, pattern)
    in_codes = pattern[:, 0]

    # Slope of each channel near zero.
    slopes = [metrics.slope_at_zero(in_codes, lut_out[:, c], n_first=5) for c in range(3)]
    # Channel divergence at code 0.
    divergence_at_zero = float(np.ptp(lut_out[0]))

    fig = viz.black_toe_curves(in_codes, lut_out)
    path = _save(ctx, fig, "black_toe")

    # Industry-ish: at code 0, R, G, B should land within ~0.005 of each
    # other (a neutral input stays neutral in shadows).
    passed = divergence_at_zero <= 0.005

    return Result(
        name="black_toe",
        summary={
            "slope_R": slopes[0],
            "slope_G": slopes[1],
            "slope_B": slopes[2],
            "divergence_at_zero": divergence_at_zero,
        },
        figure_path=path,
        units="output",
        interpretation=(
            "At code 0, the three channels should land at nearly the "
            "same value (a neutral input stays neutral in shadows). "
            "Divergence indicates either a chemistry-model bias at base "
            "fog, or numerical handling at the LUT's lower boundary. "
            "Flat-line output across [0, 0.10] is expected behavior "
            "for log inputs (V-Log, S-Log3, LogC, etc.) where code 0 "
            "sits well below scene black and the pipeline floors to a "
            "fixed value; the meaningful black-toe shape for those "
            "inputs lives near the encoded scene-black point higher up."
        ),
        references=(
            "SMPTE RP 2096-1 HDR test patterns",
            "Pomfort QC report patterns",
        ),
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
        references=(
            "Ottosson, OkLab, https://bottosson.github.io/posts/oklab/",
            "Yedlin, Display Prep Demo, yedlin.net",
            "Sobotka, AgX, github.com/sobotka/AgX",
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
        references=(
            "Hunt, 'The Reproduction of Colour' — characteristic curves",
            "ARRI K1S0-057 LogC whitepaper",
            "ANSI/SMPTE RP 180 (18% middle gray)",
        ),
        passed=None,
    )


def spectral_locus_envelope(ctx: "QAContext") -> Result:
    """Reach of the model's gamut at maximum saturation, overlaid on the
    spectral locus.

    For every input cube edge, we apply the LUT and project the output
    to xy chromaticity. The resulting envelope is the model's
    reachable gamut at maximum saturation. Against the spectral locus
    and the output primaries triangle, this tells us how much of the
    visible-color "rim" the model preserves (dye-spectra fidelity).
    """
    out_cs = ctx.spec.output_color_space
    _, segments = patterns.saturated_cube_edges(n=33)

    edges_out_xy: list[np.ndarray] = []
    for seg in segments:
        lut_out = evaluators.apply_trilinear(ctx.lut.table, seg)
        out_xyz = to_xyz(lut_out, out_cs)
        edges_out_xy.append(np.asarray(colour.XYZ_to_xy(out_xyz), dtype=float))

    fig = viz.spectral_locus_envelope(out_cs, edges_out_xy)
    path = _save(ctx, fig, "spectral_locus_envelope")

    # Quantify: fraction of saturated-edge points that land at the
    # gamut boundary of the output (within an epsilon of the triangle).
    # Loose proxy — a heavier rim measurement is post-v1.
    all_xy = np.concatenate(edges_out_xy, axis=0)
    on_locus_eps = 0.02
    locus_xy = patterns.spectral_locus_chromaticities()
    # Distance from each output xy to the locus polyline (vectorized).
    # Coarse: distance to nearest locus vertex.
    d = np.min(
        np.linalg.norm(all_xy[:, None, :] - locus_xy[None, :, :], axis=-1),
        axis=1,
    )
    rim_fraction = float(np.mean(d < on_locus_eps))

    return Result(
        name="spectral_locus_envelope",
        summary={
            "edge_points_total": int(all_xy.shape[0]),
            "rim_fraction": rim_fraction,
        },
        figure_path=path,
        units="",
        interpretation=(
            "Saturated input chromaticities should not all collapse "
            "to the interior of the output gamut — a healthy film "
            "simulation retains some of the high-chroma rim. Very low "
            "rim_fraction suggests dye-spectra fidelity issues or "
            "overly aggressive gamut compression."
        ),
        references=(
            "Mansencal (@KelSolaar), colour-science visualizations",
            "ACES Reference Gamut Compression",
        ),
        passed=None,
    )


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
    """
    from spektrafilm.utils.gamut_compression import (
        compress_xy, spectral_locus_xy,
    )
    from matplotlib.path import Path as MplPath

    spec = ctx.spec.input_gamut_compress
    ref_illuminant = _film_reference_illuminant(ctx)
    ref_xy_arr = np.asarray(
        colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"][
            ref_illuminant
        ], dtype=float,
    )

    xy, b = _cube_xy_in_film_frame(ctx, ref_illuminant)
    locus = spectral_locus_xy()

    bright_mask = b > 1e-2
    in_locus = MplPath(locus).contains_points(xy)
    oog_mask = (~in_locus) & bright_mask
    oog_fraction = float(oog_mask.sum() / max(int(bright_mask.sum()), 1))

    if spec.mode != "off" and oog_mask.any():
        xy_compressed = compress_xy(xy[oog_mask], ref_xy_arr, spec)
    else:
        xy_compressed = xy[oog_mask].copy() if oog_mask.any() else np.zeros((0, 2))

    fig, ax = plt.subplots(figsize=(7, 7), facecolor="#0a0a0a", layout="constrained")
    ax.set_facecolor("#0a0a0a")
    for spine in ax.spines.values():
        spine.set_color("#555555")
    ax.tick_params(colors="#cccccc")
    ax.grid(True, alpha=0.12, color="#fcb103")

    # Spectral locus
    ax.plot(locus[:, 0], locus[:, 1], color="#cccccc", lw=1.3, alpha=0.95,
            label="visible spectral locus")
    # Input gamut triangle (native primaries, native white)
    try:
        in_cs = colour.RGB_COLOURSPACES[
            __import__("spektrafilm_lut_creator.color_spaces", fromlist=["get"])
                .get(ctx.spec.input_color_space).primaries
        ]
        pri = np.asarray(in_cs.primaries, dtype=float)
        tri = np.vstack([pri, pri[:1]])
        ax.plot(tri[:, 0], tri[:, 1], color="#fcb103", lw=1.4, alpha=0.7,
                label=f"{ctx.spec.input_color_space} gamut")
    except Exception:
        pass
    # Reference illuminant
    ax.plot(ref_xy_arr[0], ref_xy_arr[1], "D", color="#cccccc",
            markersize=8, markeredgecolor="#0a0a0a", markeredgewidth=0.8,
            label=f"film ref illum ({ref_illuminant})")

    # In-locus samples (dim)
    in_l = in_locus & bright_mask
    if in_l.any():
        ax.scatter(xy[in_l, 0], xy[in_l, 1], s=2, c="#3a7a3a", alpha=0.35,
                   label="in-locus samples")
    # OOG (red) + their compressed destinations (green) + arrows
    if oog_mask.any() and spec.mode != "off":
        ax.scatter(xy[oog_mask, 0], xy[oog_mask, 1], s=8, c="#d23737",
                   alpha=0.7, label="OOG (input)")
        ax.scatter(xy_compressed[:, 0], xy_compressed[:, 1], s=8,
                   c="#3ad287", alpha=0.7, label="compressed (output)")
        for i in range(len(xy_compressed)):
            ax.annotate(
                "", xy=xy_compressed[i], xytext=xy[oog_mask][i],
                arrowprops=dict(arrowstyle="->", color="#999999",
                                alpha=0.45, lw=0.5),
            )
    elif oog_mask.any():
        ax.scatter(xy[oog_mask, 0], xy[oog_mask, 1], s=8, c="#d23737",
                   alpha=0.7, label="OOG (compression OFF)")

    title = (
        f"Input gamut compression — {ctx.spec.input_color_space} → film "
        f"({ref_illuminant})\n"
        f"algorithm: {spec.algorithm}    mode: {spec.mode}    "
        f"knee: t={spec.knee[0]} l={spec.knee[1]} p={spec.knee[2]}    "
        f"OOG: {oog_fraction:.1%}"
    )
    ax.set_title(title, color="#cccccc", fontsize=10)
    ax.set_xlabel("x", color="#cccccc")
    ax.set_ylabel("y", color="#cccccc")
    ax.set_xlim(-0.05, 0.85)
    ax.set_ylim(-0.05, 0.95)
    ax.set_aspect("equal")
    leg = ax.legend(loc="upper right", fontsize=8, facecolor="#1a1a1a",
                    edgecolor="#555555", labelcolor="#cccccc")
    leg.get_frame().set_alpha(0.85)

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
            "reference_illuminant": ref_illuminant,
        },
        figure_path=path,
        units="",
        interpretation=(
            "Shows which cube samples fall outside the visible spectral "
            "locus (where Hanatos 2025 spectral upsampling is well "
            "defined) and where the compression maps them. Red = input "
            "OOG, green = compressed destination, arrows = displacement. "
            "Samples in the locus pass through unchanged. The compression "
            "is baked into the per-film tc_lut at build time (n100 §3.1); "
            "this plot is the build's audit trail. Informational only — "
            "no pass/fail."
        ),
        references=(
            "ACES Reference Gamut Compression v1.3 (AMPAS, 2020)",
            "Hanatos et al., Sigmoidal Compression for Reflectance Manifold (2025)",
            "spektrafilm-research n100 §5",
        ),
        passed=None,
    )


def input_gamut_compression_smoothness(ctx: "QAContext") -> Result:
    """Probe the compression's smoothness on a circumferential ring.

    Sample a circle of directions around the film reference illuminant
    at a fixed xy radius and apply the compression to each. The output
    should be a smooth closed curve in xy — kinks or discontinuities
    here would translate into banding in the baked LUT. Two panels:
    (left) chromaticity diagram showing input circle + output curve;
    (right) the output x, y, and x+y as functions of angle, which is
    where any kinks become numerically visible.
    """
    from spektrafilm.utils.gamut_compression import (
        compress_xy, spectral_locus_xy,
    )

    spec = ctx.spec.input_gamut_compress
    ref_illuminant = _film_reference_illuminant(ctx)
    ref_xy_arr = np.asarray(
        colour.CCS_ILLUMINANTS["CIE 1931 2 Degree Standard Observer"][
            ref_illuminant
        ], dtype=float,
    )

    # Sample a ring of n directions at a radius that comfortably reaches
    # past the locus boundary in every direction (so the knee engages
    # everywhere). 0.45 is enough for D55-centred rings to cross the
    # locus in all directions.
    n = 720
    theta = np.linspace(0.0, 2.0 * np.pi, n, endpoint=False)
    radius = 0.45
    ring = np.stack(
        [ref_xy_arr[0] + radius * np.cos(theta),
         ref_xy_arr[1] + radius * np.sin(theta)],
        axis=-1,
    )
    compressed = compress_xy(ring, ref_xy_arr, spec)
    locus = spectral_locus_xy()

    # Smoothness metric: max absolute second difference along the ring
    # (a kink shows up as a localized spike in the second derivative).
    second_diff = np.diff(compressed, n=2, axis=0)
    max_kink = float(np.max(np.linalg.norm(second_diff, axis=-1)))

    fig, (ax_xy, ax_trace) = plt.subplots(
        1, 2, figsize=(13, 6.5), facecolor="#0a0a0a", layout="constrained",
    )
    for ax in (ax_xy, ax_trace):
        ax.set_facecolor("#0a0a0a")
        for spine in ax.spines.values():
            spine.set_color("#555555")
        ax.tick_params(colors="#cccccc")
        ax.grid(True, alpha=0.12, color="#fcb103")

    # Left: locus + input ring + compressed curve.
    ax_xy.plot(locus[:, 0], locus[:, 1], color="#cccccc", lw=1.3,
               alpha=0.9, label="spectral locus")
    ax_xy.plot(ring[:, 0], ring[:, 1], color="#d23737", lw=0.9, alpha=0.8,
               label=f"input ring (r={radius})")
    ax_xy.plot(compressed[:, 0], compressed[:, 1], color="#3ad287", lw=1.4,
               alpha=0.95, label="compressed ring")
    ax_xy.plot(ref_xy_arr[0], ref_xy_arr[1], "D", color="#cccccc",
               markersize=8, markeredgecolor="#0a0a0a",
               markeredgewidth=0.8, label=f"film ref ({ref_illuminant})")
    ax_xy.set_xlabel("x", color="#cccccc")
    ax_xy.set_ylabel("y", color="#cccccc")
    ax_xy.set_xlim(-0.05, 0.85)
    ax_xy.set_ylim(-0.05, 0.95)
    ax_xy.set_aspect("equal")
    leg = ax_xy.legend(loc="upper right", fontsize=8,
                       facecolor="#1a1a1a", edgecolor="#555555",
                       labelcolor="#cccccc")
    leg.get_frame().set_alpha(0.85)

    # Right: compressed x, y, x+y as functions of angle.
    theta_deg = np.degrees(theta)
    ax_trace.plot(theta_deg, compressed[:, 0], color="#d23737", lw=1.1,
                  label="x")
    ax_trace.plot(theta_deg, compressed[:, 1], color="#3ad287", lw=1.1,
                  label="y")
    ax_trace.plot(theta_deg, compressed.sum(axis=-1), color="#cccccc",
                  lw=1.1, ls="--", alpha=0.8, label="x + y")
    ax_trace.set_xlabel("angle around ref illuminant (deg)",
                       color="#cccccc")
    ax_trace.set_ylabel("compressed output", color="#cccccc")
    ax_trace.set_xlim(0, 360)
    leg2 = ax_trace.legend(loc="upper right", fontsize=8,
                           facecolor="#1a1a1a", edgecolor="#555555",
                           labelcolor="#cccccc")
    leg2.get_frame().set_alpha(0.85)

    title = (
        f"Compression smoothness probe — algorithm: {spec.algorithm}    "
        f"mode: {spec.mode}    knee: t={spec.knee[0]} l={spec.knee[1]} "
        f"p={spec.knee[2]}    max kink: {max_kink:.4f}"
    )
    fig.suptitle(title, color="#cccccc", fontsize=10)

    path = _save(ctx, fig, "input_gamut_compression_smoothness")

    return Result(
        name="input_gamut_compression_smoothness",
        summary={
            "mode": spec.mode,
            "algorithm": spec.algorithm,
            "knee_threshold": float(spec.knee[0]),
            "knee_limit": float(spec.knee[1]),
            "knee_power": float(spec.knee[2]),
            "probe_radius": radius,
            "probe_samples": n,
            "max_kink_second_diff": max_kink,
            "reference_illuminant": ref_illuminant,
        },
        figure_path=path,
        units="",
        interpretation=(
            "Samples a ring of input chromaticities around the film "
            "reference illuminant and runs them through the compression. "
            "A smooth output curve (right panel) means the compression "
            "introduces no kinks or discontinuities — kinks would "
            "translate into visible banding in the baked LUT. "
            "`max_kink_second_diff` quantifies the worst local curvature "
            "spike; values below ~1e-3 are smooth at LUT resolution. "
            "Informational only — no pass/fail."
        ),
        references=(
            "spektrafilm-research n100 §5.1 (smoothness probes)",
        ),
        passed=None,
    )


# ---------------------------------------------------------------------------
# The ordered default test list.
# ---------------------------------------------------------------------------

DEFAULT_TESTS = (
    off_grid_identity,
    monotonicity,
    jacobian_condition,
    total_variation,
    gamut_self_intersection,
    characteristic_curve,
    dynamic_range_usage,
    planckian_sweep,
    highlight_rolloff,
    black_toe,
    hue_twist_oklab,
    spectral_locus_envelope,
    input_gamut_compression_preview,
    input_gamut_compression_smoothness,
)
