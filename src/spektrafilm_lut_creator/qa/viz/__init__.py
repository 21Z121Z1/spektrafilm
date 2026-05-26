"""QA visualization library, grouped by topic.

Topic modules:

- :mod:`._base` — palette + plot-style primitives shared by every panel
- :mod:`.lut_fidelity` — panels for the 5 LUT-fidelity tests
- :mod:`.model_diagnostic` — panels for the 5 model-diagnostic tests
- :mod:`.picture_style` — panels for the 4 picture-style tests

The gamut-compression test panels live inline in
``qa/tests/gamut_compression.py`` (no shared viz fns) and aren't re-
exported here.

Existing ``from spektrafilm_lut_creator.qa import viz; viz.X(...)`` call
sites keep working because every public name lands in this namespace.
"""
from __future__ import annotations

from spektrafilm_lut_creator.qa.viz._base import (
    BG, FG, HI, DIM, RED, GREEN, BLUE, WARN,
    PANE_EDGE_RGBA, GRID_RGBA,
    SUPTITLE_FS, PANEL_TITLE_FS, SUPTITLE_PAD, PANEL_TITLE_PAD,
    IDENTITY_COLOR, IDENTITY_ALPHA,
    FOOTER_FS, FOOTER_COLOR, FOOTER_BAND_FRAC, HEADER_BAND_FRAC,
    _identity_line, add_footer,
    _setup_3d, _setup_2d, _fill_3d,
    _to_oklab, _gamut_triangle_xy,
)
from spektrafilm_lut_creator.qa.viz.lut_fidelity import (
    cube_sculpture, cube_deformation, cube_edges,
    transfer_curves,
    jacobian_condition_3d,
    output_histograms,
    gamut_compression_3d_xy,
    offgrid_error_scatter,
)
from spektrafilm_lut_creator.qa.viz.model_diagnostic import (
    density_transfer_curves,
    oklab_ab_slices,
    hue_twist_oklab,
    oklab_displacement,
    chromaticity_1931,
    planckian_path,
    dynamic_range_curve,
    spectral_locus_envelope,
)
from spektrafilm_lut_creator.qa.viz.picture_style import (
    oklab_gamut_slice_outline,
    rg_plane_slices,
    gamut_edge_stress,
    noise_sensitivity,
    noise_gradient,
)
