"""Runtime process entry points."""

from __future__ import annotations

import numpy as np

from spektrafilm.gpu.metal_serialization import serialized_metal_runtime
from spektrafilm.runtime.params_schema import RuntimePhotoParams
from spektrafilm.runtime.pipeline import SimulationPipeline, SimulationPipelineResult
from spektrafilm.utils.preview import resize_for_preview
from spektrafilm.runtime.params_builder import (
    digest_params,
    init_params,
)

class Simulator:
    """User-facing wrapper around the runtime simulation pipeline.
    The params passed to the constructor should be static and not be changed.
    They can be refreshed with update_params or soft_update, which delegate to the internal pipeline.
    """

    def __init__(self, params: RuntimePhotoParams):
        if _params_may_require_serial_runtime(params):
            with serialized_metal_runtime():
                self._pipeline = SimulationPipeline(params) # should stay private
        else:
            self._pipeline = SimulationPipeline(params) # should stay private

    def process(self, image: np.ndarray) -> np.ndarray:
        """Process the input image through the simulation pipeline and return the final result."""
        if self._uses_serial_runtime():
            with serialized_metal_runtime():
                result = self._pipeline.process(image)
                self._synchronize_serial_runtime()
                return result
        return self._pipeline.process(image)

    def process_with_metadata(self, image: np.ndarray) -> SimulationPipelineResult:
        """Process the input image and return rendered output plus runtime metadata."""
        if self._uses_serial_runtime():
            with serialized_metal_runtime():
                result = self._pipeline.process_with_metadata(image)
                self._synchronize_serial_runtime()
                return result
        return self._pipeline.process_with_metadata(image)

    def update_params(self, params: RuntimePhotoParams) -> None:
        """Update the parameters of the simulation pipeline."""
        if self._uses_serial_runtime() or _params_may_require_serial_runtime(params):
            with serialized_metal_runtime():
                try:
                    self._pipeline.update(params)
                finally:
                    self._synchronize_serial_runtime()
            return
        self._pipeline.update(params)

    def soft_update(self, **kwargs) -> None:
        """Soft update parameters by only changing the provided fields, keeping the rest unchanged.
        only selected safe parameters can be updated with this method
        """
        if self._uses_serial_runtime():
            with serialized_metal_runtime():
                try:
                    self._pipeline.soft_update(**kwargs)
                finally:
                    self._synchronize_serial_runtime()
            return
        self._pipeline.soft_update(**kwargs)

    def _uses_serial_runtime(self) -> bool:
        backend = getattr(self._pipeline, "_array_backend", None)
        return bool(getattr(backend, "requires_serial_runtime", False))

    def _synchronize_serial_runtime(self) -> None:
        backend = getattr(self._pipeline, "_array_backend", None)
        synchronize = getattr(backend, "synchronize", None)
        if callable(synchronize):
            synchronize()

    def get_timings(self) -> dict[str, float]:
        """Get the timings of the different stages of the simulation pipeline."""
        return self._pipeline.get_timings()

    def get_total_elapsed_time(self) -> float | None:
        """Get the total wall-clock time of the last process call."""
        return self._pipeline.get_total_elapsed_time()

    def format_timings(self) -> str:
        """Format the last recorded timings for display."""
        return self._pipeline.format_timings()

    def print_timings(self) -> None:
        """Print the formatted timings of the last process call."""
        self._pipeline.print_timings()


######################################################################################
# Convenience functions for single-call simulation without needing to instantiate the Simulator class.

def _params_may_require_serial_runtime(params: RuntimePhotoParams) -> bool:
    settings = getattr(params, "settings", None)
    compute_backend = str(getattr(settings, "compute_backend", "auto")).strip().lower()
    float_precision = str(getattr(settings, "float_precision", "float32")).strip().lower()
    return compute_backend in {"auto", "mlx"} and float_precision != "float64"


def simulate(image, params: RuntimePhotoParams,
             digest_params_first: bool = True,
             print_timings: bool = False):
    """Convenience function to run the simulation pipeline with a single call.
    The simulator needs digested parameters to run. By default they are digested on the fly.
    If you already have digested parameters or want to digest them yourself, set digest_params_first=False.
    """
    if digest_params_first:
        params = digest_params(params)
    simulator = Simulator(params)
    result = simulator.process(image)
    if print_timings:
        simulator.print_timings()
    return result


def simulate_preview(image, params: RuntimePhotoParams,
                     digest_params_first: bool = True,
                     print_timings: bool = False):
    """Convenience function to run the simulation pipeline with a single call.
    The simulator needs digested parameters to run. By default they are digested on the fly.
    If you already have digested parameters or want to digest them yourself, set digest_params_first=False.
    """
    max_size = params.settings.preview_max_size
    result = simulate(resize_for_preview(image, max_size), params,
                      digest_params_first=digest_params_first,
                      print_timings=print_timings)
    return result


#######################################################################################################
# Legacy for ART, to be removed in the future when the old API is fully deprecated.

class AgXPhoto(Simulator):
    def __init__(self, params: RuntimePhotoParams):
        digested_params = digest_params(params)
        super().__init__(digested_params)

# photo_params is init_params
def photo_params(film_profile, print_profile) -> RuntimePhotoParams:
    """Legacy helper to build a RuntimePhotoParams with default film and print profiles.
    Build a runtime parameter object.
    It needs to be digested with digest_params before being used in the runtime pipeline.
    film_profile - label string for the film profile to use, e.g. "kodak_portra_400
    print_profile - label string for the print profile to use, e.g. "kodak_portra_endura"
    """
    params = init_params(film_profile=film_profile, print_profile=print_profile)
    return params

__all__ = [
    "RuntimePhotoParams",
    "Simulator",
    "simulate",
    "simulate_preview",
    "AgXPhoto", # legacy for ART
    "photo_params", # legacy for ART
]
