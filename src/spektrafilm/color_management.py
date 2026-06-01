from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal, TYPE_CHECKING

import numpy as np

Transfer = Literal["linear", "cctf"]
ColorRole = Literal["scene", "display", "interchange"]
ColorManagementWorkflow = Literal["manual", "aces_reference"]

ACES_INTERCHANGE_COLOR_SPACE = "ACES2065-1"
ACES_WORKING_COLOR_SPACE = "ACEScg"
MANUAL_COLOR_MANAGEMENT_WORKFLOW = "manual"
ACES_REFERENCE_COLOR_MANAGEMENT_WORKFLOW = "aces_reference"
ACES_SCENE_LINEAR_COLOR_SPACES = frozenset(
    {
        ACES_INTERCHANGE_COLOR_SPACE,
        ACES_WORKING_COLOR_SPACE,
    }
)


@lru_cache(maxsize=1)
def _known_rgb_colourspaces() -> frozenset[str]:
    import colour

    return frozenset(str(name) for name in colour.RGB_COLOURSPACES.keys())


def is_aces_scene_linear_space(color_space: str) -> bool:
    """Return whether *color_space* is an ACES scene-linear RGB encoding."""

    return str(color_space) in ACES_SCENE_LINEAR_COLOR_SPACES


_ACES_SDR_INPUT_MATRIX = np.array(
    [
        [0.59719, 0.35458, 0.04823],
        [0.07600, 0.90834, 0.01566],
        [0.02840, 0.13383, 0.83777],
    ],
    dtype=np.float32,
)
_ACES_SDR_OUTPUT_MATRIX = np.array(
    [
        [1.60475, -0.53108, -0.07367],
        [-0.10208, 1.10813, -0.00605],
        [-0.00327, -0.07276, 1.07602],
    ],
    dtype=np.float32,
)


def _apply_rgb_matrix(image: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return np.tensordot(image, matrix.T, axes=1).astype(np.float32, copy=False)


def _aces_sdr_rrt_odt_fit(linear_srgb: np.ndarray) -> np.ndarray:
    """Stephen Hill ACES fitted SDR rendering curve for display preview."""

    color = _apply_rgb_matrix(linear_srgb, _ACES_SDR_INPUT_MATRIX)
    color = (color * (color + np.float32(0.0245786)) - np.float32(0.000090537)) / (
        color * (np.float32(0.983729) * color + np.float32(0.4329510)) + np.float32(0.238081)
    )
    return _apply_rgb_matrix(color, _ACES_SDR_OUTPUT_MATRIX)


def _srgb_cctf_encoding(linear_rgb: np.ndarray) -> np.ndarray:
    linear_rgb = np.clip(np.asarray(linear_rgb, dtype=np.float32), 0.0, None)
    return np.where(
        linear_rgb <= np.float32(0.0031308),
        np.float32(12.92) * linear_rgb,
        np.float32(1.055) * np.power(linear_rgb, np.float32(1.0 / 2.4)) - np.float32(0.055),
    ).astype(np.float32, copy=False)


def aces_sdr_video_view_transform(
    image_data: np.ndarray,
    *,
    color_space: str,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Render ACES scene-linear RGB through SpektraFilm's SDR video view.

    This is a named ACES-style SDR Output Transform for GUI preview: input is
    scene-linear ACES2065-1 or ACEScg, output is display-referred sRGB code
    values in [0, 1]. It is intentionally local and deterministic until the
    project ships an OCIO ACES config dependency.
    """

    color_space = str(color_space)
    if not is_aces_scene_linear_space(color_space):
        raise ValueError(f"ACES SDR view requires ACES scene-linear input, got {color_space!r}.")
    if colour_module is None:
        import colour as colour_module

    image = np.asarray(image_data, dtype=np.float32)
    linear_srgb = colour_module.RGB_to_RGB(
        image,
        color_space,
        "sRGB",
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    linear_srgb = np.clip(np.asarray(linear_srgb, dtype=np.float32), 0.0, None)
    rendered = _aces_sdr_rrt_odt_fit(linear_srgb)
    return np.asarray(np.clip(_srgb_cctf_encoding(rendered), 0.0, 1.0), dtype=np.float32)


@dataclass(frozen=True, slots=True)
class ColorManagementWorkflowPreset:
    workflow: ColorManagementWorkflow
    input_color_space: str | None = None
    input_cctf_decoding: bool | None = None
    output_color_space: str | None = None
    output_cctf_encoding: bool | None = None
    output_clip_min: bool | None = None
    output_clip_max: bool | None = None
    saving_color_space: str | None = None
    saving_cctf_encoding: bool | None = None


def color_management_workflow_preset(workflow: str) -> ColorManagementWorkflowPreset:
    """Return the high-level color-management workflow preset."""

    workflow = str(workflow)
    if workflow == MANUAL_COLOR_MANAGEMENT_WORKFLOW:
        return ColorManagementWorkflowPreset(workflow=MANUAL_COLOR_MANAGEMENT_WORKFLOW)
    if workflow == ACES_REFERENCE_COLOR_MANAGEMENT_WORKFLOW:
        return ColorManagementWorkflowPreset(
            workflow=ACES_REFERENCE_COLOR_MANAGEMENT_WORKFLOW,
            input_color_space=ACES_WORKING_COLOR_SPACE,
            input_cctf_decoding=False,
            output_color_space=ACES_WORKING_COLOR_SPACE,
            output_cctf_encoding=False,
            output_clip_min=False,
            output_clip_max=False,
            saving_color_space=ACES_INTERCHANGE_COLOR_SPACE,
            saving_cctf_encoding=False,
        )
    raise ValueError(
        "Unsupported color management workflow "
        f"{workflow!r}; expected 'manual' or 'aces_reference'."
    )


def apply_color_management_workflow_to_io(io: IOParams, workflow: str) -> ColorManagementWorkflowPreset:
    """Apply a color-management workflow preset to mutable runtime IO params."""

    preset = color_management_workflow_preset(workflow)
    for attr in (
        "input_color_space",
        "input_cctf_decoding",
        "output_color_space",
        "output_cctf_encoding",
        "output_clip_min",
        "output_clip_max",
    ):
        value = getattr(preset, attr)
        if value is not None:
            setattr(io, attr, value)
    return preset


@dataclass(frozen=True, slots=True)
class ColorEncoding:
    color_space: str
    transfer: Transfer
    role: ColorRole = "scene"
    clip_negatives: bool = True
    clip_highlights: bool = True

    def __post_init__(self) -> None:
        if self.color_space not in _known_rgb_colourspaces():
            common = (
                "sRGB",
                "Display P3",
                "DCI-P3",
                "Adobe RGB (1998)",
                "ITU-R BT.2020",
                "ProPhoto RGB",
                ACES_INTERCHANGE_COLOR_SPACE,
                ACES_WORKING_COLOR_SPACE,
            )
            raise ValueError(
                f"Unknown RGB colourspace {self.color_space!r}; common valid names include: {', '.join(common)}."
            )
        if self.transfer not in ("linear", "cctf"):
            raise ValueError(f"Unsupported transfer {self.transfer!r}; expected 'linear' or 'cctf'.")
        if self.role not in ("scene", "display", "interchange"):
            raise ValueError(f"Unsupported color role {self.role!r}.")

    @property
    def is_linear(self) -> bool:
        return self.transfer == "linear"

    @property
    def is_cctf_encoded(self) -> bool:
        return self.transfer == "cctf"

    @property
    def is_aces_scene_linear(self) -> bool:
        return is_aces_scene_linear_space(self.color_space)


if TYPE_CHECKING:  # pragma: no cover
    from spektrafilm.runtime.params_schema import IOParams


def input_encoding_from_io(io: IOParams) -> ColorEncoding:
    """Encoding of input pixel data as it enters the runtime pipeline."""

    color_space = str(io.input_color_space)
    if is_aces_scene_linear_space(color_space):
        return ColorEncoding(
            color_space=color_space,
            transfer="linear",
            role="scene",
            clip_negatives=False,
            clip_highlights=False,
        )

    return ColorEncoding(
        color_space=color_space,
        transfer="cctf" if bool(io.input_cctf_decoding) else "linear",
        role="scene",
    )


def output_encoding_from_io(io: IOParams) -> ColorEncoding:
    """Encoding of pixel data as produced by the runtime pipeline."""

    color_space = str(io.output_color_space)
    if is_aces_scene_linear_space(color_space):
        return ColorEncoding(
            color_space=color_space,
            transfer="linear",
            role="scene",
            clip_negatives=False,
            clip_highlights=False,
        )

    transfer: Transfer = "cctf" if bool(io.output_cctf_encoding) else "linear"
    return ColorEncoding(
        color_space=color_space,
        transfer=transfer,
        role="display" if transfer == "cctf" else "scene",
        clip_negatives=bool(getattr(io, "output_clip_min", True)),
        clip_highlights=bool(getattr(io, "output_clip_max", True)),
    )
