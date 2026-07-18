from __future__ import annotations

import numpy as np

from spektrafilm.runtime.pipeline import SimulationPipeline
from spektrafilm.runtime.stages.filming import FilmingStage
from spektrafilm.runtime.stages.printing import PrintingStage
from tests.conftest import make_fast_test_params


def _image(size: int = 12) -> np.ndarray:
    ramp = np.linspace(0.02, 0.95, size, dtype=np.float64)
    return np.stack(
        (
            np.broadcast_to(ramp[None, :], (size, size)),
            np.broadcast_to(ramp[:, None], (size, size)),
            np.full((size, size), 0.18, dtype=np.float64),
        ),
        axis=-1,
    )


def test_plain_film_exposure_skips_unused_luminance_sidecars(monkeypatch) -> None:
    calls = 0
    original = FilmingStage._raw_luminance_y

    def counted(self, raw):
        nonlocal calls
        calls += 1
        return original(self, raw)

    monkeypatch.setattr(FilmingStage, "_raw_luminance_y", counted)
    pipeline = SimulationPipeline(make_fast_test_params())

    plain = pipeline._filming_stage.expose(_image())
    assert plain.shape == (12, 12, 3)
    assert calls == 0

    metadata = pipeline._filming_stage.expose_with_metadata(_image())
    np.testing.assert_array_equal(plain, metadata.log_raw)
    assert calls == 2
    assert metadata.scene_y_raw.shape == (12, 12)
    assert metadata.post_halation_y.shape == (12, 12)


def test_disabled_print_correction_skips_reference_exposures(monkeypatch) -> None:
    calls = 0
    original = PrintingStage._film_cmy_to_print_log_raw

    def counted(self, density, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, density, *args, **kwargs)

    monkeypatch.setattr(PrintingStage, "_film_cmy_to_print_log_raw", counted)
    pipeline = SimulationPipeline(make_fast_test_params())
    output = pipeline.process(_image())

    assert output.shape == (12, 12, 3)
    assert calls == 1


def test_enabled_negative_print_correction_keeps_reference_exposures(monkeypatch) -> None:
    calls = 0
    original = PrintingStage._film_cmy_to_print_log_raw

    def counted(self, density, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, density, *args, **kwargs)

    monkeypatch.setattr(PrintingStage, "_film_cmy_to_print_log_raw", counted)
    params = make_fast_test_params()
    params.scanner.black_correction = True
    pipeline = SimulationPipeline(params)
    pipeline.process(_image())

    assert pipeline._color_reference_service.requires_printing_references()
    assert calls == 3
