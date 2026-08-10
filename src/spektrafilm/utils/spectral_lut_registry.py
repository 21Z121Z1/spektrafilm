import importlib.resources
from functools import lru_cache

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


_DATA_PACKAGE = "spektrafilm.data.luts.spectral_upsampling"


@lru_cache(maxsize=1)
def spectral_lut_registry():
    registry = {}
    for entry in importlib.resources.files(_DATA_PACKAGE).iterdir():
        if entry.name.endswith(".toml"):
            with entry.open("rb") as file:
                descriptor = tomllib.load(file)
            identifier = descriptor["identifier"]
            if identifier in registry:
                raise ValueError(f"duplicate spectral LUT identifier: {identifier}")
            registry[identifier] = descriptor
    return registry


def available_spectral_luts(kind=None):
    registry = spectral_lut_registry()
    return tuple(sorted(
        identifier
        for identifier, descriptor in registry.items()
        if kind is None or descriptor.get("kind") == kind
    ))


def spectral_lut_descriptor(identifier):
    registry = spectral_lut_registry()
    if identifier not in registry:
        raise KeyError(
            f"no spectral LUT {identifier!r}; available: {sorted(registry)}"
        )
    return registry[identifier]


def spectral_lut_resource(identifier):
    descriptor = spectral_lut_descriptor(identifier)
    resource = importlib.resources.files(_DATA_PACKAGE).joinpath(descriptor["file"])
    if not resource.is_file():
        raise FileNotFoundError(descriptor["file"])
    return resource
