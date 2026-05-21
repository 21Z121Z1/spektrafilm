from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.kernels.color import boost_highlights_backend
from spektrafilm.gpu.numpy_backend import NumpyBackend


pytestmark = pytest.mark.unit


def _boost_tiled(
    x: np.ndarray,
    *,
    tile_rows: int,
    boost_ev: float,
    boost_range: float,
    protect_ev: float,
    backend: NumpyBackend,
    x_max: float | None,
) -> np.ndarray:
    chunks: list[np.ndarray] = []
    for start_y in range(0, x.shape[0], tile_rows):
        end_y = min(start_y + tile_rows, x.shape[0])
        chunk = boost_highlights_backend(
            x[start_y:end_y, :, :],
            boost_ev,
            boost_range,
            protect_ev,
            backend,
            x_max=x_max,
        )
        chunks.append(np.asarray(chunk))
    return np.concatenate(chunks, axis=0)


def test_boost_highlights_backend_tiled_matches_full_when_x_max_is_global() -> None:
    backend = NumpyBackend()

    # Force a different max per tile so tile-local normalisation differs.
    x = np.zeros((6, 4, 3), dtype=np.float32)
    x[:3, :, :] = 0.2
    x[3:, :, :] = 0.8

    boost_ev = 4.0
    boost_range = 0.3
    protect_ev = 0.0

    full = boost_highlights_backend(x, boost_ev, boost_range, protect_ev, backend)

    tiled_local = _boost_tiled(
        x,
        tile_rows=3,
        boost_ev=boost_ev,
        boost_range=boost_range,
        protect_ev=protect_ev,
        backend=backend,
        x_max=None,
    )

    # Regression guard: without a global x_max, tiled output must differ.
    assert float(np.max(np.abs(tiled_local - full))) > 1e-3

    global_max = backend.max(x)
    tiled_global = _boost_tiled(
        x,
        tile_rows=3,
        boost_ev=boost_ev,
        boost_range=boost_range,
        protect_ev=protect_ev,
        backend=backend,
        x_max=global_max,
    )

    np.testing.assert_allclose(tiled_global, full, rtol=0.0, atol=0.0)
