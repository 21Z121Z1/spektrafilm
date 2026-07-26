import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest

from spektrafilm.profiles.io import profile_from_dict


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "profile-manufacturer-curve-validation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "profile_manufacturer_curve_validation_test",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATION
SPEC.loader.exec_module(VALIDATION)


def test_manufacturer_overlay_uses_cmy_runtime_order_and_preserves_outside():
    payload = {
        "data": {
            "wavelengths": [395.0, 400.0, 405.0, 700.0, 705.0],
            "channel_density": [
                [2.0, 3.0, 4.0],
                [0.1, 0.2, 0.3],
                [0.2, 0.3, 0.4],
                [0.3, 0.4, 0.5],
                [1.0, 2.0, 3.0],
            ],
        }
    }
    curve_report = {
        "analysis": {"profile_grid_nm": [400.0, 405.0, 700.0]},
        "stocks": {
            "provia_100f": {
                "primary_normalized": {
                    "C": [0.5, 1.0, 0.2],
                    "M": [1.0, 0.5, 0.1],
                    "Y": [0.25, 0.5, 1.0],
                }
            }
        },
    }

    candidate, summary = VALIDATION._apply_manufacturer_shape_to_payload(
        payload,
        curve_report,
        stock_key="provia_100f",
    )

    assert candidate is not payload
    assert payload["data"]["channel_density"][1] == [0.1, 0.2, 0.3]
    assert candidate["data"]["channel_density"][0] == [2.0, 3.0, 4.0]
    assert candidate["data"]["channel_density"][4] == [1.0, 2.0, 3.0]
    np.testing.assert_allclose(
        candidate["data"]["channel_density"][1:4],
        [
            [1.0, 3.0, 1.0],
            [2.0, 1.5, 2.0],
            [0.4, 0.3, 4.0],
        ],
    )
    assert summary["channel_runtime_order"] == ["C", "M", "Y"]
    assert summary["replacement_point_count"] == 3
    assert summary["outside_source_support_exactly_unchanged"] is True
    assert summary["channel_peak_scale_restoration"][
        "maximum_absolute_difference_D"
    ] == 0.0


def test_combined_candidate_provenance_does_not_claim_absolute_dyes(
    monkeypatch,
):
    profile_path = (
        VALIDATION.PUBLIC.PROFILE_DIR / "fujifilm_provia_100f.json"
    )
    original = json.loads(profile_path.read_text(encoding="utf-8"))

    def fake_base_builder(
        spec,
        batches,
        measured_wavelengths,
        median_gs0_density,
        *,
        interpolation,
    ):
        payload = copy.deepcopy(original)
        payload["data"]["base_density"][10] += 0.01
        return payload, {
            "candidate_id": f"base-{interpolation}",
            "candidate_context_sha256": "1" * 64,
            "source_manifest_sha256": "2" * 64,
            "profile_stock": "fujifilm_provia_100f",
            "material": "Fujichrome Provia 100F (RDP III)",
            "measurement_kind": "transmission",
            "measurement_status": "partial-instrument-data",
            "source_archive_count": 1,
            "source_production_group_count": 1,
            "source_production_groups": [],
            "source_batch_ids": ["F240222"],
            "source_manifest": [],
            "bundled_data_sha256": "5" * 64,
            "analysis_code_sha256": "6" * 64,
            "analysis_software_versions": {"python": "test"},
            "provenance_status": "reconstructed",
            "changed_point_count": 67,
            "unchanged_point_count": 14,
            "mean_absolute_change_D_on_support": 0.1,
            "max_absolute_change_D_on_support": 0.2,
            "interpolation": {
                "method": interpolation,
                "shared_support_range_nm": [385.0, 715.0],
                "pchip_vs_linear_max_absolute_difference_D": 0.01,
            },
        }

    monkeypatch.setattr(
        VALIDATION.PUBLIC,
        "_build_multibatch_candidate_payload",
        fake_base_builder,
    )
    grid = np.arange(400.0, 701.0, 5.0)
    curve_report = {
        "analysis": {
            "profile_grid_nm": grid.tolist(),
            "script_sha256": "3" * 64,
        },
        "result_sha256": "4" * 64,
        "stocks": {
            "provia_100f": {
                "primary_normalized": {
                    "C": np.exp(-0.5 * ((grid - 655.0) / 55.0) ** 2).tolist(),
                    "M": np.exp(-0.5 * ((grid - 540.0) / 45.0) ** 2).tolist(),
                    "Y": np.exp(-0.5 * ((grid - 445.0) / 40.0) ** 2).tolist(),
                }
            }
        },
    }
    spec = SimpleNamespace(profile_slug="fujifilm_provia_100f")

    candidate, summary = VALIDATION._build_combined_provia_candidate(
        spec,
        [],
        curve_report,
        np.arange(380.0, 781.0, 10.0),
        np.zeros(41),
        interpolation="linear",
    )
    loaded = profile_from_dict(candidate)
    channel_provenance = loaded.metadata.provenance.fields["channel_density"]

    assert loaded.info.stock == "fujifilm_provia_100f"
    assert channel_provenance.origin == "manufacturer-graph"
    assert channel_provenance.status == "source-derived"
    assert "FUJI_PROVIA_100F_AF3_036E_2000" in channel_provenance.sources
    assert "absolute dye concentration" in channel_provenance.notes
    assert "keep this candidate local" in loaded.metadata.license
    assert summary["channel_semantics"] == (
        "manufacturer-published normalized shape; absolute peak inherited"
    )
    assert summary["characteristic_curves_changed"] is False
    assert summary["log_sensitivity_changed"] is False
    assert summary["midscale_neutral_density_changed"] is False
    assert candidate["data"]["density_curves"] == original["data"][
        "density_curves"
    ]
    assert candidate["data"]["log_sensitivity"] == original["data"][
        "log_sensitivity"
    ]
    assert candidate["data"]["midscale_neutral_density"] == original["data"][
        "midscale_neutral_density"
    ]
    assert {
        field
        for field in original["data"]
        if original["data"][field] != candidate["data"][field]
    } == {"base_density", "channel_density"}

    pchip_candidate, pchip_summary = (
        VALIDATION._build_combined_provia_candidate(
            spec,
            [],
            curve_report,
            np.arange(380.0, 781.0, 10.0),
            np.zeros(41),
            interpolation="pchip",
        )
    )
    assert pchip_candidate["data"]["channel_density"] == candidate["data"][
        "channel_density"
    ]
    assert pchip_summary["candidate_context_sha256"] != summary[
        "candidate_context_sha256"
    ]
    assert pchip_summary["candidate_context"]["base_interpolation"] == "pchip"
    assert summary["candidate_context"]["base_interpolation"] == "linear"


def test_manufacturer_overlay_rejects_non_monotonic_source_grid():
    payload = {
        "data": {
            "wavelengths": [400.0, 405.0, 700.0],
            "channel_density": [[1.0, 1.0, 1.0]] * 3,
        }
    }
    report = {
        "analysis": {"profile_grid_nm": [400.0, 700.0, 405.0]},
        "stocks": {
            "provia_100f": {
                "primary_normalized": {
                    channel: [1.0, 0.5, 0.2] for channel in ("C", "M", "Y")
                }
            }
        },
    }

    with pytest.raises(ValueError, match="strictly increasing"):
        VALIDATION._apply_manufacturer_shape_to_payload(
            payload,
            report,
            stock_key="provia_100f",
        )
