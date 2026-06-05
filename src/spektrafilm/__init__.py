"""Public package exports for spektrafilm.

The top-level package stays lightweight so tooling can import submodules without
eagerly loading the full simulation stack.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "load_profile": ("spektrafilm.profiles.io", "load_profile"),
    "save_profile": ("spektrafilm.profiles.io", "save_profile"),
    "RuntimePhotoParams": ("spektrafilm.runtime.params_schema", "RuntimePhotoParams"),
    "RouteMaster": ("spektrafilm.runtime.route_master", "RouteMaster"),
    "init_params": ("spektrafilm.runtime.api", "init_params"),
    "digest_params": ("spektrafilm.runtime.api", "digest_params"),
    "Simulator": ("spektrafilm.runtime.process", "Simulator"),
    "simulate": ("spektrafilm.runtime.process", "simulate"),
    "simulate_master": ("spektrafilm.runtime.process", "simulate_master"),
    "simulate_preview": ("spektrafilm.runtime.process", "simulate_preview"),
    "simulate_with_metadata": ("spektrafilm.runtime.process", "simulate_with_metadata"),
    "AgXPhoto": ("spektrafilm.runtime.process", "AgXPhoto"),
    "photo_params": ("spektrafilm.runtime.process", "photo_params"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_path, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'spektrafilm' has no attribute {name!r}") from exc
    value = getattr(import_module(module_path), attribute)
    globals()[name] = value
    return value
