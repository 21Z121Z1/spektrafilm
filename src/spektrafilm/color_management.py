from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, TYPE_CHECKING

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
