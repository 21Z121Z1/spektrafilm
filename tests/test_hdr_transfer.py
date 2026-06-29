from __future__ import annotations

import numpy as np

from spektrafilm.hdr.transfer import (
    hlg_code_to_scene_linear,
    hlg_scene_linear_to_code,
    pq_code_to_nits,
    pq_nits_to_code,
)


def test_pq_helpers_are_finite_monotonic_and_roundtrip() -> None:
    nits = np.array([0.0, 0.1, 1.0, 203.0, 1000.0, 4000.0, 10000.0], dtype=np.float32)

    code = pq_nits_to_code(nits)
    restored = pq_code_to_nits(code)

    assert np.all(np.isfinite(code))
    assert np.all((0.0 <= code) & (code <= 1.0))
    assert np.all(np.diff(code) >= 0.0)
    np.testing.assert_allclose(restored, nits, rtol=1e-3, atol=1e-2)


def test_hlg_helpers_are_finite_monotonic_and_roundtrip() -> None:
    linear = np.linspace(0.0, 1.0, 17, dtype=np.float32)

    code = hlg_scene_linear_to_code(linear)
    restored = hlg_code_to_scene_linear(code)

    assert np.all(np.isfinite(code))
    assert np.all((0.0 <= code) & (code <= 1.0))
    assert np.all(np.diff(code) >= -1e-7)
    np.testing.assert_allclose(restored, linear, rtol=1e-4, atol=1e-5)


def test_transfer_helpers_clip_invalid_boundaries() -> None:
    pq = pq_nits_to_code(np.array([-10.0, 20_000.0], dtype=np.float32))
    hlg = hlg_scene_linear_to_code(np.array([-1.0, 1.0], dtype=np.float32))

    assert np.all(np.isfinite(pq))
    assert pq[0] == 0.0
    assert pq[1] <= 1.0
    assert np.all(np.isfinite(hlg))
    assert hlg[0] == 0.0
