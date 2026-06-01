from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from spektrafilm_gui import macos_bridge


def test_describe_catalog_exposes_defaults_and_options() -> None:
    catalog = macos_bridge.describe_catalog()

    assert catalog["defaults"]["film_stock"] == "kodak_gold_200"
    assert catalog["defaults"]["print_paper"] == "kodak_supra_endura"
    assert "kodak_portra_400" in catalog["film_profiles"]
    assert "kodak_portra_endura" in catalog["print_profiles"]
    assert "Display P3" in catalog["color_spaces"]
    assert "auto" in catalog["compute_backends"]
    assert "float32" in catalog["gpu_precisions"]


def test_build_state_from_options_maps_core_fields() -> None:
    options = macos_bridge.BridgeRenderOptions(
        input_path=Path("input.tif"),
        preview_output_path=Path("preview.png"),
        output_path=Path("output.tif"),
        mode="scan",
        input_kind="image",
        film_stock="kodak_portra_400",
        print_paper="kodak_portra_endura",
        input_color_space="Display P3",
        apply_cctf_decoding=True,
        output_color_space="Adobe RGB (1998)",
        saving_color_space="ProPhoto RGB",
        saving_cctf_encoding=False,
        preview_max_size=512,
        compute_backend="cpu",
        gpu_precision="float64",
        scan_film=True,
        auto_exposure=False,
        exposure_compensation_ev=0.5,
        print_exposure=1.25,
        print_y_filter_shift=-2.0,
        print_m_filter_shift=3.0,
        grain_active=False,
        halation_active=False,
        couplers_active=False,
        white_balance="custom",
        temperature=5100.0,
        tint=1.2,
        lens_correction=True,
    )

    state = macos_bridge.build_state_from_options(options)

    assert state.simulation.film_stock == "kodak_portra_400"
    assert state.simulation.print_paper == "kodak_portra_endura"
    assert state.input_image.input_color_space == "Display P3"
    assert state.input_image.apply_cctf_decoding is True
    assert state.simulation.output_color_space == "Adobe RGB (1998)"
    assert state.simulation.output_cctf_encoding is True
    assert state.simulation.saving_color_space == "ProPhoto RGB"
    assert state.simulation.saving_cctf_encoding is False
    assert state.display.preview_max_size == 512
    assert state.simulation.compute_backend == "cpu"
    assert state.simulation.gpu_precision == "float64"
    assert state.simulation.scan_film is True
    assert state.simulation.auto_exposure is False
    assert state.simulation.exposure_compensation_ev == 0.5
    assert state.simulation.print_exposure == 1.25
    assert state.simulation.print_y_filter_shift == -2.0
    assert state.simulation.print_m_filter_shift == 3.0
    assert state.grain.active is False
    assert state.halation.active is False
    assert state.couplers.active is False
    assert state.load_raw.white_balance == "custom"
    assert state.load_raw.temperature == 5100.0
    assert state.load_raw.tint == 1.2
    assert state.load_raw.lens_correction is True


def test_display_preview_preserves_aces_scene_highlights() -> None:
    captured: dict[str, object] = {}

    def fake_aces_transform(image, *, color_space, colour_module):
        captured["image"] = np.asarray(image).copy()
        captured["color_space"] = color_space
        captured["colour_module"] = colour_module
        return np.full_like(image, 0.5)

    preview = macos_bridge._display_preview_image(
        np.array([[[-0.2, 1.4, 2.5]]], dtype=np.float32),
        output_color_space="ACEScg",
        output_cctf_encoding=False,
        rgb_to_rgb_fn=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("RGB_to_RGB should be wrapped")),
        is_aces_scene_linear_space_fn=lambda color_space: color_space == "ACEScg",
        aces_sdr_video_view_transform_fn=fake_aces_transform,
    )

    np.testing.assert_allclose(captured["image"], [[[0.0, 1.4, 2.5]]])
    assert captured["color_space"] == "ACEScg"
    np.testing.assert_allclose(preview, [[[0.5, 0.5, 0.5]]])


def test_render_preview_uses_preview_mode_and_injected_runtime() -> None:
    calls: dict[str, object] = {}
    input_image = np.full((8, 12, 3), 0.25, dtype=np.float32)
    simulated_image = np.full((4, 6, 3), 0.5, dtype=np.float64)
    preview_output = Path(os.environ.get("TMPDIR", "/tmp")) / (
        f"spektrafilm_macos_bridge_preview_{os.getpid()}.png"
    )
    preview_output.unlink(missing_ok=True)

    class FakeSimulator:
        def __init__(self, params) -> None:
            calls["simulator_params"] = params

        def process(self, image) -> np.ndarray:
            calls["process_image"] = np.asarray(image)
            return simulated_image

        def get_total_elapsed_time(self) -> float:
            return 0.125

        def get_timings(self) -> dict[str, float]:
            return {"stage": 0.1}

    def fake_load_image(path, *, dtype=np.float32):
        calls["load_image"] = (Path(path), dtype)
        return input_image

    def fake_save_image(path, image, **kwargs):
        calls.setdefault("save_calls", []).append((Path(path), np.asarray(image), kwargs))
        Path(path).write_bytes(b"png")
        return ()

    options = macos_bridge.BridgeRenderOptions(
        input_path=Path("input.tif"),
        preview_output_path=preview_output,
        output_path=None,
        mode="preview",
        input_kind="image",
        film_stock="kodak_gold_200",
        print_paper="kodak_supra_endura",
        input_color_space="sRGB",
        apply_cctf_decoding=False,
        output_color_space="sRGB",
        saving_color_space="sRGB",
        saving_cctf_encoding=True,
        preview_max_size=4,
        compute_backend="cpu",
        gpu_precision="float32",
        scan_film=False,
        auto_exposure=True,
        exposure_compensation_ev=0.0,
        print_exposure=1.0,
        print_y_filter_shift=0.0,
        print_m_filter_shift=0.0,
        grain_active=True,
        halation_active=True,
        couplers_active=True,
        white_balance="as_shot",
        temperature=5500.0,
        tint=1.0,
        lens_correction=False,
    )

    result = macos_bridge.render(
        options,
        load_image_fn=fake_load_image,
        simulator_cls=FakeSimulator,
        build_params_fn=lambda _state: SimpleNamespace(settings=SimpleNamespace(preview_mode=False)),
        save_image_fn=fake_save_image,
        resize_for_preview_fn=lambda image, max_size: image[:4, :6, :],
        rgb_to_rgb_fn=lambda image, *_args, **_kwargs: image,
        read_metadata_fn=lambda _path: SimpleNamespace(metadata=True),
        write_metadata_fn=lambda *_args, **_kwargs: None,
    )

    assert calls["load_image"] == (Path("input.tif"), np.float32)
    assert calls["process_image"].shape == (4, 6, 3)
    assert calls["simulator_params"].settings.preview_mode is True
    assert result["mode"] == "preview"
    assert result["preview_path"] == str(preview_output)
    assert result["output_path"] is None
    assert result["width"] == 6
    assert result["height"] == 4
    assert result["timings"] == {"stage": 0.1}
    assert preview_output.exists()
    assert len(calls["save_calls"]) == 1
    preview_output.unlink(missing_ok=True)
