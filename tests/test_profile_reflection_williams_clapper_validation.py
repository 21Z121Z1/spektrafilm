import importlib.util
from pathlib import Path
import sys

import numpy as np


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "profile-reflection-williams-clapper-validation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "profile_reflection_williams_clapper_validation_test",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATION
SPEC.loader.exec_module(VALIDATION)


def test_williams_clapper_forward_inverse_round_trip_without_clipping():
    transform = VALIDATION.WilliamsClapper45_0(
        1.53,
        quadrature_order=128,
        table_size=2049,
    )
    transmittance = np.geomspace(1e-6, 1.0, 31)
    substrate = np.linspace(0.35, 0.95, 31)
    reflectance = transform.forward(transmittance, substrate)

    recovered, stats = transform.inverse(reflectance, substrate)

    np.testing.assert_allclose(recovered, transmittance, rtol=1e-10, atol=1e-12)
    assert stats["valid_count"] == 31
    assert stats["above_paper_white_endpoint_count"] == 0
    assert stats["clipped_count"] == 0


def test_williams_clapper_inverse_rejects_values_above_training_white():
    transform = VALIDATION.WilliamsClapper45_0(
        1.53,
        quadrature_order=128,
        table_size=2049,
    )
    substrate = np.array([0.8])
    paper_white = transform.forward(np.ones(1), substrate)

    recovered, stats = transform.inverse(paper_white + 0.01, substrate)

    assert np.isnan(recovered[0])
    assert stats["above_paper_white_endpoint_count"] == 1
    assert stats["clipped_count"] == 0


def test_reconstruction_gate_fails_on_any_inverse_out_of_domain_value():
    baseline = {metric: 2.0 for metric in VALIDATION.CORE_METRICS}
    candidate = {metric: 1.0 for metric in VALIDATION.CORE_METRICS}
    macro = {"baseline": baseline, "candidate": candidate}
    per_group = [
        {
            "models": {
                "baseline": baseline,
                "candidate": candidate,
            }
        }
        for _ in range(8)
    ]

    gate = VALIDATION._model_comparison_gate(
        "candidate",
        "baseline",
        per_group,
        macro,
        anchor_all_physical=True,
        inverse_out_of_domain_count=1,
    )

    assert gate["checks"]["zero_inverse_out_of_domain_elements"] is False
    assert gate["reconstruction_gate_passes"] is False
    assert gate["profile_emission_allowed"] is False
    assert gate["physical_cmy_claim_allowed"] is False


def test_dp_ii_has_no_bundled_type_ii_profile_mapping():
    dp_ii = next(
        item
        for item in VALIDATION.DATASET_SPECS
        if item.key == "crystal_archive_dp_ii"
    )

    assert dp_ii.profile_slug is None
    assert "not mapped" in dp_ii.identity_note
