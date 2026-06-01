from __future__ import annotations

import numpy as np

from spektrafilm.utils.hdr_photo import HDRPhotoRenditions
from tools.validate_profile_aware_hdr_raw_samples import _metadata_validation_checks


def test_metadata_validation_checks_cover_android_iso_and_exr_expectations(tmp_path) -> None:
    sdr = np.array([[[0.20, 0.20, 0.20], [0.45, 0.45, 0.45]]], dtype=np.float32)
    hdr = np.array([[[0.20, 0.20, 0.20], [1.80, 1.80, 1.80]]], dtype=np.float32)
    renditions = HDRPhotoRenditions(hdr_rgb=hdr, sdr_rgb=sdr, headroom=4.0)

    checks = _metadata_validation_checks(
        renditions,
        probe_dir=tmp_path,
        color_space="Display P3",
    )

    assert checks["android_ultra_hdr"]["container_directory"] is True
    assert checks["android_ultra_hdr"]["primary_and_gain_map_items"] is True
    assert checks["iso_21496_1"]["serialized_metadata_roundtrip"] is True
    assert checks["iso_21496_1"]["gain_map_validation_warnings"] == []
    assert checks["jpeg_probe"]["roundtrip_metadata"] is True
    assert checks["exr"]["required_attributes"] == ["chromaticities", "colorInteropID", "oiio:ColorSpace", "whiteLuminance", "hdrHeadroom"]
