import importlib.util
from pathlib import Path
import sys

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "profile-velvia-microcal-validation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "profile_velvia_microcal_validation_test",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATION
SPEC.loader.exec_module(VALIDATION)


def _gate_inputs(*, improves: bool, sign_test_p_value: float):
    direction = 2.0 if improves else -2.0
    win_count = 13 if improves else 5
    comparison = {
        "micro_improvement_percent": {
            "density_rmse_D": direction,
            "transmittance_rmse_percentage_points": direction,
        },
        "curve_win_count_of_18": {
            "density_rmse_D": win_count,
            "transmittance_rmse_percentage_points": win_count,
        },
        "one_sided_sign_test_p_value": {
            "density_rmse_D": sign_test_p_value,
            "transmittance_rmse_percentage_points": sign_test_p_value,
        },
    }
    variants = {
        "variant_count": 243,
        "both_micro_metrics_improve_count": 243 if improves else 0,
    }
    return (
        {
            name: comparison
            for name in VALIDATION.REFERENCE_POLICY_ORDER
        },
        {
            name: variants
            for name in VALIDATION.REFERENCE_POLICY_ORDER
        },
    )


def test_chromatic_colour_discovery_requires_exact_18_solid_colours():
    image = np.full((500, 1000, 3), 255, dtype=np.uint8)
    colours = []
    for index in range(18):
        colour = (
            20 + index * 5,
            220 - index * 4,
            10,
        )
        colours.append(colour)
        row = 30 + (index // 6) * 30
        column = 180 + (index % 6) * 100
        image[row : row + 15, column : column + 15] = colour

    discovered = VALIDATION._discover_chromatic_colours(image)

    assert len(discovered) == 18
    assert set(discovered) == set(colours)


def test_visible_curve_sampling_leaves_hidden_points_missing():
    mask = np.zeros((500, 1000), dtype=bool)
    axis = {
        "x_left_px": 180.0,
        "x_right_px": 963.0,
        "y_top_px": 33.5,
        "y_bottom_px": 467.0,
        "x_window_px": 0,
    }
    for wavelength, row in ((400.0, 300), (410.0, 280)):
        column = int(
            round(
                axis["x_left_px"]
                + (wavelength - 400.0)
                * (axis["x_right_px"] - axis["x_left_px"])
                / 300.0
            )
        )
        mask[row, column] = True

    transmittance, _ = VALIDATION._sample_visible_curve(
        mask,
        axis,
        y_min_px=30,
        y_max_px=470,
    )

    assert np.isfinite(transmittance[0])
    assert np.isnan(transmittance[1])
    assert np.isfinite(transmittance[2])


def test_external_gate_fails_when_independent_variants_do_not_improve():
    comparisons, variants = _gate_inputs(
        improves=False,
        sign_test_p_value=1.0,
    )

    gate = VALIDATION._external_gate(comparisons, variants)

    assert gate["passes"] is False
    assert gate["default_replacement_authorized"] is False
    assert not any(gate["checks"].values())


def test_external_gate_pass_does_not_authorize_default_replacement():
    comparisons, variants = _gate_inputs(
        improves=True,
        sign_test_p_value=0.04,
    )

    gate = VALIDATION._external_gate(comparisons, variants)

    assert gate["passes"] is True
    assert gate["default_replacement_authorized"] is False


def test_external_gate_requires_sign_test_threshold():
    comparisons, variants = _gate_inputs(
        improves=True,
        sign_test_p_value=0.051,
    )

    gate = VALIDATION._external_gate(comparisons, variants)

    assert gate["passes"] is False
    assert any(
        key.endswith("sign_test_p_at_most_0_05") and not passed
        for key, passed in gate["checks"].items()
    )


def test_negative_relative_density_exclusion_is_counted_and_applied():
    patch = np.full(VALIDATION.WAVELENGTHS_NM.shape, 0.8, dtype=float)
    neutral = np.full_like(patch, 0.9)
    patch[:3] = 0.95
    basis = np.column_stack(
        (
            np.ones_like(patch),
            np.linspace(0.0, 1.0, patch.size),
            np.linspace(0.0, 1.0, patch.size) ** 2,
        )
    )

    retained = VALIDATION._fit_curve(
        patch,
        np.zeros_like(patch),
        basis,
        neutral_transmittance=neutral,
    )
    excluded = VALIDATION._fit_curve(
        patch,
        np.zeros_like(patch),
        basis,
        neutral_transmittance=neutral,
        exclude_negative_relative_density=True,
    )

    assert retained["negative_relative_density_point_count"] == 3
    assert retained["excluded_negative_relative_density_point_count"] == 0
    assert excluded["excluded_negative_relative_density_point_count"] == 3
    assert excluded["visible_point_count"] == retained["visible_point_count"] - 3


def test_reference_policies_keep_generated_envelope_nonphysical():
    chromatic = np.full((18, VALIDATION.WAVELENGTHS_NM.size), 0.5)
    chromatic[0, 10] = 0.95
    neutral = np.full(VALIDATION.WAVELENGTHS_NM.shape, 0.9)
    policies = VALIDATION._reference_policies(
        {
            "chromatic_transmittance": chromatic,
            "neutral_white_transmittance": neutral,
        }
    )

    assert tuple(policies) == VALIDATION.REFERENCE_POLICY_ORDER
    envelope = policies["maximum_transmittance_envelope"]
    assert envelope["reference_transmittance"][10] == 0.95
    assert envelope["reference_transmittance"][9] == 0.9
    assert envelope["physical_base_claimed"] is False
    assert all(not policy["physical_base_claimed"] for policy in policies.values())


def test_microcal_source_hashes_are_pinned():
    assert set(VALIDATION.SOURCE_SPECS) == {
        "brochure",
        "chromatic_graph",
        "neutral_graph",
    }
    for source in VALIDATION.SOURCE_SPECS.values():
        assert len(source["sha256"]) == 64
        int(source["sha256"], 16)
