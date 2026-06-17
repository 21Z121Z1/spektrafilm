from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.hdr import HDRProjectionConfig
from spektrafilm.hdr.routemaster_export import (
    export_hdr_heic_from_simulator,
    normalize_hdr_mode,
    render_hdr_film_pair_from_master,
    render_hdr_pair_from_master,
)
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils import hdr_photo
from spektrafilm.utils.heif_iso21496 import validate_heif_iso21496


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


def _paper_onset_master() -> RouteMaster:
    scene = np.array([[0.5, 1.0, 2.0, 4.0]], dtype=np.float32)
    sdr = np.full((1, 4, 3), 0.4, dtype=np.float32)
    route = np.ones((1, 4, 3), dtype=np.float32)
    return RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route,
        route_linear_xyz=route,
        route_luminance_y=scene,
        sdr_legacy_rgb=sdr,
        scene_y_raw=scene,
        post_halation_y=scene,
        density_cmy=sdr,
        route_look_chroma=np.ones_like(route, dtype=np.float32),
        material_detail_y=None,
        diagnostics={"output_cctf_encoding": False},
    )


def test_save_hdr_photo_heic_from_pair_does_not_call_simulator(monkeypatch, tmp_path) -> None:
    sdr, hdr = _pair()
    output_path = tmp_path / "pair.heic"
    captured: dict[str, object] = {}

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))
    monkeypatch.setattr(hdr_photo, "validate_heif_iso21496", lambda path: SimpleNamespace(ok=True, errors=()))

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


def test_save_hdr_photo_heic_from_pair_rejects_metadata_until_encoder_supports_it(tmp_path) -> None:
    sdr, hdr = _pair()

    with pytest.raises(hdr_photo.HDRPhotoExportError, match="metadata embedding is not supported"):
        hdr_photo.save_hdr_photo_heic_from_pair(
            tmp_path / "pair.heic",
            sdr,
            hdr,
            color_space="Display P3",
            metadata={"hdr_mode": "paper"},
        )


def test_save_hdr_photo_heic_from_pair_fails_closed_on_iso_validation_error(monkeypatch, tmp_path) -> None:
    sdr, hdr = _pair()
    output_path = tmp_path / "pair.heic"

    monkeypatch.setattr(hdr_photo.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(hdr_photo, "_swift_command", lambda: ["swift"])
    monkeypatch.setattr(hdr_photo, "_encoder_script_path", lambda: Path("/tmp/hdr_heif_encoder.swift"))
    monkeypatch.setattr(
        hdr_photo,
        "validate_heif_iso21496",
        lambda path: SimpleNamespace(ok=False, errors=("missing tmap",)),
    )

    def fake_run(command, *, check, capture_output, text, timeout):
        Path(command[4]).write_bytes(b"partial-heic")
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(hdr_photo.subprocess, "run", fake_run)

    with pytest.raises(hdr_photo.HDRPhotoExportError, match="ISO 21496-1 validation"):
        hdr_photo.save_hdr_photo_heic_from_pair(
            output_path,
            sdr,
            hdr,
            color_space="Display P3",
            headroom=2.0,
        )

    assert not output_path.exists()


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
        assert "metadata" not in kwargs
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


def test_render_hdr_film_pair_alias_matches_route_master_pair() -> None:
    master = _master()
    config = HDRProjectionConfig(max_headroom=2.0, headroom_percentile=100.0)

    legacy = render_hdr_pair_from_master(master, hdr_mode="paper", config=config)
    film_pair = render_hdr_film_pair_from_master(master, hdr_mode="paper", config=config)

    np.testing.assert_allclose(film_pair.sdr_rgb, legacy.sdr_rgb)
    np.testing.assert_allclose(film_pair.hdr_rgb, legacy.hdr_rgb)
    assert film_pair.mode == legacy.mode


def test_reference_white_default_is_compatible_with_existing_default() -> None:
    master = _paper_onset_master()

    baseline = render_hdr_pair_from_master(
        master,
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0),
    )
    explicit = render_hdr_pair_from_master(
        master,
        hdr_mode="paper",
        config=HDRProjectionConfig(
            max_headroom=4.0,
            headroom_percentile=100.0,
            diffuse_white_scene_anchor=1.0,
            reference_white_ev=0.0,
            output_diffuse_white=1.0,
        ),
    )

    np.testing.assert_allclose(explicit.sdr_rgb, baseline.sdr_rgb)
    np.testing.assert_allclose(explicit.hdr_rgb, baseline.hdr_rgb)
    np.testing.assert_allclose(explicit.gain_map, baseline.gain_map)
    assert explicit.headroom == pytest.approx(baseline.headroom)


def test_reference_white_ev_moves_paper_hdr_onset_without_changing_sdr() -> None:
    master = _paper_onset_master()
    config_a = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0)
    config_b = HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0, reference_white_ev=1.0)

    result_a = render_hdr_pair_from_master(master, hdr_mode="paper", config=config_a)
    result_b = render_hdr_pair_from_master(master, hdr_mode="paper", config=config_b)

    np.testing.assert_allclose(result_b.sdr_rgb, result_a.sdr_rgb)
    np.testing.assert_allclose(result_b.hdr_rgb[0, 2], result_b.sdr_rgb[0, 2], atol=1e-6)
    assert np.max(result_b.hdr_rgb[0, 3] - result_b.sdr_rgb[0, 3]) > 0.01
    assert np.max(result_a.hdr_rgb[0, 2] - result_a.sdr_rgb[0, 2]) > 0.01
    assert np.allclose(result_a.hdr_rgb[0, 1], result_a.sdr_rgb[0, 1], atol=1e-6)


def test_output_diffuse_white_scales_hdr_delta_without_changing_sdr_base() -> None:
    master = _paper_onset_master()
    baseline = render_hdr_pair_from_master(
        master,
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0),
    )
    scaled = render_hdr_pair_from_master(
        master,
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0, output_diffuse_white=0.5),
    )

    np.testing.assert_allclose(scaled.sdr_rgb, baseline.sdr_rgb)
    assert not np.allclose(scaled.hdr_rgb[0, 3], baseline.hdr_rgb[0, 3])
    np.testing.assert_allclose(scaled.hdr_rgb[0, :2], scaled.sdr_rgb[0, :2], atol=1e-6)


def test_reference_white_diagnostics_are_reported() -> None:
    result = render_hdr_pair_from_master(
        _paper_onset_master(),
        hdr_mode="paper",
        config=HDRProjectionConfig(
            max_headroom=4.0,
            headroom_percentile=100.0,
            reference_white_ev=0.5,
            output_diffuse_white=1.25,
            display_reference_white_nits=203.0,
        ),
    )

    diagnostics = result.diagnostics["reference_white"]
    assert diagnostics["mode"] == "manual_scene_anchor"
    assert diagnostics["scene_diffuse_white_y"] == pytest.approx(2.0 ** 0.5)
    assert diagnostics["reference_white_ev"] == pytest.approx(0.5)
    assert diagnostics["output_diffuse_white"] == pytest.approx(1.25)
    assert diagnostics["display_reference_white_nits"] == pytest.approx(203.0)


def test_hdr_pair_debug_env_writes_pre_encoder_pair_diagnostics(monkeypatch, tmp_path) -> None:
    debug_path = tmp_path / "pair_debug.npz"
    monkeypatch.setenv("SPEKTRAFILM_HDR_PAIR_DEBUG", "1")
    monkeypatch.setenv("SPEKTRAFILM_HDR_PAIR_DEBUG_PATH", str(debug_path))

    result = render_hdr_pair_from_master(
        _paper_onset_master(),
        hdr_mode="paper",
        config=HDRProjectionConfig(max_headroom=4.0, headroom_percentile=100.0),
    )

    assert result.diagnostics["hdr_pair_debug_path"] == str(debug_path)
    assert result.diagnostics["hdr_pair_bad_pixels"] == 0
    assert result.diagnostics["hdr_pair_bad_fraction"] == 0.0
    assert result.diagnostics["hdr_pair_log_gain_min"] >= -1e-6
    payload = np.load(debug_path)
    assert set(payload.files) >= {"sdr", "hdr", "sdr_y", "hdr_y", "scene_y", "log_gain", "bad"}
    np.testing.assert_allclose(payload["sdr"], result.sdr_rgb)
    np.testing.assert_allclose(payload["hdr"], result.hdr_rgb)
    assert payload["bad"].dtype == np.uint8


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"reference_white_ev": float("nan")}, "reference_white_ev"),
        ({"display_reference_white_nits": 0.0}, "display_reference_white_nits"),
        ({"reference_white_mode": "auto"}, "reference_white_mode"),
    ],
)
def test_reference_white_config_validation_fails_fast(kwargs, message) -> None:
    with pytest.raises(ValueError, match=message):
        HDRProjectionConfig(**kwargs)


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
    monkeypatch.setattr(hdr_photo, "validate_heif_iso21496", lambda path: SimpleNamespace(ok=True, errors=()))

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


def test_coreimage_pair_export_writes_iso_tmap_and_is_mac_openable(tmp_path) -> None:
    if platform.system() != "Darwin":
        pytest.skip("CoreImage HEIC smoke requires macOS.")
    if shutil.which("swift") is None and shutil.which("xcrun") is None:
        pytest.skip("Swift toolchain is required for CoreImage HEIC smoke.")
    if shutil.which("sips") is None:
        pytest.skip("sips is required for Mac-openability smoke.")

    x = np.linspace(0.05, 1.0, 8, dtype=np.float32)
    y = np.linspace(0.0, 1.0, 8, dtype=np.float32)[:, None]
    sdr = np.stack(
        [
            np.broadcast_to(x, (8, 8)),
            np.broadcast_to(0.25 + 0.55 * y, (8, 8)),
            np.full((8, 8), 0.35, dtype=np.float32),
        ],
        axis=2,
    ).astype(np.float32)
    hdr = sdr.copy()
    hdr[..., 0] = np.clip(hdr[..., 0] * 2.0, 0.0, 2.0)
    hdr[..., 1] = np.clip(hdr[..., 1] * 1.55, 0.0, 2.0)

    output_path = tmp_path / "coreimage-route-pair.heic"
    hdr_photo.save_hdr_photo_heic_from_pair(
        output_path,
        sdr,
        hdr,
        color_space="Display P3",
        headroom=2.0,
        quality=0.82,
    )

    iso_result = validate_heif_iso21496(output_path)
    assert iso_result.ok, iso_result.errors
    assert iso_result.tmap_item_id is not None
    assert iso_result.base_item_id is not None
    assert iso_result.gain_map_item_id is not None
    assert iso_result.metadata is not None
    assert iso_result.metadata.alternate_hdr_headroom > iso_result.metadata.base_hdr_headroom

    sips = subprocess.run(
        ["sips", "-g", "pixelWidth", "-g", "pixelHeight", "-g", "format", str(output_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert sips.returncode == 0, sips.stderr
    assert "format: heic" in sips.stdout.lower()
    assert "pixelWidth: 8" in sips.stdout
    assert "pixelHeight: 8" in sips.stdout

    swift_check = tmp_path / "imageio_check.swift"
    swift_check.write_text(
        """
import Foundation
import ImageIO

let url = URL(fileURLWithPath: CommandLine.arguments[1])
guard let source = CGImageSourceCreateWithURL(url as CFURL, nil) else {
    fputs("CGImageSourceCreateWithURL failed\\n", stderr)
    exit(2)
}
let count = CGImageSourceGetCount(source)
guard count > 0 else {
    fputs("CGImageSourceGetCount returned zero\\n", stderr)
    exit(3)
}
guard let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fputs("CGImageSourceCreateImageAtIndex failed\\n", stderr)
    exit(4)
}
print("count=\\(count) width=\\(image.width) height=\\(image.height)")
""".lstrip(),
        encoding="utf-8",
    )
    swift_cmd = hdr_photo._swift_command()
    imageio = subprocess.run(
        [*swift_cmd, str(swift_check), str(output_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert imageio.returncode == 0, imageio.stderr
    assert "width=8 height=8" in imageio.stdout


def test_legacy_profile_aware_alias_warns_or_maps_to_paper() -> None:
    with pytest.warns(DeprecationWarning, match="profile_aware"):
        assert normalize_hdr_mode("profile_aware") == "paper"


def test_legacy_film_scan_aware_alias_warns_or_maps_to_light_table() -> None:
    with pytest.warns(DeprecationWarning, match="film_scan_aware"):
        assert normalize_hdr_mode("film_scan_aware") == "light_table"


def test_ideal_paper_sdr_linear_scale() -> None:
    from spektrafilm.hdr.ideal_paper import project_hdr_ideal_paper

    sdr_color = np.array([[[0.6, 0.5, 0.4]]], dtype=np.float32)
    route_color = np.array([[[0.3, 0.5, 0.7]]], dtype=np.float32)
    scene = np.array([[0.5]], dtype=np.float32)

    master = RouteMaster(
        mode="paper",
        route_kind="print_scan",
        route_linear_rgb=route_color,
        route_linear_xyz=route_color,
        route_luminance_y=np.array([[0.5]], dtype=np.float32),
        sdr_legacy_rgb=sdr_color,
        scene_y_raw=scene,
        post_halation_y=scene,
        density_cmy=sdr_color,
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={"output_color_space": "Display P3"},
    )

    result = project_hdr_ideal_paper(master)

    expected_linear = np.array([[[
        ((0.6 + 0.055) / 1.055) ** 2.4,
        ((0.5 + 0.055) / 1.055) ** 2.4,
        ((0.4 + 0.055) / 1.055) ** 2.4,
    ]]], dtype=np.float32)
    np.testing.assert_allclose(result.sdr_rgb, expected_linear, rtol=1e-3)
    np.testing.assert_allclose(result.hdr_rgb, result.sdr_rgb, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(result.gain_map, 0.0, atol=1e-4)
