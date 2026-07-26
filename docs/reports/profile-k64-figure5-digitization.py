#!/usr/bin/env python3
"""Reproducibly digitize Kodachrome 64 curves from a 1978 scanned figure.

This is a closed-evidence audit tool. It verifies the exact source PDF, reads
Figure 5 on PDF page 5, digitizes only the printed 400-700 nm / 20 nm marker
grid, and compares the resulting peak-normalized Y/M/C shapes with the bundled
Kodachrome 64 profile. It never writes a profile and never extrapolates the
figure outside its printed wavelength range.

The source page is a scan, not vector artwork. To make the reading auditable,
the script uses the native page image plus independent 600 dpi and 900 dpi
Poppler renders. Two local point-reading methods are applied to every raster.
The higher-dpi passes test rasterization stability; they do not increase the
information content of the 973 x 1463 source scan.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from PIL import Image
from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PDF = Path.home() / "Downloads" / "1978_oct_1293-1301.pdf"
PROFILE_PATH = (
    PROJECT_ROOT
    / "src"
    / "spektrafilm"
    / "data"
    / "profiles"
    / "kodak_kodachrome_64.json"
)
OUTPUT_DIR = PROJECT_ROOT / "tmp" / "profile-source-curves" / "k64"
PDF_TEMP_ROOT = PROJECT_ROOT / "tmp" / "pdfs"

EXPECTED_PDF_SHA256 = (
    "2423a00887fc60f8ea45b052a058e7af7f3467436506be849e15c0038388a8ca"
)
EXPECTED_PAGE_COUNT = 9
FIGURE_PAGE_NUMBER = 5
EXPECTED_NATIVE_PAGE_SIZE = (973, 1463)

# The visually reviewed native-image axis centers. Axis detection searches a
# narrow neighborhood around these coordinates and re-estimates each raster's
# actual line center from its ink profile.
NATIVE_AXIS_REFERENCE = {
    "left_x": 356.0,
    "right_x": 644.0,
    "top_y": 1104.0,
    "bottom_y": 1272.0,
}

WAVELENGTHS_NM = np.arange(400.0, 701.0, 20.0)
CHANNELS = ("Y", "M", "C")
PROFILE_CHANNEL_INDEX = {"Y": 2, "M": 1, "C": 0}

# Coarse, visually reviewed tracking seeds. These values identify the correct
# curve inside a +/- about 0.05-density pixel window. They are not returned as
# digitized values: both algorithms calculate the point center from source ink.
TRACKING_SEEDS_YMC = np.asarray(
    [
        [0.58, 0.38, 0.18],
        [0.84, 0.30, 0.12],
        [1.00, 0.24, 0.06],
        [0.93, 0.23, 0.03],
        [0.64, 0.37, 0.02],
        [0.31, 0.62, 0.02],
        [0.12, 0.89, 0.02],
        [0.04, 1.00, 0.04],
        [0.02, 0.88, 0.08],
        [0.00, 0.61, 0.18],
        [0.00, 0.34, 0.40],
        [0.00, 0.18, 0.77],
        [0.00, 0.10, 1.00],
        [0.00, 0.06, 0.89],
        [0.00, 0.04, 0.66],
        [0.00, 0.02, 0.47],
    ],
    dtype=float,
)

RENDER_PASSES = (
    ("pypdf_native", None),
    ("poppler_600dpi", 600),
    ("poppler_900dpi", 900),
)
METHODS = ("thresholded_ink_centroid", "column_dark_core_median")

TYPICAL_READING_BOUND_D = 0.015
AXIS_OR_CURVE_OVERLAP_BOUND_D = 0.030
AXIS_OVERLAP_DENSITY = 0.055
NATIVE_LOCALIZATION_BOUND_PX = 1.5


@dataclass(frozen=True)
class AxisGeometry:
    left_x: float
    right_x: float
    top_y: float
    bottom_y: float

    @property
    def width_px(self) -> float:
        return self.right_x - self.left_x

    @property
    def height_px(self) -> float:
        return self.bottom_y - self.top_y

    def as_dict(self) -> dict[str, float]:
        return {
            "left_x": self.left_x,
            "right_x": self.right_x,
            "top_y": self.top_y,
            "bottom_y": self.bottom_y,
            "width_px": self.width_px,
            "height_px": self.height_px,
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _verify_source(reader: PdfReader) -> dict[str, Any]:
    if not SOURCE_PDF.is_file():
        raise FileNotFoundError(f"Required source PDF is missing: {SOURCE_PDF}")
    source_sha = _sha256(SOURCE_PDF)
    if source_sha != EXPECTED_PDF_SHA256:
        raise ValueError(
            "Source PDF SHA-256 mismatch: "
            f"expected {EXPECTED_PDF_SHA256}, got {source_sha}"
        )
    if len(reader.pages) != EXPECTED_PAGE_COUNT:
        raise ValueError(
            f"Expected {EXPECTED_PAGE_COUNT} PDF pages, got {len(reader.pages)}"
        )
    return {
        "path": str(SOURCE_PDF),
        "sha256": source_sha,
        "page_count": len(reader.pages),
        "figure_page_number_1_based": FIGURE_PAGE_NUMBER,
        "citation": (
            "Scarpace, F. L., and Friederichs, S. J. (1978), "
            "A Method of Determining Spectral Analytical Dye Densities, "
            "Photogrammetric Engineering and Remote Sensing 44(10), "
            "1293-1301, Figure 5."
        ),
        "public_source_url": (
            "https://www.asprs.org/wp-content/uploads/pers/1978journal/"
            "oct/1978_oct_1293-1301.pdf"
        ),
    }


def _extract_native_page_image(reader: PdfReader) -> Image.Image:
    page = reader.pages[FIGURE_PAGE_NUMBER - 1]
    images = list(page.images)
    if not images:
        raise ValueError("PDF page 5 contains no extractable raster image")
    largest = max(images, key=lambda item: item.image.width * item.image.height)
    image = largest.image.convert("L")
    if image.size != EXPECTED_NATIVE_PAGE_SIZE:
        raise ValueError(
            "Unexpected native page raster dimensions: "
            f"expected {EXPECTED_NATIVE_PAGE_SIZE}, got {image.size}"
        )
    return image


def _poppler_version(pdftoppm: str) -> str:
    result = subprocess.run(
        [pdftoppm, "-v"],
        check=True,
        capture_output=True,
        text=True,
    )
    return (result.stderr or result.stdout).splitlines()[0].strip()


def _render_poppler_page(
    pdftoppm: str,
    dpi: int,
    work_dir: Path,
) -> tuple[Image.Image, str]:
    prefix = work_dir / f"page-5-{dpi}dpi"
    result = subprocess.run(
        [
            pdftoppm,
            "-f",
            str(FIGURE_PAGE_NUMBER),
            "-l",
            str(FIGURE_PAGE_NUMBER),
            "-r",
            str(dpi),
            "-gray",
            "-png",
            "-singlefile",
            str(SOURCE_PDF),
            str(prefix),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rendered_path = prefix.with_suffix(".png")
    if not rendered_path.is_file():
        raise FileNotFoundError(f"Poppler did not create {rendered_path}")
    warning = result.stderr.strip()
    with Image.open(rendered_path) as loaded:
        image = loaded.convert("L").copy()
    return image, warning


def _line_center(
    gray: np.ndarray,
    *,
    orientation: str,
    expected: float,
    search_radius: int,
    span_start: float,
    span_end: float,
) -> tuple[float, float]:
    height, width = gray.shape
    limit = width if orientation == "vertical" else height
    start = max(0, int(round(expected)) - search_radius)
    stop = min(limit, int(round(expected)) + search_radius + 1)
    candidates = np.arange(start, stop, dtype=int)
    scores: list[float] = []
    for candidate in candidates:
        if orientation == "vertical":
            values = 255.0 - gray[
                int(round(span_start)) : int(round(span_end)), candidate
            ]
        else:
            values = 255.0 - gray[
                candidate, int(round(span_start)) : int(round(span_end))
            ]
        scores.append(float(np.mean(values)))
    score_array = np.asarray(scores, dtype=float)
    maximum = float(np.max(score_array))
    core = candidates[score_array >= 0.80 * maximum]
    if core.size == 0:
        raise ValueError(f"Could not detect {orientation} axis line")
    return float(np.mean(core)), maximum


def _detect_axes(image: Image.Image) -> tuple[AxisGeometry, dict[str, float]]:
    gray = np.asarray(image, dtype=float)
    height, width = gray.shape
    native_width, native_height = EXPECTED_NATIVE_PAGE_SIZE
    scale_x = width / native_width
    scale_y = height / native_height
    expected = AxisGeometry(
        left_x=NATIVE_AXIS_REFERENCE["left_x"] * scale_x,
        right_x=NATIVE_AXIS_REFERENCE["right_x"] * scale_x,
        top_y=NATIVE_AXIS_REFERENCE["top_y"] * scale_y,
        bottom_y=NATIVE_AXIS_REFERENCE["bottom_y"] * scale_y,
    )
    search_x = max(6, int(round(6.0 * scale_x)))
    search_y = max(6, int(round(6.0 * scale_y)))
    y_margin = 0.04 * expected.height_px
    x_margin = 0.04 * expected.width_px
    left_x, left_score = _line_center(
        gray,
        orientation="vertical",
        expected=expected.left_x,
        search_radius=search_x,
        span_start=expected.top_y + y_margin,
        span_end=expected.bottom_y - y_margin,
    )
    right_x, right_score = _line_center(
        gray,
        orientation="vertical",
        expected=expected.right_x,
        search_radius=search_x,
        span_start=expected.top_y + y_margin,
        span_end=expected.bottom_y - y_margin,
    )
    top_y, top_score = _line_center(
        gray,
        orientation="horizontal",
        expected=expected.top_y,
        search_radius=search_y,
        span_start=left_x + x_margin,
        span_end=right_x - x_margin,
    )
    bottom_y, bottom_score = _line_center(
        gray,
        orientation="horizontal",
        expected=expected.bottom_y,
        search_radius=search_y,
        span_start=left_x + x_margin,
        span_end=right_x - x_margin,
    )
    geometry = AxisGeometry(left_x, right_x, top_y, bottom_y)
    if geometry.width_px <= 0.0 or geometry.height_px <= 0.0:
        raise ValueError(f"Invalid detected axes: {geometry}")
    return geometry, {
        "left_ink_score": left_score,
        "right_ink_score": right_score,
        "top_ink_score": top_score,
        "bottom_ink_score": bottom_score,
    }


def _point_window(
    gray: np.ndarray,
    axes: AxisGeometry,
    wavelength_nm: float,
    seed_density: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    x_nominal = axes.left_x + (
        (wavelength_nm - 400.0) / 300.0
    ) * axes.width_px
    y_seed = axes.bottom_y - seed_density * axes.height_px
    radius_x = max(3, int(round(axes.width_px * (5.0 / 288.0))))
    radius_y = max(4, int(round(axes.height_px * (8.0 / 168.0))))
    x0 = max(0, int(round(x_nominal)) - radius_x)
    x1 = min(gray.shape[1], int(round(x_nominal)) + radius_x + 1)
    y0 = max(int(np.floor(axes.top_y)), int(round(y_seed)) - radius_y)
    y1 = min(
        int(np.ceil(axes.bottom_y)) + 1,
        int(round(y_seed)) + radius_y + 1,
    )
    patch = gray[y0:y1, x0:x1]
    yy, xx = np.mgrid[y0:y1, x0:x1]
    return patch, yy, xx, x_nominal, y_seed


def _measure_point(
    gray: np.ndarray,
    axes: AxisGeometry,
    wavelength_nm: float,
    seed_density: float,
    method: str,
) -> dict[str, float]:
    patch, yy, xx, x_nominal, y_seed = _point_window(
        gray,
        axes,
        wavelength_nm,
        seed_density,
    )
    if patch.size == 0:
        raise ValueError(f"Empty point window at {wavelength_nm} nm")
    if method == "thresholded_ink_centroid":
        weights = np.clip(225.0 - patch, 0.0, None) ** 1.2
        total = float(np.sum(weights))
        if total <= 0.0:
            raise ValueError(f"No thresholded ink at {wavelength_nm} nm")
        y_measured = float(np.sum(weights * yy) / total)
        x_measured = float(np.sum(weights * xx) / total)
    elif method == "column_dark_core_median":
        column_y: list[float] = []
        column_x: list[float] = []
        for column in range(patch.shape[1]):
            values = patch[:, column]
            darkest = float(np.min(values))
            if darkest >= 200.0:
                continue
            core = np.flatnonzero(values <= min(200.0, darkest + 8.0))
            if core.size:
                column_y.append(float(np.mean(core) + yy[0, 0]))
                column_x.append(float(xx[0, column]))
        if not column_y:
            raise ValueError(f"No dark core at {wavelength_nm} nm")
        y_measured = float(np.median(column_y))
        x_measured = float(np.median(column_x))
    else:
        raise ValueError(f"Unknown point method: {method}")
    raw_density = float(
        np.clip(
            (axes.bottom_y - y_measured) / axes.height_px,
            0.0,
            1.0,
        )
    )
    return {
        "x_nominal_px": x_nominal,
        "x_measured_px": x_measured,
        "y_seed_px": y_seed,
        "y_measured_px": y_measured,
        "raw_density": raw_density,
    }


def _measure_raster(
    pass_name: str,
    image: Image.Image,
    render_dpi: int | None,
    poppler_warning: str,
) -> tuple[dict[str, Any], dict[str, np.ndarray]]:
    axes, axis_scores = _detect_axes(image)
    gray = np.asarray(image, dtype=float)
    method_arrays: dict[str, np.ndarray] = {}
    point_details: dict[str, dict[str, list[dict[str, float]]]] = {}
    for method in METHODS:
        raw = np.zeros((len(WAVELENGTHS_NM), len(CHANNELS)), dtype=float)
        method_details: dict[str, list[dict[str, float]]] = {}
        for channel_index, channel in enumerate(CHANNELS):
            details: list[dict[str, float]] = []
            for wavelength_index, wavelength_nm in enumerate(WAVELENGTHS_NM):
                measured = _measure_point(
                    gray,
                    axes,
                    float(wavelength_nm),
                    float(TRACKING_SEEDS_YMC[wavelength_index, channel_index]),
                    method,
                )
                raw[wavelength_index, channel_index] = measured["raw_density"]
                details.append(measured)
            peak = float(np.max(raw[:, channel_index]))
            if peak <= 0.0:
                raise ValueError(f"Zero {channel} peak in {pass_name}/{method}")
            raw[:, channel_index] /= peak
            for row_index, detail in enumerate(details):
                detail["normalized_density"] = float(
                    raw[row_index, channel_index]
                )
            method_details[channel] = details
        method_arrays[method] = raw
        point_details[method] = method_details
    width, height = image.size
    report = {
        "name": pass_name,
        "rasterizer": "pypdf-native-xobject" if render_dpi is None else "Poppler",
        "render_dpi": render_dpi,
        "image_size_px": [width, height],
        "axis_geometry_px": axes.as_dict(),
        "axis_ink_scores": axis_scores,
        "poppler_warning": poppler_warning or None,
        "point_measurements": point_details,
    }
    return report, method_arrays


def _consensus(
    measurements: dict[str, dict[str, np.ndarray]],
    native_axes: AxisGeometry,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    stack = np.stack(
        [
            measurements[pass_name][method]
            for pass_name, _ in RENDER_PASSES
            for method in METHODS
        ]
    )
    consensus = np.median(stack, axis=0)
    consensus /= np.max(consensus, axis=0)
    minimum = np.min(stack, axis=0)
    maximum = np.max(stack, axis=0)
    half_range = 0.5 * (maximum - minimum)
    native_pixel_density = 1.0 / native_axes.height_px
    uncertainty = np.maximum(
        TYPICAL_READING_BOUND_D,
        half_range + native_pixel_density,
    )
    overlap = consensus <= AXIS_OVERLAP_DENSITY
    uncertainty[overlap] = np.maximum(
        uncertainty[overlap], AXIS_OR_CURVE_OVERLAP_BOUND_D
    )
    return consensus, uncertainty, half_range, stack


def _load_profile_comparison(
    figure_ymc: np.ndarray,
) -> tuple[dict[str, Any], np.ndarray, np.ndarray]:
    profile_sha_before = _sha256(PROFILE_PATH)
    with PROFILE_PATH.open(encoding="utf-8") as handle:
        profile = json.load(handle)
    data = profile["data"]
    profile_data_sha = _canonical_json_sha256(data)
    profile_wavelengths = np.asarray(data["wavelengths"], dtype=float)
    channel_density = np.asarray(data["channel_density"], dtype=float)
    all_channels_finite = np.all(np.isfinite(channel_density), axis=1)
    finite_wavelengths = profile_wavelengths[all_channels_finite]
    if finite_wavelengths.size == 0:
        raise ValueError("Bundled K64 profile has no common finite channel range")
    common = (
        (WAVELENGTHS_NM >= finite_wavelengths.min())
        & (WAVELENGTHS_NM <= finite_wavelengths.max())
    )
    common_wavelengths = WAVELENGTHS_NM[common]
    figure_common = figure_ymc[common]

    profile_full_ymc = channel_density[all_channels_finite][
        :, [PROFILE_CHANNEL_INDEX[channel] for channel in CHANNELS]
    ]
    profile_full_ymc /= np.max(profile_full_ymc, axis=0)
    profile_sampled = np.column_stack(
        [
            np.interp(
                common_wavelengths,
                finite_wavelengths,
                profile_full_ymc[:, channel_index],
            )
            for channel_index in range(len(CHANNELS))
        ]
    )
    channels: dict[str, Any] = {}
    for channel_index, channel in enumerate(CHANNELS):
        figure_curve = figure_common[:, channel_index]
        profile_curve = profile_sampled[:, channel_index]
        cosine = float(
            np.dot(figure_curve, profile_curve)
            / (
                np.linalg.norm(figure_curve)
                * np.linalg.norm(profile_curve)
            )
        )
        channels[channel] = {
            "cosine_similarity": cosine,
            "rmse_normalized_density": float(
                np.sqrt(np.mean(np.square(figure_curve - profile_curve)))
            ),
            "mae_normalized_density": float(
                np.mean(np.abs(figure_curve - profile_curve))
            ),
            "figure_marker_peak_nm": float(
                common_wavelengths[np.argmax(figure_curve)]
            ),
            "profile_20nm_sample_peak_nm": float(
                common_wavelengths[np.argmax(profile_curve)]
            ),
            "profile_full_grid_peak_nm": float(
                finite_wavelengths[
                    np.argmax(profile_full_ymc[:, channel_index])
                ]
            ),
            "profile_full_grid_interval_nm": 5.0,
        }
    overall_rmse = float(
        np.sqrt(np.mean(np.square(figure_common - profile_sampled)))
    )
    comparison = {
        "profile_path": str(PROFILE_PATH),
        "profile_file_sha256_before": profile_sha_before,
        "profile_data_sha256": profile_data_sha,
        "profile_channel_order": ["C", "M", "Y"],
        "comparison_channel_order": list(CHANNELS),
        "comparison_wavelengths_nm": common_wavelengths.tolist(),
        "comparison_range_reason": (
            "Figure data are 400-700 nm, but all three bundled profile "
            "channels are jointly finite only from 425-695 nm. The common "
            "printed 20 nm markers are therefore 440-680 nm. No endpoint "
            "extrapolation is used."
        ),
        "normalization": (
            "Each figure curve is normalized to its printed unit peak. Each "
            "profile curve is normalized to its maximum on the full common "
            "finite 5 nm profile grid before 20 nm sampling."
        ),
        "channels": channels,
        "overall_rmse_normalized_density": overall_rmse,
        "shape_consistency_gate": {
            "cosine_similarity_minimum": 0.99,
            "rmse_maximum_normalized_density": 0.03,
            "peak_difference_maximum_nm": 20.0,
            "passed": bool(
                all(
                    metrics["cosine_similarity"] >= 0.99
                    and metrics["rmse_normalized_density"] <= 0.03
                    and abs(
                        metrics["figure_marker_peak_nm"]
                        - metrics["profile_full_grid_peak_nm"]
                    )
                    <= 20.0
                    for metrics in channels.values()
                )
            ),
        },
    }
    return comparison, common_wavelengths, profile_sampled


def _write_csv(
    path: Path,
    consensus: np.ndarray,
    uncertainty: np.ndarray,
    half_range: np.ndarray,
    measurements: dict[str, dict[str, np.ndarray]],
) -> None:
    pass_method_pairs = [
        (pass_name, method)
        for pass_name, _ in RENDER_PASSES
        for method in METHODS
    ]
    fieldnames = ["wavelength_nm"]
    for channel in CHANNELS:
        fieldnames.extend(
            [
                f"{channel}_consensus_normalized_density",
                f"{channel}_conservative_bound_density",
                f"{channel}_method_pass_half_range",
                f"{channel}_axis_or_curve_overlap",
            ]
        )
        fieldnames.extend(
            f"{channel}_{pass_name}_{method}"
            for pass_name, method in pass_method_pairs
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row_index, wavelength_nm in enumerate(WAVELENGTHS_NM):
            row: dict[str, str] = {"wavelength_nm": f"{wavelength_nm:.1f}"}
            for channel_index, channel in enumerate(CHANNELS):
                value = consensus[row_index, channel_index]
                row[f"{channel}_consensus_normalized_density"] = f"{value:.6f}"
                row[f"{channel}_conservative_bound_density"] = (
                    f"{uncertainty[row_index, channel_index]:.6f}"
                )
                row[f"{channel}_method_pass_half_range"] = (
                    f"{half_range[row_index, channel_index]:.6f}"
                )
                row[f"{channel}_axis_or_curve_overlap"] = str(
                    bool(value <= AXIS_OVERLAP_DENSITY)
                ).lower()
                for pass_name, method in pass_method_pairs:
                    row[f"{channel}_{pass_name}_{method}"] = (
                        f"{measurements[pass_name][method][row_index, channel_index]:.6f}"
                    )
            writer.writerow(row)


def _write_source_overlay(
    path: Path,
    image: Image.Image,
    axes: AxisGeometry,
    consensus: np.ndarray,
) -> None:
    gray = np.asarray(image)
    margin_x = int(round(0.08 * axes.width_px))
    margin_y_top = int(round(0.10 * axes.height_px))
    margin_y_bottom = int(round(0.30 * axes.height_px))
    x0 = max(0, int(np.floor(axes.left_x)) - margin_x)
    x1 = min(gray.shape[1], int(np.ceil(axes.right_x)) + margin_x)
    y0 = max(0, int(np.floor(axes.top_y)) - margin_y_top)
    y1 = min(gray.shape[0], int(np.ceil(axes.bottom_y)) + margin_y_bottom)

    figure, axis = plt.subplots(figsize=(12, 7), dpi=160)
    axis.imshow(gray[y0:y1, x0:x1], cmap="gray", vmin=0, vmax=255)
    colors = {"Y": "#e2ad00", "M": "#cf2c82", "C": "#00a5a8"}
    for channel_index, channel in enumerate(CHANNELS):
        x = axes.left_x + (
            (WAVELENGTHS_NM - 400.0) / 300.0
        ) * axes.width_px
        y = axes.bottom_y - consensus[:, channel_index] * axes.height_px
        axis.plot(
            x - x0,
            y - y0,
            color=colors[channel],
            marker="o",
            markersize=3.5,
            linewidth=1.2,
            label=f"{channel} consensus",
        )
    axis.set_title(
        "K64 Figure 5 - axis-calibrated 20 nm consensus overlay\n"
        "Colored points are audit overlays; the source scan remains unchanged."
    )
    axis.set_axis_off()
    axis.legend(loc="upper center", ncols=3, framealpha=0.85)
    figure.tight_layout()
    figure.savefig(
        path,
        bbox_inches="tight",
        metadata={"Software": "Spektrafilm closed-evidence audit"},
    )
    plt.close(figure)


def _write_profile_comparison_plot(
    path: Path,
    consensus: np.ndarray,
    uncertainty: np.ndarray,
    common_wavelengths: np.ndarray,
    profile_sampled: np.ndarray,
) -> None:
    common = np.isin(WAVELENGTHS_NM, common_wavelengths)
    colors = {"Y": "#d49b00", "M": "#c02b76", "C": "#008f92"}
    figure, axes = plt.subplots(3, 1, figsize=(9, 10), dpi=160, sharex=True)
    for channel_index, (axis, channel) in enumerate(zip(axes, CHANNELS)):
        axis.errorbar(
            WAVELENGTHS_NM,
            consensus[:, channel_index],
            yerr=uncertainty[:, channel_index],
            color=colors[channel],
            marker="o",
            markersize=4,
            linewidth=1.4,
            elinewidth=0.8,
            capsize=2,
            label="Figure 5 digitization",
        )
        axis.plot(
            common_wavelengths,
            profile_sampled[:, channel_index],
            color="#222222",
            marker="s",
            markersize=3,
            linewidth=1.2,
            label="Bundled profile (common finite range)",
        )
        axis.axvspan(400.0, 440.0, color="#dddddd", alpha=0.25)
        axis.axvspan(680.0, 700.0, color="#dddddd", alpha=0.25)
        axis.set_ylabel(f"{channel} density\n(unit peak)")
        axis.set_ylim(-0.06, 1.08)
        axis.grid(alpha=0.2)
        if channel_index == 0:
            axis.legend(loc="upper right")
        axis.scatter(
            WAVELENGTHS_NM[~common],
            consensus[~common, channel_index],
            facecolors="none",
            edgecolors=colors[channel],
            s=24,
            zorder=4,
        )
    axes[-1].set_xlabel("Wavelength (nm)")
    figure.suptitle(
        "Kodachrome 64: 1978 Figure 5 vs bundled normalized channel density\n"
        "Open circles/shading mark figure-only endpoints; no profile extrapolation."
    )
    figure.tight_layout(rect=(0, 0, 1, 0.95))
    figure.savefig(
        path,
        metadata={"Software": "Spektrafilm closed-evidence audit"},
    )
    plt.close(figure)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(SOURCE_PDF)
    source_report = _verify_source(reader)
    native_image = _extract_native_page_image(reader)
    pdftoppm = shutil.which("pdftoppm")
    if pdftoppm is None:
        raise FileNotFoundError("pdftoppm is required for independent renders")

    pass_reports: dict[str, dict[str, Any]] = {}
    measurements: dict[str, dict[str, np.ndarray]] = {}
    images: dict[str, Image.Image] = {"pypdf_native": native_image}
    poppler_warnings: dict[str, str] = {"pypdf_native": ""}
    with tempfile.TemporaryDirectory(
        prefix="k64-figure5-", dir=PDF_TEMP_ROOT
    ) as temporary:
        temporary_dir = Path(temporary)
        for pass_name, render_dpi in RENDER_PASSES:
            if render_dpi is not None:
                image, warning = _render_poppler_page(
                    pdftoppm,
                    render_dpi,
                    temporary_dir,
                )
                images[pass_name] = image
                poppler_warnings[pass_name] = warning
            report, pass_measurements = _measure_raster(
                pass_name,
                images[pass_name],
                render_dpi,
                poppler_warnings[pass_name],
            )
            pass_reports[pass_name] = report
            measurements[pass_name] = pass_measurements

    native_axes_dict = pass_reports["pypdf_native"]["axis_geometry_px"]
    native_axes = AxisGeometry(
        left_x=float(native_axes_dict["left_x"]),
        right_x=float(native_axes_dict["right_x"]),
        top_y=float(native_axes_dict["top_y"]),
        bottom_y=float(native_axes_dict["bottom_y"]),
    )
    consensus, uncertainty, half_range, stack = _consensus(
        measurements,
        native_axes,
    )
    comparison, common_wavelengths, profile_sampled = _load_profile_comparison(
        consensus
    )

    csv_path = OUTPUT_DIR / "k64_figure5_digitized.csv"
    overlay_path = OUTPUT_DIR / "k64_figure5_source_overlay.png"
    comparison_plot_path = OUTPUT_DIR / "k64_figure5_profile_comparison.png"
    report_path = OUTPUT_DIR / "k64_figure5_digitization.json"
    _write_csv(csv_path, consensus, uncertainty, half_range, measurements)
    overlay_axes_dict = pass_reports["poppler_600dpi"]["axis_geometry_px"]
    overlay_axes = AxisGeometry(
        left_x=float(overlay_axes_dict["left_x"]),
        right_x=float(overlay_axes_dict["right_x"]),
        top_y=float(overlay_axes_dict["top_y"]),
        bottom_y=float(overlay_axes_dict["bottom_y"]),
    )
    _write_source_overlay(
        overlay_path,
        images["poppler_600dpi"],
        overlay_axes,
        consensus,
    )
    _write_profile_comparison_plot(
        comparison_plot_path,
        consensus,
        uncertainty,
        common_wavelengths,
        profile_sampled,
    )

    native_pixel_density = 1.0 / native_axes.height_px
    native_pixel_wavelength = 300.0 / native_axes.width_px
    points: list[dict[str, Any]] = []
    for row_index, wavelength_nm in enumerate(WAVELENGTHS_NM):
        row: dict[str, Any] = {"wavelength_nm": float(wavelength_nm)}
        for channel_index, channel in enumerate(CHANNELS):
            row[channel] = {
                "consensus_normalized_density": float(
                    consensus[row_index, channel_index]
                ),
                "conservative_reading_bound_density": float(
                    uncertainty[row_index, channel_index]
                ),
                "method_pass_half_range": float(
                    half_range[row_index, channel_index]
                ),
                "axis_or_curve_overlap": bool(
                    consensus[row_index, channel_index]
                    <= AXIS_OVERLAP_DENSITY
                ),
            }
        points.append(row)

    artifact_hashes = {
        csv_path.name: _sha256(csv_path),
        overlay_path.name: _sha256(overlay_path),
        comparison_plot_path.name: _sha256(comparison_plot_path),
    }
    report = {
        "schema_version": 1,
        "source": source_report,
        "script": {
            "path": str(Path(__file__).resolve()),
            "sha256": _sha256(Path(__file__).resolve()),
        },
        "tools": {
            "pypdf_version": __import__("pypdf").__version__,
            "poppler": _poppler_version(pdftoppm),
            "numpy_version": np.__version__,
            "matplotlib_version": matplotlib.__version__,
            "pillow_version": __import__("PIL").__version__,
        },
        "figure_semantics": {
            "printed_wavelength_range_nm": [400.0, 700.0],
            "printed_marker_interval_nm": 20.0,
            "output_wavelengths_nm": WAVELENGTHS_NM.tolist(),
            "density_semantics": "unit-peak spectral dye density",
            "no_extrapolation": True,
            "classification": (
                "manufacturer-prior-oriented effective/source reconstruction"
            ),
            "classification_reason": (
                "The paper measured 330 physical Kodachrome 64 patches, but "
                "its characteristic-vector solution was rotated/oriented "
                "toward representative manufacturer dye curves. Figure 5 is "
                "therefore physical-patch-constrained evidence, not a unique "
                "blind analytical separation and not an absolute-density "
                "profile replacement."
            ),
        },
        "raster_information_limit": {
            "native_page_size_px": list(EXPECTED_NATIVE_PAGE_SIZE),
            "native_axis_size_px": [
                native_axes.width_px,
                native_axes.height_px,
            ],
            "one_native_axis_pixel_nm": native_pixel_wavelength,
            "one_native_axis_pixel_density": native_pixel_density,
            "localization_bound_native_px": NATIVE_LOCALIZATION_BOUND_PX,
            "localization_bound_nm": (
                NATIVE_LOCALIZATION_BOUND_PX * native_pixel_wavelength
            ),
            "localization_bound_density": (
                NATIVE_LOCALIZATION_BOUND_PX * native_pixel_density
            ),
            "typical_conservative_reading_bound_density": (
                TYPICAL_READING_BOUND_D
            ),
            "axis_or_curve_overlap_reading_bound_density": (
                AXIS_OR_CURVE_OVERLAP_BOUND_D
            ),
            "interpretation": (
                "600/900 dpi rendering is a resampling stability check. It "
                "does not exceed the information content of the native scan. "
                "Bounds are conservative reading bounds, not statistical "
                "confidence intervals or instrument uncertainty."
            ),
        },
        "digitization_design": {
            "passes": [name for name, _ in RENDER_PASSES],
            "methods": list(METHODS),
            "measurement_count_per_channel_point": int(stack.shape[0]),
            "consensus": "median of 3 raster passes x 2 point-reading methods",
            "channel_peak_normalization": True,
            "tracking_seed_role": (
                "Selects a narrow local source-ink window only; values are "
                "not copied into the output."
            ),
        },
        "raster_passes": pass_reports,
        "points": points,
        "profile_comparison": comparison,
        "decision": {
            "evidence_role": "validation-only",
            "supports_current_normalized_shape": bool(
                comparison["shape_consistency_gate"]["passed"]
            ),
            "allows_default_profile_replacement": False,
            "reason": (
                "The normalized shapes agree on the non-extrapolated common "
                "range, but Figure 5 supplies neither raw 330 x 16 spectra, "
                "absolute dye amplitudes, same-roll base-plus-fog, processing "
                "metadata, nor a unique manufacturer-independent separation."
            ),
            "profile_numeric_arrays_modified": False,
        },
        "artifact_sha256": artifact_hashes,
    }
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    profile_sha_after = _sha256(PROFILE_PATH)
    if profile_sha_after != comparison["profile_file_sha256_before"]:
        raise RuntimeError("Bundled K64 profile changed while audit was running")

    result = {
        "source_pdf_sha256": source_report["sha256"],
        "script_sha256": report["script"]["sha256"],
        "output_dir": str(OUTPUT_DIR),
        "profile_unchanged": True,
        "shape_consistency_gate_passed": comparison["shape_consistency_gate"][
            "passed"
        ],
        "overall_rmse_normalized_density": comparison[
            "overall_rmse_normalized_density"
        ],
        "channel_metrics": comparison["channels"],
        "artifacts": {
            **artifact_hashes,
            report_path.name: _sha256(report_path),
        },
    }
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
