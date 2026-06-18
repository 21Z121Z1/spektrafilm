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
        scene_luminance=np.array([[1.0, 2.0]], dtype=np.float32),
        render_rgb=np.array([[[0.5, 0.5, 0.5], [1.0, 2.0, 3.0]]], dtype=np.float32),
        source_role="hdr_rendition",
    )

    json_payload = metadata.to_json_dict()
    assert json_payload["schema"] == "spektrafilm.hdr.dynamic_metadata"
    assert json_payload["dynamic_metadata"]["application"]["id"] == "spektrafilm"
    assert json_payload["source_role"] == "hdr_rendition"
    assert json.loads(json.dumps(json_payload, sort_keys=True))["eotf"] == "scene-linear"

    exr_attrs = metadata.to_exr_attributes()
    assert exr_attrs["dynamicMetadataApplication"] == "spektrafilm"
    assert exr_attrs["dynamicMetadataVersion"] == "1"
    assert exr_attrs["hdrSourceRole"] == "hdr_rendition"
    assert exr_attrs["hdrHeadroom"] == 2.0
