from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.utils.crop_resize import crop_image

pytestmark = pytest.mark.unit


class TestCropImage:
    def test_center_crop_produces_correct_size(self) -> None:
        image = np.random.default_rng(42).random((100, 200, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.25, 0.25))
        # size is fraction of long side (200). 0.25 * 200 = 50 pixels each axis.
        assert cropped.shape[0] == 50
        assert cropped.shape[1] == 50
        assert cropped.shape[2] == 3

    def test_crop_preserves_pixel_values(self) -> None:
        image = np.ones((100, 100, 3)) * 0.5
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.5, 0.5))
        np.testing.assert_allclose(cropped, 0.5)

    def test_edge_crop_clamps_to_image_bounds(self) -> None:
        image = np.arange(100 * 100 * 3, dtype=float).reshape(100, 100, 3)
        # Crop near top-left corner.
        cropped = crop_image(image, center=(0.0, 0.0), size=(0.3, 0.3))
        assert cropped.shape == (30, 30, 3)
        np.testing.assert_array_equal(cropped, image[:30, :30, :])

    def test_edge_crop_near_bottom_right(self) -> None:
        image = np.arange(100 * 100 * 3, dtype=float).reshape(100, 100, 3)
        cropped = crop_image(image, center=(1.0, 1.0), size=(0.3, 0.3))
        assert cropped.shape == (30, 30, 3)
        np.testing.assert_array_equal(cropped, image[70:100, 70:100, :])

    def test_crop_size_exceeding_image_clamps(self) -> None:
        image = np.arange(50 * 50 * 3, dtype=float).reshape(50, 50, 3)
        # Request crop larger than image.
        cropped = crop_image(image, center=(0.5, 0.5), size=(2.0, 2.0))
        assert cropped.shape == image.shape
        np.testing.assert_array_equal(cropped, image)

    def test_non_square_image(self) -> None:
        image = np.random.default_rng(42).random((30, 100, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.2, 0.2))
        assert cropped.ndim == 3
        assert cropped.shape[2] == 3

    def test_asymmetric_crop_size(self) -> None:
        image = np.random.default_rng(42).random((100, 200, 3))
        cropped = crop_image(image, center=(0.5, 0.5), size=(0.1, 0.5))
        # size is (x, y) as a fraction of the long side (200):
        # width = 0.1 * 200, height = 0.5 * 200.
        assert cropped.shape == (100, 20, 3)

    def test_output_always_3d(self) -> None:
        image = np.random.default_rng(42).random((64, 64, 3))
        for center in [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]:
            cropped = crop_image(image, center=center, size=(0.1, 0.1))
            assert cropped.ndim == 3
