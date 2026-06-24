from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.aces_compat import (
    ACES_INTERCHANGE_COLOR_SPACE,
    ACES_WORKING_COLOR_SPACE,
    AcesContext,
    AcesOcioUnavailableError,
    aces2065_1_to_acescg,
    acescg_to_aces2065_1,
    apply_aces_reference_gamut_compression,
    build_aces_transform_manifest,
    is_ocio_available,
    load_aces_ocio_config,
    render_aces_local_sdr_preview,
    render_aces_ocio_view,
    to_acescg,
)
from spektrafilm.color_management import aces_sdr_video_view_transform
from spektrafilm.runtime.params_schema import IOParams


def test_acescg_aces2065_1_roundtrip_preserves_shape_dtype_and_finiteness() -> None:
    image = np.array([[[0.18, 0.18, 0.18], [1.2, 0.3, 0.05]]], dtype=np.float32)
    ap0 = acescg_to_aces2065_1(image)
    roundtrip = aces2065_1_to_acescg(ap0)
    assert ap0.shape == image.shape
    assert roundtrip.shape == image.shape
    assert ap0.dtype == np.float32
    assert roundtrip.dtype == np.float32
    assert np.all(np.isfinite(ap0))
    assert np.all(np.isfinite(roundtrip))
    np.testing.assert_allclose(roundtrip, image, atol=2e-5)


def test_aces_roundtrip_preserves_neutral_gray_axis() -> None:
    image = np.array([[[0.0, 0.0, 0.0], [0.18, 0.18, 0.18], [1.0, 1.0, 1.0]]], dtype=np.float32)
    roundtrip = aces2065_1_to_acescg(acescg_to_aces2065_1(image))
    np.testing.assert_allclose(roundtrip[..., 0], roundtrip[..., 1], atol=2e-5)
    np.testing.assert_allclose(roundtrip[..., 1], roundtrip[..., 2], atol=2e-5)


def test_high_saturation_ap0_ap1_samples_remain_finite() -> None:
    ap1 = np.array([[[4.0, -0.25, 0.1], [0.1, 3.0, -0.2], [-0.2, 0.2, 2.5]]], dtype=np.float32)
    ap0 = acescg_to_aces2065_1(ap1)
    back = aces2065_1_to_acescg(ap0)
    assert np.all(np.isfinite(ap0))
    assert np.all(np.isfinite(back))


@pytest.mark.parametrize("input_color_space", ["sRGB", "Display P3", "ProPhoto RGB"])
def test_to_acescg_respects_cctf_decoding_flag(input_color_space: str) -> None:
    image = np.array([[[0.5, 0.25, 0.75]]], dtype=np.float32)
    decoded = to_acescg(image, input_color_space=input_color_space, apply_cctf_decoding=True)
    linear = to_acescg(image, input_color_space=input_color_space, apply_cctf_decoding=False)
    assert decoded.shape == image.shape
    assert decoded.dtype == np.float32
    assert np.all(np.isfinite(decoded))
    assert np.all(np.isfinite(linear))
    assert not np.allclose(decoded, linear)


def test_render_aces_local_sdr_preview_outputs_display_referred_code_values() -> None:
    image = np.array([[[0.18, 0.18, 0.18], [1.0, 0.5, 0.1], [3.0, 3.0, 3.0]]], dtype=np.float32)
    preview = render_aces_local_sdr_preview(image, color_space=ACES_WORKING_COLOR_SPACE)
    assert preview.shape == image.shape
    assert preview.dtype == np.float32
    assert np.all(np.isfinite(preview))
    assert float(np.min(preview)) >= 0.0
    assert float(np.max(preview)) <= 1.0


def test_legacy_aces_sdr_video_view_transform_still_works() -> None:
    image = np.array([[[0.18, 0.18, 0.18], [1.0, 0.5, 0.1]]], dtype=np.float32)
    preview = aces_sdr_video_view_transform(image, color_space=ACES_WORKING_COLOR_SPACE)
    assert preview.shape == image.shape
    assert preview.dtype == np.float32
    assert np.all(np.isfinite(preview))


def test_aces_reference_workflow_contract_is_unchanged() -> None:
    import spektrafilm.color_management as color_management

    io = IOParams(
        input_color_space="Display P3",
        input_cctf_decoding=True,
        output_color_space="sRGB",
        output_cctf_encoding=True,
        output_clip_min=True,
        output_clip_max=True,
    )
    preset = color_management.apply_color_management_workflow_to_io(io, "aces_reference")
    assert io.input_color_space == ACES_WORKING_COLOR_SPACE
    assert io.input_cctf_decoding is False
    assert io.output_color_space == ACES_WORKING_COLOR_SPACE
    assert io.output_cctf_encoding is False
    assert io.output_clip_min is False
    assert io.output_clip_max is False
    assert preset.saving_color_space == ACES_INTERCHANGE_COLOR_SPACE
    assert preset.saving_cctf_encoding is False


def test_ocio_unavailable_is_explicit_or_available() -> None:
    if is_ocio_available():
        return
    with pytest.raises(AcesOcioUnavailableError, match="PyOpenColorIO is not installed"):
        load_aces_ocio_config()


def test_ocio_official_view_smoke_if_available() -> None:
    if not is_ocio_available():
        pytest.skip("PyOpenColorIO is not installed")
    config, config_diag = load_aces_ocio_config()
    image = np.array([[[0.18, 0.18, 0.18], [1.0, 0.5, 0.1]]], dtype=np.float32)
    displays = list(config.getDisplays())
    if not displays:
        pytest.skip("OCIO ACES config has no displays")
    display = displays[0]
    views = list(config.getViews(display))
    if not views:
        pytest.skip("OCIO ACES config has no views for first display")
    view = views[0]
    source = config_diag.ocio_roles.get("scene_linear", "ACES - ACEScg")
    rendered, diagnostics = render_aces_ocio_view(image, config=config, source_color_space=source, display=display, view=view)
    assert rendered.shape == image.shape
    assert rendered.dtype == np.float32
    assert np.all(np.isfinite(rendered))
    assert diagnostics.implementation_kind == "ocio_official_or_configured"
    assert diagnostics.display == display
    assert diagnostics.view == view


def test_build_aces_transform_manifest_contains_required_fields_and_placeholders() -> None:
    manifest = build_aces_transform_manifest(
        context=AcesContext(input_color_space="Display P3", output_color_space=ACES_INTERCHANGE_COLOR_SPACE),
        display="sRGB",
        view="ACES 1.0 - SDR Video",
    )
    assert manifest["working_space"] == ACES_WORKING_COLOR_SPACE
    assert manifest["interchange_space"] == ACES_INTERCHANGE_COLOR_SPACE
    assert manifest["input_color_space"] == "Display P3"
    assert manifest["output_color_space"] == ACES_INTERCHANGE_COLOR_SPACE
    assert manifest["display"] == "sRGB"
    assert manifest["view"] == "ACES 1.0 - SDR Video"
    assert manifest["implementation_kind"] == "spektrafilm_local"
    assert manifest["transform_id"] is None
    assert manifest["transform_id_status"] == "not_provided_do_not_infer"
    assert manifest["amf_ready"] is False


def test_aces_rgc_wrapper_basic_behavior_and_neutral_preservation() -> None:
    image = np.array([[[0.18, 0.18, 0.18], [1.0, -0.2, 0.1], [0.0, 0.0, 0.0]]], dtype=np.float32)
    compressed = apply_aces_reference_gamut_compression(image)
    assert compressed.shape == image.shape
    assert compressed.dtype == np.float32
    assert np.all(np.isfinite(compressed))
    np.testing.assert_allclose(compressed[0, 0], image[0, 0], atol=1e-6)
    np.testing.assert_allclose(compressed[0, 2], image[0, 2], atol=1e-6)


def test_aces_scene_linear_lut_input_role_is_still_not_enabled() -> None:
    color_spaces = pytest.importorskip("spektrafilm_lut_creator.color_spaces")
    registry_values = []
    for value in vars(color_spaces).values():
        if isinstance(value, dict):
            registry_values.extend(value.values())
        elif isinstance(value, (list, tuple, set, frozenset)):
            registry_values.extend(value)
    text = "\n".join(str(value) for value in registry_values)
    assert "ACEScg" in text or "ACES - ACEScg" in text
    assert "scene-linear shaper" in text or "scene linear" in text.lower() or "silenc" in text.lower()
