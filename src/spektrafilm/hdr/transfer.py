from __future__ import annotations

import numpy as np
import colour

_PQ_MAX_NITS = 10_000.0


def pq_nits_to_code(nits: np.ndarray | float) -> np.ndarray:
    """Encode absolute luminance in nits to BT.2100 PQ code values."""

    values = np.asarray(nits, dtype=np.float32)
    encoded = np.asarray(
        colour.models.eotf_inverse_BT2100_PQ(np.clip(values, 0.0, _PQ_MAX_NITS)),
        dtype=np.float32,
    )
    return np.where(values <= 0.0, np.float32(0.0), encoded).astype(np.float32, copy=False)


def pq_code_to_nits(code_values: np.ndarray | float) -> np.ndarray:
    """Decode BT.2100 PQ code values to absolute luminance in nits."""

    values = np.asarray(code_values, dtype=np.float32)
    return np.asarray(
        colour.models.eotf_BT2100_PQ(np.clip(values, 0.0, 1.0)),
        dtype=np.float32,
    )


def hlg_scene_linear_to_code(values: np.ndarray | float) -> np.ndarray:
    """Encode normalized scene-linear values to BT.2100 HLG code values."""

    linear = np.asarray(values, dtype=np.float32)
    return np.asarray(
        colour.models.oetf_BT2100_HLG(np.clip(linear, 0.0, None)),
        dtype=np.float32,
    )


def hlg_code_to_scene_linear(code_values: np.ndarray | float) -> np.ndarray:
    """Decode BT.2100 HLG code values to normalized scene-linear values."""

    encoded = np.asarray(code_values, dtype=np.float32)
    return np.asarray(
        colour.models.oetf_inverse_BT2100_HLG(np.clip(encoded, 0.0, 1.0)),
        dtype=np.float32,
    )


__all__ = [
    "pq_nits_to_code",
    "pq_code_to_nits",
    "hlg_scene_linear_to_code",
    "hlg_code_to_scene_linear",
]
