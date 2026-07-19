from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.density import (
    cmy_to_log_xyz_backend,
    compute_density_spectral,
    density_to_light,
    interpolate_exposure_to_density_backend,
    light_to_raw,
    safe_log10_backend,
)
from tests.precision.staircase import StageSnapshot, representative_rgb


def _tables(dtype: np.dtype[Any]) -> dict[str, np.ndarray]:
    wavelengths = np.linspace(380.0, 780.0, 81, dtype=dtype)

    def gaussian(center: float, width: float) -> np.ndarray:
        return np.exp(-0.5 * ((wavelengths - dtype.type(center)) / dtype.type(width)) ** 2).astype(dtype)

    channel_density = np.stack(
        (gaussian(610.0, 72.0), gaussian(535.0, 60.0), gaussian(445.0, 48.0)), axis=-1
    ) * dtype.type(1.25)
    illuminant = (dtype.type(0.55) + dtype.type(0.45) * gaussian(550.0, 135.0)).astype(dtype)
    sensitivity = np.stack(
        (gaussian(600.0, 55.0), gaussian(540.0, 48.0), gaussian(455.0, 42.0)), axis=-1
    )
    cmfs = np.stack(
        (gaussian(600.0, 48.0), gaussian(550.0, 42.0), gaussian(445.0, 35.0)), axis=-1
    )
    base_density = (dtype.type(0.06) + dtype.type(0.015) * np.sin(wavelengths / dtype.type(37.0))).astype(dtype)
    log_axis = np.tile(np.linspace(-8.0, 2.0, 65, dtype=dtype)[:, None], (1, 3))
    curve_base = dtype.type(3.0) / (dtype.type(1.0) + np.exp(-dtype.type(1.2) * (log_axis + dtype.type(2.0))))
    curves = curve_base * np.asarray([1.0, 0.94, 0.88], dtype=dtype)
    xyz_to_rgb = np.asarray(
        [[3.24096994, -1.53738318, -0.49861076], [-0.96924364, 1.8759675, 0.04155506], [0.05563008, -0.20397696, 1.05697151]],
        dtype=dtype,
    )
    return {
        "channel_density": channel_density,
        "illuminant": illuminant,
        "sensitivity": sensitivity,
        "cmfs": cmfs,
        "base_density": base_density,
        "log_axis": log_axis,
        "curves": curves,
        "xyz_to_rgb": xyz_to_rgb,
    }


def _profile_tables(
    dtype: np.dtype[Any],
    case: Mapping[str, Any],
) -> dict[str, np.ndarray]:
    from spektrafilm.config import STANDARD_OBSERVER_CMFS
    from spektrafilm.model.illuminants import standard_illuminant
    from spektrafilm.profiles.io import load_profile

    film = load_profile(str(case["profile"]))
    paper = load_profile("kodak_portra_endura")
    direct_scan = case["route"] == "direct_scan"
    scan_medium = film if direct_scan else paper
    illuminant = np.asarray(
        standard_illuminant(scan_medium.info.viewing_illuminant),
        dtype=dtype,
    )
    sensitivity = np.power(
        dtype.type(10.0),
        np.asarray(paper.data.log_sensitivity, dtype=dtype),
    )
    sensitivity /= np.maximum(
        np.sum(sensitivity, axis=0, keepdims=True, dtype=dtype),
        dtype.type(1e-10),
    )
    xyz_to_rgb = np.asarray(
        [
            [3.24096994, -1.53738318, -0.49861076],
            [-0.96924364, 1.8759675, 0.04155506],
            [0.05563008, -0.20397696, 1.05697151],
        ],
        dtype=dtype,
    )

    def exposure_axis(profile) -> np.ndarray:
        axis = np.asarray(profile.data.log_exposure, dtype=dtype)
        return np.repeat(axis[:, None], 3, axis=1)

    return {
        "film_channel_density": np.asarray(film.data.channel_density, dtype=dtype),
        "film_base_density": np.asarray(film.data.base_density, dtype=dtype),
        "film_log_axis": exposure_axis(film),
        "film_curves": np.asarray(film.data.density_curves, dtype=dtype),
        "paper_channel_density": np.asarray(paper.data.channel_density, dtype=dtype),
        "paper_base_density": np.asarray(paper.data.base_density, dtype=dtype),
        "paper_log_axis": exposure_axis(paper),
        "paper_curves": np.asarray(paper.data.density_curves, dtype=dtype),
        "paper_sensitivity": sensitivity,
        "scan_channel_density": np.asarray(scan_medium.data.channel_density, dtype=dtype),
        "scan_base_density": np.asarray(scan_medium.data.base_density, dtype=dtype),
        "illuminant": illuminant,
        "cmfs": np.asarray(STANDARD_OBSERVER_CMFS[:], dtype=dtype),
        "xyz_to_rgb": xyz_to_rgb,
    }


def _resolved_tables(
    dtype: np.dtype[Any],
    case: Mapping[str, Any] | None,
) -> dict[str, np.ndarray]:
    if case is None:
        tables = _tables(dtype)
        return {
            **tables,
            "film_channel_density": tables["channel_density"],
            "film_base_density": tables["base_density"],
            "film_log_axis": tables["log_axis"],
            "film_curves": tables["curves"],
            "paper_channel_density": tables["channel_density"],
            "paper_base_density": tables["base_density"],
            "paper_log_axis": tables["log_axis"],
            "paper_curves": tables["curves"] * dtype.type(0.92),
            "paper_sensitivity": tables["sensitivity"],
            "scan_channel_density": tables["channel_density"],
            "scan_base_density": tables["base_density"],
        }
    return _profile_tables(dtype, case)


def _case_seed(case: Mapping[str, Any] | None) -> int:
    if case is None:
        return 20260719
    return 20260719 + sum(str(case["id"]).encode("ascii"))


def _spatial_gain(
    shape: tuple[int, int],
    dtype: np.dtype[Any],
) -> np.ndarray:
    yy, xx = np.indices(shape, dtype=np.float64)
    gain = 1.0 + 0.0125 * np.sin(xx * 0.73 + yy * 0.41)
    return np.asarray(gain[..., None], dtype=dtype)


def _shared_grain_math(density: Any, counts: Any, dtype: np.dtype[Any]) -> np.ndarray:
    d = np.asarray(density, dtype=dtype)
    n = np.asarray(counts, dtype=dtype)
    density_max = np.asarray([3.2, 3.0, 2.8], dtype=dtype)
    particles = np.asarray([120.0, 95.0, 80.0], dtype=dtype)
    uniformity = np.asarray([0.98, 0.97, 0.96], dtype=dtype)
    probability = np.clip(d / density_max, dtype.type(1e-6), dtype.type(1.0 - 1e-6))
    saturation = dtype.type(1.0) - probability * uniformity * dtype.type(1.0 - 1e-6)
    return (n * (density_max / particles) * saturation).astype(dtype)


def _interp_reference(values: np.ndarray, x_axis: np.ndarray, curves: np.ndarray, dtype: np.dtype[Any]) -> np.ndarray:
    values = np.asarray(values, dtype=dtype)
    result = np.empty_like(values)
    for channel in range(3):
        x = x_axis[:, channel]
        y = curves[:, channel]
        indices = np.searchsorted(x, values[..., channel], side="right")
        indices = np.clip(indices, 1, len(x) - 1)
        lo = indices - 1
        x0, x1 = x[lo], x[indices]
        y0, y1 = y[lo], y[indices]
        t = (values[..., channel] - x0) / (x1 - x0)
        interpolated = y0 + t * (y1 - y0)
        result[..., channel] = np.where(values[..., channel] <= x[0], y[0], np.where(values[..., channel] >= x[-1], y[-1], interpolated))
    return result.astype(dtype)


def _finalize_numpy(
    *,
    image: np.ndarray,
    labels: np.ndarray,
    dtype: np.dtype[Any],
    scan_xyz_override: np.ndarray | None = None,
    case: Mapping[str, Any] | None = None,
) -> dict[str, StageSnapshot]:
    t = _resolved_tables(dtype, case)
    camera_matrix = np.asarray([[0.72, 0.18, 0.10], [0.12, 0.78, 0.10], [0.08, 0.17, 0.75]], dtype=dtype)
    raw = np.maximum(np.asarray(image, dtype=dtype) @ camera_matrix.T, dtype.type(0.0)) + dtype.type(1e-6)
    if case is not None and bool(case["spatial"]):
        raw = (raw * _spatial_gain(image.shape[:2], dtype)).astype(dtype)
    film_log = np.log10(raw).astype(dtype)
    film_density = _interp_reference(
        film_log,
        t["film_log_axis"],
        t["film_curves"],
        dtype,
    )
    grain_enabled = case is None or bool(case["grain"])
    if grain_enabled:
        counts = np.random.default_rng(_case_seed(case)).poisson(
            100.0,
            size=film_density.shape,
        ).astype(np.int32)
        grain_density = _shared_grain_math(film_density, counts, dtype)
    else:
        grain_density = film_density

    direct_scan = case is not None and case["route"] == "direct_scan"
    paper_log = None
    paper_density = None
    if direct_scan:
        scan_cmy = grain_density
    else:
        density_spectral = (
            np.einsum(
                "ijk,lk->ijl",
                grain_density,
                t["film_channel_density"],
                dtype=dtype,
            )
            + t["film_base_density"]
        )
        print_light = np.nan_to_num(
            np.power(dtype.type(10.0), -density_spectral) * t["illuminant"],
            nan=dtype.type(0.0),
        )
        paper_raw = np.einsum(
            "ijk,kl->ijl",
            print_light,
            t["paper_sensitivity"],
            dtype=dtype,
        )
        paper_log = np.log10(
            np.maximum(paper_raw, dtype.type(0.0)) + dtype.type(1e-10)
        ).astype(dtype)
        paper_density = _interp_reference(
            paper_log,
            t["paper_log_axis"],
            t["paper_curves"],
            dtype,
        )
        scan_cmy = paper_density

    scan_density = (
        np.einsum(
            "ijk,lk->ijl",
            scan_cmy,
            t["scan_channel_density"],
            dtype=dtype,
        )
        + t["scan_base_density"]
    )
    transmittance = np.power(dtype.type(10.0), -scan_density).astype(dtype)
    scan_light = np.nan_to_num(
        transmittance * t["illuminant"],
        nan=dtype.type(0.0),
    )
    normalization = np.sum(t["illuminant"] * t["cmfs"][:, 1], dtype=dtype)
    scan_xyz = np.einsum("ijk,kl->ijl", scan_light, t["cmfs"], dtype=dtype) / normalization
    if scan_xyz_override is not None:
        scan_xyz = np.asarray(scan_xyz_override, dtype=dtype)
    # A fixed scan calibration exposes shadows, midtones, display white, and
    # super-white values instead of leaving this compact synthetic spectrum in
    # an unrepresentatively dark numerical range.
    calibration_value = 500.0 if case is None else 5.0
    calibration = np.full(
        image.shape[:2] + (1,),
        dtype.type(calibration_value),
        dtype=dtype,
    )
    calibration[np.max(np.abs(image), axis=-1, keepdims=True) < dtype.type(1e-5)] = dtype.type(0.01)
    output_linear = ((scan_xyz @ t["xyz_to_rgb"].T + scan_xyz[..., 1:2]) * calibration).astype(dtype)
    output_linear[0, 4, :] = np.maximum(output_linear[0, 4, :], dtype.type(1.5))
    sdr = np.clip(output_linear, dtype.type(0.0), dtype.type(1.0)).astype(dtype)
    encoded = np.where(
        sdr <= dtype.type(np.float32(0.0031308)),
        sdr * dtype.type(12.92),
        dtype.type(1.055) * np.power(sdr, dtype.type(1.0 / 2.4)) - dtype.type(0.055),
    ).astype(dtype)
    maximum = dtype.type(1023.0)
    encoded_quantized = (np.rint(encoded * maximum) / maximum).astype(dtype)
    decoded_sdr = np.where(
        encoded_quantized <= dtype.type(np.float32(0.04045)),
        encoded_quantized / dtype.type(12.92),
        np.power((encoded_quantized + dtype.type(0.055)) / dtype.type(1.055), dtype.type(2.4)),
    ).astype(dtype)

    luminance = np.tensordot(np.maximum(output_linear, dtype.type(0.0)), np.asarray([0.2126, 0.7152, 0.0722], dtype=dtype), axes=([-1], [0])).astype(dtype)
    headroom = dtype.type(max(0.0, float(np.log2(max(float(np.percentile(luminance, 99.0)), 1.0)))))
    alternate = (decoded_sdr * (dtype.type(1.0) + dtype.type(3.0) * np.clip(luminance[..., None], 0.0, 1.0))).astype(dtype)
    offset = dtype.type(1.0 / 1023.0)
    gain = np.log2(np.maximum((alternate + offset) / (decoded_sdr + offset), dtype.type(1e-8))).astype(dtype)
    g_min, g_max = dtype.type(np.min(gain)), dtype.type(np.max(gain))
    normalized_gain = ((gain - g_min) / max(dtype.type(g_max - g_min), dtype.type(1e-8))).astype(dtype)
    gain_quantized = (np.rint(np.clip(normalized_gain, 0.0, 1.0) * maximum) / maximum).astype(dtype)
    restored_gain = (gain_quantized * (g_max - g_min) + g_min).astype(dtype)
    decoded_hdr = ((decoded_sdr + offset) * np.power(dtype.type(2.0), restored_gain) - offset).astype(dtype)

    def snapshot(value: Any) -> StageSnapshot:
        return StageSnapshot(np.asarray(value), labels)

    snapshots = {
        "film_raw_exposure": snapshot(raw),
        "film_log_exposure": snapshot(film_log),
        "film_cmy_density": snapshot(film_density),
        "scan_spectral_transmittance": StageSnapshot(transmittance, labels),
        "scan_xyz": snapshot(scan_xyz),
        "scene_output_linear_rgb": snapshot(output_linear),
        "sdr_pre_encode": snapshot(sdr),
        "decoded_final_sdr": snapshot(decoded_sdr),
    }
    if grain_enabled:
        snapshots["grain_density_shared_random"] = snapshot(grain_density)
    if paper_log is not None and paper_density is not None:
        snapshots["paper_log_exposure"] = snapshot(paper_log)
        snapshots["paper_cmy_density"] = snapshot(paper_density)
    if case is None or case["output"] == "hdr":
        snapshots.update({
            "hdr_linear_luminance": StageSnapshot(luminance, labels),
            "hdr_headroom": StageSnapshot(np.asarray([headroom], dtype=dtype)),
            "gain_map": snapshot(gain_quantized),
            "decoded_final_hdr": snapshot(decoded_hdr),
        })
    return snapshots


def _mlx_stages(
    image: np.ndarray,
    labels: np.ndarray,
    *,
    fused: bool,
    case: Mapping[str, Any] | None = None,
) -> dict[str, StageSnapshot]:
    backend = select_backend("mlx", precision="float32")
    dtype = np.dtype(np.float32)
    t = _resolved_tables(dtype, case)
    camera_matrix = np.asarray([[0.72, 0.18, 0.10], [0.12, 0.78, 0.10], [0.08, 0.17, 0.75]], dtype=np.float32)
    image_mx = backend.asarray(image.astype(np.float32))
    raw = backend.maximum(
        backend.matmul(image_mx, backend.asarray(camera_matrix.T)), np.float32(0.0)
    ) + np.float32(1e-6)
    if case is not None and bool(case["spatial"]):
        raw = raw * backend.asarray(_spatial_gain(image.shape[:2], dtype))
    film_log = backend.log10(raw)
    film_density = interpolate_exposure_to_density_backend(
        film_log,
        t["film_log_axis"][:, 0],
        t["film_curves"],
        np.float32(1.0),
        backend,
    )

    grain_enabled = case is None or bool(case["grain"])
    if grain_enabled:
        counts = np.random.default_rng(_case_seed(case)).poisson(
            100.0,
            size=image.shape,
        ).astype(np.int32)
        density_max = backend.asarray(np.asarray([3.2, 3.0, 2.8], dtype=np.float32))
        particles = backend.asarray(np.asarray([120.0, 95.0, 80.0], dtype=np.float32))
        uniformity = backend.asarray(np.asarray([0.98, 0.97, 0.96], dtype=np.float32))
        probability = backend.clip(
            film_density / density_max,
            np.float32(1e-6),
            np.float32(1.0 - 1e-6),
        )
        saturation = np.float32(1.0) - probability * uniformity * np.float32(1.0 - 1e-6)
        grain_density = (
            backend.asarray(counts, dtype=backend.mx.float32)
            * (density_max / particles)
            * saturation
        )
    else:
        grain_density = film_density

    direct_scan = case is not None and case["route"] == "direct_scan"
    paper_log = None
    paper_density = None
    if direct_scan:
        scan_cmy = grain_density
    else:
        print_density_spectral = compute_density_spectral(
            t["film_channel_density"],
            grain_density,
            t["film_base_density"],
            backend,
        )
        print_light = density_to_light(
            print_density_spectral,
            t["illuminant"],
            backend,
        )
        paper_raw = light_to_raw(print_light, t["paper_sensitivity"], backend)
        paper_log = safe_log10_backend(paper_raw, backend)
        paper_density = interpolate_exposure_to_density_backend(
            paper_log,
            t["paper_log_axis"][:, 0],
            t["paper_curves"],
            np.float32(1.0),
            backend,
        )
        scan_cmy = paper_density

    scan_density = compute_density_spectral(
        t["scan_channel_density"],
        scan_cmy,
        t["scan_base_density"],
        backend,
    )
    transmittance = backend.power(10.0, -scan_density)
    if fused:
        normalization = float(np.sum(t["illuminant"] * t["cmfs"][:, 1], dtype=np.float32))
        log_xyz = cmy_to_log_xyz_backend(
            scan_cmy,
            t["scan_channel_density"],
            t["scan_base_density"],
            t["illuminant"],
            t["cmfs"],
            normalization,
            backend,
        )
        xyz = backend.power(10.0, log_xyz)
    else:
        light = density_to_light(scan_density, t["illuminant"], backend)
        xyz = light_to_raw(light, t["cmfs"], backend)
        normalization = float(np.sum(t["illuminant"] * t["cmfs"][:, 1], dtype=np.float32))
        xyz = xyz / np.float32(normalization)
    evaluation_values = [film_log, film_density, grain_density, transmittance, xyz]
    if paper_log is not None and paper_density is not None:
        evaluation_values.extend((paper_log, paper_density))
    backend.eval(*evaluation_values)

    def snapshot(value: Any) -> StageSnapshot:
        return StageSnapshot(backend.to_numpy(value).astype(np.float32, copy=False), labels)

    snapshots = {
        "film_raw_exposure": snapshot(raw),
        "film_log_exposure": snapshot(film_log),
        "film_cmy_density": snapshot(film_density),
        "scan_spectral_transmittance": snapshot(transmittance),
        "scan_xyz": snapshot(xyz),
    }
    if grain_enabled:
        snapshots["grain_density_shared_random"] = snapshot(grain_density)
    if paper_log is not None and paper_density is not None:
        snapshots["paper_log_exposure"] = snapshot(paper_log)
        snapshots["paper_cmy_density"] = snapshot(paper_density)
    return snapshots


def run_synthetic_staircase(
    *,
    include_mlx: bool = True,
    case: Mapping[str, Any] | None = None,
) -> dict[str, dict[str, StageSnapshot]]:
    shape = (13, 19) if case is None else tuple(int(value) for value in case["shape"])
    image, labels = representative_rgb(*shape)
    paths = {
        "cpu64": _finalize_numpy(
            image=image,
            labels=labels,
            dtype=np.dtype(np.float64),
            case=case,
        ),
        "cpu32": _finalize_numpy(
            image=image,
            labels=labels,
            dtype=np.dtype(np.float32),
            case=case,
        ),
    }
    if not include_mlx:
        return paths
    try:
        unfused_stages = _mlx_stages(image, labels, fused=False, case=case)
        candidate_stages = _mlx_stages(image, labels, fused=True, case=case)
    except BackendUnavailableError:
        return paths
    paths["mlx32_unfused"] = _finalize_numpy(
        image=image,
        labels=labels,
        dtype=np.dtype(np.float32),
        scan_xyz_override=unfused_stages["scan_xyz"].values,
        case=case,
    )
    paths["mlx32_unfused"].update(unfused_stages)
    paths["mlx32_candidate"] = _finalize_numpy(
        image=image,
        labels=labels,
        dtype=np.dtype(np.float32),
        scan_xyz_override=candidate_stages["scan_xyz"].values,
        case=case,
    )
    paths["mlx32_candidate"].update(candidate_stages)
    return paths


def run_contract_case_staircases(
    contract: Mapping[str, Any],
    *,
    include_mlx: bool = True,
) -> dict[str, dict[str, dict[str, StageSnapshot]]]:
    return {
        str(case["id"]): run_synthetic_staircase(
            include_mlx=include_mlx,
            case=case,
        )
        for case in contract["sample_set"]
    }
