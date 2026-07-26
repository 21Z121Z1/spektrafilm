#!/usr/bin/env python3
"""Extract and compare published Fujifilm spectral dye-density curves.

This analysis is intentionally separate from bundled profile generation.  It
verifies exact manufacturer-PDF hashes, reads vector Bezier paths where they
exist, reads the separated one-bit colour masks in the Provia product sheet,
and writes only local audit artifacts under ``tmp/``.

The published reversal-film curves are same-stock manufacturer measurements
made after separated-light exposure and normalized to a density level of 1.0.
They are representative production data, not retained raw observations for a
particular roll.  Consequently this script calls them ``source-derived``
shape evidence and never labels them raw instrument measurements.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable
import urllib.request

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pypdf
from pypdf import PdfReader
from pypdf.generic import ContentStream


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PDF_DIR = PROJECT_ROOT / "tmp" / "pdfs" / "profile-curves"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "tmp" / "profile-source-curves" / "fuji"
PROFILE_DIR = PROJECT_ROOT / "src" / "spektrafilm" / "data" / "profiles"
PROFILE_GRID = np.arange(400.0, 700.0 + 0.1, 5.0)
USER_AGENT = "Mozilla/5.0 Spektrafilm source-curve evidence audit"


@dataclass(frozen=True)
class PdfSpec:
    key: str
    filename: str
    url: str
    sha256: str


@dataclass(frozen=True)
class AxisCalibration:
    x_coordinates: tuple[float, ...]
    wavelengths_nm: tuple[float, ...]
    y_coordinates: tuple[float, ...]
    densities: tuple[float, ...]
    coordinate_space: str


@dataclass(frozen=True)
class VectorCurveSpec:
    source_key: str
    page_index: int
    painted_path_index: int
    axis: AxisCalibration


PDF_SPECS = {
    "provia_product_2000": PdfSpec(
        key="provia_product_2000",
        filename="provia100f_in_2000.pdf",
        url=(
            "https://asset.fujifilm.com/www/in/files/2020-07/"
            "0b154ed25442c231feccf22032620306/"
            "films_provia-100f_datasheet_01.pdf"
        ),
        sha256=(
            "e28d54e76e8fcdf44c8ffacc930b5b8f2ea54a7cdaeedfcc91790e68eb599de8"
        ),
    ),
    "velvia_product_2005": PdfSpec(
        key="velvia_product_2005",
        filename="velvia100_af3-202e.pdf",
        url=(
            "https://asset.fujifilm.com/www/in/files/2020-07/"
            "053a4dd52b58d6f75cd3ad35dd03998c/"
            "films_velvia-100_datasheet_01.pdf"
        ),
        sha256=(
            "4c57a27b978311ca2ef819f2bf2d74c757639d27f9f0bd94e5f49c4b1c3d5902"
        ),
    ),
    "professional_data_guide_2005": PdfSpec(
        key="professional_data_guide_2005",
        filename="fujifilm_professional_film_data_guide.pdf",
        url=(
            "https://asset.fujifilm.com/www/ca/files/2020-04/"
            "9cdee030ab7fc76bbcfddbcd38650038/"
            "ProfessionalFilmDataGuide.pdf"
        ),
        sha256=(
            "64c6455651b9f13f5cd190219e4928d1fdf13ecf33859c4691d830bced8d3d36"
        ),
    ),
}


VELVIA_PRODUCT_VECTOR = VectorCurveSpec(
    source_key="velvia_product_2005",
    page_index=7,
    painted_path_index=8,
    axis=AxisCalibration(
        x_coordinates=(344.970, 404.430, 463.323, 522.190),
        wavelengths_nm=(400.0, 500.0, 600.0, 700.0),
        y_coordinates=(197.186, 256.725, 316.267),
        densities=(0.0, 0.5, 1.0),
        coordinate_space="PDF user coordinates (bottom-left origin)",
    ),
)


VELVIA_GUIDE_VECTOR = VectorCurveSpec(
    source_key="professional_data_guide_2005",
    page_index=23,
    painted_path_index=25,
    axis=AxisCalibration(
        x_coordinates=(507.369, 536.369, 565.369, 593.619),
        wavelengths_nm=(400.0, 500.0, 600.0, 700.0),
        y_coordinates=(398.545, 426.629, 454.629),
        densities=(0.0, 0.5, 1.0),
        coordinate_space="PDF user coordinates (bottom-left origin)",
    ),
)


PROVIA_GUIDE_VECTOR = VectorCurveSpec(
    source_key="professional_data_guide_2005",
    page_index=24,
    painted_path_index=25,
    axis=AxisCalibration(
        x_coordinates=(508.388, 537.388, 565.638, 593.701),
        wavelengths_nm=(400.0, 500.0, 600.0, 700.0),
        y_coordinates=(399.945, 435.529, 468.529),
        densities=(0.0, 0.5, 1.0),
        coordinate_space="PDF user coordinates (bottom-left origin)",
    ),
)


PROVIA_PRODUCT_AXIS = AxisCalibration(
    x_coordinates=(112.5, 163.0, 414.5, 656.0, 903.5, 951.5),
    wavelengths_nm=(380.0, 400.0, 500.0, 600.0, 700.0, 720.0),
    y_coordinates=(628.0, 381.0, 127.0),
    densities=(0.0, 0.5, 1.0),
    coordinate_space="embedded 972x734 image-mask pixels (top-left origin)",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _ensure_pdf(spec: PdfSpec, pdf_dir: Path, download_missing: bool) -> Path:
    path = pdf_dir / spec.filename
    if not path.exists():
        if not download_missing:
            raise FileNotFoundError(
                f"Missing {path}; rerun with --download-missing or place the PDF there"
            )
        pdf_dir.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            spec.url,
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        path.write_bytes(data)
    actual = _sha256(path)
    if actual != spec.sha256:
        raise ValueError(
            f"Unexpected SHA-256 for {path}: expected {spec.sha256}, got {actual}"
        )
    return path


def _piecewise_map(
    values: np.ndarray,
    coordinates: Iterable[float],
    physical_values: Iterable[float],
) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64)
    xp = np.asarray(tuple(coordinates), dtype=np.float64)
    fp = np.asarray(tuple(physical_values), dtype=np.float64)
    order = np.argsort(xp)
    xp = xp[order]
    fp = fp[order]
    result = np.interp(values, xp, fp)
    left = values < xp[0]
    right = values > xp[-1]
    if np.any(left):
        slope = (fp[1] - fp[0]) / (xp[1] - xp[0])
        result[left] = fp[0] + (values[left] - xp[0]) * slope
    if np.any(right):
        slope = (fp[-1] - fp[-2]) / (xp[-1] - xp[-2])
        result[right] = fp[-1] + (values[right] - xp[-1]) * slope
    return result


def _affine_map(
    values: np.ndarray,
    coordinates: Iterable[float],
    physical_values: Iterable[float],
) -> np.ndarray:
    coefficients = np.polyfit(
        np.asarray(tuple(coordinates), dtype=np.float64),
        np.asarray(tuple(physical_values), dtype=np.float64),
        1,
    )
    return np.polyval(coefficients, np.asarray(values, dtype=np.float64))


def _axis_to_data(
    x: np.ndarray,
    y: np.ndarray,
    axis: AxisCalibration,
    *,
    affine: bool = False,
) -> tuple[np.ndarray, np.ndarray]:
    mapper = _affine_map if affine else _piecewise_map
    wavelengths = mapper(x, axis.x_coordinates, axis.wavelengths_nm)
    densities = mapper(y, axis.y_coordinates, axis.densities)
    return wavelengths, densities


def _split_subpaths(commands: list[tuple[bytes, list[float]]]):
    subpaths: list[list[tuple[bytes, list[float]]]] = []
    current: list[tuple[bytes, list[float]]] = []
    for operator, operands in commands:
        if operator == b"m":
            if current:
                subpaths.append(current)
            current = [(operator, operands)]
        elif current:
            current.append((operator, operands))
    if current:
        subpaths.append(current)
    return subpaths


def _painted_paths(reader: PdfReader, page_index: int):
    page = reader.pages[page_index]
    content = ContentStream(page.get_contents(), reader)
    current: list[tuple[bytes, list[float]]] = []
    painted: list[dict[str, Any]] = []
    stroke_operators = {b"S", b"s", b"B", b"B*", b"b", b"b*"}
    paint_operators = stroke_operators | {b"f", b"f*", b"F", b"n"}
    path_operators = {b"m", b"l", b"c", b"v", b"y", b"h", b"re"}
    for operands, operator in content.operations:
        if operator in path_operators:
            current.append((operator, [float(value) for value in operands]))
        elif operator in paint_operators:
            if current and operator in stroke_operators:
                painted.append(
                    {
                        "paint_operator": operator.decode("ascii"),
                        "commands": current.copy(),
                    }
                )
            current = []
    return painted


def _sample_subpath(
    commands: list[tuple[bytes, list[float]]],
    samples_per_segment: int,
) -> tuple[np.ndarray, np.ndarray]:
    if not commands or commands[0][0] != b"m":
        raise ValueError("A sampled subpath must begin with a move command")
    current = np.asarray(commands[0][1], dtype=np.float64)
    start = current.copy()
    xs = [float(current[0])]
    ys = [float(current[1])]

    def append_cubic(p0, p1, p2, p3):
        t = np.linspace(0.0, 1.0, samples_per_segment + 1)[1:]
        omt = 1.0 - t
        points = (
            omt[:, None] ** 3 * p0
            + 3.0 * omt[:, None] ** 2 * t[:, None] * p1
            + 3.0 * omt[:, None] * t[:, None] ** 2 * p2
            + t[:, None] ** 3 * p3
        )
        xs.extend(points[:, 0].tolist())
        ys.extend(points[:, 1].tolist())

    for operator, operands in commands[1:]:
        if operator == b"l":
            end = np.asarray(operands, dtype=np.float64)
            t = np.linspace(0.0, 1.0, samples_per_segment + 1)[1:]
            points = current + (end - current) * t[:, None]
            xs.extend(points[:, 0].tolist())
            ys.extend(points[:, 1].tolist())
            current = end
        elif operator == b"c":
            values = np.asarray(operands, dtype=np.float64).reshape(3, 2)
            append_cubic(current, values[0], values[1], values[2])
            current = values[2]
        elif operator == b"v":
            values = np.asarray(operands, dtype=np.float64).reshape(2, 2)
            append_cubic(current, current, values[0], values[1])
            current = values[1]
        elif operator == b"y":
            values = np.asarray(operands, dtype=np.float64).reshape(2, 2)
            append_cubic(current, values[0], values[1], values[1])
            current = values[1]
        elif operator == b"h":
            t = np.linspace(0.0, 1.0, samples_per_segment + 1)[1:]
            points = current + (start - current) * t[:, None]
            xs.extend(points[:, 0].tolist())
            ys.extend(points[:, 1].tolist())
            current = start.copy()
        else:
            raise ValueError(f"Unsupported path operator {operator!r}")
    return np.asarray(xs), np.asarray(ys)


def _resample_monotonic(
    wavelengths: np.ndarray,
    densities: np.ndarray,
    grid: np.ndarray,
) -> np.ndarray:
    order = np.argsort(wavelengths, kind="stable")
    wavelengths = wavelengths[order]
    densities = densities[order]
    unique_wavelengths, inverse = np.unique(wavelengths, return_inverse=True)
    if len(unique_wavelengths) != len(wavelengths):
        sums = np.bincount(inverse, weights=densities)
        counts = np.bincount(inverse)
        densities = sums / counts
        wavelengths = unique_wavelengths
    if grid[0] < wavelengths[0] or grid[-1] > wavelengths[-1]:
        raise ValueError(
            f"Curve support {wavelengths[0]:.3f}-{wavelengths[-1]:.3f} nm "
            f"does not cover requested {grid[0]:.3f}-{grid[-1]:.3f} nm"
        )
    return np.interp(grid, wavelengths, densities)


def _assign_channels(curves: list[np.ndarray], grid: np.ndarray):
    assigned: dict[str, np.ndarray] = {}
    peak_locations: dict[str, float] = {}
    for curve in curves:
        peak = float(grid[int(np.argmax(curve))])
        if peak < 500.0:
            channel = "Y"
        elif peak < 600.0:
            channel = "M"
        else:
            channel = "C"
        if channel in assigned:
            raise ValueError(f"Multiple extracted curves assigned to {channel}")
        assigned[channel] = curve
        peak_locations[channel] = peak
    if set(assigned) != {"Y", "M", "C"}:
        raise ValueError(f"Incomplete channel assignment: {sorted(assigned)}")
    return assigned, peak_locations


def _extract_vector_curves(
    spec: VectorCurveSpec,
    paths: dict[str, Path],
    *,
    samples_per_segment: int,
    affine_axis: bool = False,
):
    reader = PdfReader(paths[spec.source_key])
    painted = _painted_paths(reader, spec.page_index)
    try:
        selected = painted[spec.painted_path_index]
    except IndexError as exc:
        raise ValueError(
            f"Painted path index {spec.painted_path_index} missing in "
            f"{spec.source_key} page {spec.page_index + 1}"
        ) from exc
    subpaths = _split_subpaths(selected["commands"])
    curve_subpaths = [
        subpath
        for subpath in subpaths
        if sum(operator in {b"c", b"v", b"y"} for operator, _ in subpath) >= 2
    ]
    if len(curve_subpaths) != 3:
        raise ValueError(
            f"Expected exactly three curve subpaths, got {len(curve_subpaths)}"
        )
    curves: list[np.ndarray] = []
    source_ranges = []
    for subpath in curve_subpaths:
        x, y = _sample_subpath(subpath, samples_per_segment)
        wavelength, density = _axis_to_data(
            x,
            y,
            spec.axis,
            affine=affine_axis,
        )
        source_ranges.append(
            {
                "wavelength_min_nm": float(np.min(wavelength)),
                "wavelength_max_nm": float(np.max(wavelength)),
                "density_min": float(np.min(density)),
                "density_max": float(np.max(density)),
            }
        )
        curves.append(
            np.maximum(
                _resample_monotonic(wavelength, density, PROFILE_GRID),
                0.0,
            )
        )
    assigned, peaks = _assign_channels(curves, PROFILE_GRID)
    return {
        "channels": assigned,
        "peaks_nm": peaks,
        "source_ranges": source_ranges,
        "painted_path_count": len(painted),
        "selected_painted_path_index": spec.painted_path_index,
        "selected_paint_operator": selected["paint_operator"],
        "curve_subpath_count": len(curve_subpaths),
        "samples_per_segment": samples_per_segment,
    }


def _extract_provia_product_curves(
    paths: dict[str, Path],
    *,
    affine_axis: bool = False,
    center_method: str = "median",
):
    if center_method not in {"median", "midrange"}:
        raise ValueError("center_method must be 'median' or 'midrange'")
    reader = PdfReader(paths["provia_product_2000"])
    page = reader.pages[5]
    images = {image.name: image.image for image in page.images}
    names = {"Y": "Im64.tiff", "M": "Im65.tiff", "C": "Im66.tiff"}
    channels: dict[str, np.ndarray] = {}
    thickness: dict[str, dict[str, float]] = {}
    source_ranges = {}
    for channel, name in names.items():
        if name not in images:
            raise ValueError(f"Expected separated image mask {name} was not found")
        mask = np.asarray(images[name].convert("L")) < 128
        populated_columns = np.flatnonzero(mask.any(axis=0))
        centers = []
        low_rows = []
        high_rows = []
        for x in populated_columns:
            rows = np.flatnonzero(mask[:, x])
            if center_method == "median":
                centers.append(float(np.median(rows)))
            else:
                centers.append(float(0.5 * (np.min(rows) + np.max(rows))))
            low_rows.append(float(np.min(rows)))
            high_rows.append(float(np.max(rows)))
        x = populated_columns.astype(np.float64)
        center_y = np.asarray(centers)
        low_y = np.asarray(low_rows)
        high_y = np.asarray(high_rows)
        wavelength, density = _axis_to_data(
            x,
            center_y,
            PROVIA_PRODUCT_AXIS,
            affine=affine_axis,
        )
        _, density_from_low_row = _axis_to_data(
            x,
            low_y,
            PROVIA_PRODUCT_AXIS,
            affine=affine_axis,
        )
        _, density_from_high_row = _axis_to_data(
            x,
            high_y,
            PROVIA_PRODUCT_AXIS,
            affine=affine_axis,
        )
        center = np.maximum(
            _resample_monotonic(wavelength, density, PROFILE_GRID),
            0.0,
        )
        upper = _resample_monotonic(
            wavelength,
            np.maximum(density_from_low_row, density_from_high_row),
            PROFILE_GRID,
        )
        lower = _resample_monotonic(
            wavelength,
            np.minimum(density_from_low_row, density_from_high_row),
            PROFILE_GRID,
        )
        channels[channel] = center
        thickness[channel] = {
            "max_half_line_density": float(
                np.max(np.maximum(upper - center, center - lower))
            ),
            "mean_half_line_density": float(
                np.mean(np.maximum(upper - center, center - lower))
            ),
        }
        source_ranges[channel] = {
            "mask_name": name,
            "mask_size": list(mask.shape[::-1]),
            "foreground_pixel_count": int(mask.sum()),
            "populated_x_min": int(populated_columns[0]),
            "populated_x_max": int(populated_columns[-1]),
            "wavelength_min_nm": float(np.min(wavelength)),
            "wavelength_max_nm": float(np.max(wavelength)),
        }
    peaks = {
        channel: float(PROFILE_GRID[int(np.argmax(curve))])
        for channel, curve in channels.items()
    }
    return {
        "channels": channels,
        "peaks_nm": peaks,
        "line_thickness_uncertainty": thickness,
        "source_ranges": source_ranges,
        "page_index": 5,
        "page_number": 6,
        "center_method": center_method,
        "mask_semantics": {
            "Im63.tiff": "black axes, labels, and annotations",
            "Im64.tiff": "yellow dye curve",
            "Im65.tiff": "magenta dye curve",
            "Im66.tiff": "cyan dye curve",
        },
    }


def _normalized(channels: dict[str, np.ndarray]):
    return {
        channel: curve / float(np.max(curve))
        for channel, curve in channels.items()
    }


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denominator) if denominator else math.nan


def _fwhm(grid: np.ndarray, curve: np.ndarray) -> float | None:
    peak = float(np.max(curve))
    indices = np.flatnonzero(curve >= 0.5 * peak)
    if len(indices) < 2:
        return None
    return float(grid[indices[-1]] - grid[indices[0]])


def _comparison(a: dict[str, np.ndarray], b: dict[str, np.ndarray]):
    result = {}
    for channel in ("Y", "M", "C"):
        left = a[channel]
        right = b[channel]
        delta = left - right
        result[channel] = {
            "cosine": _cosine(left, right),
            "rmse_D": float(np.sqrt(np.mean(delta * delta))),
            "mean_absolute_D": float(np.mean(np.abs(delta))),
            "max_absolute_D": float(np.max(np.abs(delta))),
            "peak_left_nm": float(PROFILE_GRID[int(np.argmax(left))]),
            "peak_right_nm": float(PROFILE_GRID[int(np.argmax(right))]),
            "peak_shift_nm": float(
                PROFILE_GRID[int(np.argmax(left))]
                - PROFILE_GRID[int(np.argmax(right))]
            ),
            "fwhm_left_nm": _fwhm(PROFILE_GRID, left),
            "fwhm_right_nm": _fwhm(PROFILE_GRID, right),
        }
    return result


def _load_profile_channels(path: Path):
    payload = json.loads(path.read_text())
    data = payload["data"]
    wavelengths = np.asarray(data["wavelengths"], dtype=np.float64)
    matrix = np.asarray(
        [
            [np.nan if value is None else float(value) for value in row]
            for row in data["channel_density"]
        ],
        dtype=np.float64,
    )
    # Runtime/profile order is C, M, Y; source-curve reporting order is Y, M, C.
    columns = {"C": 0, "M": 1, "Y": 2}
    result = {}
    for channel, column in columns.items():
        valid = np.isfinite(matrix[:, column])
        result[channel] = np.interp(
            PROFILE_GRID,
            wavelengths[valid],
            matrix[valid, column],
        )
    return result


def _load_effective_velvia_candidate():
    manifest_path = (
        PROJECT_ROOT
        / "tmp"
        / "profile-public-batch-candidates"
        / "CURRENT_CANDIDATES.json"
    )
    if not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest.get("authoritative_for_this_run", []):
        if (
            entry.get("profile") == "fujifilm_velvia_100"
            and entry.get("candidate_kind") == "effective_basis"
            and entry.get("gate_passes") is True
        ):
            path = Path(entry["output"]["path"])
            if path.exists() and _sha256(path) == entry["output"]["sha256"]:
                return _load_profile_channels(path), {
                    "path": str(path.resolve()),
                    "sha256": entry["output"]["sha256"],
                    "candidate_id": entry["candidate_id"],
                }
    return None


def _axis_summary(axis: AxisCalibration):
    x = np.asarray(axis.x_coordinates, dtype=np.float64)
    wavelengths = np.asarray(axis.wavelengths_nm, dtype=np.float64)
    y = np.asarray(axis.y_coordinates, dtype=np.float64)
    densities = np.asarray(axis.densities, dtype=np.float64)
    x_fit = np.polyval(np.polyfit(x, wavelengths, 1), x)
    y_fit = np.polyval(np.polyfit(y, densities, 1), y)
    return {
        "coordinate_space": axis.coordinate_space,
        "x_coordinates": x.tolist(),
        "wavelengths_nm": wavelengths.tolist(),
        "y_coordinates": y.tolist(),
        "densities": densities.tolist(),
        "max_wavelength_affine_residual_nm": float(
            np.max(np.abs(wavelengths - x_fit))
        ),
        "max_density_affine_residual_D": float(
            np.max(np.abs(densities - y_fit))
        ),
        "mapping": "piecewise linear through published tick/grid anchors",
        "affine_mapping_role": "sensitivity alternative only",
    }


def _channels_to_json(channels: dict[str, np.ndarray]):
    return {channel: curve.tolist() for channel, curve in channels.items()}


def _write_csv(
    path: Path,
    primary: dict[str, np.ndarray],
    secondary: dict[str, np.ndarray],
    uncertainty: dict[str, np.ndarray],
):
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "wavelength_nm",
                "primary_Y_D",
                "primary_M_D",
                "primary_C_D",
                "secondary_Y_D",
                "secondary_M_D",
                "secondary_C_D",
                "edition_envelope_Y_D",
                "edition_envelope_M_D",
                "edition_envelope_C_D",
            ]
        )
        for index, wavelength in enumerate(PROFILE_GRID):
            writer.writerow(
                [
                    f"{wavelength:.1f}",
                    *[f"{primary[c][index]:.10f}" for c in ("Y", "M", "C")],
                    *[
                        f"{secondary[c][index]:.10f}"
                        for c in ("Y", "M", "C")
                    ],
                    *[
                        f"{uncertainty[c][index]:.10f}"
                        for c in ("Y", "M", "C")
                    ],
                ]
            )


def _plot(
    output_path: Path,
    stock_results: dict[str, dict[str, Any]],
):
    colours = {"Y": "#d6b800", "M": "#d50083", "C": "#008fbd"}
    figure, axes = plt.subplots(2, 3, figsize=(15, 8), sharex=True)
    for row, stock in enumerate(("provia_100f", "velvia_100")):
        result = stock_results[stock]
        for column, channel in enumerate(("Y", "M", "C")):
            axis = axes[row, column]
            axis.plot(
                PROFILE_GRID,
                result["primary_normalized"][channel],
                color=colours[channel],
                linewidth=2.2,
                label="manufacturer primary",
            )
            axis.plot(
                PROFILE_GRID,
                result["secondary_normalized"][channel],
                color="black",
                linewidth=1.2,
                linestyle="--",
                label="manufacturer cross-edition",
            )
            axis.plot(
                PROFILE_GRID,
                result["bundled_normalized"][channel],
                color="#6f6f6f",
                linewidth=1.2,
                linestyle=":",
                label="bundled profile",
            )
            if "effective_candidate_normalized" in result:
                axis.plot(
                    PROFILE_GRID,
                    result["effective_candidate_normalized"][channel],
                    color="#2d7f2d",
                    linewidth=1.0,
                    linestyle="-.",
                    label="batch-effective candidate",
                )
            axis.set_title(f"{stock.replace('_', ' ').title()} — {channel}")
            axis.set_xlim(400, 700)
            axis.set_ylim(-0.03, 1.08)
            axis.grid(alpha=0.25)
            if row == 1:
                axis.set_xlabel("Wavelength (nm)")
            if column == 0:
                axis.set_ylabel("Peak-normalized spectral density")
    handles_by_label = {}
    for axis in axes.flat:
        handles, labels = axis.get_legend_handles_labels()
        for handle, label in zip(handles, labels, strict=True):
            handles_by_label.setdefault(label, handle)
    figure.legend(
        list(handles_by_label.values()),
        list(handles_by_label),
        loc="lower center",
        ncol=len(handles_by_label),
    )
    figure.suptitle(
        "Published Fujifilm separated-light dye-density curves vs profiles"
    )
    figure.tight_layout(rect=(0, 0.07, 1, 0.95))
    figure.savefig(output_path, dpi=180)
    plt.close(figure)


def build_report(paths: dict[str, Path], output_dir: Path):
    provia_primary = _extract_provia_product_curves(paths)
    provia_primary_repeat = _extract_provia_product_curves(
        paths,
        center_method="midrange",
    )
    provia_affine = _extract_provia_product_curves(paths, affine_axis=True)
    provia_secondary = _extract_vector_curves(
        PROVIA_GUIDE_VECTOR,
        paths,
        samples_per_segment=8192,
    )
    provia_secondary_repeat = _extract_vector_curves(
        PROVIA_GUIDE_VECTOR,
        paths,
        samples_per_segment=2048,
    )

    velvia_primary = _extract_vector_curves(
        VELVIA_PRODUCT_VECTOR,
        paths,
        samples_per_segment=8192,
    )
    velvia_primary_repeat = _extract_vector_curves(
        VELVIA_PRODUCT_VECTOR,
        paths,
        samples_per_segment=2048,
    )
    velvia_affine = _extract_vector_curves(
        VELVIA_PRODUCT_VECTOR,
        paths,
        samples_per_segment=8192,
        affine_axis=True,
    )
    velvia_secondary = _extract_vector_curves(
        VELVIA_GUIDE_VECTOR,
        paths,
        samples_per_segment=8192,
    )
    velvia_secondary_repeat = _extract_vector_curves(
        VELVIA_GUIDE_VECTOR,
        paths,
        samples_per_segment=2048,
    )

    bundled_provia = _load_profile_channels(
        PROFILE_DIR / "fujifilm_provia_100f.json"
    )
    bundled_velvia = _load_profile_channels(
        PROFILE_DIR / "fujifilm_velvia_100.json"
    )
    effective = _load_effective_velvia_candidate()

    stock_results: dict[str, dict[str, Any]] = {}
    extracted = {
        "provia_100f": (
            provia_primary,
            provia_secondary,
            provia_affine,
            provia_secondary_repeat,
            bundled_provia,
        ),
        "velvia_100": (
            velvia_primary,
            velvia_secondary,
            velvia_affine,
            velvia_primary_repeat,
            bundled_velvia,
        ),
    }
    for stock, (
        primary,
        secondary,
        affine,
        repeat,
        bundled,
    ) in extracted.items():
        primary_normalized = _normalized(primary["channels"])
        secondary_normalized = _normalized(secondary["channels"])
        bundled_normalized = _normalized(bundled)
        edition_envelope = {
            channel: np.abs(
                primary_normalized[channel] - secondary_normalized[channel]
            )
            for channel in ("Y", "M", "C")
        }
        method_sensitivity = {
            "axis_piecewise_vs_affine": _comparison(
                primary_normalized,
                _normalized(affine["channels"]),
            ),
            "primary_repeat_extraction": (
                _comparison(
                    primary_normalized,
                    _normalized(provia_primary_repeat["channels"]),
                )
                if stock == "provia_100f"
                else _comparison(
                    primary_normalized,
                    _normalized(repeat["channels"]),
                )
            ),
            "secondary_vector_8192_vs_2048_samples_per_segment": (
                _comparison(
                    secondary_normalized,
                    _normalized(provia_secondary_repeat["channels"]),
                )
                if stock == "provia_100f"
                else _comparison(
                    secondary_normalized,
                    _normalized(velvia_secondary_repeat["channels"]),
                )
            ),
        }
        stock_result = {
            "primary_channels": primary["channels"],
            "secondary_channels": secondary["channels"],
            "primary_normalized": primary_normalized,
            "secondary_normalized": secondary_normalized,
            "bundled_normalized": bundled_normalized,
            "edition_envelope": edition_envelope,
            "manufacturer_cross_edition_comparison": _comparison(
                primary_normalized,
                secondary_normalized,
            ),
            "bundled_vs_manufacturer_primary": _comparison(
                bundled_normalized,
                primary_normalized,
            ),
            "method_sensitivity": method_sensitivity,
            "primary_extraction_metadata": {
                key: value for key, value in primary.items() if key != "channels"
            },
            "secondary_extraction_metadata": {
                key: value
                for key, value in secondary.items()
                if key != "channels"
            },
        }
        if stock == "velvia_100" and effective is not None:
            effective_channels, effective_metadata = effective
            effective_normalized = _normalized(effective_channels)
            stock_result["effective_candidate_normalized"] = effective_normalized
            stock_result["effective_candidate_metadata"] = effective_metadata
            stock_result["effective_candidate_vs_manufacturer_primary"] = (
                _comparison(effective_normalized, primary_normalized)
            )
        stock_results[stock] = stock_result

    output_dir.mkdir(parents=True, exist_ok=True)
    for stock, result in stock_results.items():
        _write_csv(
            output_dir / f"{stock}_published_curves_400_700_5nm.csv",
            result["primary_channels"],
            result["secondary_channels"],
            result["edition_envelope"],
        )
    plot_path = output_dir / "fuji_published_curve_profile_comparison.png"
    _plot(plot_path, stock_results)

    report = {
        "created": "2026-07-13",
        "scope": {
            "bundled_profiles_modified": False,
            "outputs_are_local_audit_artifacts": True,
            "candidate_authorization": False,
            "evidence_class": "same-stock manufacturer published measurement graph",
            "field_status_if_used": "source-derived",
            "measurement_status_if_used_alone": "no-raw-instrument-data",
            "semantic_model": (
                "separated-light reversal-film spectral diffuse density curves; "
                "density level set to 1.0"
            ),
            "caveat": (
                "representative general-production data, not raw observations "
                "for a retained particular roll"
            ),
        },
        "analysis": {
            "script": str(Path(__file__).resolve()),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "profile_grid_nm": PROFILE_GRID.tolist(),
            "channel_reporting_order": ["Y", "M", "C"],
            "profile_runtime_order": ["C", "M", "Y"],
            "vector_sampling_primary": 8192,
            "vector_sampling_repeat": 2048,
            "interpolation": "linear at the fixed 5 nm comparison grid",
            "negative_graph_excursions": "clipped to zero and disclosed",
            "software_versions": {
                "pypdf": pypdf.__version__,
                "numpy": np.__version__,
                "matplotlib": matplotlib.__version__,
            },
        },
        "sources": {
            key: {
                "path": str(paths[key].resolve()),
                "url": PDF_SPECS[key].url,
                "sha256": PDF_SPECS[key].sha256,
            }
            for key in paths
        },
        "axis_calibrations": {
            "provia_product_2000": _axis_summary(PROVIA_PRODUCT_AXIS),
            "provia_guide_2005": _axis_summary(PROVIA_GUIDE_VECTOR.axis),
            "velvia_product_2005": _axis_summary(VELVIA_PRODUCT_VECTOR.axis),
            "velvia_guide_2005": _axis_summary(VELVIA_GUIDE_VECTOR.axis),
        },
        "stocks": {},
        "outputs": {
            "plot": str(plot_path.resolve()),
            "csv": {
                stock: str(
                    (
                        output_dir
                        / f"{stock}_published_curves_400_700_5nm.csv"
                    ).resolve()
                )
                for stock in stock_results
            },
        },
        "output_artifact_sha256": {
            "plot": _sha256(plot_path),
            "csv": {
                stock: _sha256(
                    output_dir
                    / f"{stock}_published_curves_400_700_5nm.csv"
                )
                for stock in stock_results
            },
        },
    }
    for stock, result in stock_results.items():
        report["stocks"][stock] = {
            key: (
                _channels_to_json(value)
                if key.endswith("_channels")
                else {
                    channel: curve.tolist() for channel, curve in value.items()
                }
                if key
                in {
                    "primary_normalized",
                    "secondary_normalized",
                    "bundled_normalized",
                    "edition_envelope",
                    "effective_candidate_normalized",
                }
                else value
            )
            for key, value in result.items()
        }
    report["result_sha256"] = _canonical_sha256(report["stocks"])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-dir", type=Path, default=DEFAULT_PDF_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--download-missing", action="store_true")
    args = parser.parse_args()

    paths = {
        key: _ensure_pdf(spec, args.pdf_dir, args.download_missing)
        for key, spec in PDF_SPECS.items()
    }
    report = build_report(paths, args.output_dir)
    report_path = args.output_dir / "fuji_source_curve_digitization.json"
    encoded = json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n"
    report_path.write_text(encoded)
    print(
        json.dumps(
            {
                "report": str(report_path.resolve()),
                "report_sha256": _sha256(report_path),
                "result_sha256": report["result_sha256"],
                "bundled_profiles_modified": False,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
