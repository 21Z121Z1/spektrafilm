"""Optional array backends for GPU acceleration experiments."""

from spektrafilm.gpu.backend import (
    BackendUnavailableError,
    select_backend,
)

__all__ = [
    "BackendUnavailableError",
    "select_backend",
]
