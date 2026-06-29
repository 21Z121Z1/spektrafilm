from __future__ import annotations

import builtins

import numpy as np
import pytest

from spektrafilm.aces_compat import (
    ACES_INTERCHANGE_COLOR_SPACE,
    ACES_WORKING_COLOR_SPACE,
    AcesContext,
    OcioUnavailableError,
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
import spektrafilm.color_management as color_management_module


def _sample_rgb() -> np.ndarray:
    return np.array(
        [
            [[0.18, 0.18, 0.18], [1.0, 0.2, 0.05]],
            [[4.0, -0.2, 0.5], [0.0, 1.5, 8.0]],
        ],
        dtype=np.float32,
    )


def test_acescg_aces2065_roundtrip_preserves_shape_dtype_and_finite_values() -> None:
    acescg = _sample_rgb()
    ap0 = acescg_to_aces2065_1(acescg)
    roundtrip = aces2065_1_to_acescg(ap0)

    assert ap0.shape == acescg.shape
    assert roundtrip.shape == acescg.shape
    assert ap0.dtype == np.float32
    assert roundtrip.dtype == np.float32
    assert np.all(np.isfinite(ap0))
    assert np.all(np.isfinite(roundtrip))
    np.testing.assert_allclose(roundtrip, acescg, atol=2e-6, rtol=2e-6)


def test_neutral_gray_axis_roundtrip_stays_neutral() -> None:
    gray = np.linspace(0.0, 16.0, 17, dtype=np.float32)
    acescg = np.stack([gray, gray, gray], axis=-1)
    ap0 = acescg_to_aces2065_1(acescg)
    roundtrip = aces2065_1_to_acescg(ap0)

    np.testing.assert_allclose(ap0[..., 0], ap0[..., 1], atol=1e-6)
    np.testing.assert_allclose(ap0[..., 1], ap0[..., 2], atol=1e-6)
    np.testing.assert_allclose(roundtrip, acescg, atol=2e-6, rtol=2e-6)


@pytest.mark.parametrize("space", [ACES_WORKING_COLOR_SPACE, ACES_INTERCHANGE_COLOR_SPACE])
def test_high_saturation_aces_samples_remain_finite(space: str) -> None:
    samples = np.array(
        [
            [10.0, -2.0, 0.1],
            [-0.5, 5.0, 0.0],
            [0.0, -1.0, 7.0],
            [100.0, 0.001, -4.0],
        ],
        dtype=np.float32,
    )
    out = acescg_to_aces2065_1(samples) if space == ACES_WORKING_COLOR_SPACE else aces2065_1_to_acescg(samples)
    assert out.shape == samples.shape
    assert np.all(np.isfinite(out))


@pytest.mark.parametrize("space", ["sRGB", "Display P3", "ProPhoto RGB"])
def test_to_acescg_respects_apply_cctf_decoding(space: str) -> None:
    encoded = np.array([[[0.5, 0.25, 0.75]]], dtype=np.float32)
    decoded = to_acescg(encoded, input_color_space=space, apply_cctf_decoding=True)
    linear = to_acescg(encoded, input_color_space=space, apply_cctf_decoding=False)

    assert decoded.shape == encoded.shape
    assert linear.shape == encoded.shape
    assert np.all(np.isfinite(decoded))
    assert np.all(np.isfinite(linear))
    assert not np.allclose(decoded, linear)


def test_render_aces_local_sdr_preview_outputs_unit_code_values() -> None:
    preview, diagnostics = render_aces_local_sdr_preview(
        _sample_rgb(),
        color_space=ACES_WORKING_COLOR_SPACE,
    )

    assert preview.dtype == np.float32
    assert preview.shape == _sample_rgb().shape
    assert np.all(np.isfinite(preview))
    assert float(preview.min()) >= 0.0
    assert float(preview.max()) <= 1.0
    assert diagnostics.implementation_kind == "spektrafilm_local"
    assert "not an official ACES Output Transform" in " ".join(diagnostics.notes)


def test_legacy_color_management_aces_preview_still_works() -> None:
    preview = aces_sdr_video_view_transform(
        _sample_rgb(),
        color_space=ACES_WORKING_COLOR_SPACE,
    )

    assert preview.shape == _sample_rgb().shape
    assert preview.dtype == np.float32
    assert np.all(np.isfinite(preview))


def test_aces_reference_workflow_behavior_is_unchanged() -> None:
    io = IOParams(
        input_color_space="Display P3",
        input_cctf_decoding=True,
        output_color_space="sRGB",
        output_cctf_encoding=True,
        output_clip_min=True,
        output_clip_max=True,
    )

    preset = color_management_module.apply_color_management_workflow_to_io(io, "aces_reference")

    assert io.input_color_space == ACES_WORKING_COLOR_SPACE
    assert io.input_cctf_decoding is False
    assert io.output_color_space == ACES_WORKING_COLOR_SPACE
    assert io.output_cctf_encoding is False
    assert io.output_clip_min is False
    assert io.output_clip_max is False
    assert preset.saving_color_space == ACES_INTERCHANGE_COLOR_SPACE
    assert preset.saving_cctf_encoding is False


def test_ocio_unavailable_raises_clear_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "PyOpenColorIO":
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert is_ocio_available() is False
    with pytest.raises(OcioUnavailableError, match="PyOpenColorIO is required"):
        render_aces_ocio_view(_sample_rgb())


def test_ocio_available_loads_aces_config_and_renders_smoke_view() -> None:
    ocio = pytest.importorskip("PyOpenColorIO")
    config, config_diag = load_aces_ocio_config(ocio_module=ocio)
    image = np.array([[[0.18, 0.18, 0.18], [1.0, 0.25, 0.1]]], dtype=np.float32)

    out, diagnostics = render_aces_ocio_view(
        image,
        config=config,
        context=AcesContext(),
        ocio_module=ocio,
    )

    assert config_diag.implementation_kind == "ocio_official"
    assert config_diag.config_source in {"builtin", "file"}
    assert diagnostics.implementation_kind == "ocio_official"
    assert diagnostics.display == "sRGB - Display"
    assert diagnostics.view is not None
    assert diagnostics.roles["aces_interchange"] == ACES_INTERCHANGE_COLOR_SPACE
    assert out.shape == image.shape
    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))


def test_build_aces_transform_manifest_contains_required_fields() -> None:
    preview, preview_diag = render_aces_local_sdr_preview(
        np.array([[[0.18, 0.18, 0.18]]], dtype=np.float32),
        color_space=ACES_WORKING_COLOR_SPACE,
    )
    assert preview.shape == (1, 1, 3)

    manifest = build_aces_transform_manifest(
        context=AcesContext(input_color_space="Display P3", output_color_space="sRGB"),
        preview_diagnostics=preview_diag,
        input_color_space="Display P3",
        output_color_space="sRGB",
    )

    assert manifest["working_space"] == ACES_WORKING_COLOR_SPACE
    assert manifest["interchange_space"] == ACES_INTERCHANGE_COLOR_SPACE
    assert manifest["input_color_space"] == "Display P3"
    assert manifest["output_color_space"] == "sRGB"
    assert manifest["implementation_kind"] == "spektrafilm_local"
    assert manifest["transform_ids"]["input_transform_id"] is None
    assert manifest["transform_ids"]["output_transform_id"] is None
    assert "does not invent" in manifest["transform_ids"]["notes"]
    assert manifest["amf"]["sidecar_kind"] == "project_local_manifest"


def test_aces_rgc_wrapper_preserves_shape_finite_and_neutral_axis() -> None:
    rgb = np.array(
        [
            [0.18, 0.18, 0.18],
            [1.0, 1.0, 1.0],
            [1.5, -0.1, -0.05],
        ],
        dtype=np.float32,
    )

    out, diagnostics = apply_aces_reference_gamut_compression(rgb)

    assert out.shape == rgb.shape
    assert out.dtype == np.float32
    assert np.all(np.isfinite(out))
    np.testing.assert_allclose(out[:2], rgb[:2], atol=1e-6)
    assert out[2, 1] >= 0.0
    assert out[2, 2] >= 0.0
    assert diagnostics.implementation_kind == "spektrafilm_local"
    assert "distinct from perceptual" in " ".join(diagnostics.notes)


def test_lut_creator_aces_scene_linear_inputs_remain_silenced() -> None:
    from spektrafilm_lut_creator.color_spaces import get, list_input_spaces
    from spektrafilm_lut_creator.builders import BundleBuilder
    from tests.lut_creator.factories import make_bundle_spec

    assert ACES_WORKING_COLOR_SPACE not in list_input_spaces()
    assert ACES_INTERCHANGE_COLOR_SPACE not in list_input_spaces()
    assert get(ACES_WORKING_COLOR_SPACE).role == ()
    assert get(ACES_INTERCHANGE_COLOR_SPACE).role == ()

    spec = make_bundle_spec(name="acescg_input_guard", input_color_space=ACES_WORKING_COLOR_SPACE)
    with pytest.raises(ValueError, match="not registered as an input"):
        BundleBuilder(spec).build()


def test_color_management_lazy_reexports_aces_helpers() -> None:
    assert color_management_module.to_acescg is to_acescg
    assert color_management_module.render_aces_local_sdr_preview is render_aces_local_sdr_preview
