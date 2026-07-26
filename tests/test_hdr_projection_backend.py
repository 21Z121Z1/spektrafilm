from __future__ import annotations

import numpy as np
import pytest

from spektrafilm.gpu.backend import BackendUnavailableError, select_backend
from spektrafilm.gpu.residency import record_backend_residency
from spektrafilm.hdr import HDRProjectionConfig, project_hdr_ideal_paper, project_hdr_light_table
from spektrafilm.hdr.routemaster_export import export_hdr_heic_from_simulator
from spektrafilm.runtime.route_master import RouteMaster
from spektrafilm.utils import hdr_photo


pytestmark = pytest.mark.integration


def _mlx_available_or_skip():
    try:
        return select_backend("mlx", precision="float32")
    except BackendUnavailableError as exc:
        pytest.skip(str(exc))


def _arrays() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    route_y = np.array([[0.25, 0.75, 1.0, 1.2]], dtype=np.float32)
    route_chroma = np.array([1.0, 0.55, 0.25], dtype=np.float32)
    route_rgb = route_y[..., None] * route_chroma
    scene_y = np.array([[0.25, 1.0, 2.0, 6.0]], dtype=np.float32)
    return route_rgb, route_y, scene_y


def _master(*, backend=None, mode: str = "light_table", output_cctf_encoding: bool = False) -> RouteMaster:
    route_rgb, route_y, scene_y = _arrays()
    route_kind = "film_scan" if mode == "light_table" else "print_scan"

    def arr(value):
        return value if backend is None else backend.asarray(value)

    return RouteMaster(
        mode=mode,  # type: ignore[arg-type]
        route_kind=route_kind,  # type: ignore[arg-type]
        route_linear_rgb=arr(route_rgb),
        route_luminance_y=arr(route_y),
        sdr_legacy_rgb=arr(np.clip(route_rgb, 0.0, 1.0)),
        scene_y_raw=arr(scene_y),
        post_halation_y=arr(scene_y * np.float32(1.1)),
        route_linear_xyz=None,
        density_cmy=None,
        route_look_chroma=None,
        material_detail_y=None,
        diagnostics={
            "output_cctf_encoding": output_cctf_encoding,
            "output_color_space": "sRGB",
        },
    )


def test_light_table_projection_keeps_mlx_arrays_until_boundary() -> None:
    backend = _mlx_available_or_skip()
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)
    expected = project_hdr_light_table(_master(mode="light_table"), config)

    with record_backend_residency() as recorder:
        actual = project_hdr_light_table(_master(backend=backend, mode="light_table"), config)
        backend.synchronize()

    assert backend._is_mlx_array(actual.sdr_rgb)
    assert backend._is_mlx_array(actual.hdr_rgb)
    assert backend._is_mlx_array(actual.hdr_luminance_y)
    assert backend._is_mlx_array(actual.gain_map)
    assert actual.diagnostics["projection_backend"] == "mlx"
    assert recorder.summary()["to_numpy"] == 0
    np.testing.assert_allclose(np.asarray(actual.sdr_rgb), expected.sdr_rgb, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(np.asarray(actual.hdr_rgb), expected.hdr_rgb, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(np.asarray(actual.gain_map), expected.gain_map, rtol=1e-5, atol=1e-6)


def test_backend_fast_path_records_metadata_statistics_omission() -> None:
    backend = _mlx_available_or_skip()
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)

    result = project_hdr_light_table(_master(backend=backend, mode="light_table"), config)

    assert result.diagnostics["projection_backend"] == "mlx"
    assert result.diagnostics["projection_metadata_statistics"] == "omitted_backend_fast_path"
    assert "full-frame scene/render statistics readback" in result.diagnostics["projection_metadata_statistics_reason"]
    assert result.standards_metadata.scene_statistics == {}


def test_backend_projection_profile_reports_percentile_sort_costs(monkeypatch) -> None:
    backend = _mlx_available_or_skip()
    monkeypatch.setenv("SPEKTRAFILM_HDR_PROJECTION_PROFILE", "1")
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)

    result = project_hdr_light_table(_master(backend=backend, mode="light_table"), config)
    backend.synchronize()

    profile = result.diagnostics["projection_profile"]
    calls = profile["percentile_calls"]
    labels = {call["label"] for call in calls}

    # The extension gain uses a fixed span (no content percentile) since the
    # crop-stability fix, so only the final content-headroom sort remains.
    assert labels == {"headroom"}
    assert all(call["operation"] == "mx.sort_percentile" for call in calls)
    assert all(call["size"] == 4 for call in calls)
    assert all(call["sort_to_scalar_ms"] >= 0.0 for call in calls)
    assert profile["percentile_sort_ms_total"] >= 0.0
    assert "mlx_peak_memory_bytes" in profile
    assert "mlx_cache_memory_end_bytes" in profile


def test_generic_paper_projection_keeps_mlx_arrays_when_no_chemical_profile() -> None:
    backend = _mlx_available_or_skip()
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)
    expected = project_hdr_ideal_paper(_master(mode="paper"), config)

    actual = project_hdr_ideal_paper(_master(backend=backend, mode="paper"), config)

    assert backend._is_mlx_array(actual.sdr_rgb)
    assert backend._is_mlx_array(actual.hdr_rgb)
    assert actual.diagnostics["projection_backend"] == "mlx"
    assert actual.diagnostics["paper_rolloff_strategy"] == "generic_scene_extension"
    np.testing.assert_allclose(np.asarray(actual.hdr_rgb), expected.hdr_rgb, rtol=1e-5, atol=1e-6)


def test_projection_decodes_cctf_encoded_sdr_base_on_backend() -> None:
    backend = _mlx_available_or_skip()
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)
    expected = project_hdr_light_table(
        _master(mode="light_table", output_cctf_encoding=True), config
    )

    result = project_hdr_light_table(
        _master(backend=backend, mode="light_table", output_cctf_encoding=True),
        config,
    )

    assert backend._is_mlx_array(result.sdr_rgb)
    assert backend._is_mlx_array(result.hdr_rgb)
    assert result.diagnostics["projection_backend"] == "mlx"
    np.testing.assert_allclose(np.asarray(result.sdr_rgb), expected.sdr_rgb, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(np.asarray(result.hdr_rgb), expected.hdr_rgb, rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(np.asarray(result.gain_map), expected.gain_map, rtol=1e-5, atol=1e-6)


def test_projection_falls_back_to_numpy_for_host_resident_masters() -> None:
    config = HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0)

    result = project_hdr_light_table(
        _master(mode="light_table", output_cctf_encoding=True),
        config,
    )

    assert isinstance(result.sdr_rgb, np.ndarray)
    assert isinstance(result.hdr_rgb, np.ndarray)
    assert "projection_backend" not in result.diagnostics


def test_paper_projection_with_chemical_profile_stays_on_numpy_path() -> None:
    backend = _mlx_available_or_skip()
    master = _master(backend=backend, mode="paper")
    master.diagnostics.update({
        "film": "kodak_portra_400",
        "paper": "kodak_portra_endura",
    })

    result = project_hdr_ideal_paper(
        master,
        HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0),
    )

    assert isinstance(result.sdr_rgb, np.ndarray)
    assert isinstance(result.hdr_rgb, np.ndarray)
    assert "projection_backend" not in result.diagnostics
    assert result.diagnostics["paper_rolloff_strategy"] == "chemical_print"


def test_export_materializes_backend_projection_pair_at_heic_boundary(monkeypatch, tmp_path) -> None:
    backend = _mlx_available_or_skip()
    captured: dict[str, object] = {}

    def fake_save(filename, sdr_rgb, hdr_rgb, **kwargs):
        captured["filename"] = filename
        captured["sdr_rgb"] = sdr_rgb
        captured["hdr_rgb"] = hdr_rgb
        captured["kwargs"] = kwargs
        return ("saved",)

    monkeypatch.setattr(hdr_photo, "save_hdr_photo_heic_from_pair", fake_save)
    output_path = tmp_path / "out.heic"

    diagnostics = export_hdr_heic_from_simulator(
        simulator=None,
        image=None,
        filename=output_path,
        hdr_mode="light_table",
        config=HDRProjectionConfig(max_headroom=5.0, headroom_percentile=100.0),
        color_space="sRGB",
        master=_master(backend=backend, mode="light_table"),
    )

    assert diagnostics == ("saved",)
    assert captured["filename"] == output_path
    assert isinstance(captured["sdr_rgb"], np.ndarray)
    assert isinstance(captured["hdr_rgb"], np.ndarray)
    assert captured["sdr_rgb"].flags.c_contiguous
    assert captured["hdr_rgb"].flags.c_contiguous
