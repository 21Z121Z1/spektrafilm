from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass, replace
from typing import Any


Mode = str


_UPSTREAM_COMPAT_COMMON: dict[str, Any] = {
    "camera": {
        "exposure_compensation_ev": 0.0,
        "auto_exposure": False,
        "auto_exposure_method": "center_weighted",
        "lens_blur_um": 0.0,
        "film_format_mm": 35.0,
        "filter_uv": (0.0, 410.0, 8.0),
        "filter_ir": (0.0, 675.0, 15.0),
        "diffusion_filter": {"active": False},
    },
    "enlarger": {
        "illuminant": "TH-KG3",
        "print_exposure": 1.0,
        "print_exposure_compensation": False,
        "normalize_print_exposure": True,
        "y_filter_shift": 0.0,
        "m_filter_shift": 0.0,
        "y_filter_neutral": 55,
        "m_filter_neutral": 65,
        "c_filter_neutral": 0,
        "lens_blur": 0.0,
        "diffusion_filter": {"active": False},
        "preflash_exposure": 0.0,
        "preflash_y_filter_shift": 0.0,
        "preflash_m_filter_shift": 0.0,
    },
    "scanner": {
        "lens_blur": 0.0,
        "white_correction": False,
        "black_correction": False,
        "white_level": 0.98,
        "black_level": 0.01,
        "unsharp_mask": (0.0, 0.0),
    },
    "film_render": {
        "density_curve_gamma": 1.0,
        "grain": {"active": False},
        "halation": {"active": False, "boost_ev": 0.0},
        "dir_couplers": {"active": True, "amount": 1.0, "diffusion_size_um": 0.0},
        "glare": {"active": False},
    },
    "print_render": {
        "glare": {"active": False},
    },
    "io": {
        "input_color_space": "sRGB",
        "input_cctf_decoding": False,
        "output_color_space": "sRGB",
        "output_cctf_encoding": True,
        "input_gamut_compress": {"active": False},
        "output_gamut_compress": {"algorithm": "off", "lightness_compression": None},
        "crop": False,
        "crop_center": (0.5, 0.5),
        "crop_size": (0.1, 0.1),
        "upscale_factor": 1.0,
    },
    "settings": {
        "rgb_to_raw_method": "hanatos2025",
        "apply_hanatos2025_adaptation_window": True,
        "apply_hanatos2025_adaptation_surface": False,
        "spectral_gaussian_blur": 0.0,
        "use_enlarger_lut": False,
        "use_scanner_lut": False,
        "lut_resolution": 17,
        "use_fast_stats": False,
        "preview_max_size": 640,
        "preview_mode": False,
        "neutral_print_filters_from_database": False,
    },
}


_UPSTREAM_COMPAT_RENDERING: dict[str, Any] = {
    "debug": {
        "deactivate_spatial_effects": False,
        "deactivate_stochastic_effects": True,
        "print_timings": False,
        "lut_mode": False,
    },
    "film_render": {
        "halation": {"active": True, "boost_ev": 0.0},
        "dir_couplers": {"active": True},
    },
}


_UPSTREAM_COMPAT_STRICT: dict[str, Any] = {
    "debug": {
        "deactivate_spatial_effects": True,
        "deactivate_stochastic_effects": True,
        "print_timings": False,
        "lut_mode": True,
    },
}


def build_param_spec(
    *,
    mode: Mode,
    case: dict[str, Any],
    backend: str,
    materialize_policy: str = "numpy_float64",
) -> dict[str, Any]:
    if mode not in {"upstream_compat", "product_sdr"}:
        raise ValueError("mode must be 'upstream_compat' or 'product_sdr'")

    common = (
        _build_upstream_compat_common(case)
        if mode == "upstream_compat"
        else _build_product_sdr_common(case)
    )
    candidate_settings = {
        "compute_backend": backend,
        "gpu_precision": "float64" if backend == "cpu" else "float32",
        "materialize_policy": materialize_policy,
        "gpu_validate": False,
    }
    return {
        "mode": mode,
        "fixture": copy.deepcopy(case),
        "film_profile": case["film_profile"],
        "print_profile": case["print_profile"],
        "scan_film": bool(case["scan_film"]),
        "common_overrides": common,
        "reference_overrides": {},
        "candidate_overrides": {
            "settings": candidate_settings,
            "io": {
                "output_clip_min": False,
                "output_clip_max": False,
            },
        },
    }


def build_runtime_params(spec: dict[str, Any], *, implementation: str):
    from spektrafilm.runtime.params_builder import digest_params, init_params

    if implementation not in {"reference", "candidate"}:
        raise ValueError("implementation must be 'reference' or 'candidate'")

    params = init_params(
        film_profile=str(spec["film_profile"]),
        print_profile=str(spec["print_profile"]),
    )
    apply_overrides(params, spec.get("common_overrides", {}))
    extra_key = f"{implementation}_overrides"
    apply_overrides(params, spec.get(extra_key, {}))
    params.io.scan_film = bool(spec["scan_film"])
    params = digest_params(params)
    params.io.scan_film = bool(spec["scan_film"])
    return params


def apply_overrides(target: Any, overrides: dict[str, Any]) -> None:
    missing: list[str] = []
    _apply_overrides(target, overrides, path="", missing=missing)
    if missing:
        joined = ", ".join(sorted(missing))
        raise AttributeError(f"alignment param override targets missing fields: {joined}")


def _build_upstream_compat_common(case: dict[str, Any]) -> dict[str, Any]:
    common = copy.deepcopy(_UPSTREAM_COMPAT_COMMON)
    if str(case.get("fixture_kind")) == "rendering":
        _deep_update(common, _UPSTREAM_COMPAT_RENDERING)
    else:
        _deep_update(common, _UPSTREAM_COMPAT_STRICT)
    common.setdefault("io", {})["scan_film"] = bool(case["scan_film"])
    return common


def _build_product_sdr_common(case: dict[str, Any]) -> dict[str, Any]:
    from spektrafilm_gui.params_mapper import build_params_from_state
    from spektrafilm_gui.state import PROJECT_DEFAULT_GUI_STATE, clone_gui_state, digest_after_selection

    state = clone_gui_state(PROJECT_DEFAULT_GUI_STATE)
    state.selection.film_stock = str(case["film_profile"])
    state.selection.print_paper = str(case["print_profile"])
    state.simulation.io.scan_film = bool(case["scan_film"])
    raw_params = build_params_from_state(state)
    digested = digest_after_selection(copy.deepcopy(raw_params))
    digested.io.scan_film = bool(case["scan_film"])

    common = _extract_common_overrides(digested)
    common.setdefault("io", {})["scan_film"] = bool(case["scan_film"])
    return common


def _extract_common_overrides(params: Any) -> dict[str, Any]:
    return {
        "camera": _to_plain_dataclass(params.camera),
        "enlarger": _to_plain_dataclass(params.enlarger),
        "scanner": _to_plain_dataclass(params.scanner),
        "film_render": _to_plain_dataclass(params.film_render),
        "print_render": _to_plain_dataclass(params.print_render),
        "io": _filter_known_keys(
            _to_plain_dataclass(params.io),
            {
                "input_color_space",
                "input_cctf_decoding",
                "output_color_space",
                "output_cctf_encoding",
                "input_gamut_compress",
                "output_gamut_compress",
                "crop",
                "crop_center",
                "crop_size",
                "upscale_factor",
                "scan_film",
            },
            dropped={"output_clip_min", "output_clip_max"},
            section="io",
        ),
        "debug": _to_plain_dataclass(params.debug),
        "settings": _filter_known_keys(
            _to_plain_dataclass(params.settings),
            {
                "rgb_to_raw_method",
                "apply_hanatos2025_adaptation_window",
                "apply_hanatos2025_adaptation_surface",
                "spectral_gaussian_blur",
                "use_enlarger_lut",
                "use_scanner_lut",
                "lut_resolution",
                "use_fast_stats",
                "preview_max_size",
                "preview_mode",
                "neutral_print_filters_from_database",
            },
            dropped={
                "color_management_workflow",
                "compute_backend",
                "gpu_precision",
                "materialize_policy",
                "gpu_validate",
                "gpu_validation_tolerance",
                "gpu_aggressive_cleanup",
                "gpu_cleanup_cache_threshold_mb",
                "gpu_tile_rows",
                "gpu_disable_spectral_tiling",
                "gpu_spatial_tile_rows",
                "gpu_disable_spatial_tiling",
            },
            section="settings",
        ),
    }


def _apply_overrides(target: Any, overrides: dict[str, Any], *, path: str, missing: list[str]) -> None:
    for key, value in overrides.items():
        attr = _target_attr(target, key)
        current_path = f"{path}.{key}" if path else key
        if attr is None:
            missing.append(current_path)
            continue
        if isinstance(value, dict):
            child = getattr(target, attr)
            if _is_frozen_dataclass(child):
                setattr(target, attr, _replace_dataclass(child, value, path=current_path, missing=missing))
            else:
                _apply_overrides(child, value, path=current_path, missing=missing)
        else:
            setattr(target, attr, _tupleify(value))


def _target_attr(target: Any, key: str) -> str | None:
    if hasattr(target, key):
        return key
    grain_aliases = {
        "particle_area_um2": "agx_particle_area_um2",
        "particle_scale": "agx_particle_scale",
        "particle_scale_layers": "agx_particle_scale_layers",
        "agx_particle_area_um2": "particle_area_um2",
        "agx_particle_scale": "particle_scale",
        "agx_particle_scale_layers": "particle_scale_layers",
    }
    alias = grain_aliases.get(key)
    if alias and hasattr(target, alias):
        return alias
    return None


def _is_frozen_dataclass(value: Any) -> bool:
    return is_dataclass(value) and getattr(value, "__dataclass_params__").frozen


def _replace_dataclass(value: Any, overrides: dict[str, Any], *, path: str, missing: list[str]) -> Any:
    kwargs: dict[str, Any] = {}
    for key, item in overrides.items():
        attr = _target_attr(value, key)
        current_path = f"{path}.{key}" if path else key
        if attr is None:
            missing.append(current_path)
            continue
        current = getattr(value, attr)
        if isinstance(item, dict) and is_dataclass(current):
            kwargs[attr] = _replace_dataclass(current, item, path=current_path, missing=missing)
        else:
            kwargs[attr] = _tupleify(item)
    if missing:
        return value
    return replace(value, **kwargs)


def _to_plain_dataclass(value: Any) -> Any:
    if is_dataclass(value):
        result: dict[str, Any] = {}
        for field in fields(value):
            key = _canonical_field_name(field.name)
            result[key] = _to_plain_dataclass(getattr(value, field.name))
        return result
    if isinstance(value, tuple):
        return tuple(_to_plain_dataclass(item) for item in value)
    if isinstance(value, list):
        return [_to_plain_dataclass(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_plain_dataclass(item) for key, item in value.items()}
    return value


def _canonical_field_name(name: str) -> str:
    return {
        "agx_particle_area_um2": "particle_area_um2",
        "agx_particle_scale": "particle_scale",
        "agx_particle_scale_layers": "particle_scale_layers",
    }.get(name, name)


def _filter_keys(values: dict[str, Any], allowed: set[str]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if key in allowed}


def _filter_known_keys(
    values: dict[str, Any],
    allowed: set[str],
    *,
    dropped: set[str],
    section: str,
) -> dict[str, Any]:
    unknown = set(values) - allowed - dropped
    if unknown:
        joined = ", ".join(sorted(unknown))
        raise ValueError(f"unmapped {section} schema drift for upstream alignment: {joined}")
    return _filter_keys(values, allowed)


def _tupleify(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_tupleify(item) for item in value)
    return value


def _deep_update(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = copy.deepcopy(value)
