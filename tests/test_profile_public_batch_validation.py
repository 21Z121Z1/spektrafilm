import importlib.util
from dataclasses import replace
from io import BytesIO
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pytest

from spektrafilm.profiles.io import profile_from_dict


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "reports"
    / "profile-public-batch-validation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "profile_public_batch_validation",
    SCRIPT_PATH,
)
assert SPEC is not None and SPEC.loader is not None
VALIDATION = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATION
SPEC.loader.exec_module(VALIDATION)


def _dataset_spec(key: str):
    return next(spec for spec in VALIDATION.DATASET_SPECS if spec.key == key)


def _synthetic_batches(
    spec,
    *,
    count: int = 3,
):
    profile = json.loads(
        (
            VALIDATION.PROFILE_DIR / f"{spec.profile_slug}.json"
        ).read_text(encoding="utf-8")
    )
    profile_wavelengths = np.asarray(profile["data"]["wavelengths"], dtype=float)
    profile_basis = np.asarray(profile["data"]["channel_density"], dtype=float)
    support = np.all(np.isfinite(profile_basis), axis=1)
    if spec.measurement_kind == "transmission":
        wavelengths = np.arange(380.0, 781.0, 10.0)
    else:
        wavelengths = np.arange(400.0, 701.0, 10.0)
    basis = np.column_stack(
        [
            np.interp(
                wavelengths,
                profile_wavelengths[support],
                profile_basis[support, channel],
            )
            for channel in range(3)
        ]
    )
    names = np.array(["GS0", *[f"P{index:03d}" for index in range(1, 288)]])
    generator = np.random.default_rng(20260713)
    coefficients = generator.uniform(0.0, 0.55, size=(288, 3))
    coefficients[0] = 0.0
    base_shape = 0.18 + 0.035 * np.square((wavelengths - 560.0) / 200.0)
    shifts = np.linspace(-0.006, 0.006, count)
    batches = []
    for index, shift in enumerate(shifts):
        density = base_shape + shift + coefficients @ basis.T
        values = np.power(10.0, -density)
        batches.append(
            VALIDATION.BatchData(
                batch_id=f"T{index:06d}",
                material=spec.material,
                production_date=f"2026:{index + 1:02d}",
                created=f"2026-07-{index + 1:02d}",
                wavelengths=wavelengths,
                names=names,
                values=values,
                archive_sha256=f"{index + 1:064x}",
                source_member=f"T{index:06d}.spectral",
                raw_zero_value_count=0,
            )
        )
    return batches


def test_archive_links_filters_and_deduplicates_supported_batches():
    html = """
    <a href="F240222.zip">F</a>
    <a href="F240222.zip">duplicate</a>
    <a href="N230513.zip">N</a>
    <a href="R200204.zip">R</a>
    <a href="E240220.zip">ignored</a>
    """

    assert VALIDATION._archive_links(html) == [
        "F240222.zip",
        "N230513.zip",
        "R200204.zip",
    ]


def test_archive_metadata_prefers_batch_file_over_fault_file():
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(
            "R110714/Extras/Fault.txt",
            'MATERIAL "Wrong donor"\nPROD_DATE "2010:12"\n',
        )
        archive.writestr(
            "R110714/R110714.txt",
            'MATERIAL "Kodak Professional Ultra Endura"\n'
            'PROD_DATE "2011:07"\nCREATED "December 07, 2011"\n',
        )
    with zipfile.ZipFile(BytesIO(buffer.getvalue())) as archive:
        metadata = VALIDATION._archive_metadata(archive, "R110714")

    assert metadata["MATERIAL"] == "Kodak Professional Ultra Endura"
    assert metadata["PROD_DATE"] == "2011:07"


def test_cxf_parser_recovers_named_spectra():
    payload = b"""<?xml version="1.0"?>
    <CXF><SampleSet>
      <Sample><Name>GS0</Name><SampleAttribute><Spectrum Conditions="1">
        <Value Name="400">0.8</Value><Value Name="410">0.7</Value>
      </Spectrum></SampleAttribute></Sample>
      <Sample><Name>A1</Name><SampleAttribute><Spectrum Conditions="1">
        <Value Name="400">0.2</Value><Value Name="410">0.1</Value>
      </Spectrum></SampleAttribute></Sample>
    </SampleSet></CXF>"""

    names, wavelengths, values = VALIDATION._parse_cxf_spectra(payload)

    np.testing.assert_array_equal(names, ["GS0", "A1"])
    np.testing.assert_array_equal(wavelengths, [400.0, 410.0])
    np.testing.assert_allclose(values, [[0.8, 0.7], [0.2, 0.1]])


def test_raw_zero_is_allowed_outside_gs0_but_not_in_gs0():
    names = np.array(["GS0", *[f"P{index}" for index in range(1, 288)]])
    wavelengths = np.array([380.0, 390.0, 400.0])
    values = np.full((288, 3), 0.5)
    values[1, 0] = 0.0

    VALIDATION._validate_batch_arrays(names, wavelengths, values, "T000001")

    values[0, 0] = 0.0
    with pytest.raises(ValueError, match="GS0"):
        VALIDATION._validate_batch_arrays(names, wavelengths, values, "T000001")


def test_leave_one_batch_out_median_base_improves_synthetic_exact_stock():
    spec = _dataset_spec("provia_100f")
    batches = _synthetic_batches(spec)

    result, wavelengths, candidate_base = (
        VALIDATION._evaluate_cross_batch_base(
            spec,
            batches,
            floors=(1e-3,),
        )
    )

    floor = result["results_by_measurement_floor"]["0.001"]
    bundled = floor["models"]["bundled_base"]
    candidate = floor["models"]["multibatch_median_gs0"]
    assert result["direct_gs0_base_rmse_D"]["candidate_batch_wins"] == 3
    assert candidate["density_rmse_D"] < bundled["density_rmse_D"]
    assert (
        candidate["transmission_rmse_percentage_points"]
        < bundled["transmission_rmse_percentage_points"]
    )
    assert floor["candidate_batch_win_counts"]["density_rmse_D"] == 3
    assert len(wavelengths) == len(candidate_base)


def test_multibatch_candidate_changes_only_base_data_and_is_loadable():
    spec = _dataset_spec("provia_100f")
    batches = _synthetic_batches(spec)
    _, wavelengths, candidate_base = VALIDATION._evaluate_cross_batch_base(
        spec,
        batches,
        floors=(1e-3,),
    )

    payload, summary = VALIDATION._build_multibatch_candidate_payload(
        spec,
        batches,
        wavelengths,
        candidate_base,
        interpolation="pchip",
    )
    candidate = profile_from_dict(payload)
    json.dumps(payload, allow_nan=False)
    original = json.loads(
        (
            VALIDATION.PROFILE_DIR / f"{spec.profile_slug}.json"
        ).read_text(encoding="utf-8")
    )
    changed_data_fields = [
        name
        for name in original["data"]
        if original["data"][name] != payload["data"][name]
    ]

    assert changed_data_fields == ["base_density"]
    assert candidate.info.stock == spec.profile_slug
    assert summary["source_batch_count"] == 3
    assert len(summary["source_manifest_sha256"]) == 64
    provenance = candidate.metadata.provenance.fields["base_density"]
    assert provenance.origin == "published-measurement"
    assert provenance.status == "reconstructed"
    assert (
        candidate.metadata.provenance.measurement_status
        == "partial-instrument-data"
    )
    assert (
        "leave-one-production-date-group-out-validation"
        in provenance.transformations
    )
    assert "do not redistribute" in candidate.metadata.license


def test_reflection_candidate_runtime_is_finite_monotonic_and_deterministic():
    spec = _dataset_spec("endura_premier")
    batches = _synthetic_batches(spec)
    _, wavelengths, candidate_base = VALIDATION._evaluate_cross_batch_base(
        spec,
        batches,
        floors=(1e-2,),
    )
    pchip, _ = VALIDATION._build_multibatch_candidate_payload(
        spec,
        batches,
        wavelengths,
        candidate_base,
        interpolation="pchip",
    )
    linear, _ = VALIDATION._build_multibatch_candidate_payload(
        spec,
        batches,
        wavelengths,
        candidate_base,
        interpolation="linear",
    )
    bundled = json.loads(
        (
            VALIDATION.PROFILE_DIR / f"{spec.profile_slug}.json"
        ).read_text(encoding="utf-8")
    )

    result = VALIDATION._evaluate_runtime_candidates(
        spec,
        bundled,
        pchip,
        linear,
    )

    assert result["route"] == "negative-film optical print and paper scan"
    assert result["pchip_repeat_max_absolute_difference"] == pytest.approx(0.0)
    assert all(
        profile_result["all_arrays_finite"]
        for profile_result in result["profiles"].values()
    )
    assert all(
        profile_result["neutral_ramp_monotonic_non_decreasing"]
        for profile_result in result["profiles"].values()
    )


def test_positive_basis_path_is_nonnegative_but_preserves_actual_baseline():
    bundled = np.array(
        [
            [1.2, 0.2, -5e-5],
            [0.4, 1.1, 0.1],
            [0.1, 0.3, 1.3],
        ]
    )
    free = np.array(
        [
            [1.0, 0.3, 0.0],
            [0.5, 1.0, 0.2],
            [0.2, 0.4, 1.0],
        ]
    )

    baseline = VALIDATION._blended_basis(bundled, free, 0.0)
    candidate = VALIDATION._blended_basis(bundled, free, 0.25)

    np.testing.assert_array_equal(baseline, bundled)
    assert np.any(baseline < 0.0)
    assert np.all(candidate >= 0.0)
    np.testing.assert_allclose(
        np.max(candidate, axis=0),
        np.max(bundled, axis=0),
    )


def test_effective_basis_validation_and_payload_are_auditable():
    spec = _dataset_spec("provia_100f")
    batches = _synthetic_batches(spec)
    base_result, base_wavelengths, candidate_base = (
        VALIDATION._evaluate_cross_batch_base(
            spec,
            batches,
            floors=(1e-3,),
        )
    )
    result, basis_wavelengths, effective_basis = (
        VALIDATION._evaluate_effective_basis_path(
            spec,
            batches,
            alphas=(0.0, 0.25),
            folds=3,
            iterations=4,
            seed=20260713,
            initialization_count=1,
            selected_alpha=0.25,
        )
    )

    assert base_result["batch_count"] == 3
    assert result["selected_alpha"] == 0.25
    assert result["candidate_gate"]["default_replacement_authorized"] is False
    assert np.all(effective_basis >= 0.0)
    assert len(basis_wavelengths) == effective_basis.shape[0]
    chronological = result[
        "chronological_newest_production_group_holdout"
    ]
    assert chronological["train_test_production_groups_disjoint"] is True
    assert set(chronological["test_production_groups"]).isdisjoint(
        chronological["training_production_groups"]
    )

    payload, summary = VALIDATION._build_effective_basis_candidate_payload(
        spec,
        batches,
        base_wavelengths,
        candidate_base,
        basis_wavelengths,
        effective_basis,
        selected_alpha=0.25,
        interpolation="pchip",
    )
    candidate = profile_from_dict(payload)
    json.dumps(payload, allow_nan=False)
    original = json.loads(
        (
            VALIDATION.PROFILE_DIR / f"{spec.profile_slug}.json"
        ).read_text(encoding="utf-8")
    )
    changed_data_fields = [
        name
        for name in original["data"]
        if original["data"][name] != payload["data"][name]
    ]

    assert set(changed_data_fields) == {"base_density", "channel_density"}
    assert summary["fields_changed"] == ["base_density", "channel_density"]
    assert (
        summary["channel_interpolation"]["negative_interpolation_roundoff"][
            "material_negative_values_allowed"
        ]
        is False
    )
    assert summary["channel_interpolation"][
        "outside_measured_range_exactly_unchanged"
    ]
    assert summary["channel_interpolation"][
        "channel_peak_scale_restoration"
    ]["selected_peak_max_absolute_difference_D"] == pytest.approx(0.0)
    assert candidate.info.stock == spec.profile_slug
    channel_provenance = candidate.metadata.provenance.fields["channel_density"]
    assert channel_provenance.status == "reconstructed"
    assert "not analytical dye spectra" in channel_provenance.notes


def test_production_date_groups_are_never_split_or_overweighted():
    spec = _dataset_spec("provia_100f")
    original_batches = _synthetic_batches(spec, count=4)
    batches = [
        replace(original_batches[0], production_date="2025:01"),
        replace(
            original_batches[1],
            production_date="2025:01",
            names=original_batches[1].names[::-1],
            values=original_batches[1].values[::-1],
        ),
        replace(original_batches[2], production_date="2025:02"),
        replace(original_batches[3], production_date="2025:03"),
    ]

    base_result, _, candidate_base = VALIDATION._evaluate_cross_batch_base(
        spec,
        batches,
        floors=(1e-3,),
    )
    gs0_density = np.stack(
        [
            -np.log10(batch.values[batch.names == "GS0"][0])
            for batch in batches
        ]
    )
    expected = np.median(
        np.stack(
            [
                np.median(gs0_density[:2], axis=0),
                gs0_density[2],
                gs0_density[3],
            ]
        ),
        axis=0,
    )

    assert base_result["archive_count"] == 4
    assert base_result["production_group_count"] == 3
    np.testing.assert_allclose(candidate_base, expected)
    floor = base_result["results_by_measurement_floor"]["0.001"]
    assert floor["held_out_unit"] == "complete PROD_DATE production-proxy group"
    assert floor["production_group_count"] == 3

    basis_result, _, _ = VALIDATION._evaluate_effective_basis_path(
        spec,
        batches,
        alphas=(0.0, 0.25),
        folds=3,
        iterations=4,
        seed=20260713,
        initialization_count=1,
        selected_alpha=0.25,
    )
    held_out_groups = [
        group
        for fold in basis_result["outer_fold_test_groups"]
        for group in fold
    ]
    assert sorted(held_out_groups) == ["2025:01", "2025:02", "2025:03"]


def test_cross_production_date_exact_spectral_duplicates_are_all_excluded():
    spec = _dataset_spec("velvia_100")
    batches = _synthetic_batches(spec, count=3)
    duplicate = replace(
        batches[0],
        batch_id="DUP0001",
        production_date="2030:12",
        archive_sha256="f" * 64,
    )

    filtered, exclusions = (
        VALIDATION._exclude_cross_production_date_duplicate_spectra(
            [*batches, duplicate]
        )
    )

    assert {batch.batch_id for batch in filtered} == {
        batches[1].batch_id,
        batches[2].batch_id,
    }
    assert {row["batch"] for row in exclusions} == {
        batches[0].batch_id,
        duplicate.batch_id,
    }
    assert all(
        row["duplicate_production_groups"]
        == [batches[0].production_date, duplicate.production_date]
        for row in exclusions
    )


def test_effective_basis_metrics_are_invariant_to_patch_row_order():
    spec = _dataset_spec("provia_100f")
    canonical = _synthetic_batches(spec, count=4)
    reordered = list(canonical)
    reordered[1] = replace(
        canonical[1],
        names=canonical[1].names[::-1],
        values=canonical[1].values[::-1],
    )
    kwargs = {
        "alphas": (0.0, 0.25),
        "folds": 4,
        "iterations": 4,
        "seed": 20260713,
        "initialization_count": 1,
        "selected_alpha": 0.25,
    }

    expected, _, _ = VALIDATION._evaluate_effective_basis_path(
        spec,
        canonical,
        **kwargs,
    )
    actual, _, _ = VALIDATION._evaluate_effective_basis_path(
        spec,
        reordered,
        **kwargs,
    )

    assert actual["path_results"] == expected["path_results"]


def test_zero_shape_delta_is_identity_on_final_profile_grid():
    spec = _dataset_spec("provia_100f")
    profile = json.loads(
        (
            VALIDATION.PROFILE_DIR / f"{spec.profile_slug}.json"
        ).read_text(encoding="utf-8")
    )
    profile_wavelengths = np.asarray(profile["data"]["wavelengths"], dtype=float)
    current_channels = np.asarray(
        profile["data"]["channel_density"],
        dtype=float,
    )
    finite = np.all(np.isfinite(current_channels), axis=1)
    measured_wavelengths = np.arange(400.0, 701.0, 10.0)
    current_on_measured = np.column_stack(
        [
            np.interp(
                measured_wavelengths,
                profile_wavelengths[finite],
                current_channels[finite, channel],
            )
            for channel in range(3)
        ]
    )

    candidate, replacement_support, summary = (
        VALIDATION._resample_effective_basis_to_profile_grid(
            profile_wavelengths,
            current_channels,
            measured_wavelengths,
            current_on_measured,
            interpolation="pchip",
        )
    )

    np.testing.assert_allclose(candidate, current_channels, equal_nan=True)
    assert np.any(replacement_support)
    assert summary["zero_delta_identity_max_absolute_difference_D"] == 0.0
    assert summary["outside_measured_range_exactly_unchanged"] is True
    assert summary["channel_peak_scale_restoration"][
        "selected_peak_max_absolute_difference_D"
    ] == pytest.approx(0.0)
