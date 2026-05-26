from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.utils import hdr_photo
from spektrafilm.utils.hdr_curve_profiles import (
    HDRCurveDefaults,
    FilmPrintHDRCurveProfile,
    build_profile_hdr_curve,
    build_profile_preserving_hdr_curve,
    evaluate_profile_sdr_curve,
)


# ---------------------------------------------------------------------------
# Existing tests (updated for paper rolloff behavior change)
# ---------------------------------------------------------------------------


def test_hdr_photo_mapping_builds_authored_sdr_and_hdr_renditions() -> None:
    image = np.array([[[1.0, 1.0, 1.0], [4.0, 4.0, 4.0]]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(diffuse_white=1.0, sdr_paper_white=0.9, max_headroom=4.0)

    renditions = hdr_photo.prepare_hdr_photo_renditions(image, mapping=mapping)

    # With paper rolloff enabled (default), the 4.0 pixel is compressed.
    assert renditions.headroom > 1.0
    assert renditions.headroom <= 4.0
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [1.0, 1.0, 1.0])
    # The authored SDR base preserves the user look and clips only at SDR white.
    np.testing.assert_allclose(renditions.sdr_rgb[0, 0], [1.0, 1.0, 1.0])
    np.testing.assert_allclose(renditions.sdr_rgb[0, 1], [1.0, 1.0, 1.0])


def test_hdr_photo_sdr_tone_map_preserves_hue_ratios() -> None:
    image = np.array([[[4.0, 2.0, 1.0]]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        diffuse_white=1.0,
        sdr_paper_white=0.9,
        max_headroom=4.0,
        preserve_sdr_base=False,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(image, mapping=mapping)

    # Hue ratios 4:2:1 must be preserved in SDR tone map.
    sdr = renditions.sdr_rgb[0, 0]
    np.testing.assert_allclose(sdr[1] / sdr[0], 0.5, rtol=1e-5)
    np.testing.assert_allclose(sdr[2] / sdr[0], 0.25, rtol=1e-5)


def test_hdr_photo_sdr_tone_map_compresses_mid_highlights_with_a_shoulder() -> None:
    image = np.array([[[2.0, 2.0, 2.0], [4.0, 4.0, 4.0]]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        diffuse_white=1.0,
        sdr_paper_white=0.9,
        max_headroom=4.0,
        preserve_sdr_base=False,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(image, mapping=mapping)

    # SDR mid-highlight should be above paper_white but below 1.0.
    assert 0.9 < float(renditions.sdr_rgb[0, 0, 0]) < 1.0
    assert float(renditions.sdr_rgb[0, 1].max()) <= 1.0


def test_hdr_photo_headroom_caps_extreme_outliers() -> None:
    image = np.array([[[0.25, 1.5, 100.0]]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(diffuse_white=1.0, sdr_paper_white=0.9, max_headroom=8.0)

    renditions = hdr_photo.prepare_hdr_photo_renditions(image, mapping=mapping)
    payload = hdr_photo._rgba_float_payload(renditions.hdr_rgb, headroom=renditions.headroom)

    # Headroom should be capped by max_headroom.
    assert renditions.headroom <= 8.0
    assert float(payload[..., :3].max()) <= 8.0


def test_hdr_photo_rejects_sdr_only_renditions() -> None:
    image = np.full((1, 1, 3), 1.0, dtype=np.float32)

    with pytest.raises(ValueError, match="above SDR white"):
        hdr_photo.prepare_hdr_photo_renditions(image)


def test_hdr_photo_scene_luminance_graft_exports_paper_limited_look_as_hdr() -> None:
    look_rgb = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)

    # Disable diffuse lift to test the raw specular graft / rolloff behavior
    mapping = hdr_photo.HDRPhotoMapping(hdr_diffuse_lift_enabled=False)

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
    )

    # With rolloff, headroom is determined by robust percentile.
    assert renditions.headroom > 1.0
    # Shadows near look_rgb remain close to original.
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [0.8, 0.8, 0.8], atol=0.05)
    # Highlight is above 1.0 and bounded by default max_headroom (8.0).
    assert float(renditions.hdr_rgb[0, 1].max()) > 1.0
    assert float(renditions.hdr_rgb[0, 1].max()) <= 8.0
    assert float(renditions.sdr_rgb.max()) <= 1.0


def test_hdr_photo_scene_luminance_graft_caps_one_hot_pixel() -> None:
    look_rgb = np.full((1, 3, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 2.0, 100.0]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0)

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
    )

    # Headroom must be capped by max_headroom.
    assert renditions.headroom <= 8.0
    # All HDR values must be within headroom.
    assert float(renditions.hdr_rgb.max()) <= renditions.headroom + 1e-6


def test_hdr_photo_rejects_nonfinite_values() -> None:
    image = np.array([[[0.25, np.inf, 1.5]]], dtype=np.float32)

    with pytest.raises(ValueError, match="finite"):
        hdr_photo._prepare_hdr_rgb(image)


def test_save_hdr_photo_heic_passes_authored_sdr_and_hdr_payloads(monkeypatch, tmp_path) -> None:
    image = np.array([[[1.0, 1.0, 1.0], [4.0, 2.0, 1.0]]], dtype=np.float32)
    output_path = tmp_path / "out.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))

    def fake_run(command, *, check, capture_output, text, timeout):
        captured["command"] = command
        captured["check"] = check
        captured["capture_output"] = capture_output
        captured["text"] = text
        captured["timeout"] = timeout
        captured["sdr_payload"] = np.fromfile(command[2], dtype=np.float32).reshape(1, 2, 4)
        captured["hdr_payload"] = np.fromfile(command[3], dtype=np.float32).reshape(1, 2, 4)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    hdr_photo.save_hdr_photo_heic(output_path, image, color_space="Display P3", quality=0.8)

    # Command should have 11 arguments now, with gain_map_mode as the last one.
    assert captured["command"][-1] == "rgb"

    # With rolloff, the diffuse-white pixel remains 1.0.
    np.testing.assert_allclose(captured["hdr_payload"][0, 0, :3], [1.0, 1.0, 1.0])
    # The highlight pixel is compressed by rolloff but above 1.0.
    assert float(captured["hdr_payload"][0, 1, :3].max()) > 1.0
    # Default save path preserves the authored SDR base.
    sdr_pixel = captured["sdr_payload"][0, 1, :3]
    np.testing.assert_allclose(sdr_pixel, [1.0, 1.0, 1.0])
    np.testing.assert_allclose(captured["sdr_payload"][..., 3], 1.0)
    np.testing.assert_allclose(captured["hdr_payload"][..., 3], 1.0)


def test_save_hdr_photo_heic_uses_scene_luminance_sidecar(monkeypatch, tmp_path) -> None:
    image = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    output_path = tmp_path / "out.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))

    def fake_run(command, *, check, capture_output, text, timeout):
        captured["command"] = command
        captured["sdr_payload"] = np.fromfile(command[2], dtype=np.float32).reshape(1, 2, 4)
        captured["hdr_payload"] = np.fromfile(command[3], dtype=np.float32).reshape(1, 2, 4)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    hdr_photo.save_hdr_photo_heic(
        output_path,
        image,
        color_space="Display P3",
        scene_luminance=scene_luminance,
        gain_map_mode="luma",
    )

    # Headroom is a float (the command arg at index 8).
    headroom = float(captured["command"][8])
    assert headroom > 1.0

    # Should use the explicitly provided luma gain map mode
    assert captured["command"][-1] == "luma"
    # HDR highlight pixel is compressed by rolloff, above 1.0, bounded by default max_headroom.
    assert float(captured["hdr_payload"][0, 1, :3].max()) > 1.0
    assert float(captured["hdr_payload"][0, 1, :3].max()) <= 8.0
    assert float(captured["sdr_payload"][..., :3].max()) <= 1.0


# ---------------------------------------------------------------------------
# New Logistic paper rolloff tests
# ---------------------------------------------------------------------------


def test_logistic_rolloff_2x_diffuse_white_does_not_reach_max_headroom() -> None:
    """2× diffuse white must NOT jump near max_headroom with default params."""

    scene_y = np.array([2.0], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0)
    result = hdr_photo._apply_rolloff(scene_y, mapping=mapping)

    # Must be well above diffuse white.
    assert float(result[0]) > 1.0
    # Must be strictly compressed (not boosted).
    assert float(result[0]) < 2.0
    # Expected to be around 1.9 with default params.
    np.testing.assert_allclose(result[0], 1.91, atol=0.05)


def test_content_headroom_robust_percentile_ignores_one_hot_pixel() -> None:
    """A single hot pixel must not determine content headroom."""

    image = np.full((100, 100, 3), 2.0, dtype=np.float32)
    image[50, 50] = [100.0, 100.0, 100.0]
    headroom = hdr_photo._content_headroom(image, percentile=99.9)
    # 99.9th percentile of 10000 pixels should be dominated by the 2.0 majority.
    assert headroom == pytest.approx(2.0, abs=0.5)
    assert headroom < 10.0  # must NOT be 100.0


def test_logistic_rolloff_does_not_inherit_paper_white_limit() -> None:
    """Paper look white ~0.8 must NOT clamp HDR target."""

    look_rgb = np.full((1, 2, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 4.0]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=4.0)

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
    )

    # Highlight must exceed 1.0 — not clamped to 0.8 or sdr_paper_white.
    assert float(renditions.hdr_rgb[0, 1].max()) > 1.0
    assert float(renditions.hdr_rgb[0, 1].max()) > 0.9


def test_logistic_rolloff_monotonic_and_bounded() -> None:
    """Logistic rolloff output must be monotonically non-decreasing and bounded."""

    scene_y = np.array([1.0, 2.0, 4.0, 16.0], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0)
    result = hdr_photo._apply_rolloff(scene_y, mapping=mapping)

    # Monotonic.
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1] + 1e-7
    # Bounded by max_headroom.
    assert float(result.max()) <= 8.0


def test_rolloff_is_strict_compression() -> None:
    """Rolloff must act as strict compression: rolled_y <= scene_y everywhere."""

    scene_y = np.array([0.5, 1.0, 1.1, 1.25, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)

    # Logistic
    mapping_logi = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_mode="logistic")
    result_logi = hdr_photo._apply_rolloff(scene_y, mapping=mapping_logi)

    # Logarithmic
    mapping_loga = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_mode="logarithmic")
    result_loga = hdr_photo._apply_rolloff(scene_y, mapping=mapping_loga)

    for s, logi, loga in zip(scene_y, result_logi, result_loga):
        assert logi <= s + 1e-5, f"Logistic boosted {s} to {logi}"
        assert loga <= s + 1e-5, f"Logarithmic boosted {s} to {loga}"


def test_logistic_rolloff_preserves_midtones() -> None:
    """Scene luminance below graft_start should leave HDR target near look_rgb."""

    # Include one bright pixel so the image has valid HDR headroom.
    look_rgb = np.full((1, 3, 3), 0.5, dtype=np.float32)
    scene_luminance = np.array([[0.3, 0.5, 4.0]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=4.0)

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
    )

    # Midtones (scene_y < graft_start=0.75) should be close to look_rgb.
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [0.5, 0.5, 0.5], atol=0.05)
    np.testing.assert_allclose(renditions.hdr_rgb[0, 1], [0.5, 0.5, 0.5], atol=0.05)


def test_logistic_rolloff_k_affects_steepness() -> None:
    """Higher k should produce steeper shoulder transition (higher progress -> stronger compression -> lower output)."""

    scene_y = np.array([2.0], dtype=np.float32)
    mapping_steep = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_k=10.0)
    result_steep = hdr_photo._apply_rolloff(scene_y, mapping=mapping_steep)

    mapping_gentle = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_k=3.0)
    result_gentle = hdr_photo._apply_rolloff(scene_y, mapping=mapping_gentle)

    # Steeper transition means progress reaches 1.0 faster,
    # resulting in stronger compression and lower output at intermediate values.
    assert float(result_steep[0]) < float(result_gentle[0])


def test_logistic_rolloff_exposure_scale_controls_transition_rate() -> None:
    """Larger exposure_scale produces gentler transition."""

    scene_y = np.array([2.0], dtype=np.float32)
    mapping_fast = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_exposure_scale=1.0)
    result_fast = hdr_photo._apply_rolloff(scene_y, mapping=mapping_fast)

    mapping_slow = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_exposure_scale=5.0)
    result_slow = hdr_photo._apply_rolloff(scene_y, mapping=mapping_slow)

    # Faster transition (smaller scale) reaches higher progress faster -> stronger compression -> lower output.
    assert float(result_fast[0]) < float(result_slow[0])


def test_logistic_rolloff_below_start_is_identity() -> None:
    """Values at or below start must pass through unchanged."""

    scene_y = np.array([0.2, 0.5, 0.9, 1.0], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0)
    result = hdr_photo._apply_rolloff(scene_y, mapping=mapping)

    np.testing.assert_allclose(result, scene_y, rtol=1e-6)


def test_logarithmic_rolloff_monotonic_and_bounded() -> None:
    """Logarithmic fallback should also be monotonic and bounded."""

    scene_y = np.array([1.0, 2.0, 4.0, 16.0], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(max_headroom=8.0, paper_rolloff_mode="logarithmic")
    result = hdr_photo._apply_rolloff(scene_y, mapping=mapping)

    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1] + 1e-7
    assert float(result.max()) <= 8.0

def test_graft_blend_happens_in_ev_domain_with_smooth_transition() -> None:
    """Graft blend should use default range [1.0, 4.0] and EV-domain smoothstep."""

    scene_y = np.array([[0.5, 1.0, 1.25, 2.0, 4.0, 8.0]], dtype=np.float32)
    look_y_vals = np.array([0.5, 0.8, 0.85, 0.9, 1.0, 1.0], dtype=np.float32)
    look_rgb = np.zeros((1, 6, 3), dtype=np.float32)
    for i in range(6):
        look_rgb[0, i, :] = look_y_vals[i]

    mapping = hdr_photo.HDRPhotoMapping(
        graft_start=1.0, graft_end=4.0, graft_strength=0.5,
        hdr_diffuse_lift_enabled=False
    )

    # Call internal graft helper directly
    grafted, _ = hdr_photo._graft_scene_luminance(
        look_rgb, scene_y,
        mapping=mapping
    )
    target_y = np.max(grafted, axis=2)

    # Manually check graft contribution (blend factor w).
    rolled_y = hdr_photo._apply_rolloff(scene_y, mapping=mapping)
    target_y_flat = target_y.flatten()
    look_y_flat = look_y_vals
    rolled_y_flat = rolled_y.flatten()

    # 0.5 and 1.0: w = 0, target_y == look_y
    assert float(target_y_flat[0]) == float(look_y_flat[0])
    assert float(target_y_flat[1]) == float(look_y_flat[1])

    # 1.25: just entering EV domain. log2(1.25) ~ 0.32, log2(4) = 2. w should be very small.
    # So target_y is mostly look_y.
    assert float(target_y_flat[2]) < float((look_y_flat[2] + rolled_y_flat[2]) / 2)
    np.testing.assert_allclose(target_y_flat[2], look_y_flat[2], atol=0.05)

    # 2.0: log2(2.0) = 1.0. midpoint of [0.0, 2.0]. smoothstep(0.5) = 0.5.
    # w = 0.5 * 0.5 = 0.25
    w_mid = 0.25
    expected_mid = (1.0 - w_mid) * look_y_flat[3] + w_mid * rolled_y_flat[3]
    np.testing.assert_allclose(target_y_flat[3], expected_mid, rtol=1e-5)

    # 4.0 and 8.0: max blend = 0.5
    w_max = 0.5
    expected_max = (1.0 - w_max) * look_y_flat[4] + w_max * rolled_y_flat[4]
    np.testing.assert_allclose(target_y_flat[4], expected_max, rtol=1e-5)

def test_hdr_photo_graft_clips_hot_pixel_but_preserves_headroom() -> None:
    """Hot pixels clip to headroom rather than raising headroom indefinitely."""
    look_rgb = np.full((100, 100, 3), 0.8, dtype=np.float32)
    scene_luminance = np.full((100, 100), 2.0, dtype=np.float32)
    # One extreme hot pixel out of 10000 pixels
    scene_luminance[50, 50] = 1000.0

    mapping = hdr_photo.HDRPhotoMapping(max_headroom=10.0)
    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping, scene_luminance=scene_luminance
    )

    headroom = renditions.headroom
    assert headroom < 10.0  # Did not jump to max_headroom
    # Expected headroom from scene_y=2.0, look_y=0.8
    assert headroom == pytest.approx(1.08, abs=0.15)  # Dominated by 2.0 pixels

    # The hot pixel was compressed and then clamped to max_headroom or headroom
    # The payload serialization caps it exactly to headroom
    payload = hdr_photo._rgba_float_payload(renditions.hdr_rgb, headroom=headroom)
    assert float(payload[50, 50, :3].max()) <= headroom + 1e-5


def test_mapping_validation_rejects_invalid_rolloff_mode() -> None:
    with pytest.raises(ValueError, match="paper_rolloff_mode"):
        hdr_photo.HDRPhotoMapping(paper_rolloff_mode="invalid")


def test_mapping_validation_rejects_invalid_graft_range() -> None:
    with pytest.raises(ValueError, match="graft_start"):
        hdr_photo.HDRPhotoMapping(graft_start=1.5, graft_end=1.0)


def test_mapping_validation_rejects_invalid_headroom_percentile() -> None:
    with pytest.raises(ValueError, match="headroom_percentile"):
        hdr_photo.HDRPhotoMapping(headroom_percentile=0.0)


def test_mapping_validation_rejects_invalid_gain_map_mode() -> None:
    with pytest.raises(ValueError, match="gain_map_mode"):
        hdr_photo.HDRPhotoMapping(gain_map_mode="invalid")  # type: ignore


def test_mapping_validation_rejects_invalid_max_chroma_gain() -> None:
    with pytest.raises(ValueError, match="profile_hdr_max_chroma_gain"):
        hdr_photo.HDRPhotoMapping(profile_hdr_max_chroma_gain=0.5)


def test_mapping_validation_rejects_invalid_path_to_white_strength() -> None:
    with pytest.raises(ValueError, match="profile_hdr_path_to_white_strength"):
        hdr_photo.HDRPhotoMapping(profile_hdr_path_to_white_strength=-0.1)
    with pytest.raises(ValueError, match="profile_hdr_path_to_white_strength"):
        hdr_photo.HDRPhotoMapping(profile_hdr_path_to_white_strength=1.5)


def test_mapping_validation_rejects_reversed_path_to_white_ev_range() -> None:
    with pytest.raises(ValueError, match="profile_hdr_path_to_white_start_ev"):
        hdr_photo.HDRPhotoMapping(profile_hdr_path_to_white_start_ev=3.0, profile_hdr_path_to_white_end_ev=1.0)


def test_mapping_validation_rejects_negative_recovery_knee_ev() -> None:
    with pytest.raises(ValueError, match="profile_hdr_recovery_knee_ev"):
        hdr_photo.HDRPhotoMapping(profile_hdr_recovery_knee_ev=-0.5, profile_hdr_recovery_full_ev=1.0)


def test_save_hdr_photo_heic_gain_map_mode_dispatch(monkeypatch, tmp_path) -> None:
    image = np.array([[[1.0, 1.0, 1.0], [4.0, 4.0, 4.0]]], dtype=np.float32)
    output_path = tmp_path / "out.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))

    def fake_run(command, *, check, capture_output, text, timeout):
        captured["command"] = command
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    hdr_photo.save_hdr_photo_heic(output_path, image, color_space="Display P3", gain_map_mode="luma")
    assert captured["command"][-1] == "luma"

    hdr_photo.save_hdr_photo_heic(output_path, image, color_space="Display P3", gain_map_mode="rgb")
    assert captured["command"][-1] == "rgb"


# ---------------------------------------------------------------------------
# HDR Diffuse Lift and Delta Merge Tests
# ---------------------------------------------------------------------------


def test_diffuse_lift_precise_anchoring() -> None:
    """Diffuse lift must map scene_y=1.0 to hdr_diffuse_white_target when look_y matches reference."""
    look_rgb = np.full((1, 1, 3), 0.8387, dtype=np.float32)
    scene_luminance = np.array([[1.0]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_diffuse_white_target=1.25,
        look_diffuse_white_reference=0.8387,  # explicitly matching look_rgb
    )
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, scene_luminance=scene_luminance, mapping=mapping)

    # target_y should be exactly 1.25
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [1.25, 1.25, 1.25], atol=1e-5)


def test_diffuse_lift_preserves_mid_gray() -> None:
    """Diffuse lift must not perturb mid-gray where diffuse_w is near 0."""
    look_rgb = np.full((1, 2, 3), 0.4647, dtype=np.float32)
    scene_luminance = np.array([[0.184, 4.0]], dtype=np.float32) # Add a hot pixel to ensure valid HDR export

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_diffuse_white_target=1.5,
        look_diffuse_white_reference=0.8387,
    )
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, scene_luminance=scene_luminance, mapping=mapping)

    # target_y should remain close to look_rgb
    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [0.4647, 0.4647, 0.4647], atol=1e-5)


def test_diffuse_lift_does_not_trigger_specular_graft() -> None:
    """At scene_y=1.0, w_spec should be 0, so target_y comes purely from diffuse lift."""
    look_rgb = np.full((1, 2, 3), 0.8387, dtype=np.float32)
    scene_luminance = np.array([[1.0, 4.0]], dtype=np.float32) # Add a hot pixel

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_diffuse_white_target=1.5,
        look_diffuse_white_reference=0.8387,
        graft_start=1.0, # Log2(1.0) == 0, smoothstep starts here so w_spec == 0
    )
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, scene_luminance=scene_luminance, mapping=mapping)

    np.testing.assert_allclose(renditions.hdr_rgb[0, 0], [1.5, 1.5, 1.5], atol=1e-5)


def test_specular_rolloff_extends_above_diffuse_baseline() -> None:
    """At high highlights, specular rolloff must add delta to the diffuse baseline."""
    look_rgb = np.full((1, 1, 3), 0.9103, dtype=np.float32)
    scene_luminance = np.array([[8.0]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_diffuse_white_target=1.25,
        look_diffuse_white_reference=0.8387,
        max_headroom=8.0,
    )
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, scene_luminance=scene_luminance, mapping=mapping)

    hdr_max = float(renditions.hdr_rgb[0, 0].max())
    # Should extend beyond 1.25 due to specular contribution.
    assert hdr_max > 1.25
    # Should stay within max_headroom
    assert hdr_max <= 8.0


def test_diffuse_lift_fallback_on_low_key_image() -> None:
    """If the image has no scene_y ~ 1.0, look_white estimation falls back safely without blowing up."""
    # A completely dark low-key image
    look_rgb = np.full((10, 10, 3), 0.1, dtype=np.float32)
    scene_luminance = np.full((10, 10), 0.05, dtype=np.float32)

    # Add a single 4.0 pixel so headroom passes
    scene_luminance[0, 0] = 4.0
    look_rgb[0, 0] = [0.8, 0.8, 0.8]

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_diffuse_white_target=1.5,
        # Intentionally no explicit reference, forces fallback logic
    )

    # Run the pipeline
    renditions = hdr_photo.prepare_hdr_photo_renditions(look_rgb, scene_luminance=scene_luminance, mapping=mapping)

    # Since scene_y is tiny, diffuse_w is 0. Target Y must be unchanged.
    np.testing.assert_allclose(renditions.hdr_rgb[0, 1], [0.1, 0.1, 0.1], atol=1e-5)


def _synthetic_safe_hdr_profile() -> FilmPrintHDRCurveProfile:
    scene_y = np.array([0.0625, 0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)
    sdr_y = np.array([0.018, 0.045, 0.090, 0.46, 0.83, 0.89, 0.925, 0.948, 0.958], dtype=np.float32)
    return FilmPrintHDRCurveProfile(
        film="synthetic_safe",
        paper="test_paper",
        polarity="increasing",
        safe_for_profile_aware_hdr=True,
        look_diffuse_white_y=0.83,
        shoulder_limit_y=0.958,
        midtone_slope=0.74,
        highlight_slope=0.012,
        shoulder_severity=0.85,
        highlight_tint_spread=0.0,
        defaults=HDRCurveDefaults(
            look_diffuse_white_reference=0.83,
            hdr_diffuse_lift_strength=1.0,
            hdr_diffuse_lift_start=0.35,
            hdr_diffuse_lift_end=1.0,
            paper_rolloff_k=5.5,
            paper_rolloff_exposure_scale=2.5,
            graft_strength=1.0,
            safe_max_headroom=6.0,
        ),
        scene_y=scene_y,
        sdr_luminance_y=sdr_y,
    )


def test_profile_aware_mapping_reconstructs_paired_sdr_hdr_curve_on_neutral_ramp() -> None:
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)
    look_rgb = np.repeat(s_profile.reshape(1, -1, 1), 3, axis=2).astype(np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_y.reshape(1, -1),
    )

    sdr_y = np.max(renditions.sdr_rgb[0], axis=1)
    hdr_y = np.max(renditions.hdr_rgb[0], axis=1)
    # Use the new profile-preserving curve for reference.
    h_profile = build_profile_preserving_hdr_curve(
        profile, scene_y, diffuse_white=1.0, mapping=mapping,
    )

    np.testing.assert_allclose(sdr_y, s_profile, atol=0.02)
    np.testing.assert_allclose(hdr_y, h_profile, atol=0.06)
    assert renditions.mapping_mode_used == "profile_aware"
    assert np.all(np.diff(h_profile) >= -1e-6)
    # Gain near zero below diffuse white.
    assert np.max(np.abs(h_profile[scene_y <= 0.184] - s_profile[scene_y <= 0.184])) <= 0.03
    # HDR extends highlights above SDR.
    assert np.all(h_profile[scene_y >= 2.0] > s_profile[scene_y >= 2.0])
    assert np.ptp(h_profile[scene_y >= 2.0]) > np.ptp(s_profile[scene_y >= 2.0])
    log_gain = np.log2(np.maximum(hdr_y / np.maximum(sdr_y, 1e-8), 1e-8))
    assert np.isfinite(log_gain).all()
    assert float(np.max(np.abs(np.diff(log_gain)))) <= 0.5


def test_profile_aware_mapping_preserves_user_look() -> None:
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)

    # Simulate a user tweaking the look to be 80% brightness of the default profile.
    # (Using 0.5 would push HDR max below 1.0 with the gentler profile-preserving curve.)
    scale = 0.8
    look_rgb = np.repeat((s_profile * scale).reshape(1, -1, 1), 3, axis=2).astype(np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        profile_hdr_peak_ev=2.5,  # boost to guarantee headroom above 1.0 after scaling
    )
    h_profile = build_profile_preserving_hdr_curve(
        profile, scene_y, diffuse_white=1.0, mapping=mapping,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_y.reshape(1, -1),
    )

    sdr_y = np.max(renditions.sdr_rgb[0], axis=1)
    hdr_y = np.max(renditions.hdr_rgb[0], axis=1)

    # SDR base must exactly match the user's scaled look
    np.testing.assert_allclose(sdr_y, s_profile * scale, atol=1e-5)

    # HDR gain is relative to s_profile. Since look is scaled, hdr_y must be scale * h_profile
    expected_hdr_y = np.clip(h_profile * scale, 0.0, 6.0)
    np.testing.assert_allclose(hdr_y, expected_hdr_y, atol=0.05)


def test_profile_aware_mapping_requires_scene_luminance_to_create_headroom() -> None:
    profile = _synthetic_safe_hdr_profile()
    look_rgb = np.full((1, 3, 3), 0.83, dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
    )

    with pytest.raises(ValueError, match="scene luminance sidecar"):
        hdr_photo.prepare_hdr_photo_renditions(look_rgb, mapping=mapping)


def test_profile_aware_mapping_falls_back_for_unsafe_profile() -> None:
    unsafe_profile = _synthetic_safe_hdr_profile()
    unsafe_profile = FilmPrintHDRCurveProfile(
        film=unsafe_profile.film,
        paper=unsafe_profile.paper,
        polarity="decreasing",
        safe_for_profile_aware_hdr=False,
        look_diffuse_white_y=unsafe_profile.look_diffuse_white_y,
        shoulder_limit_y=unsafe_profile.shoulder_limit_y,
        midtone_slope=unsafe_profile.midtone_slope,
        highlight_slope=unsafe_profile.highlight_slope,
        shoulder_severity=unsafe_profile.shoulder_severity,
        highlight_tint_spread=unsafe_profile.highlight_tint_spread,
        defaults=unsafe_profile.defaults,
        scene_y=unsafe_profile.scene_y,
        sdr_luminance_y=unsafe_profile.sdr_luminance_y,
    )
    look_rgb = np.full((1, 3, 3), 0.8, dtype=np.float32)
    scene_luminance = np.array([[0.8, 2.0, 4.0]], dtype=np.float32)
    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=unsafe_profile,
        max_headroom=6.0,
    )

    with pytest.raises(ValueError, match="safe increasing curve profile"):
        hdr_photo.prepare_hdr_photo_renditions(
            look_rgb,
            mapping=mapping,
            scene_luminance=scene_luminance,
        )


def test_source_chroma_color_recovery() -> None:
    """source_chroma mode should reconstruct high-light colors from scene_rgb, bypassing SDR shoulder desaturation."""
    profile = _synthetic_safe_hdr_profile()

    # Create a highlight pixel that is colored in scene but washed out in SDR
    scene_luminance = np.array([[8.0]], dtype=np.float32)
    # The actual scene_rgb has strong blue tint (B > G > R). We must make sure its luma is exactly 8.0 to pass divergence check.
    # Luma = 0.2126*R + 0.7152*G + 0.0722*B
    # R=4.0, G=4.0 -> 0.9278 * 4.0 = 3.7112
    # B = (8.0 - 3.7112) / 0.0722 = 59.401662
    scene_rgb = np.array([[[4.0, 4.0, 59.401662]]], dtype=np.float32)

    # The SDR look is almost perfectly white due to rolloff compression
    sdr_look_y = evaluate_profile_sdr_curve(profile, scene_luminance) # approx 0.948
    look_rgb = np.array([[[0.94, 0.945, 0.95]]], dtype=np.float32) # slight blue tint left

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
        profile_hdr_max_chroma_gain=50.0,  # disable chroma limit so recovery can express full range
        profile_hdr_path_to_white_strength=0.0,  # disable path-to-white
        profile_hdr_peak_ev=2.5,  # boost peak to ensure hdr_gain triggers blend
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb
    )

    hdr_rgb = renditions.hdr_rgb

    # We expect the blue channel to be significantly higher than the red channel,
    # matching the proportion of scene_rgb rather than look_rgb
    b_to_r_ratio = float(hdr_rgb[0, 0, 2] / max(float(hdr_rgb[0, 0, 0]), 1e-8))

    assert b_to_r_ratio > 3.0, f"Expected strong blue recovery, got ratio {b_to_r_ratio}"

    # Verify luminance is in the right ballpark
    h_profile_target = build_profile_preserving_hdr_curve(profile, scene_luminance, diffuse_white=1.0, mapping=mapping)
    hdr_luma = hdr_photo.luminance_y(hdr_rgb)
    np.testing.assert_allclose(hdr_luma, h_profile_target, rtol=0.15)


def test_bounded_look_chroma_color_recovery() -> None:
    """bounded_look_chroma should expand saturation safely, governed by masks."""
    profile = _synthetic_safe_hdr_profile()
    scene_luminance = np.array([[8.0]], dtype=np.float32)

    # Needs enough saturation to pass neutral guard (sat > 0.05)
    # 0.95 - 0.8 = 0.15, sat = 0.15/0.95 = 0.157
    look_rgb = np.array([[[0.8, 0.9, 0.95]]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="bounded_look_chroma",
        hdr_highlight_saturation_boost=1.5,  # Force a boost
        profile_hdr_path_to_white_strength=0.0,  # Disable path to white
        hdr_highlight_path_to_white=0.0,
        profile_hdr_max_chroma_gain=50.0,  # Disable chroma limit
    )

    # Base case (off)
    mapping_off = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="off",
        profile_hdr_path_to_white_strength=0.0,
        hdr_highlight_path_to_white=0.0,
        profile_hdr_max_chroma_gain=50.0,
    )

    renditions_boosted = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping, scene_luminance=scene_luminance
    )

    renditions_off = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_off, scene_luminance=scene_luminance
    )

    hdr_rgb_boosted = renditions_boosted.hdr_rgb
    hdr_rgb_off = renditions_off.hdr_rgb

    boosted_ratio = float(hdr_rgb_boosted[0, 0, 2] / hdr_rgb_boosted[0, 0, 0])
    off_ratio = float(hdr_rgb_off[0, 0, 2] / hdr_rgb_off[0, 0, 0])

    assert boosted_ratio > off_ratio, f"Bounded look chroma should have expanded the saturation. got {boosted_ratio} vs {off_ratio}"


def test_gamut_compression_prevents_clipping() -> None:
    """Gamut compression should reduce chroma instead of hard clipping when channels exceed headroom."""
    profile = _synthetic_safe_hdr_profile()
    scene_luminance = np.array([[8.0]], dtype=np.float32)

    # Provide an extreme scene_rgb that would blow past max_headroom
    scene_rgb = np.array([[[0.0, 0.0, 100.0]]], dtype=np.float32)
    look_rgb = np.array([[[0.94, 0.945, 0.95]]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma"
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb,
        mapping=mapping,
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb
    )

    hdr_rgb = renditions.hdr_rgb
    # The max channel should be capped to max_headroom
    assert float(np.max(hdr_rgb)) <= 6.0001
    # Gamut compression shrinks towards luma, so the color isn't a hard clip


# ---------------------------------------------------------------------------
# Acceptance criteria tests (7 items from implementation plan)
# ---------------------------------------------------------------------------


def test_mode_off_is_identical_to_plain_gain() -> None:
    """验收 #2: mode='off' 输出必须与 look * hdr_gain 完全一致。"""
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)
    # Saturated ramp (red tint)
    look_rgb = np.stack([s_profile * 1.0, s_profile * 0.6, s_profile * 0.3], axis=-1).reshape(1, -1, 3).astype(np.float32)
    scene_luminance = scene_y.reshape(1, -1)

    mapping_off = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="off",
    )

    # Use default source_chroma mode but without scene_rgb → should also degrade to off
    mapping_source_no_rgb = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
    )

    renditions_off = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_off, scene_luminance=scene_luminance
    )
    renditions_degraded = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_source_no_rgb, scene_luminance=scene_luminance
    )

    # source_chroma with no scene_rgb must degrade to off behavior
    np.testing.assert_allclose(renditions_off.hdr_rgb, renditions_degraded.hdr_rgb, atol=1e-6)
    np.testing.assert_allclose(renditions_off.sdr_rgb, renditions_degraded.sdr_rgb, atol=1e-6)
    assert "degrading to off" in " ".join(renditions_degraded.diagnostics)


def test_neutral_ramp_stays_neutral_under_source_chroma() -> None:
    """验收 #3: 纯灰度斜坡在 source_chroma 下不会被染上彩色。"""
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)

    # Neutral look: R=G=B
    look_rgb = np.repeat(s_profile.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    # Neutral scene_rgb: R=G=B = scene_y
    scene_rgb = np.repeat(scene_y.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping,
        scene_luminance=scene_y.reshape(1, -1),
        scene_rgb=scene_rgb
    )

    hdr_rgb = renditions.hdr_rgb
    # For each pixel, R≈G≈B (neutral), check max spread / max_channel
    for i in range(hdr_rgb.shape[1]):
        pixel = hdr_rgb[0, i]
        spread = float(np.max(pixel) - np.min(pixel))
        # Allow very small numerical noise
        assert spread < 0.02, f"Pixel {i} is not neutral: {pixel}, spread={spread}"


def test_hue_preservation_through_source_chroma_recovery() -> None:
    """验收 #4: 有色高光在恢复过程中保持色相。"""
    profile = _synthetic_safe_hdr_profile()

    # Scene: red-ish highlight at 4x diffuse
    scene_luminance = np.array([[4.0]], dtype=np.float32)
    # Red dominant scene: R >> G >> B, luma=4.0
    # Y = 0.2126*R + 0.7152*G + 0.0722*B
    # R=10, G=3.0 → 0.2126*10 + 0.7152*3 = 2.126 + 2.1456 = 4.2716
    # Need B = (4.0 - 4.2716) / 0.0722 → negative, adjust
    # R=8, G=3.5 → 0.2126*8 + 0.7152*3.5 = 1.7008 + 2.5032 = 4.204
    # B = (4.0 - 4.204) / 0.0722 → negative, adjust more
    # R=6, G=4.0 → 0.2126*6 + 0.7152*4 = 1.2756 + 2.8608 = 4.1364
    # B = (4.0 - 4.1364) / 0.0722 → negative
    # Let's just use R=8, G=2.0, B=(4.0 - 0.2126*8 - 0.7152*2) / 0.0722
    # = (4.0 - 1.7008 - 1.4304) / 0.0722 = 0.8688 / 0.0722 = 12.034
    # That gives a purple tint, not red. Let's do a simpler approach.
    # Use scene_y directly and chroma ratios: R=2*Y, G=0.7*Y, B=0.3*Y won't have Y=scene_y
    # Instead: scene_rgb = [R, G, B] s.t. Y(scene_rgb)=scene_y
    # For red: R=large, G=small, B=small. Y = 0.2126*R + 0.7152*G + 0.0722*B = 4.0
    # R=16, G=0.5, B=0.5 → Y = 0.2126*16 + 0.7152*0.5 + 0.0722*0.5 = 3.4016 + 0.3576 + 0.0361 = 3.7953
    # Close enough? No, within 5% of 4.0 → 3.8 < 4.0*0.95=3.8 → borderline fail
    # R=16.5, G=0.5, B=0.5 → Y = 0.2126*16.5 + 0.3576 + 0.0361 = 3.5079 + 0.3937 = 3.9016 → 2.5% off → OK
    # Actually let me be precise:
    # R=a, G=0.5, B=0.5 → Y = 0.2126*a + 0.7152*0.5 + 0.0722*0.5 = 0.2126a + 0.3937
    # Y=4.0 → a = (4.0 - 0.3937) / 0.2126 = 3.6063/0.2126 = 16.966
    scene_rgb = np.array([[[16.966, 0.5, 0.5]]], dtype=np.float32)

    # SDR look: red-ish but desaturated by shoulder
    look_rgb = np.array([[[0.93, 0.91, 0.91]]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping,
        scene_luminance=scene_luminance,
        scene_rgb=scene_rgb
    )

    hdr = renditions.hdr_rgb[0, 0]
    # Hue check: R should be dominant (matching scene_rgb), G and B close to each other
    assert float(hdr[0]) > float(hdr[1]), f"Red should dominate: {hdr}"
    assert float(hdr[0]) > float(hdr[2]), f"Red should dominate: {hdr}"
    # G and B should be similar (both small in scene)
    gb_ratio = float(hdr[1]) / max(float(hdr[2]), 1e-8)
    assert 0.5 < gb_ratio < 2.0, f"G/B ratio should be near 1.0 (same in scene), got {gb_ratio}"


def test_path_to_white_approaches_neutral_at_peak() -> None:
    """验收 #5: 接近 peak headroom 的像素应自然退白。

    Tests _apply_hdr_color_recovery directly. Uses a near-neutral scene_rgb
    that produces hdr_rgb within gamut so gamut compression doesn't override pw.
    """
    max_headroom = 6.0
    # h_profile = 5.5 → inside pw transition zone
    h_profile = np.array([[5.5]], dtype=np.float32)
    s_profile = np.array([[0.95]], dtype=np.float32)
    hdr_gain = h_profile / s_profile
    scene_y = np.array([[10.0]], dtype=np.float32)

    scene_rgb = np.array([[[10.5, 9.8, 9.8]]], dtype=np.float32)
    look_rgb = np.array([[[0.96, 0.93, 0.93]]], dtype=np.float32)

    # look_white ≈ 0.95, so h_ev = log2(5.5 / 0.95) ≈ 2.53
    look_white = 0.95

    mapping_pw_on = hdr_photo.HDRPhotoMapping(
        max_headroom=max_headroom,
        hdr_highlight_color_mode="source_chroma",
        profile_hdr_path_to_white_strength=1.0,
        profile_hdr_max_chroma_gain=50.0,  # disable chroma limit for this test
    )
    mapping_pw_off = hdr_photo.HDRPhotoMapping(
        max_headroom=max_headroom,
        hdr_highlight_color_mode="source_chroma",
        profile_hdr_path_to_white_strength=0.0,
        hdr_highlight_path_to_white=0.0,
        profile_hdr_max_chroma_gain=50.0,
    )

    diag_on: list[str] = []
    diag_off: list[str] = []
    hdr_on = hdr_photo._apply_hdr_color_recovery(
        look=look_rgb, h_profile=h_profile, s_profile=s_profile,
        hdr_gain=hdr_gain, scene_y=scene_y, scene_rgb=scene_rgb,
        mapping=mapping_pw_on, diagnostics=diag_on,
        max_headroom=max_headroom, look_white=look_white,
    )
    hdr_off = hdr_photo._apply_hdr_color_recovery(
        look=look_rgb, h_profile=h_profile, s_profile=s_profile,
        hdr_gain=hdr_gain, scene_y=scene_y, scene_rgb=scene_rgb,
        mapping=mapping_pw_off, diagnostics=diag_off,
        max_headroom=max_headroom, look_white=look_white,
    )

    sat_on = float(np.max(hdr_on[0, 0]) - np.min(hdr_on[0, 0])) / max(float(np.max(hdr_on[0, 0])), 1e-8)
    sat_off = float(np.max(hdr_off[0, 0]) - np.min(hdr_off[0, 0])) / max(float(np.max(hdr_off[0, 0])), 1e-8)

    assert sat_on < sat_off, f"Path-to-white should reduce saturation at peak: sat_on={sat_on}, sat_off={sat_off}"


def test_luminance_follows_profile_before_constraints() -> None:
    """验收 #6: mode=off 的 luminance 严格遵循 h_profile。"""
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)

    # Neutral ramp → luminance should match h_profile exactly
    look_rgb = np.repeat(s_profile.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="off",
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping,
        scene_luminance=scene_y.reshape(1, -1),
    )

    h_profile = build_profile_preserving_hdr_curve(profile, scene_y, diffuse_white=1.0, mapping=mapping)
    hdr_y = hdr_photo.luminance_y(renditions.hdr_rgb)
    # For neutral ramp with mode=off: hdr_y = look_y * hdr_gain = s_profile * (h_profile / s_profile) = h_profile
    np.testing.assert_allclose(hdr_y[0], h_profile, atol=0.06)


def test_source_chroma_per_pixel_divergence_fallback() -> None:
    """Guardrail #3: 逐像素 divergence — 有效像素做 recovery，偏差像素做 gain-only。"""
    profile = _synthetic_safe_hdr_profile()

    # Two pixels: first has consistent scene_rgb, second has divergent scene_rgb
    scene_luminance = np.array([[4.0, 4.0]], dtype=np.float32)

    # Pixel 0: consistent (luma matches scene_y within 5%)
    # Y = 0.2126*R + 0.7152*G + 0.0722*B = 4.0
    # R=16.966, G=0.5, B=0.5 → Y≈4.0
    # Pixel 1: divergent (luma = 1.0 ≠ 4.0)
    scene_rgb = np.array([[[16.966, 0.5, 0.5], [1.0, 1.0, 1.0]]], dtype=np.float32)

    s_profile = evaluate_profile_sdr_curve(profile, scene_luminance)
    look_rgb = np.array([[[0.93, 0.91, 0.91], [0.93, 0.93, 0.93]]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
        hdr_highlight_path_to_white=0.0,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping,
        scene_luminance=scene_luminance, scene_rgb=scene_rgb
    )

    # Should have per-pixel divergence diagnostic
    assert any("diverged" in d for d in renditions.diagnostics), f"Expected divergence diagnostic, got: {renditions.diagnostics}"

    # Pixel 0 should have color recovery (R > G because red scene)
    hdr_px0 = renditions.hdr_rgb[0, 0]
    assert float(hdr_px0[0]) > float(hdr_px0[1]), f"Pixel 0 should have red recovery: {hdr_px0}"

    # Pixel 1 should be gain-only (R≈G≈B since look was neutral)
    hdr_px1 = renditions.hdr_rgb[0, 1]
    spread = float(np.max(hdr_px1) - np.min(hdr_px1))
    assert spread < 0.01, f"Pixel 1 should be neutral (gain-only): {hdr_px1}, spread={spread}"


def test_source_chroma_does_not_silently_switch_to_bounded() -> None:
    """Guardrail #4: source_chroma 在无 scene_rgb 时降级到 off，不会偷偷切换到 bounded_look_chroma。"""
    profile = _synthetic_safe_hdr_profile()
    scene_luminance = np.array([[4.0]], dtype=np.float32)
    look_rgb = np.array([[[0.8, 0.9, 0.95]]], dtype=np.float32)

    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
        hdr_highlight_saturation_boost=2.0,  # Would boost if it switched to bounded
    )

    # No scene_rgb provided
    renditions_degraded = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping, scene_luminance=scene_luminance
    )

    # Compare with explicit off
    mapping_off = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="off",
    )
    renditions_off = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_off, scene_luminance=scene_luminance
    )
    # Should be identical to "off", not "bounded_look_chroma"
    np.testing.assert_allclose(renditions_degraded.hdr_rgb, renditions_off.hdr_rgb, atol=1e-6)
    assert any("degrading to off" in d for d in renditions_degraded.diagnostics)


# ---------------------------------------------------------------------------
# Profile-preserving integration tests
# ---------------------------------------------------------------------------


def test_sdr_zero_regression_with_hdr_enabled() -> None:
    """SDR base must be identical regardless of HDR curve mode."""
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)
    look_rgb = np.repeat(s_profile.reshape(1, -1, 1), 3, axis=2).astype(np.float32)
    scene_luminance = scene_y.reshape(1, -1)

    mapping_new = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        profile_curve_mode="profile_preserving",
    )
    mapping_legacy = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        profile_curve_mode="legacy_graft",
    )

    rend_new = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_new, scene_luminance=scene_luminance,
    )
    rend_legacy = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping_legacy, scene_luminance=scene_luminance,
    )

    # SDR base must be identical in both modes — no regression.
    np.testing.assert_allclose(rend_new.sdr_rgb, rend_legacy.sdr_rgb, atol=1e-6)
    # SDR must match the original look (clipped to [0,1]).
    expected_sdr = np.clip(look_rgb, 0.0, 1.0)
    np.testing.assert_allclose(rend_new.sdr_rgb, expected_sdr, atol=1e-6)


def test_print_exposure_changes_hdr_through_profile() -> None:
    """Changing the S_profile (simulating print exposure) must change the HDR output."""
    scene_y = np.array([0.0625, 0.125, 0.184, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0], dtype=np.float32)

    # Profile A: normal print exposure.
    sdr_a = np.array([0.018, 0.045, 0.090, 0.46, 0.83, 0.89, 0.925, 0.948, 0.958], dtype=np.float32)
    # Profile B: darker print exposure (all SDR values lower).
    sdr_b = sdr_a * 0.8

    from types import SimpleNamespace
    profile_a = _make_test_profile(scene_y, sdr_a)
    profile_b = _make_test_profile(scene_y, sdr_b)

    mapping_a = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile_a,
        max_headroom=6.0,
        headroom_percentile=100.0,
    )
    mapping_b = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile_b,
        max_headroom=6.0,
        headroom_percentile=100.0,
    )

    s_a = evaluate_profile_sdr_curve(profile_a, scene_y)
    s_b = evaluate_profile_sdr_curve(profile_b, scene_y)
    look_a = np.repeat(s_a.reshape(1, -1, 1), 3, axis=2).astype(np.float32)
    look_b = np.repeat(s_b.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    rend_a = hdr_photo.prepare_hdr_photo_renditions(
        look_a, mapping=mapping_a, scene_luminance=scene_y.reshape(1, -1),
    )
    rend_b = hdr_photo.prepare_hdr_photo_renditions(
        look_b, mapping=mapping_b, scene_luminance=scene_y.reshape(1, -1),
    )

    # HDR outputs must differ because profiles differ.
    assert not np.allclose(rend_a.hdr_rgb, rend_b.hdr_rgb, atol=0.01), \
        "HDR output should change when S_profile changes"
    # SDR outputs must also differ (darker print = darker SDR).
    assert not np.allclose(rend_a.sdr_rgb, rend_b.sdr_rgb, atol=0.01), \
        "SDR output should change when S_profile changes"


def _make_test_profile(
    scene_y: np.ndarray,
    sdr_y: np.ndarray,
) -> FilmPrintHDRCurveProfile:
    """Helper for test_print_exposure_changes_hdr_through_profile."""
    return FilmPrintHDRCurveProfile(
        film="test",
        paper="test",
        polarity="increasing",
        safe_for_profile_aware_hdr=True,
        look_diffuse_white_y=float(np.interp(1.0, scene_y, sdr_y)),
        shoulder_limit_y=float(np.max(sdr_y)),
        midtone_slope=0.7,
        highlight_slope=0.02,
        shoulder_severity=0.85,
        highlight_tint_spread=0.0,
        defaults=HDRCurveDefaults(
            look_diffuse_white_reference=float(np.interp(1.0, scene_y, sdr_y)),
            hdr_diffuse_lift_strength=1.0,
            hdr_diffuse_lift_start=0.35,
            hdr_diffuse_lift_end=1.0,
            paper_rolloff_k=5.5,
            paper_rolloff_exposure_scale=2.5,
            graft_strength=1.0,
            safe_max_headroom=6.0,
        ),
        scene_y=scene_y,
        sdr_luminance_y=sdr_y,
    )


def test_path_to_white_ev_relative_to_look_white() -> None:
    """Path-to-white must use EV distance from look_white, not absolute headroom."""
    profile = _synthetic_safe_hdr_profile()
    scene_y = profile.scene_y
    s_profile = evaluate_profile_sdr_curve(profile, scene_y)
    look_rgb = np.repeat(s_profile.reshape(1, -1, 1), 3, axis=2).astype(np.float32)

    # Slight warm tint in scene_rgb so path-to-white has something to desaturate.
    scene_rgb = np.repeat(scene_y.reshape(1, -1, 1), 3, axis=2).astype(np.float32)
    scene_rgb[..., 0] *= 1.1
    scene_rgb[..., 2] *= 0.9

    # Strong path-to-white.
    mapping = hdr_photo.HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        max_headroom=6.0,
        headroom_percentile=100.0,
        hdr_highlight_color_mode="source_chroma",
        profile_hdr_path_to_white_strength=1.0,
        profile_hdr_path_to_white_start_ev=0.5,
        profile_hdr_path_to_white_end_ev=1.5,
    )

    renditions = hdr_photo.prepare_hdr_photo_renditions(
        look_rgb, mapping=mapping,
        scene_luminance=scene_y.reshape(1, -1),
        scene_rgb=scene_rgb,
    )

    hdr_rgb = renditions.hdr_rgb
    # At the highest scene_y, the pixel should be nearly neutral (path-to-white effect).
    peak_pixel = hdr_rgb[0, -1]
    if float(np.max(peak_pixel)) > 0.01:
        spread = float(np.max(peak_pixel) - np.min(peak_pixel))
        relative_spread = spread / float(np.max(peak_pixel))
        assert relative_spread < 0.15, (
            f"Peak pixel should be near-neutral with strong path-to-white, "
            f"but relative spread = {relative_spread:.3f}, pixel = {peak_pixel}"
        )


def test_gain_map_max_matches_actual_h_over_s() -> None:
    from spektrafilm.utils.hdr_photo import prepare_hdr_photo_renditions, HDRPhotoMapping
    from spektrafilm.utils.hdr_curve_profiles import FilmPrintHDRCurveProfile, HDRCurveDefaults
    import numpy as np

    scene_y = np.array([0.5, 1.0, 4.0, 16.0], dtype=np.float32)
    sdr_y = np.array([0.45, 0.83, 0.94, 0.98], dtype=np.float32)

    profile = FilmPrintHDRCurveProfile(
        film="test", paper="test", polarity="increasing", safe_for_profile_aware_hdr=True,
        look_diffuse_white_y=0.83, shoulder_limit_y=0.98,
        midtone_slope=0.7, highlight_slope=0.02, shoulder_severity=0.85, highlight_tint_spread=0.0,
        defaults=HDRCurveDefaults(
            look_diffuse_white_reference=0.83,
            hdr_diffuse_lift_strength=1.0,
            hdr_diffuse_lift_start=0.35,
            hdr_diffuse_lift_end=1.0,
            paper_rolloff_k=5.5,
            paper_rolloff_exposure_scale=2.5,
            graft_strength=1.0,
            safe_max_headroom=6.0,
        ), scene_y=scene_y, sdr_luminance_y=sdr_y
    )

    mapping = HDRPhotoMapping(
        hdr_mapping_mode="profile_aware",
        curve_profile=profile,
        hdr_render_ev=0.0,
        headroom_percentile=100.0,
        profile_hdr_mode="modern_recovery_peak_budget",
        profile_hdr_target_peak_ev=2.03,
        profile_hdr_normalize_percentile=99.9,
    )

    shape = (4, 4, 3)
    look_rgb = np.full(shape, 0.5, dtype=np.float32)
    scene_lum = np.full(shape[:2], 1.0, dtype=np.float32)

    scene_lum[0, 0] = 16.0
    look_rgb[0, 0] = 0.98

    renditions = prepare_hdr_photo_renditions(
        look_rgb,
        scene_luminance=scene_lum,
        mapping=mapping,
    )

    final_luma = np.max(renditions.hdr_rgb, axis=2)
    actual_gain_linear = final_luma / np.maximum(np.max(look_rgb, axis=2), 1e-8)
    expected_headroom = float(np.max(actual_gain_linear))

    import pytest
    assert renditions.headroom == pytest.approx(expected_headroom, rel=1e-3)


# ---------------------------------------------------------------------------
# Extended HDRPhotoMapping __post_init__ validation tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, match",
    [
        ({"diffuse_white": 0.0}, "diffuse_white"),
        ({"diffuse_white": -1.0}, "diffuse_white"),
        ({"sdr_paper_white": 0.0}, "sdr_paper_white"),
        ({"sdr_paper_white": 1.0}, "sdr_paper_white"),
        ({"max_headroom": 1.0}, "max_headroom"),
        ({"max_headroom": -1.0}, "max_headroom"),
        ({"shoulder_strength": 0.0}, "shoulder_strength"),
        ({"shoulder_strength": -1.0}, "shoulder_strength"),
        ({"paper_rolloff_start": 0.0}, "paper_rolloff_start"),
        ({"paper_rolloff_k": -1.0}, "paper_rolloff_k"),
        ({"paper_rolloff_exposure_scale": 0.0}, "paper_rolloff_exposure_scale"),
        ({"paper_rolloff_strength": -1.0}, "paper_rolloff_strength"),
        ({"graft_strength": -0.1}, "graft_strength"),
        ({"graft_strength": 1.5}, "graft_strength"),
        ({"hdr_diffuse_white_target": 0.0}, "hdr_diffuse_white_target"),
        ({"hdr_diffuse_lift_start": 1.0, "hdr_diffuse_lift_end": 0.5}, "hdr_diffuse_lift_start"),
        ({"hdr_diffuse_lift_strength": -0.1}, "hdr_diffuse_lift_strength"),
        ({"hdr_diffuse_lift_strength": 1.5}, "hdr_diffuse_lift_strength"),
        ({"look_diffuse_white_reference": 0.0}, "look_diffuse_white_reference"),
        ({"look_diffuse_white_reference": -1.0}, "look_diffuse_white_reference"),
        ({"hdr_highlight_color_mode": "invalid"}, "hdr_highlight_color_mode"),
        ({"hdr_highlight_gamut": "invalid"}, "hdr_highlight_gamut"),
        ({"hdr_highlight_saturation_boost": -1.0}, "hdr_highlight_saturation_boost"),
        ({"hdr_highlight_chroma_limit": -1.0}, "hdr_highlight_chroma_limit"),
        ({"hdr_highlight_path_to_white": -1.0}, "hdr_highlight_path_to_white"),
        ({"profile_curve_mode": "invalid"}, "profile_curve_mode"),
        ({"profile_hdr_peak_ev": 0.0}, "profile_hdr_peak_ev"),
        ({"profile_hdr_strength": -0.1}, "profile_hdr_strength"),
        ({"profile_hdr_strength": 1.5}, "profile_hdr_strength"),
        ({"profile_hdr_softness_ev": 0.0}, "profile_hdr_softness_ev"),
        ({"diffuse_white_override": 0.0}, "diffuse_white_override"),
        ({"diffuse_white_override": -1.0}, "diffuse_white_override"),
        ({"profile_hdr_mode": "invalid"}, "profile_hdr_mode"),
        ({"profile_hdr_target_peak_ev": 0.0}, "profile_hdr_target_peak_ev"),
        ({"profile_hdr_normalize_percentile": 0.0}, "profile_hdr_normalize_percentile"),
        ({"profile_hdr_normalize_percentile": 101.0}, "profile_hdr_normalize_percentile"),
        ({"profile_hdr_recovery_ratio": -0.1}, "profile_hdr_recovery_ratio"),
        ({"hdr_mapping_mode": "invalid"}, "hdr_mapping_mode"),
    ],
)
def test_mapping_validation_rejects_invalid_values(kwargs: dict, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        hdr_photo.HDRPhotoMapping(**kwargs)
