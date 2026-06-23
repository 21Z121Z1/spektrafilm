from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np


ALL_TAPS: tuple[str, ...] = (
    "rgb_pre",
    "log_e_film",
    "cmy_film",
    "log_e_print",
    "cmy_print",
    "rgb_out",
)
PRINT_TAPS: frozenset[str] = frozenset({"log_e_print", "cmy_print"})


@dataclass(frozen=True)
class AlignmentCase:
    fixture_id: str
    image: np.ndarray
    film_profile: str
    print_profile: str
    scan_film: bool
    fixture_kind: str
    description: str

    def to_spec(self) -> dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "film_profile": self.film_profile,
            "print_profile": self.print_profile,
            "scan_film": self.scan_film,
            "fixture_kind": self.fixture_kind,
            "description": self.description,
        }


def expected_taps(case: AlignmentCase | dict[str, object]) -> tuple[str, ...]:
    scan_film = bool(case["scan_film"] if isinstance(case, dict) else case.scan_film)
    if scan_film:
        return tuple(tap for tap in ALL_TAPS if tap not in PRINT_TAPS)
    return ALL_TAPS


def skipped_taps(case: AlignmentCase | dict[str, object]) -> tuple[str, ...]:
    scan_film = bool(case["scan_film"] if isinstance(case, dict) else case.scan_film)
    return tuple(sorted(PRINT_TAPS)) if scan_film else ()


def fixture_image(fixture_id: str) -> np.ndarray:
    for case in iter_cases("full"):
        if case.fixture_id == fixture_id:
            return case.image.copy()
    raise KeyError(f"unknown SDR alignment fixture {fixture_id!r}")


def iter_cases(suite: str) -> Iterable[AlignmentCase]:
    suite = str(suite)
    if suite not in {"quick", "full"}:
        raise ValueError("suite must be 'quick' or 'full'")

    quick = (
        AlignmentCase(
            fixture_id="gray_ramp_16_print",
            image=_gray_ramp(16, 16, high=1.0),
            film_profile="kodak_portra_400",
            print_profile="kodak_portra_endura",
            scan_film=False,
            fixture_kind="strict",
            description="16x16 neutral gray ramp through negative-print-scan route",
        ),
        AlignmentCase(
            fixture_id="positive_scan_film_8",
            image=_color_patches(8, 8),
            film_profile="fujifilm_provia_100f",
            print_profile="kodak_portra_endura",
            scan_film=True,
            fixture_kind="strict",
            description="8x8 color patches through positive film scan route",
        ),
    )
    if suite == "quick":
        return quick

    full = quick + (
        AlignmentCase(
            fixture_id="color_patches_16_print",
            image=_color_patches(16, 16),
            film_profile="kodak_portra_400",
            print_profile="kodak_portra_endura",
            scan_film=False,
            fixture_kind="strict",
            description="16x16 repeated photographic color patches",
        ),
        AlignmentCase(
            fixture_id="highlight_ramp_32_print",
            image=_highlight_ramp(32, 16),
            film_profile="kodak_portra_400",
            print_profile="kodak_portra_endura",
            scan_film=False,
            fixture_kind="rendering",
            description="32x16 highlight ramp with spatial effects enabled",
        ),
        AlignmentCase(
            fixture_id="saturation_cube_17_print",
            image=_saturation_grid(17),
            film_profile="kodak_ektar_100",
            print_profile="kodak_portra_endura",
            scan_film=False,
            fixture_kind="strict",
            description="17x17 high-saturation RGB grid",
        ),
        AlignmentCase(
            fixture_id="structured_scene_32_scan_film",
            image=_structured_scene(32, 32),
            film_profile="fujifilm_velvia_100",
            print_profile="kodak_portra_endura",
            scan_film=True,
            fixture_kind="rendering",
            description="32x32 deterministic structured positive scan route",
        ),
    )
    return full


def _gray_ramp(width: int, height: int, *, high: float) -> np.ndarray:
    ramp = np.linspace(0.01, high, width, dtype=np.float64)
    image = np.ones((height, width, 3), dtype=np.float64)
    image *= ramp[None, :, None]
    return image


def _color_patches(width: int, height: int) -> np.ndarray:
    patches = np.array(
        [
            [0.02, 0.02, 0.02],
            [0.18, 0.18, 0.18],
            [0.90, 0.90, 0.90],
            [1.00, 0.00, 0.00],
            [0.00, 1.00, 0.00],
            [0.00, 0.00, 1.00],
            [0.93, 0.63, 0.48],
            [0.43, 0.62, 0.95],
            [0.23, 0.47, 0.18],
            [1.20, 0.20, 0.08],
            [0.20, 1.15, 0.18],
            [0.10, 0.30, 1.25],
        ],
        dtype=np.float64,
    )
    index = np.arange(width * height) % len(patches)
    return patches[index].reshape(height, width, 3)


def _highlight_ramp(width: int, height: int) -> np.ndarray:
    x = np.linspace(0.001, 2.0, width, dtype=np.float64)
    y = np.linspace(0.75, 1.25, height, dtype=np.float64)
    base = y[:, None] * x[None, :]
    image = np.empty((height, width, 3), dtype=np.float64)
    image[..., 0] = base
    image[..., 1] = base * 0.92 + 0.02
    image[..., 2] = base * 0.78 + 0.04
    return image


def _saturation_grid(size: int) -> np.ndarray:
    r = np.linspace(0.0, 1.35, size, dtype=np.float64)
    g = np.linspace(0.0, 1.35, size, dtype=np.float64)
    rr, gg = np.meshgrid(r, g)
    image = np.empty((size, size, 3), dtype=np.float64)
    image[..., 0] = rr
    image[..., 1] = gg
    image[..., 2] = np.mod(rr * 0.7 + gg * 0.35 + 0.08, 1.25)
    return image


def _structured_scene(width: int, height: int) -> np.ndarray:
    rng = np.random.default_rng(20260623)
    yy, xx = np.mgrid[0:height, 0:width]
    x = xx.astype(np.float64) / max(width - 1, 1)
    y = yy.astype(np.float64) / max(height - 1, 1)
    image = np.empty((height, width, 3), dtype=np.float64)
    image[..., 0] = 0.04 + 0.95 * x
    image[..., 1] = 0.08 + 0.75 * y
    image[..., 2] = 0.12 + 0.55 * (1.0 - x) + 0.15 * y
    image += rng.normal(0.0, 0.015, size=image.shape)
    image[height // 4 : height // 4 + 3, width // 3 : width // 3 + 3] = (1.6, 1.45, 1.15)
    return np.clip(image, 0.0, 1.8)

