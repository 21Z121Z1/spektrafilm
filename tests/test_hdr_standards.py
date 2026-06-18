from __future__ import annotations

import json

import numpy as np

from spektrafilm.hdr.standards import (
    HDRStandardsMetadata,
    build_hdr_standards_metadata,
    pq_code_values_to_nits,
    pq_nits_to_code_values,
)


def test_pq_round_trip_is_stable() -> None:
    nits = np.array([0.0, 1.0, 203.0, 1000.0, 10000.0], dtype=np.float32)
    code_values = pq_nits_to_code_values(nits)
    restored = pq_code_values_to_nits(code_values)
    np.testing.assert_allclose(restored, nits, rtol=1e-3, atol=1e-2)


def test_hdr_standards_metadata_json_and_exr_attributes() -> None:
    metadata = build_hdr_standards_metadata(
        color_space="Display P3",
        hdr_headroom=2.0,
        mastering_scene_white=1.0,
        mastering_look_white=0.9,
        mastering_display_white_nits=203.0,
        mastering_target_peak_ev=1.0,
        mastering_curve_budget_ev=1.0,
        scene_luminance=np.array([[1.0, 2.0]], dtype=np.float32),
        render_rgb=np.array([[[0.5, 0.5, 0.5], [1.0, 2.0, 3.0]]], dtype=np.float32),
        source_role="hdr_rendition",
    )

    json_payload = metadata.to_json_dict()
    assert json_payload["schema"] == "spektrafilm.hdr.dynamic_metadata"
    assert json_payload["dynamic_metadata"]["application"]["id"] == "spektrafilm"
    assert json_payload["source_role"] == "hdr_rendition"
    assert json.loads(json.dumps(json_payload, sort_keys=True))["eotf"] == "scene-linear"
    assert json_payload["mastering_summary"]["scene_white"] == 1.0
    assert json_payload["mastering_summary"]["look_white"] == 0.9

    exr_attrs = metadata.to_exr_attributes()
    assert exr_attrs["dynamicMetadataApplication"] == "spektrafilm"
    assert exr_attrs["dynamicMetadataVersion"] == "1"
    assert exr_attrs["hdrSourceRole"] == "hdr_rendition"
    assert exr_attrs["hdrHeadroom"] == 2.0
    assert exr_attrs["masteringSceneWhite"] == 1.0
    assert exr_attrs["masteringLookWhite"] == 0.9
    assert exr_attrs["masteringDisplayWhiteLuminance"] == 203.0
    assert exr_attrs["masteringTargetPeakEv"] == 1.0
    assert exr_attrs["masteringCurveBudgetEv"] == 1.0
    assert "masteringSummary" in exr_attrs


def test_hdr_standards_metadata_treats_unity_headroom_as_zero_ev() -> None:
    metadata = build_hdr_standards_metadata(
        color_space="Display P3",
        hdr_headroom=1.0,
        scene_luminance=np.array([[1.0]], dtype=np.float32),
        render_rgb=np.array([[[1.0, 1.0, 1.0]]], dtype=np.float32),
        source_role="hdr_rendition",
    )

    assert metadata.mastering_target_peak_ev == 0.0
    assert metadata.mastering_curve_budget_ev == 0.0
    assert metadata.to_json_dict()["mastering_summary"]["target_peak_ev"] == 0.0
    assert metadata.to_exr_attributes()["masteringTargetPeakEv"] == 0.0
