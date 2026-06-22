"""Runtime package exports."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "digest_params": ("spektrafilm.runtime.params_builder", "digest_params"),
    "RuntimePhotoParams": ("spektrafilm.runtime.params_schema", "RuntimePhotoParams"),
    "Simulator": ("spektrafilm.runtime.process", "Simulator"),
    "RouteMaster": ("spektrafilm.runtime.route_master", "RouteMaster"),
    "init_params": ("spektrafilm.runtime.params_builder", "init_params"),
    "load_profile": ("spektrafilm.profiles.io", "load_profile"),
    "save_profile": ("spektrafilm.profiles.io", "save_profile"),
    "simulate": ("spektrafilm.runtime.process", "simulate"),
    "simulate_master": ("spektrafilm.runtime.process", "simulate_master"),
    "simulate_with_master": ("spektrafilm.runtime.process", "simulate_with_master"),
    "simulate_with_metadata": ("spektrafilm.runtime.process", "simulate_with_metadata"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_path, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module 'spektrafilm.runtime' has no attribute {name!r}") from exc
    value = getattr(import_module(module_path), attribute)
    globals()[name] = value
    return value
