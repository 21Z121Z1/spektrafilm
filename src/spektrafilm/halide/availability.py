from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module as _import_module
from typing import Callable, Any


@dataclass(frozen=True, slots=True)
class HalideAvailability:
    installed: bool
    version: str | None = None
    install_dir: str | None = None
    error: str | None = None


def probe_halide(
    *,
    import_module: Callable[[str], Any] = _import_module,
) -> HalideAvailability:
    """Return lightweight diagnostics for the optional Halide package."""
    try:
        halide = import_module("halide")
    except Exception as exc:
        return HalideAvailability(
            installed=False,
            error=str(exc),
        )

    install_dir = None
    install_dir_fn = getattr(halide, "install_dir", None)
    if callable(install_dir_fn):
        try:
            install_dir = str(install_dir_fn())
        except Exception as exc:
            return HalideAvailability(
                installed=True,
                version=getattr(halide, "__version__", None),
                error=f"failed to query install_dir: {exc}",
            )

    return HalideAvailability(
        installed=True,
        version=getattr(halide, "__version__", None),
        install_dir=install_dir,
    )
