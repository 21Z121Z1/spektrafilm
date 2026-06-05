from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.hdr import HDRProjectionConfig
from spektrafilm.hdr.routemaster_export import (
    export_hdr_heic_from_simulator,
    normalize_hdr_mode,
    render_hdr_pair_from_master,
)
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils import hdr_photo


def _pair() -> tuple[np.ndarray, np.ndarray]:
    sdr = np.array([[[0.5, 0.4, 0.3], [0.9, 0.8, 0.7]]], dtype=np.float32)
    hdr = np.array([[[0.5, 0.4, 0.3], [1.8, 1.6, 1.4]]], dtype=np.float32)
    return sdr, hdr


def _master() -> RouteMaster:
    sdr, hdr_seed = _pair()
    y = np.max(sdr, axis=2)
    scene = np.array([[0.5, 4.0]], dtype=np.float32)
    return RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=hdr_seed,
        route_linear_xyz=hdr_seed,
        route_luminance_y=y,
        sdr_legacy_rgb=sdr,
        scene_y_raw=scene,
        post_halation_y=scene,
        density_cmy=sdr,
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={},
    )


def test_save_hdr_photo_heic_from_pair_does_not_call_simulator(monkeypatch, tmp_path) -> None:
    sdr, hdr = _pair()
    output_path = tmp_path / "pair.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))

    def forbidden_prepare(*_args, **_kwargs):
        raise AssertionError("pair encoder must not prepare HDR renditions")

    def fake_run(command, *, check, capture_output, text, timeout):
        captured["command"] = command
        captured["sdr_payload"] = np.fromfile(command[2], dtype=np.float32).reshape(1, 2, 4)
        captured["hdr_payload"] = np.fromfile(command[3], dtype=np.float32).reshape(1, 2, 4)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo, "prepare_hdr_photo_renditions", forbidden_prepare)
    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    diagnostics = hdr_photo.save_hdr_photo_heic_from_pair(
        output_path,
        sdr,
        hdr,
        color_space="Display P3",
        quality=0.8,
    )

    assert diagnostics == ()
    assert captured["command"][-1] == "rgb"
    np.testing.assert_allclose(captured["sdr_payload"][..., :3], sdr)
    np.testing.assert_allclose(captured["hdr_payload"][..., :3], hdr)


def test_export_route_master_single_full_res_render(monkeypatch, tmp_path) -> None:
    calls: list[str] = []
    output_path = tmp_path / "out.heic"

    class FakeSimulator:
        def process_master(self, image, *, hdr_mode):
            calls.append(f"{hdr_mode}:{image}")
            return _master()

    def fake_save(filename, sdr_rgb, hdr_rgb, **kwargs):
        assert filename == output_path
        assert sdr_rgb.shape == hdr_rgb.shape
        assert kwargs["color_space"] == "Display P3"
        return ("pair_saved",)

    monkeypatch.setattr(hdr_photo, "save_hdr_photo_heic_from_pair", fake_save)

    diagnostics = export_hdr_heic_from_simulator(
        FakeSimulator(),
        "frame",
        output_path,
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=2.0),
        color_space="Display P3",
    )

    assert calls == ["paper:frame"]
    assert diagnostics == ("pair_saved",)


def test_no_duplicate_scan_when_exporting_hdr(monkeypatch, tmp_path) -> None:
    class FakeSimulator:
        def __init__(self) -> None:
            self.count = 0

        def process_master(self, image, *, hdr_mode):
            del image, hdr_mode
            self.count += 1
            return _master()

    fake = FakeSimulator()
    monkeypatch.setattr(hdr_photo, "save_hdr_photo_heic_from_pair", lambda *args, **kwargs: ())

    export_hdr_heic_from_simulator(
        fake,
        np.zeros((1, 2, 3), dtype=np.float32),
        tmp_path / "out.heic",
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=2.0),
        color_space="Display P3",
    )

    assert fake.count == 1


def test_heic_encoder_accepts_pre_rendered_pair(monkeypatch, tmp_path) -> None:
    sdr, hdr = _pair()
    output_path = tmp_path / "pair.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))

    def fake_run(command, *, check, capture_output, text, timeout):
        captured["headroom"] = float(command[8])
        captured["quality"] = float(command[9])
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    hdr_photo.save_hdr_photo_heic_from_pair(
        output_path,
        sdr,
        hdr,
        color_space="Display P3",
        headroom=2.0,
        quality=0.72,
        gain_map_mode="luma",
    )

    assert captured["headroom"] == pytest.approx(2.0)
    assert captured["quality"] == pytest.approx(0.72)


def test_gain_map_metadata_valid() -> None:
    result = render_hdr_pair_from_master(
        _master(),
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=2.0, headroom_percentile=100.0),
    )

    assert result.gain_map_metadata is not None
    assert hdr_photo.validate_gain_map(result.gain_map, result.gain_map_metadata) == []


def test_legacy_profile_aware_alias_warns_or_maps_to_paper() -> None:
    with pytest.warns(DeprecationWarning, match="profile_aware"):
        assert normalize_hdr_mode("profile_aware") == "paper"


def test_legacy_film_scan_aware_alias_warns_or_maps_to_light_table() -> None:
    with pytest.warns(DeprecationWarning, match="film_scan_aware"):
        assert normalize_hdr_mode("film_scan_aware") == "light_table"
