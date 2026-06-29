"""ACES/OCIO compatibility helpers for the runtime package.

This module keeps ACES-oriented glue out of ``color_management.py`` while
preserving the existing public API there.  The local preview path is a fast,
deterministic Spektrafilm implementation; the official view path is explicitly
OCIO-backed and fails clearly when PyOpenColorIO or an ACES config is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from spektrafilm.color_management import (
    ACES_INTERCHANGE_COLOR_SPACE,
    ACES_WORKING_COLOR_SPACE,
    aces_sdr_video_view_transform,
)
from spektrafilm.utils.gamut_compression import (
    OutputGamutCompressSpec,
    compress_rgb,
)


DEFAULT_ACES_BUILTIN_CONFIGS: tuple[str, ...] = (
    "studio-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "studio-config-v2.2.0_aces-v1.3_ocio-v2.4",
    "studio-config-v2.1.0_aces-v1.3_ocio-v2.3",
    "studio-config-v1.0.0_aces-v1.3_ocio-v2.1",
    "cg-config-v4.0.0_aces-v2.0_ocio-v2.5",
    "cg-config-v2.2.0_aces-v1.3_ocio-v2.4",
)


class AcesCompatibilityError(RuntimeError):
    """Base exception for ACES compatibility failures."""


class OcioUnavailableError(AcesCompatibilityError):
    """Raised when an official OCIO path is requested without PyOpenColorIO."""


class AcesOcioConfigError(AcesCompatibilityError):
    """Raised when an ACES OCIO config cannot be loaded or validated."""


@dataclass(frozen=True, slots=True)
class AcesTransformDiagnostics:
    """Diagnostics for an ACES conversion or view transform."""

    implementation_kind: str
    source_color_space: str
    target_color_space: str | None = None
    config_source: str | None = None
    config_path: str | None = None
    builtin_config_name: str | None = None
    display: str | None = None
    view: str | None = None
    look: str | None = None
    roles: dict[str, str] = field(default_factory=dict)
    transform_id: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AcesContext:
    """Project-local ACES compatibility context.

    ``transform_id`` fields are intentionally optional placeholders.  They
    should be populated only when using an official transform with a known ID.
    """

    working_space: str = ACES_WORKING_COLOR_SPACE
    interchange_space: str = ACES_INTERCHANGE_COLOR_SPACE
    ocio_config_path: str | Path | None = None
    ocio_builtin_config: str | None = None
    display: str = "sRGB - Display"
    view: str | None = None
    look: str | None = None
    input_color_space: str | None = None
    output_color_space: str | None = None
    local_preview_transform_id: str | None = None
    ocio_view_transform_id: str | None = None
    implementation_kind: str = "spektrafilm_local"


def _import_ocio():
    try:
        import PyOpenColorIO as ocio
    except ImportError as exc:  # pragma: no cover - exercised by monkeypatch tests.
        raise OcioUnavailableError(
            "PyOpenColorIO is required for official ACES OCIO view rendering. "
            "Install the dev extra or pass through the local preview API explicitly."
        ) from exc
    return ocio


def is_ocio_available() -> bool:
    """Return whether PyOpenColorIO can be imported."""

    try:
        _import_ocio()
    except OcioUnavailableError:
        return False
    return True


def _builtin_config_names(ocio: Any) -> tuple[str, ...]:
    registry_type = getattr(ocio, "BuiltinConfigRegistry", None)
    if registry_type is None:
        return ()
    try:
        names: list[str] = []
        for item in registry_type().getBuiltinConfigs():
            if isinstance(item, tuple) and item:
                names.append(str(item[0]))
            else:
                names.append(str(item))
        return tuple(names)
    except Exception:
        try:
            return tuple(str(name) for name in registry_type())
        except Exception:
            return ()


def load_aces_ocio_config(
    config_path: str | Path | None = None,
    *,
    builtin_config_name: str | None = None,
    ocio_module: Any | None = None,
) -> tuple[Any, AcesTransformDiagnostics]:
    """Load a user ACES OCIO config or a known built-in ACES config.

    Raises a clear exception instead of silently falling back to the local
    preview path.  Returns ``(config, diagnostics)``.
    """

    ocio = ocio_module if ocio_module is not None else _import_ocio()
    try:
        if config_path is not None:
            config = ocio.Config.CreateFromFile(str(config_path))
            config.validate()
            diagnostics = AcesTransformDiagnostics(
                implementation_kind="ocio_official",
                source_color_space=ACES_WORKING_COLOR_SPACE,
                config_source="file",
                config_path=str(config_path),
                roles=_config_roles(config),
            )
            return config, diagnostics

        candidates = (builtin_config_name,) if builtin_config_name else DEFAULT_ACES_BUILTIN_CONFIGS
        available = set(_builtin_config_names(ocio))
        for candidate in candidates:
            if candidate is None:
                continue
            if available and candidate not in available:
                continue
            config = ocio.Config.CreateFromBuiltinConfig(candidate)
            config.validate()
            diagnostics = AcesTransformDiagnostics(
                implementation_kind="ocio_official",
                source_color_space=ACES_WORKING_COLOR_SPACE,
                config_source="builtin",
                builtin_config_name=candidate,
                roles=_config_roles(config),
            )
            return config, diagnostics
    except OcioUnavailableError:
        raise
    except Exception as exc:
        raise AcesOcioConfigError(f"Failed to load ACES OCIO config: {exc}") from exc

    raise AcesOcioConfigError(
        "No usable ACES OCIO built-in config was found. "
        f"Tried: {', '.join(str(c) for c in candidates if c)}."
    )


def _config_roles(config: Any) -> dict[str, str]:
    roles: dict[str, str] = {}
    for role in ("aces_interchange", "scene_linear", "color_timing", "compositing_log"):
        try:
            if config.hasRole(role):
                roles[role] = str(config.getRoleColorSpace(role))
        except Exception:
            continue
    return roles


def _as_float32_rgb(image_data: np.ndarray) -> np.ndarray:
    image = np.asarray(image_data, dtype=np.float32)
    if image.shape[-1:] != (3,):
        raise ValueError(f"Expected RGB data with last dimension 3, got shape {image.shape}.")
    return image


def to_acescg(
    image_data: np.ndarray,
    *,
    input_color_space: str,
    apply_cctf_decoding: bool = False,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Convert RGB data from a colour-science RGB space to ACEScg."""

    if colour_module is None:
        import colour as colour_module

    image = _as_float32_rgb(image_data)
    out = colour_module.RGB_to_RGB(
        image,
        str(input_color_space),
        ACES_WORKING_COLOR_SPACE,
        apply_cctf_decoding=bool(apply_cctf_decoding),
        apply_cctf_encoding=False,
    )
    return np.asarray(out, dtype=np.float32)


def acescg_to_aces2065_1(
    image_data: np.ndarray,
    *,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Convert scene-linear ACEScg (AP1) to ACES2065-1 (AP0)."""

    if colour_module is None:
        import colour as colour_module

    image = _as_float32_rgb(image_data)
    out = colour_module.RGB_to_RGB(
        image,
        ACES_WORKING_COLOR_SPACE,
        ACES_INTERCHANGE_COLOR_SPACE,
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    return np.asarray(out, dtype=np.float32)


def aces2065_1_to_acescg(
    image_data: np.ndarray,
    *,
    colour_module: Any | None = None,
) -> np.ndarray:
    """Convert scene-linear ACES2065-1 (AP0) to ACEScg (AP1)."""

    if colour_module is None:
        import colour as colour_module

    image = _as_float32_rgb(image_data)
    out = colour_module.RGB_to_RGB(
        image,
        ACES_INTERCHANGE_COLOR_SPACE,
        ACES_WORKING_COLOR_SPACE,
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )
    return np.asarray(out, dtype=np.float32)


def render_aces_local_sdr_preview(
    image_data: np.ndarray,
    *,
    color_space: str = ACES_WORKING_COLOR_SPACE,
    colour_module: Any | None = None,
) -> tuple[np.ndarray, AcesTransformDiagnostics]:
    """Render the existing Spektrafilm local ACES-style SDR preview."""

    preview = aces_sdr_video_view_transform(
        image_data,
        color_space=color_space,
        colour_module=colour_module,
    )
    diagnostics = AcesTransformDiagnostics(
        implementation_kind="spektrafilm_local",
        source_color_space=str(color_space),
        target_color_space="sRGB display code values",
        display="sRGB",
        view="Spektrafilm local ACES-style SDR preview",
        transform_id=None,
        notes=(
            "Local deterministic ACES-style preview; not an official ACES Output Transform.",
        ),
    )
    return preview, diagnostics


def _default_view_for_display(config: Any, display: str, explicit_view: str | None) -> str:
    views = list(config.getViews(display))
    if explicit_view is not None:
        if explicit_view not in views:
            raise AcesOcioConfigError(
                f"OCIO display {display!r} does not provide view {explicit_view!r}; "
                f"available views: {views}."
            )
        return explicit_view
    for preferred_prefix in ("ACES 2.0 - SDR", "ACES 1.0 - SDR Video"):
        for view in views:
            if str(view).startswith(preferred_prefix):
                return str(view)
    for view in views:
        if str(view) != "Raw":
            return str(view)
    raise AcesOcioConfigError(f"OCIO display {display!r} has no usable view.")


def render_aces_ocio_view(
    image_data: np.ndarray,
    *,
    context: AcesContext | None = None,
    config: Any | None = None,
    display: str | None = None,
    view: str | None = None,
    source_color_space: str = ACES_WORKING_COLOR_SPACE,
    ocio_module: Any | None = None,
) -> tuple[np.ndarray, AcesTransformDiagnostics]:
    """Render scene-linear ACES through an official OCIO display/view path."""

    ocio = ocio_module if ocio_module is not None else _import_ocio()
    ctx = context or AcesContext()
    loaded_diag: AcesTransformDiagnostics | None = None
    if config is None:
        config, loaded_diag = load_aces_ocio_config(
            ctx.ocio_config_path,
            builtin_config_name=ctx.ocio_builtin_config,
            ocio_module=ocio,
        )
    display_name = display or ctx.display
    if display_name not in list(config.getDisplays()):
        raise AcesOcioConfigError(
            f"OCIO config does not provide display {display_name!r}; "
            f"available displays: {list(config.getDisplays())}."
        )
    view_name = _default_view_for_display(config, display_name, view or ctx.view)

    transform = ocio.DisplayViewTransform()
    transform.setSrc(str(source_color_space))
    transform.setDisplay(display_name)
    transform.setView(view_name)
    if ctx.look:
        transform.setLooksBypass(False)
    processor = config.getProcessor(transform).getDefaultCPUProcessor()

    image = _as_float32_rgb(image_data)
    flat = np.array(image.reshape(-1, 3), dtype=np.float32, copy=True)
    processor.applyRGB(flat)
    out = flat.reshape(image.shape).astype(np.float32, copy=False)
    diagnostics = AcesTransformDiagnostics(
        implementation_kind="ocio_official",
        source_color_space=str(source_color_space),
        target_color_space="display/view code values",
        config_source=loaded_diag.config_source if loaded_diag else None,
        config_path=loaded_diag.config_path if loaded_diag else None,
        builtin_config_name=loaded_diag.builtin_config_name if loaded_diag else ctx.ocio_builtin_config,
        display=display_name,
        view=view_name,
        look=ctx.look,
        roles=_config_roles(config),
        transform_id=ctx.ocio_view_transform_id,
        notes=("Official OCIO display/view path; output range is config/view dependent.",),
    )
    return out, diagnostics


def apply_aces_reference_gamut_compression(
    image_data: np.ndarray,
    *,
    spec: OutputGamutCompressSpec | None = None,
) -> tuple[np.ndarray, AcesTransformDiagnostics]:
    """Apply the existing ACES RGC v1.3 output compression wrapper."""

    rgc_spec = spec or OutputGamutCompressSpec(algorithm="aces_rgc", knee=(0.815, 1.0, 1.2))
    if rgc_spec.algorithm != "aces_rgc":
        raise ValueError("apply_aces_reference_gamut_compression requires algorithm='aces_rgc'.")
    image = _as_float32_rgb(image_data)
    out = compress_rgb(image, rgc_spec).astype(np.float32, copy=False)
    diagnostics = AcesTransformDiagnostics(
        implementation_kind="spektrafilm_local",
        source_color_space="linear RGB",
        target_color_space="linear RGB after ACES RGC",
        transform_id=None,
        notes=(
            "ACES Reference Gamut Compression v1.3 wrapper over Spektrafilm's existing implementation.",
            "This is distinct from perceptual output gamut compression algorithms.",
        ),
    )
    return out, diagnostics


def build_aces_transform_manifest(
    *,
    context: AcesContext | None = None,
    input_color_space: str | None = None,
    output_color_space: str | None = None,
    preview_diagnostics: AcesTransformDiagnostics | None = None,
    ocio_diagnostics: AcesTransformDiagnostics | None = None,
    rgc_diagnostics: AcesTransformDiagnostics | None = None,
) -> dict[str, Any]:
    """Build a project-local manifest with future AMF-compatible fields."""

    ctx = context or AcesContext()
    active_diag = ocio_diagnostics or preview_diagnostics
    return {
        "schema": "spektrafilm.aces_transform_manifest",
        "schema_version": 1,
        "working_space": ctx.working_space,
        "interchange_space": ctx.interchange_space,
        "input_color_space": input_color_space or ctx.input_color_space,
        "output_color_space": output_color_space or ctx.output_color_space,
        "preview": _diagnostics_dict(preview_diagnostics),
        "ocio_view": _diagnostics_dict(ocio_diagnostics),
        "reference_gamut_compression": _diagnostics_dict(rgc_diagnostics),
        "implementation_kind": active_diag.implementation_kind if active_diag else ctx.implementation_kind,
        "display": active_diag.display if active_diag else ctx.display,
        "view": active_diag.view if active_diag else ctx.view,
        "look": active_diag.look if active_diag else ctx.look,
        "transform_ids": {
            "input_transform_id": None,
            "look_transform_id": None,
            "output_transform_id": active_diag.transform_id if active_diag else None,
            "reference_gamut_compression_transform_id": None,
            "notes": "Placeholders only; Spektrafilm does not invent official ACES Transform IDs.",
        },
        "amf": {
            "compatible": False,
            "sidecar_kind": "project_local_manifest",
            "notes": "Future AMF mapping field; this is not an official AMF document.",
        },
    }


def _diagnostics_dict(diagnostics: AcesTransformDiagnostics | None) -> dict[str, Any] | None:
    if diagnostics is None:
        return None
    return {
        "implementation_kind": diagnostics.implementation_kind,
        "source_color_space": diagnostics.source_color_space,
        "target_color_space": diagnostics.target_color_space,
        "config_source": diagnostics.config_source,
        "config_path": diagnostics.config_path,
        "builtin_config_name": diagnostics.builtin_config_name,
        "display": diagnostics.display,
        "view": diagnostics.view,
        "look": diagnostics.look,
        "roles": dict(diagnostics.roles),
        "transform_id": diagnostics.transform_id,
        "notes": list(diagnostics.notes),
    }
