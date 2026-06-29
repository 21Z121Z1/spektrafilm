from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np


ACES_INTERCHANGE_COLOR_SPACE = "ACES2065-1"
ACES_WORKING_COLOR_SPACE = "ACEScg"
ACES_LOG_GRADING_COLOR_SPACES = frozenset({"ACEScct", "ACEScc"})
ACES_SCENE_LINEAR_COLOR_SPACES = frozenset({ACES_INTERCHANGE_COLOR_SPACE, ACES_WORKING_COLOR_SPACE})


class AcesOcioUnavailableError(RuntimeError):
    """Raised when an official OCIO ACES path is requested but unavailable."""


@dataclass(frozen=True, slots=True)
class AcesTransformDiagnostics:
    implementation_kind: str
    source_color_space: str | None = None
    destination_color_space: str | None = None
    display: str | None = None
    view: str | None = None
    looks: str | None = None
    ocio_config_source: str | None = None
    ocio_config_cache_id: str | None = None
    ocio_roles: Mapping[str, str] = field(default_factory=dict)
    transform_id: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcesContext:
    working_space: str = ACES_WORKING_COLOR_SPACE
    interchange_space: str = ACES_INTERCHANGE_COLOR_SPACE
    input_color_space: str | None = None
    output_color_space: str | None = None
    apply_cctf_decoding: bool = False
    display: str | None = None
    view: str | None = None
    looks: str | None = None
    implementation_kind: str = "spektrafilm_local"
    transform_id: str | None = None
    ocio_config_source: str | None = None


_ACES_SDR_INPUT_MATRIX = np.array(
    [[0.59719, 0.35458, 0.04823], [0.07600, 0.90834, 0.01566], [0.02840, 0.13383, 0.83777]],
    dtype=np.float32,
)
_ACES_SDR_OUTPUT_MATRIX = np.array(
    [[1.60475, -0.53108, -0.07367], [-0.10208, 1.10813, -0.00605], [-0.00327, -0.07276, 1.07602]],
    dtype=np.float32,
)
_COMMON_ACES_BUILTIN_CONFIGS = (
    "studio-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "studio-config-v2.2.0_aces-v1.3_ocio-v2.4",
    "studio-config-v2.1.0_aces-v1.3_ocio-v2.3",
    "studio-config-v1.0.0_aces-v1.3_ocio-v2.1",
    "cg-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "cg-config-v2.2.0_aces-v1.3_ocio-v2.4",
    "cg-config-v2.1.0_aces-v1.3_ocio-v2.3",
)


def is_aces_scene_linear_space(color_space: str) -> bool:
    return str(color_space) in ACES_SCENE_LINEAR_COLOR_SPACES


def is_ocio_available() -> bool:
    try:
        _import_ocio()
    except AcesOcioUnavailableError:
        return False
    return True


def _import_ocio() -> Any:
    try:
        import PyOpenColorIO as ocio
    except Exception:
        try:
            import opencolorio as ocio  # type: ignore[no-redef]
        except Exception as exc:
            raise AcesOcioUnavailableError(
                "PyOpenColorIO is not installed. Install the dev extra or provide "
                "an environment with opencolorio to use official ACES OCIO views."
            ) from exc
    return ocio


def _as_float32_rgb(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image, dtype=np.float32)
    if array.shape[-1] != 3:
        raise ValueError(f"Expected RGB array with last dimension 3, got shape {array.shape!r}.")
    return array


def _colour_module(colour_module: Any | None = None) -> Any:
    if colour_module is not None:
        return colour_module
    import colour

    return colour


def to_acescg(
    image_data: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Convert RGB data from a named colour-science RGB space to ACEScg scene-linear."""

    colour = _colour_module(colour_module)
    image = _as_float32_rgb(image_data)
    converted = colour.RGB_to_RGB(
        image,
        str(input_color_space),
        ACES_WORKING_COLOR_SPACE,
        apply_cctf_decoding=bool(apply_cctf_decoding),
        apply_cctf_encoding=False,
    )
    return np.asarray(converted, dtype=np.float32)


def acescg_to_aces2065_1(image_data: np.ndarray, *, colour_module: Any | None = None) -> np.ndarray:
    colour = _colour_module(colour_module)
    image = _as_float32_rgb(image_data)
    converted = colour.RGB_to_RGB(
        image,
        ACES_WORKING_COLOR_SPACE,
        ACES_INTERCHANGE_COLOR_SPACE,
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    return np.asarray(converted, dtype=np.float32)


def aces2065_1_to_acescg(image_data: np.ndarray, *, colour_module: Any | None = None) -> np.ndarray:
    colour = _colour_module(colour_module)
    image = _as_float32_rgb(image_data)
    converted = colour.RGB_to_RGB(
        image,
        ACES_INTERCHANGE_COLOR_SPACE,
        ACES_WORKING_COLOR_SPACE,
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    return np.asarray(converted, dtype=np.float32)


def _apply_rgb_matrix(image: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    return np.tensordot(image, matrix.T, axes=1).astype(np.float32, copy=False)


def _aces_sdr_rrt_odt_fit(linear_srgb: np.ndarray) -> np.ndarray:
    color = _apply_rgb_matrix(linear_srgb, _ACES_SDR_INPUT_MATRIX)
    color = (color * (color + np.float32(0.0245786)) - np.float32(0.000090537)) / (
        color * (np.float32(0.983729) * color + np.float32(0.4329510)) + np.float32(0.238081)
    )
    return _apply_rgb_matrix(color, _ACES_SDR_OUTPUT_MATRIX)


def _srgb_cctf_encoding(linear_rgb: np.ndarray) -> np.ndarray:
    linear_rgb = np.clip(np.asarray(linear_rgb, dtype=np.float32), 0.0, None)
    return np.where(
        linear_rgb <= np.float32(0.0031308),
        np.float32(12.92) * linear_rgb,
        np.float32(1.055) * np.power(linear_rgb, np.float32(1.0 / 2.4)) - np.float32(0.055),
    ).astype(np.float32, copy=False)


def render_aces_local_sdr_preview(
    image_data: np.ndarray,
    *,
    color_space: str,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Render ACES scene-linear RGB through Spektrafilm's local SDR preview.

    This path is intentionally labelled local. It is not an official OCIO/CTL
    ACES Output Transform and must not be used to claim Studio Config parity.
    """

    color_space = str(color_space)
    if not is_aces_scene_linear_space(color_space):
        raise ValueError(f"ACES local SDR preview requires ACES scene-linear input, got {color_space!r}.")
    colour = _colour_module(colour_module)
    image = _as_float32_rgb(image_data)
    linear_srgb = colour.RGB_to_RGB(
        image,
        color_space,
        "sRGB",
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    linear_srgb = np.clip(np.asarray(linear_srgb, dtype=np.float32), 0.0, None)
    rendered = _aces_sdr_rrt_odt_fit(linear_srgb)
    return np.asarray(np.clip(_srgb_cctf_encoding(rendered), 0.0, 1.0), dtype=np.float32)


def _builtin_config_names(ocio: Any) -> tuple[str, ...]:
    getter = getattr(ocio, "BuiltinConfigRegistry", None)
    if getter is not None:
        try:
            registry = getter()
            get_builtin_configs = getattr(registry, "getBuiltinConfigs", None)
            items = get_builtin_configs() if get_builtin_configs is not None else registry
            names = []
            for item in items:
                if isinstance(item, str):
                    names.append(item)
                elif isinstance(item, Sequence) and item:
                    names.append(str(item[0]))
                else:
                    names.append(str(item))
            if names:
                return tuple(names)
        except Exception:
            pass
    return _COMMON_ACES_BUILTIN_CONFIGS


def _validate_ocio_config(config: Any) -> None:
    validate = getattr(config, "validate", None)
    if validate is not None:
        validate()


def load_aces_ocio_config(
    config_path: str | Path | None = None,
    *,
    builtin_config_name: str | None = None,
    ocio_module: Any | None = None,
) -> tuple[Any, AcesTransformDiagnostics]:
    """Load an official/user OCIO config for ACES view rendering.

    ``ocio_module`` is an optional test seam. Runtime callers should leave it
    unset so PyOpenColorIO/opencolorio is imported normally.
    """

    ocio = ocio_module if ocio_module is not None else _import_ocio()
    if config_path is not None:
        path = str(Path(config_path).expanduser())
        config = ocio.Config.CreateFromFile(path)
        _validate_ocio_config(config)
        return config, _diagnostics_for_config(config, config_source=path)

    names = (builtin_config_name,) if builtin_config_name else tuple(
        name for name in _builtin_config_names(ocio) if "aces" in str(name).lower()
    )
    attempted: list[str] = []
    last_exc: Exception | None = None
    for name in names:
        if not name:
            continue
        attempted.append(str(name))
        try:
            config = ocio.Config.CreateFromBuiltinConfig(str(name))
            _validate_ocio_config(config)
            return config, _diagnostics_for_config(config, config_source=f"builtin:{name}")
        except Exception as exc:
            last_exc = exc
    raise AcesOcioUnavailableError(
        "Unable to load an ACES OCIO built-in config. Attempted: "
        f"{', '.join(attempted) if attempted else '<none found>'}. Provide config_path explicitly."
    ) from last_exc


def _diagnostics_for_config(config: Any, *, config_source: str) -> AcesTransformDiagnostics:
    roles: dict[str, str] = {}
    for role in (
        "aces_interchange",
        "scene_linear",
        "color_timing",
        "compositing_log",
        "color_picking",
        "default",
        "data",
    ):
        try:
            value = config.getRoleColorSpace(role)
        except Exception:
            value = None
        if value:
            roles[role] = str(value)
    try:
        cache_id = str(config.getCacheID())
    except Exception:
        cache_id = None
    return AcesTransformDiagnostics(
        implementation_kind="ocio_official_or_configured",
        ocio_config_source=config_source,
        ocio_config_cache_id=cache_id,
        ocio_roles=roles,
    )


def _default_view_for_display(config: Any, display: str, explicit_view: str | None) -> str:
    try:
        views = [str(view) for view in config.getViews(display)]
    except Exception as exc:
        raise AcesOcioUnavailableError(f"Unable to list OCIO views for display {display!r}.") from exc
    if explicit_view is not None:
        if explicit_view not in views:
            raise AcesOcioUnavailableError(
                f"OCIO display {display!r} does not provide view {explicit_view!r}; available views: {views}."
            )
        return explicit_view
    for preferred_prefix in ("ACES 2.0 - SDR", "ACES 1.0 - SDR Video"):
        for candidate in views:
            if candidate.startswith(preferred_prefix):
                return candidate
    for candidate in views:
        if candidate != "Raw":
            return candidate
    raise AcesOcioUnavailableError(f"OCIO display {display!r} has no usable view.")


def render_aces_ocio_view(
    image_data: np.ndarray,
    *,
    config: Any,
    source_color_space: str = "ACES - ACEScg",
    display: str,
    view: str | None = None,
    looks: str | None = None,
    ocio_module: Any | None = None,
) -> tuple[np.ndarray, AcesTransformDiagnostics]:
    """Render ACES scene-linear RGB through a supplied OCIO display/view."""

    ocio = ocio_module if ocio_module is not None else _import_ocio()
    view_name = _default_view_for_display(config, display, view)
    image = np.ascontiguousarray(_as_float32_rgb(image_data), dtype=np.float32)
    try:
        processor = config.getProcessor(source_color_space, display, view_name, ocio.TRANSFORM_DIR_FORWARD)
    except TypeError:
        transform = ocio.DisplayViewTransform(
            src=source_color_space,
            display=display,
            view=view_name,
            looks=looks or "",
            direction=ocio.TRANSFORM_DIR_FORWARD,
        )
        processor = config.getProcessor(transform)
    cpu = processor.getDefaultCPUProcessor()
    flat = np.ascontiguousarray(image.reshape((-1, 3)), dtype=np.float32)
    cpu.applyRGB(flat)
    result = flat.reshape(image.shape).astype(np.float32, copy=False)
    diagnostics = _diagnostics_for_config(config, config_source="provided")
    return result, AcesTransformDiagnostics(
        implementation_kind="ocio_official_or_configured",
        source_color_space=source_color_space,
        display=display,
        view=view_name,
        looks=looks,
        ocio_config_source=diagnostics.ocio_config_source,
        ocio_config_cache_id=diagnostics.ocio_config_cache_id,
        ocio_roles=diagnostics.ocio_roles,
        notes=("Rendered through PyOpenColorIO processor; output semantics depend on the supplied config.",),
    )


def apply_aces_reference_gamut_compression(
    image_data: np.ndarray,
    *,
    threshold: float = 0.0,
    limit: float = 1.0,
    power: float = 6.0,
) -> np.ndarray:
    """Apply Spektrafilm's existing ACES RGC-family RGB compression wrapper."""

    from spektrafilm.utils.gamut_compression import compress_rgb_aces_rgc

    image = _as_float32_rgb(image_data)
    compressed = compress_rgb_aces_rgc(image, threshold=float(threshold), limit=float(limit), power=float(power))
    return np.asarray(compressed, dtype=np.float32)


def build_aces_transform_manifest(
    *,
    context: AcesContext | None = None,
    diagnostics: AcesTransformDiagnostics | None = None,
    input_color_space: str | None = None,
    output_color_space: str | None = None,
    display: str | None = None,
    view: str | None = None,
    implementation_kind: str | None = None,
    transform_id: str | None = None,
) -> dict[str, Any]:
    """Build a project-local ACES transform manifest for future AMF sidecars."""

    ctx = context or AcesContext()
    diag = diagnostics
    kind = implementation_kind or (diag.implementation_kind if diag else ctx.implementation_kind)
    tid = transform_id or (diag.transform_id if diag else ctx.transform_id)
    manifest: dict[str, Any] = {
        "schema": "spektrafilm.aces_transform_manifest.v1",
        "working_space": ctx.working_space,
        "interchange_space": ctx.interchange_space,
        "input_color_space": input_color_space or ctx.input_color_space,
        "output_color_space": output_color_space or ctx.output_color_space,
        "display": display or (diag.display if diag else ctx.display),
        "view": view or (diag.view if diag else ctx.view),
        "looks": diag.looks if diag else ctx.looks,
        "implementation_kind": kind,
        "transform_id": tid,
        "transform_id_status": "explicit" if tid else "not_provided_do_not_infer",
        "amf_ready": False,
        "amf_notes": (
            "Project-local manifest only. It preserves fields needed for future AMF emission "
            "but does not claim ACES AMF conformance or invent official Transform IDs."
        ),
    }
    if diag is not None:
        manifest["ocio"] = {
            "config_source": diag.ocio_config_source,
            "config_cache_id": diag.ocio_config_cache_id,
            "roles": dict(diag.ocio_roles),
        }
        manifest["diagnostic_notes"] = list(diag.notes)
    return manifest
