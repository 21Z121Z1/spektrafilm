from __future__ import annotations

import pytest

import spektrafilm.color_management as color_management_module
from spektrafilm.color_management import (
    ACES_INTERCHANGE_COLOR_SPACE,
    ACES_WORKING_COLOR_SPACE,
    ColorEncoding,
    input_encoding_from_io,
    is_aces_scene_linear_space,
    output_encoding_from_io,
)
from spektrafilm.runtime.params_schema import IOParams
from spektrafilm_gui.options import RGBColorSpaces


def test_input_encoding_from_io_maps_decoding_flag_to_transfer() -> None:
    linear_io = IOParams(input_color_space="ProPhoto RGB", input_cctf_decoding=False)
    cctf_io = IOParams(input_color_space="Display P3", input_cctf_decoding=True)

    linear_encoding = input_encoding_from_io(linear_io)
    cctf_encoding = input_encoding_from_io(cctf_io)

    assert linear_encoding.color_space == "ProPhoto RGB"
    assert linear_encoding.transfer == "linear"
    assert linear_encoding.role == "scene"
    assert cctf_encoding.color_space == "Display P3"
    assert cctf_encoding.transfer == "cctf"
    assert cctf_encoding.role == "scene"


def test_output_encoding_from_io_maps_sdr_png_jpeg_contract() -> None:
    io = IOParams(
        output_color_space="Display P3",
        output_cctf_encoding=True,
        output_clip_min=True,
        output_clip_max=True,
    )

    encoding = output_encoding_from_io(io)

    assert encoding.color_space == "Display P3"
    assert encoding.transfer == "cctf"
    assert encoding.role == "display"
    assert encoding.clip_negatives is True
    assert encoding.clip_highlights is True


def test_output_encoding_from_io_maps_hdr_exr_contract() -> None:
    io = IOParams(
        output_color_space=ACES_INTERCHANGE_COLOR_SPACE,
        output_cctf_encoding=False,
        output_clip_min=True,
        output_clip_max=False,
    )

    encoding = output_encoding_from_io(io)

    assert encoding.color_space == ACES_INTERCHANGE_COLOR_SPACE
    assert encoding.transfer == "linear"
    assert encoding.role == "scene"
    assert encoding.clip_negatives is False
    assert encoding.clip_highlights is False


@pytest.mark.parametrize("color_space", [ACES_INTERCHANGE_COLOR_SPACE, ACES_WORKING_COLOR_SPACE])
def test_aces_io_encodings_force_scene_linear_unclipped_contract(color_space: str) -> None:
    input_encoding = input_encoding_from_io(
        IOParams(input_color_space=color_space, input_cctf_decoding=True)
    )
    output_encoding = output_encoding_from_io(
        IOParams(
            output_color_space=color_space,
            output_cctf_encoding=True,
            output_clip_min=True,
            output_clip_max=True,
        )
    )

    assert is_aces_scene_linear_space(color_space)
    assert input_encoding.transfer == "linear"
    assert input_encoding.role == "scene"
    assert input_encoding.clip_negatives is False
    assert input_encoding.clip_highlights is False
    assert output_encoding.transfer == "linear"
    assert output_encoding.role == "scene"
    assert output_encoding.clip_negatives is False
    assert output_encoding.clip_highlights is False


def test_color_encoding_rejects_unknown_color_space() -> None:
    with pytest.raises(ValueError, match="Unknown RGB colourspace"):
        ColorEncoding(color_space="srgb", transfer="cctf")


def test_gui_rgb_color_spaces_include_acescg_working_space() -> None:
    assert RGBColorSpaces.ACEScg.value == ACES_WORKING_COLOR_SPACE


def test_manual_color_management_workflow_leaves_io_unchanged() -> None:
    io = IOParams(
        input_color_space="Display P3",
        input_cctf_decoding=True,
        output_color_space="sRGB",
        output_cctf_encoding=True,
        output_clip_min=True,
        output_clip_max=True,
    )

    preset = color_management_module.apply_color_management_workflow_to_io(io, "manual")

    assert io.input_color_space == "Display P3"
    assert io.input_cctf_decoding is True
    assert io.output_color_space == "sRGB"
    assert io.output_cctf_encoding is True
    assert io.output_clip_min is True
    assert io.output_clip_max is True
    assert preset.saving_color_space is None
    assert preset.saving_cctf_encoding is None


def test_aces_reference_workflow_sets_aces_working_and_interchange_contract() -> None:
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


def test_color_management_workflow_rejects_unknown_mode() -> None:
    with pytest.raises(ValueError, match="Unsupported color management workflow"):
        color_management_module.apply_color_management_workflow_to_io(IOParams(), "unknown")
