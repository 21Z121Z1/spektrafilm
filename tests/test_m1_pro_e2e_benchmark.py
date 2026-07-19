from __future__ import annotations

import hashlib

import numpy as np

from tests.benchmarks.benchmark_m1_pro_e2e import _array_digest, generated_linear_image
from tests.benchmarks.benchmark_m1_pro_preview_updates import summarize


def test_generated_linear_benchmark_image_is_deterministic_hdr_input() -> None:
    first = generated_linear_image(7, 11, 4.0)
    second = generated_linear_image(7, 11, 4.0)

    np.testing.assert_array_equal(first, second)
    assert first.dtype == np.float32
    assert first.shape == (7, 11, 3)
    assert float(first[..., 0].max()) == 4.0


def test_benchmark_digest_matches_numpy_without_precision_loss() -> None:
    array = np.linspace(0.0, 3.0, 97 * 101 * 3, dtype=np.float32).reshape(97, 101, 3)
    digest = _array_digest(array)

    assert digest["sha256"] == hashlib.sha256(array.view(np.uint8)).hexdigest()
    assert digest["finite_fraction"] == 1.0
    assert digest["sum"] == float(np.sum(array, dtype=np.float64))
    assert digest["mean"] == float(np.mean(array, dtype=np.float64))


def test_preview_benchmark_summary_reports_median_min_max() -> None:
    assert summarize([0.4, 0.1, 0.2]) == {
        "median": 0.2,
        "min": 0.1,
        "max": 0.4,
    }
