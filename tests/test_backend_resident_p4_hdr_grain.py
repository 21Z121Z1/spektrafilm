from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.residency import record_backend_residency
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.utils.gamut_compression import OutputGamutCompressSpec


pytestmark = pytest.mark.integration


def _mlx_available_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _image(size: int = 12) -> np.ndarray:
    x = np.linspace(0.05, 0.95, size, dtype=np.float32)[None, :]
    y = np.linspace(0.04, 0.84, size, dtype=np.float32)[:, None]
    xx = np.broadcast_to(x, (size, size))
    yy = np.broadcast_to(y, (size, size))
    return np.stack(
        [
            0.05 + 0.80 * xx,
            0.08 + 0.75 * yy,
            0.10 + 0.35 * (xx + yy),
        ],
        axis=-1,
    ).astype(np.float32)


def _params(*, backend: str = "cpu", materialize_policy: str = "numpy_float64", grain: bool = False):
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = not grain
    params.settings.compute_backend = backend
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = materialize_policy
    if backend == "mlx" and materialize_policy == "backend":
        params.settings.color_precision_policy = "fast"
    params.settings.gpu_validate = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.use_fast_stats = True
    params.film_render.grain.active = bool(grain)
    params.film_render.grain.sublayers_active = False
    params.film_render.grain.blur = 0.0
    params.film_render.grain.blur_dye_clouds_um = 0.0
    params.film_render.grain.micro_structure = (0.0, 0.0)
    params.print_render.glare.active = False
    return digest_params(params)


def _format_events(events) -> str:
    return "\n".join(
        f"{event.direction} {event.shape} {event.dtype} {event.nbytes} "
        f"{event.reason} {event.stack_label}"
        for event in events
    )


def _matrix_params(scenario: str):
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.io.input_color_space = "sRGB"
    params.io.input_cctf_decoding = False
    params.io.output_color_space = "sRGB"
    params.io.output_cctf_encoding = True
    params.io.crop = False
    params.io.upscale_factor = 1.0
    params.camera.auto_exposure = False
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.color_precision_policy = "fast"
    params.settings.gpu_validate = False
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.use_fast_stats = True
    params.debug.deactivate_spatial_effects = False
    params.debug.deactivate_stochastic_effects = True

    params.film_render.grain.active = False
    params.film_render.grain.sublayers_active = False
    params.film_render.halation.active = False
    params.film_render.dir_couplers.active = False
    params.print_render.glare.active = False
    params.camera.diffusion_filter.active = False
    params.enlarger.diffusion_filter.active = False
    params.scanner.lens_blur = 0.0
    params.scanner.unsharp_mask = (0.0, 0.0)
    params.io.output_gamut_compress = OutputGamutCompressSpec(algorithm="oklch")

    if scenario == "halation":
        params.film_render.halation.active = True
        params.film_render.halation.scatter_amount = 0.35
        params.film_render.halation.halation_amount = 0.25
    elif scenario == "grain":
        params.debug.deactivate_stochastic_effects = False
        params.film_render.grain.active = True
        params.film_render.grain.blur = 0.0
        params.film_render.grain.blur_dye_clouds_um = 0.0
        params.film_render.grain.micro_structure = (0.0, 0.0)
    elif scenario == "dir_couplers":
        params.film_render.dir_couplers.active = True
        params.film_render.dir_couplers.amount = 0.45
        params.film_render.dir_couplers.diffusion_size_um = 2.0
    elif scenario == "camera_diffusion":
        params.camera.diffusion_filter.active = True
        params.camera.diffusion_filter.strength = 0.125
    elif scenario == "enlarger_diffusion":
        params.enlarger.diffusion_filter.active = True
        params.enlarger.diffusion_filter.strength = 0.125
    elif scenario == "glare":
        params.print_render.glare.active = True
        params.print_render.glare.percent = 0.01
        params.print_render.glare.blur = 0.1
    elif scenario == "chemistry":
        params.film_render.density_curve_gamma = 1.08
        params.enlarger.print_exposure = 1.08
        params.enlarger.y_filter_shift = 2.0
        params.enlarger.m_filter_shift = -2.0
    elif scenario == "scanner_blur_unsharp":
        params.scanner.lens_blur = 0.15
        params.scanner.unsharp_mask = (0.2, 0.2)
    elif scenario == "scan_film_route":
        params.io.scan_film = True
    elif scenario == "print_route":
        params.io.scan_film = False
    elif scenario.startswith("gamut_"):
        params.io.output_gamut_compress = OutputGamutCompressSpec(
            algorithm=scenario.removeprefix("gamut_")
        )
    elif scenario.startswith("rgb_to_raw_"):
        params.settings.rgb_to_raw_method = scenario.removeprefix("rgb_to_raw_")
    else:
        raise AssertionError(f"unhandled scenario {scenario!r}")

    return digest_params(params)


def test_process_with_metadata_cpu_default_keeps_legacy_image_and_cpu_sidecar() -> None:
    pipeline = SimulationPipeline(_params())

    result = pipeline.process_with_metadata(_image())

    assert isinstance(result.image, np.ndarray)
    assert result.image.dtype == np.float64
    assert result.hdr_scene_energy is not None
    assert isinstance(result.hdr_scene_energy.scene_luminance, np.ndarray)
    assert result.hdr_scene_energy.scene_luminance.dtype == np.float32
    assert result.hdr_scene_energy.scene_luminance.shape == _image().shape[:2]
    assert "SimulationPipeline.hdr_scene_luminance_materialize" not in pipeline.get_timings()


def test_process_with_metadata_mlx_backend_keeps_image_resident_and_times_sidecar() -> None:
    _mlx_available_or_skip()
    pipeline = SimulationPipeline(_params(backend="mlx", materialize_policy="backend"))

    result = pipeline.process_with_metadata(_image())

    assert pipeline._backend._is_mlx_array(result.image)
    assert result.hdr_scene_energy is not None
    scene_luminance = result.hdr_scene_energy.scene_luminance
    assert isinstance(scene_luminance, np.ndarray)
    assert scene_luminance.dtype == np.float32
    assert scene_luminance.shape == _image().shape[:2]
    assert np.isfinite(scene_luminance).all()
    assert pipeline.get_timings()["SimulationPipeline.hdr_scene_luminance_materialize"] >= 0.0


def test_process_with_metadata_sidecar_readback_is_diagnostic_allowed_on_mlx() -> None:
    _mlx_available_or_skip()
    pipeline = SimulationPipeline(_params(backend="mlx", materialize_policy="backend"))

    with record_backend_residency() as recorder:
        result = pipeline.process_with_metadata(_image())
        pipeline._backend.synchronize()

    assert pipeline._backend._is_mlx_array(result.image)
    assert recorder.summary()["unallowed_to_numpy"] == 0
    assert any(
        event.direction == "to_numpy"
        and "SimulationPipeline.hdr_scene_luminance_materialize" in pipeline.get_timings()
        for event in recorder.events
    )


def test_route_master_mlx_backend_materializes_cpu_sidecars_explicitly() -> None:
    _mlx_available_or_skip()
    params = _params(backend="mlx", materialize_policy="backend")
    params.settings.hdr_route_sidecar_policy = "full"
    pipeline = SimulationPipeline(params)

    master = pipeline.process_master(_image(), hdr_mode="paper")

    for field in (
        master.route_linear_rgb,
        master.route_linear_xyz,
        master.route_luminance_y,
        master.sdr_legacy_rgb,
        master.scene_y_raw,
        master.post_halation_y,
        master.density_cmy,
    ):
        assert isinstance(field, np.ndarray)
        assert np.isfinite(field).all()
    assert pipeline.get_timings()["SimulationPipeline.route_master_materialize"] >= 0.0
    assert master.diagnostics["route_kind"] == "print_scan"


def test_normal_mlx_runtime_has_no_unallowed_sidecar_readback() -> None:
    _mlx_available_or_skip()
    pipeline = SimulationPipeline(_params(backend="mlx", materialize_policy="backend"))

    with record_backend_residency() as recorder:
        result = pipeline.process(_image())
        pipeline._backend.synchronize()

    assert pipeline._backend._is_mlx_array(result)
    assert recorder.summary()["unallowed_to_numpy"] == 0
    assert "SimulationPipeline.hdr_scene_luminance_materialize" not in pipeline.get_timings()
    assert "SimulationPipeline.route_master_materialize" not in pipeline.get_timings()


def test_grain_on_mlx_runtime_keeps_output_backend_resident() -> None:
    _mlx_available_or_skip()
    pipeline = SimulationPipeline(_params(backend="mlx", materialize_policy="backend", grain=True))

    with record_backend_residency(small_array_bytes=64) as recorder:
        result = pipeline.process(_image(10))
        pipeline._backend.synchronize()

    assert pipeline._backend._is_mlx_array(result)
    assert recorder.summary()["unallowed_to_numpy"] == 0
    assert not any("_grain_cpu_reference_numpy" in event.reason for event in recorder.events)
    result_np = pipeline._backend.to_numpy(result)
    assert result_np.dtype == np.float32
    assert np.isfinite(result_np).all()


@pytest.mark.parametrize(
    "scenario",
    [
        "halation",
        "grain",
        "dir_couplers",
        "camera_diffusion",
        "enlarger_diffusion",
        "glare",
        "chemistry",
        "scanner_blur_unsharp",
        "scan_film_route",
        "print_route",
        "gamut_off",
        "gamut_aces_rgc",
        "gamut_oklch",
        "gamut_oklrab",
        "gamut_jzazbz",
        "gamut_cam16ucs",
        "rgb_to_raw_hanatos2025",
        "rgb_to_raw_mallett2019",
    ],
)
def test_gui_exposed_adjustment_matrix_stays_mlx_resident(scenario: str) -> None:
    _mlx_available_or_skip()
    pipeline = SimulationPipeline(_matrix_params(scenario))

    with record_backend_residency(small_array_bytes=1024) as recorder:
        result = pipeline.process(_image(10))
        pipeline._backend.synchronize()

    assert pipeline._backend._is_mlx_array(result), scenario
    assert result.dtype == pipeline._backend.mx.float32
    unallowed = recorder.unallowed_to_numpy_events()
    assert not unallowed, f"{scenario}\n{_format_events(unallowed)}"
