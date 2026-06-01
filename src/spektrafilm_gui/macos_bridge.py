from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from spektrafilm_gui.options import ComputeBackend, GpuPrecision, RGBColorSpaces


DEFAULT_FILM_STOCK = "kodak_gold_200"
DEFAULT_PRINT_PAPER = "kodak_supra_endura"


RAW_EXTENSIONS = {
    ".3fr",
    ".arw",
    ".cr2",
    ".cr3",
    ".dng",
    ".erf",
    ".fff",
    ".iiq",
    ".kdc",
    ".mef",
    ".mos",
    ".mrw",
    ".nef",
    ".orf",
    ".pef",
    ".raf",
    ".raw",
    ".rw2",
    ".sr2",
    ".srf",
    ".x3f",
}


@dataclass(frozen=True, slots=True)
class BridgeRenderOptions:
    input_path: Path
    preview_output_path: Path
    output_path: Path | None
    mode: str
    input_kind: str
    film_stock: str
    print_paper: str
    input_color_space: str
    apply_cctf_decoding: bool
    output_color_space: str
    saving_color_space: str
    saving_cctf_encoding: bool
    preview_max_size: int
    compute_backend: str
    gpu_precision: str
    scan_film: bool
    auto_exposure: bool
    exposure_compensation_ev: float
    print_exposure: float
    print_y_filter_shift: float
    print_m_filter_shift: float
    grain_active: bool
    halation_active: bool
    couplers_active: bool
    white_balance: str
    temperature: float
    tint: float
    lens_correction: bool
    output_cctf_encoding: bool = True


class CLIUsageError(ValueError):
    pass


def _enum_values(enum_cls: type[Any]) -> list[str]:
    return [member.value for member in enum_cls]


def _profile_catalog() -> tuple[list[str], list[str]]:
    profiles_dir = Path(__file__).resolve().parents[1] / "spektrafilm" / "data" / "profiles"
    films: list[str] = []
    papers: list[str] = []
    for profile_path in sorted(profiles_dir.glob("*.json")):
        try:
            with profile_path.open("r") as file:
                data = json.load(file)
        except (OSError, json.JSONDecodeError):
            continue
        info = data.get("info", {})
        stock = info.get("stock") or profile_path.stem
        support = info.get("support")
        if support == "paper":
            papers.append(str(stock))
        else:
            films.append(str(stock))
    return films, papers


def describe_catalog() -> dict[str, object]:
    films, papers = _profile_catalog()
    return {
        "film_profiles": films,
        "print_profiles": papers,
        "color_spaces": _enum_values(RGBColorSpaces),
        "compute_backends": _enum_values(ComputeBackend),
        "gpu_precisions": _enum_values(GpuPrecision),
        "defaults": {
            "film_stock": DEFAULT_FILM_STOCK,
            "print_paper": DEFAULT_PRINT_PAPER,
            "input_color_space": "sRGB",
            "apply_cctf_decoding": False,
            "output_color_space": "sRGB",
            "output_cctf_encoding": True,
            "saving_color_space": "sRGB",
            "saving_cctf_encoding": True,
            "preview_max_size": 640,
            "compute_backend": "cpu",
            "gpu_precision": "float32",
            "scan_film": False,
            "auto_exposure": True,
            "exposure_compensation_ev": 0.0,
            "print_exposure": 1.0,
            "print_y_filter_shift": 0.0,
            "print_m_filter_shift": 0.0,
            "grain_active": True,
            "halation_active": True,
            "couplers_active": True,
        },
    }


def build_state_from_options(options: BridgeRenderOptions):
    from spektrafilm_gui.state import build_default_gui_state

    state = build_default_gui_state(
        film_stock=options.film_stock,
        print_paper=options.print_paper,
    )
    state.input_image.input_color_space = options.input_color_space
    state.input_image.apply_cctf_decoding = bool(options.apply_cctf_decoding)
    state.display.preview_max_size = int(options.preview_max_size)

    state.load_raw.white_balance = options.white_balance
    state.load_raw.temperature = float(options.temperature)
    state.load_raw.tint = float(options.tint)
    state.load_raw.lens_correction = bool(options.lens_correction)

    state.simulation.film_stock = options.film_stock
    state.simulation.print_paper = options.print_paper
    state.simulation.output_color_space = options.output_color_space
    state.simulation.output_cctf_encoding = bool(options.output_cctf_encoding)
    state.simulation.saving_color_space = options.saving_color_space
    state.simulation.saving_cctf_encoding = bool(options.saving_cctf_encoding)
    state.simulation.compute_backend = options.compute_backend
    state.simulation.gpu_precision = options.gpu_precision
    state.simulation.scan_film = bool(options.scan_film)
    state.simulation.auto_exposure = bool(options.auto_exposure)
    state.simulation.exposure_compensation_ev = float(options.exposure_compensation_ev)
    state.simulation.print_exposure = float(options.print_exposure)
    state.simulation.print_y_filter_shift = float(options.print_y_filter_shift)
    state.simulation.print_m_filter_shift = float(options.print_m_filter_shift)

    state.grain.active = bool(options.grain_active)
    state.halation.active = bool(options.halation_active)
    state.couplers.active = bool(options.couplers_active)
    return state


def _is_raw_input(path: Path, input_kind: str) -> bool:
    if input_kind == "raw":
        return True
    if input_kind == "image":
        return False
    return path.suffix.lower() in RAW_EXTENSIONS


def _load_input_image(options: BridgeRenderOptions, *, load_image_fn: Callable[..., Any]) -> Any:
    import numpy as np

    if _is_raw_input(options.input_path, options.input_kind):
        from spektrafilm.utils.raw_file_processor import load_and_process_raw_file

        return load_and_process_raw_file(
            str(options.input_path),
            white_balance=options.white_balance,
            temperature=options.temperature,
            tint=options.tint,
            lens_correction=options.lens_correction,
            output_colorspace=options.input_color_space,
            output_cctf_encoding=options.apply_cctf_decoding,
        )
    return load_image_fn(options.input_path, dtype=np.float32)


def _load_image_default(path: str | Path, *, dtype: Any = None) -> Any:
    import numpy as np
    from PIL import Image

    dtype = np.float32 if dtype is None else dtype
    image = Image.open(path).convert("RGB")
    return np.asarray(image, dtype=dtype) / dtype.type(255)


def _save_image_default(
    path: str | Path,
    image: np.ndarray,
    bit_depth: int | None = None,
    *,
    color_space: str | None = None,
    cctf_encoding: bool = True,
    **kwargs: Any,
) -> object:
    import numpy as np

    del bit_depth, color_space, cctf_encoding, kwargs
    output_path = Path(path)
    ext = output_path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".png", ".tif", ".tiff"}:
        from PIL import Image

        pixels = np.uint8(np.clip(np.asarray(image)[..., :3], 0.0, 1.0) * 255.0)
        Image.fromarray(pixels, mode="RGB").save(output_path)
        return ()

    from spektrafilm.utils.io import save_image_oiio

    return save_image_oiio(str(output_path), image)


def _read_metadata_default(_path: str) -> object | None:
    return None


def _write_metadata_default(*_args: Any, **_kwargs: Any) -> None:
    return None


def _rgb_to_rgb(image: Any, *args: Any, **kwargs: Any) -> Any:
    import colour

    return colour.RGB_to_RGB(image, *args, **kwargs)


def _display_preview_image(
    image: Any,
    *,
    output_color_space: str,
    output_cctf_encoding: bool,
    rgb_to_rgb_fn: Callable[..., np.ndarray],
    is_aces_scene_linear_space_fn: Callable[[str], bool] | None = None,
    aces_sdr_video_view_transform_fn: Callable[..., Any] | None = None,
) -> Any:
    import numpy as np

    source = np.asarray(image)[..., :3]
    normalized = np.clip(source, 0.0, 1.0)
    if output_color_space == "sRGB" and output_cctf_encoding:
        return normalized

    if is_aces_scene_linear_space_fn is None:
        from spektrafilm.color_management import is_aces_scene_linear_space

        is_aces_scene_linear_space_fn = is_aces_scene_linear_space

    if is_aces_scene_linear_space_fn(output_color_space):
        if aces_sdr_video_view_transform_fn is None:
            from spektrafilm.color_management import aces_sdr_video_view_transform

            aces_sdr_video_view_transform_fn = aces_sdr_video_view_transform

        class ColourAdapter:
            RGB_to_RGB = staticmethod(rgb_to_rgb_fn)

        return aces_sdr_video_view_transform_fn(
            np.clip(source, 0.0, None),
            color_space=output_color_space,
            colour_module=ColourAdapter,
        )
    try:
        transform_source = normalized if output_cctf_encoding else np.clip(source, 0.0, None)
        converted = rgb_to_rgb_fn(
            transform_source,
            output_color_space,
            "sRGB",
            apply_cctf_decoding=output_cctf_encoding,
            apply_cctf_encoding=True,
        )
    except (AttributeError, LookupError, RuntimeError, TypeError, ValueError):
        return normalized
    return np.clip(np.asarray(converted)[..., :3], 0.0, 1.0)


def _saving_image(
    image: Any,
    *,
    output_color_space: str,
    output_cctf_encoding: bool,
    saving_color_space: str,
    saving_cctf_encoding: bool,
    rgb_to_rgb_fn: Callable[..., np.ndarray],
) -> Any:
    import numpy as np

    if output_color_space == saving_color_space and output_cctf_encoding == saving_cctf_encoding:
        return np.asarray(image)[..., :3]
    return np.asarray(
        rgb_to_rgb_fn(
            np.asarray(image)[..., :3],
            output_color_space,
            saving_color_space,
            apply_cctf_decoding=output_cctf_encoding,
            apply_cctf_encoding=saving_cctf_encoding,
        )
    )


def render(
    options: BridgeRenderOptions,
    *,
    load_image_fn: Callable[..., Any] = _load_image_default,
    simulator_cls: type[Any] | None = None,
    digest_params_fn: Callable[[Any], Any] | None = None,
    build_params_fn: Callable[[Any], Any] | None = None,
    save_image_fn: Callable[..., object] = _save_image_default,
    resize_for_preview_fn: Callable[[Any, int], Any] | None = None,
    rgb_to_rgb_fn: Callable[..., Any] = _rgb_to_rgb,
    is_aces_scene_linear_space_fn: Callable[[str], bool] | None = None,
    aces_sdr_video_view_transform_fn: Callable[..., Any] | None = None,
    read_metadata_fn: Callable[[str], object | None] = _read_metadata_default,
    write_metadata_fn: Callable[..., None] = _write_metadata_default,
) -> dict[str, object]:
    import numpy as np

    if simulator_cls is None:
        from spektrafilm.runtime.api import Simulator

        simulator_type = Simulator
    else:
        simulator_type = simulator_cls

    if digest_params_fn is None:
        if simulator_cls is None:
            from spektrafilm.runtime.api import digest_params

            params_digester = digest_params
        else:
            params_digester = lambda params: params
    else:
        params_digester = digest_params_fn

    if build_params_fn is None:
        from spektrafilm_gui.params_mapper import build_params_from_state

        params_builder = build_params_from_state
    else:
        params_builder = build_params_fn

    if resize_for_preview_fn is None:
        from spektrafilm.utils.preview import resize_for_preview

        preview_resizer = resize_for_preview
    else:
        preview_resizer = resize_for_preview_fn

    if options.mode not in {"preview", "scan"}:
        raise ValueError(f"Unsupported render mode: {options.mode!r}")
    if options.input_kind not in {"auto", "image", "raw"}:
        raise ValueError(f"Unsupported input kind: {options.input_kind!r}")
    if options.preview_max_size <= 0:
        raise ValueError("preview_max_size must be greater than zero")

    state = build_state_from_options(options)
    source_image = _load_input_image(options, load_image_fn=load_image_fn)
    simulation_image = (
        preview_resizer(source_image, options.preview_max_size)
        if options.mode == "preview"
        else source_image
    )

    params = params_builder(state)
    params.settings.preview_mode = options.mode == "preview"
    digested_params = params_digester(params)
    start = perf_counter()
    simulator = simulator_type(digested_params)
    output_image = np.asarray(simulator.process(np.asarray(simulation_image, dtype=np.float64)))
    fallback_elapsed = perf_counter() - start
    elapsed = getattr(simulator, "get_total_elapsed_time", lambda: fallback_elapsed)()
    timings = getattr(simulator, "get_timings", lambda: {})()

    preview_image = _display_preview_image(
        output_image,
        output_color_space=options.output_color_space,
        output_cctf_encoding=options.output_cctf_encoding,
        rgb_to_rgb_fn=rgb_to_rgb_fn,
        is_aces_scene_linear_space_fn=is_aces_scene_linear_space_fn,
        aces_sdr_video_view_transform_fn=aces_sdr_video_view_transform_fn,
    )
    options.preview_output_path.parent.mkdir(parents=True, exist_ok=True)
    save_image_fn(
        str(options.preview_output_path),
        preview_image,
        bit_depth=8,
        color_space="sRGB",
        cctf_encoding=True,
    )

    metadata_warning = None
    if options.output_path is not None:
        output_to_save = _saving_image(
            output_image,
            output_color_space=options.output_color_space,
            output_cctf_encoding=options.output_cctf_encoding,
            saving_color_space=options.saving_color_space,
            saving_cctf_encoding=options.saving_cctf_encoding,
            rgb_to_rgb_fn=rgb_to_rgb_fn,
        )
        options.output_path.parent.mkdir(parents=True, exist_ok=True)
        save_image_fn(
            str(options.output_path),
            output_to_save,
            color_space=options.saving_color_space,
            cctf_encoding=options.saving_cctf_encoding,
        )
        try:
            write_metadata_fn(
                str(options.output_path),
                read_metadata_fn(str(options.input_path)),
                saving_color_space=options.saving_color_space,
                saving_cctf_encoding=options.saving_cctf_encoding,
            )
        except Exception as exc:
            metadata_warning = f"{type(exc).__name__}: {exc}"

    return {
        "ok": True,
        "mode": options.mode,
        "preview_path": str(options.preview_output_path),
        "output_path": None if options.output_path is None else str(options.output_path),
        "width": int(output_image.shape[1]),
        "height": int(output_image.shape[0]),
        "elapsed_seconds": float(elapsed if elapsed is not None else fallback_elapsed),
        "display_status": "Preview written as sRGB PNG",
        "metadata_warning": metadata_warning,
        "timings": {str(key): float(value) for key, value in dict(timings).items()},
    }


def _json_default(value: object) -> object:
    import numpy as np

    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.generic):
        return value.item()
    if dataclass_is_instance(value):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def dataclass_is_instance(value: object) -> bool:
    return hasattr(value, "__dataclass_fields__") and not isinstance(value, type)


def _parse_render_args(args: list[str]) -> dict[str, object]:
    values: dict[str, object] = {
        "output": None,
        "mode": "preview",
        "input_kind": "auto",
        "film_stock": DEFAULT_FILM_STOCK,
        "print_paper": DEFAULT_PRINT_PAPER,
        "input_color_space": "sRGB",
        "apply_cctf_decoding": False,
        "output_color_space": "sRGB",
        "output_cctf_encoding": True,
        "saving_color_space": "sRGB",
        "saving_cctf_encoding": True,
        "preview_max_size": 640,
        "compute_backend": "cpu",
        "gpu_precision": "float32",
        "scan_film": False,
        "auto_exposure": True,
        "exposure_compensation_ev": 0.0,
        "print_exposure": 1.0,
        "print_y_filter_shift": 0.0,
        "print_m_filter_shift": 0.0,
        "grain_active": True,
        "halation_active": True,
        "couplers_active": True,
        "white_balance": "as_shot",
        "temperature": 5500.0,
        "tint": 1.0,
        "lens_correction": False,
    }
    string_flags = {
        "input",
        "preview-output",
        "output",
        "mode",
        "input-kind",
        "film-stock",
        "print-paper",
        "input-color-space",
        "output-color-space",
        "saving-color-space",
        "compute-backend",
        "gpu-precision",
        "white-balance",
    }
    int_flags = {"preview-max-size"}
    float_flags = {
        "exposure-compensation-ev",
        "print-exposure",
        "print-y-filter-shift",
        "print-m-filter-shift",
        "temperature",
        "tint",
    }
    bool_flags = {
        "apply-cctf-decoding",
        "output-cctf-encoding",
        "saving-cctf-encoding",
        "scan-film",
        "auto-exposure",
        "grain-active",
        "halation-active",
        "couplers-active",
        "lens-correction",
    }

    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            raise CLIUsageError(f"Unexpected positional argument: {token}")

        raw_name = token[2:]
        if raw_name.startswith("no-") and raw_name[3:] in bool_flags:
            values[raw_name[3:].replace("-", "_")] = False
            i += 1
            continue
        if raw_name in bool_flags:
            values[raw_name.replace("-", "_")] = True
            i += 1
            continue
        if raw_name not in string_flags | int_flags | float_flags:
            raise CLIUsageError(f"Unknown option: {token}")
        if i + 1 >= len(args):
            raise CLIUsageError(f"Missing value for {token}")

        raw_value = args[i + 1]
        key = raw_name.replace("-", "_")
        try:
            if raw_name in int_flags:
                values[key] = int(raw_value)
            elif raw_name in float_flags:
                values[key] = float(raw_value)
            else:
                values[key] = raw_value
        except ValueError as exc:
            raise CLIUsageError(f"Invalid value for {token}: {raw_value}") from exc
        i += 2

    for required in ("input", "preview_output"):
        if required not in values:
            raise CLIUsageError(f"Missing required option: --{required.replace('_', '-')}")
    return values


def _options_from_mapping(values: dict[str, object]) -> BridgeRenderOptions:
    return BridgeRenderOptions(
        input_path=Path(str(values["input"])),
        preview_output_path=Path(str(values["preview_output"])),
        output_path=None if values["output"] is None else Path(str(values["output"])),
        mode=str(values["mode"]),
        input_kind=str(values["input_kind"]),
        film_stock=str(values["film_stock"]),
        print_paper=str(values["print_paper"]),
        input_color_space=str(values["input_color_space"]),
        apply_cctf_decoding=bool(values["apply_cctf_decoding"]),
        output_color_space=str(values["output_color_space"]),
        output_cctf_encoding=bool(values["output_cctf_encoding"]),
        saving_color_space=str(values["saving_color_space"]),
        saving_cctf_encoding=bool(values["saving_cctf_encoding"]),
        preview_max_size=int(values["preview_max_size"]),
        compute_backend=str(values["compute_backend"]),
        gpu_precision=str(values["gpu_precision"]),
        scan_film=bool(values["scan_film"]),
        auto_exposure=bool(values["auto_exposure"]),
        exposure_compensation_ev=float(values["exposure_compensation_ev"]),
        print_exposure=float(values["print_exposure"]),
        print_y_filter_shift=float(values["print_y_filter_shift"]),
        print_m_filter_shift=float(values["print_m_filter_shift"]),
        grain_active=bool(values["grain_active"]),
        halation_active=bool(values["halation_active"]),
        couplers_active=bool(values["couplers_active"]),
        white_balance=str(values["white_balance"]),
        temperature=float(values["temperature"]),
        tint=float(values["tint"]),
        lens_correction=bool(values["lens_correction"]),
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        raise CLIUsageError("Expected command: describe or render")
    command = args[0]
    if command == "describe":
        if len(args) != 1:
            raise CLIUsageError("describe does not accept options")
        payload = describe_catalog()
    elif command == "render":
        payload = render(_options_from_mapping(_parse_render_args(args[1:])))
    else:
        raise CLIUsageError(f"Unknown command: {command}")
    print(json.dumps(payload, default=_json_default, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}), file=sys.stderr)
        raise SystemExit(1)
