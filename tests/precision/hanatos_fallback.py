from __future__ import annotations

import copy
from unittest.mock import patch

import numpy as np

import spektrafilm.runtime.stages.filming as filming_module
from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.kernels.density import safe_log10_backend
from spektrafilm.runtime.params_builder import digest_params, init_params
from spektrafilm.runtime.pipeline import SimulationPipeline
from tests.precision.staircase import load_contract, numeric_metrics, representative_rgb


def _params():
    params = init_params(film_profile="kodak_portra_400", print_profile="kodak_portra_endura")
    params.debug.deactivate_spatial_effects = True
    params.debug.deactivate_stochastic_effects = True
    params.settings.use_enlarger_lut = False
    params.settings.use_scanner_lut = False
    params.settings.compute_backend = "mlx"
    params.settings.gpu_precision = "float32"
    params.settings.materialize_policy = "backend"
    params.settings.color_precision_policy = "balanced"
    params.settings.gpu_validate = False
    params.io.upscale_factor = 1.0
    params.io.crop = False
    params.camera.auto_exposure = False
    params.camera.exposure_compensation_ev = 0.0
    return digest_params(params)


def _numpy_output(pipeline: SimulationPipeline, value) -> np.ndarray:
    backend = pipeline._backend
    backend.eval(value)
    return backend.to_numpy(value)


def run_hanatos_fallback_audit() -> dict[str, object]:
    """Compare the previous and candidate balanced MLX CPU-fallback callsites."""
    try:
        select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        return {"available": False, "reason": str(exc)}

    image, labels = representative_rgb(height=9, width=16)
    image = np.clip(image, 0.0, 4.0).astype(np.float32)
    params = _params()
    pipeline = SimulationPipeline(copy.deepcopy(params))
    backend_image = pipeline._backend.asarray(image)

    with patch.object(
        filming_module,
        "rgb_to_raw_hanatos2025_mlx_cpu_fallback",
        filming_module.rgb_to_raw_hanatos2025,
    ):
        raw_reference64 = pipeline._filming_stage._rgb_to_film_raw(backend_image)
    raw_candidate64 = pipeline._filming_stage._rgb_to_film_raw(backend_image)
    raw_reference32 = np.asarray(raw_reference64, dtype=np.float32)
    raw_candidate32 = np.asarray(raw_candidate64, dtype=np.float32)
    log_reference = safe_log10_backend(raw_reference64, pipeline._backend)
    log_candidate = safe_log10_backend(raw_candidate64, pipeline._backend)
    pipeline._backend.eval(log_reference, log_candidate)
    log_reference32 = pipeline._backend.to_numpy(log_reference)
    log_candidate32 = pipeline._backend.to_numpy(log_candidate)

    with patch.object(
        filming_module,
        "rgb_to_raw_hanatos2025_mlx_cpu_fallback",
        filming_module.rgb_to_raw_hanatos2025,
    ):
        reference_pipeline = SimulationPipeline(copy.deepcopy(params))
        final_reference = _numpy_output(reference_pipeline, reference_pipeline.process(image))
    candidate_pipeline = SimulationPipeline(copy.deepcopy(params))
    final_candidate = _numpy_output(candidate_pipeline, candidate_pipeline.process(image))

    contract = load_contract()["hanatos_balanced_fallback"]
    raw64_metrics = numeric_metrics(raw_reference64, raw_candidate64, condition_labels=labels)
    raw32_metrics = numeric_metrics(raw_reference32, raw_candidate32, condition_labels=labels)
    log_metrics = numeric_metrics(log_reference32, log_candidate32, condition_labels=labels)
    final_metrics = numeric_metrics(final_reference, final_candidate, condition_labels=labels, clip_bounds=(0.0, 1.0))
    failures: list[str] = []
    if raw64_metrics["max_abs"] > float(contract["cpu64_intermediate_max_abs_budget"]):
        failures.append("film_raw_cpu64 exceeds the locked intermediate budget")
    for name, metrics in (
        ("film_raw_float32", raw32_metrics),
        ("film_log_exposure", log_metrics),
        ("final_output", final_metrics),
    ):
        if not metrics["bitwise_equal"]:
            failures.append(f"{name} is not bitwise equal")
    return {
        "available": True,
        "reference": contract["reference"],
        "candidate": contract["candidate"],
        "metrics": {
            "film_raw_cpu64": raw64_metrics,
            "film_raw_float32": raw32_metrics,
            "film_log_exposure": log_metrics,
            "final_output": final_metrics,
        },
        "failures": failures,
    }
