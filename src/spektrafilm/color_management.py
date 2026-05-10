from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TYPE_CHECKING

Transfer = Literal["linear", "cctf"]
ColorRole = Literal["scene", "display", "interchange"]


@dataclass(frozen=True, slots=True)
class ColorEncoding:
    color_space: str
    transfer: Transfer
    role: ColorRole = "scene"
    clip_negatives: bool = True
    clip_highlights: bool = True

    @property
    def is_linear(self) -> bool:
        return self.transfer == "linear"

    @property
    def is_cctf_encoded(self) -> bool:
        return self.transfer == "cctf"


if TYPE_CHECKING:  # pragma: no cover
    from spektrafilm.runtime.params_schema import IOParams


def input_encoding_from_io(io: IOParams) -> ColorEncoding:
    """Encoding of input pixel data as it enters the runtime pipeline."""

    return ColorEncoding(
        color_space=str(io.input_color_space),
        transfer="cctf" if bool(io.input_cctf_decoding) else "linear",
        role="scene",
    )


def output_encoding_from_io(io: IOParams) -> ColorEncoding:
    """Encoding of pixel data as produced by the runtime pipeline."""

    transfer: Transfer = "cctf" if bool(io.output_cctf_encoding) else "linear"
    return ColorEncoding(
        color_space=str(io.output_color_space),
        transfer=transfer,
        role="display" if transfer == "cctf" else "scene",
        clip_negatives=bool(getattr(io, "output_clip_min", True)),
        clip_highlights=bool(getattr(io, "output_clip_max", True)),
    )
