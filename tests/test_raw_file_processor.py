from types import SimpleNamespace

import numpy as np
import pytest

from spektrafilm.utils import raw_file_processor


def _stub_raw_reader(monkeypatch, raw_image: np.ndarray) -> None:
    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def postprocess(self, **_kwargs):
            return raw_image

    monkeypatch.setattr(
        raw_file_processor,
        'rawpy',
        SimpleNamespace(
            imread=lambda path: Reader(),
            ColorSpace=SimpleNamespace(ACES='ACES'),
        ),
    )


def _stub_exif(monkeypatch, **overrides) -> None:
    values = {
        'make': 'Canon',
        'model': 'Canon EOS 5D Mark IV',
        'lens_make': 'Canon',
        'lens_model': 'Canon EF 50mm f/1.8 STM',
        'focal_length': 50.0,
        'f_number': 2.8,
    }
    values.update(overrides)
    exif_metadata = raw_file_processor.ExifData(**values)
    monkeypatch.setattr(raw_file_processor, '_read_exif_metadata', lambda path: exif_metadata)


def test_process_raw_file_daylight_uses_float32_matrix_colour_conversion(monkeypatch):
    raw_image = np.full((1, 1, 3), 16384, dtype=np.uint16)
    captured = {}

    class Reader:
        daylight_whitebalance = [2.0, 1.0, 1.5, 1.0]
        rgb_xyz_matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def postprocess(self, **kwargs):
            captured['postprocess'] = kwargs
            return raw_image

    def imread(path):
        captured['path'] = path
        return Reader()

    def fail_rgb_to_rgb(*_args, **_kwargs):
        raise AssertionError('linear RAW conversion must not materialize through colour.RGB_to_RGB')

    def fake_matrix_rgb_to_rgb(input_colourspace, output_colourspace, **kwargs):
        captured['matrix'] = {
            'input_colourspace': input_colourspace,
            'output_colourspace': output_colourspace,
            'kwargs': kwargs,
        }
        return np.diag([1.0, 2.0, 3.0])

    monkeypatch.setattr(
        raw_file_processor,
        'rawpy',
        SimpleNamespace(
            imread=imread,
            ColorSpace=SimpleNamespace(ACES='ACES'),
        ),
    )
    monkeypatch.setattr(raw_file_processor.colour, 'RGB_to_RGB', fail_rgb_to_rgb)
    monkeypatch.setattr(raw_file_processor.colour, 'matrix_RGB_to_RGB', fake_matrix_rgb_to_rgb)

    result = raw_file_processor.load_and_process_raw_file(
        'example.nef',
        white_balance='daylight',
        output_colorspace='sRGB',
        output_cctf_encoding=False,
    )

    expected_linear = raw_image.astype(np.float32) / 65535.0
    np.testing.assert_allclose(result, expected_linear * np.array([1.0, 2.0, 3.0], dtype=np.float32))
    assert result.dtype == np.float32
    assert captured['path'] == 'example.nef'
    assert captured['postprocess']['output_color'] == 'ACES'
    assert captured['postprocess']['output_bps'] == 16
    assert captured['postprocess']['no_auto_bright'] is True
    assert captured['postprocess']['gamma'] == (1, 1)
    assert 'user_wb' not in captured['postprocess']
    assert 'use_camera_wb' not in captured['postprocess']
    assert captured['matrix']['input_colourspace'] == raw_file_processor.colour.RGB_COLOURSPACES['ACES2065-1']
    assert captured['matrix']['output_colourspace'] == raw_file_processor.colour.RGB_COLOURSPACES['sRGB']
    assert captured['matrix']['kwargs']['chromatic_adaptation_transform'] == 'CAT02'


def test_process_raw_file_as_shot_uses_camera_white_balance(monkeypatch):
    raw_image = np.full((1, 1, 3), 32768, dtype=np.uint16)
    captured = {}

    class Reader:
        daylight_whitebalance = [2.0, 1.0, 1.5, 1.0]
        rgb_xyz_matrix = np.array(
            [
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
                [0.0, 1.0, 0.0],
            ],
            dtype=np.float64,
        )

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def postprocess(self, **kwargs):
            captured['postprocess'] = kwargs
            return raw_image

    monkeypatch.setattr(
        raw_file_processor,
        'rawpy',
        SimpleNamespace(
            imread=lambda path: Reader(),
            ColorSpace=SimpleNamespace(ACES='ACES'),
        ),
    )

    result = raw_file_processor.load_and_process_raw_file('example.nef', white_balance='as_shot')

    np.testing.assert_allclose(result, raw_image.astype(np.float32) / 65535.0)
    assert result.dtype == np.float32
    assert captured['postprocess']['use_camera_wb'] is True
    assert 'user_wb' not in captured['postprocess']


def test_linear_colourspace_conversion_matches_colour_reference_without_float64_output() -> None:
    rgb = np.array(
        [
            [[0.05, 0.10, 0.20], [0.25, 0.50, 0.75]],
            [[0.90, 0.40, 0.15], [1.10, 0.95, 0.60]],
        ],
        dtype=np.float32,
    )

    actual = raw_file_processor._convert_linear_rgb_colourspace(
        rgb,
        'ProPhoto RGB',
        output_cctf_encoding=False,
    )
    expected = raw_file_processor.colour.RGB_to_RGB(
        rgb,
        input_colourspace=raw_file_processor.colour.RGB_COLOURSPACES['ACES2065-1'],
        output_colourspace=raw_file_processor.colour.RGB_COLOURSPACES['ProPhoto RGB'],
        apply_cctf_decoding=False,
        apply_cctf_encoding=False,
    )

    assert actual.dtype == np.float32
    np.testing.assert_allclose(actual, expected.astype(np.float32), rtol=0.0, atol=2e-7)


@pytest.mark.parametrize(
    (
        'white_balance',
        'temperature',
        'tint',
        'expected_result_scale',
        'expected_source_white',
    ),
    [
        ('tungsten', None, None, np.array([1.0, 1.0, 1.0], dtype=np.float32), np.array([2.85, 1.0, 1.425])),
        ('custom', 3200.0, 0.85, np.array([1.0, 0.85, 1.0], dtype=np.float32), np.array([3.2, 1.0, 1.6])),
        ('custom', 6504.0, 1.0, np.array([1.0, 1.0, 1.0], dtype=np.float32), None),
    ],
    ids=['tungsten', 'custom-tungsten', 'custom-daylight'],
)
def test_process_raw_file_temperature_white_balance_variants(monkeypatch, white_balance, temperature, tint, expected_result_scale, expected_source_white):
    raw_image = np.full((1, 1, 3), 16384, dtype=np.uint16)
    postprocess_calls: list[dict[str, object]] = []
    adaptation_calls = []

    class Reader:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def postprocess(self, **kwargs):
            postprocess_calls.append(kwargs)
            return raw_image

    monkeypatch.setattr(
        raw_file_processor,
        'rawpy',
        SimpleNamespace(
            imread=lambda path: Reader(),
            ColorSpace=SimpleNamespace(ACES='ACES'),
        ),
    )
    monkeypatch.setattr(raw_file_processor.colour, 'CCT_to_xy', lambda temperature, method='CIE Illuminant D Series': np.array([temperature, 0.0]))
    monkeypatch.setattr(raw_file_processor.colour, 'xy_to_XYZ', lambda xy: np.array([xy[0] / 1000.0, 1.0, xy[0] / 2000.0]))
    monkeypatch.setattr(raw_file_processor.colour, 'RGB_to_XYZ', lambda image, **kwargs: image)

    def fake_chromatic_adaptation(xyz, source_white_xyz, target_white_xyz, **kwargs):
        adaptation_calls.append(
            {
                'source': source_white_xyz,
                'target': target_white_xyz,
                'kwargs': kwargs,
            }
        )
        return xyz + np.float32(0.25)

    monkeypatch.setattr(raw_file_processor.colour, 'chromatic_adaptation', fake_chromatic_adaptation)
    monkeypatch.setattr(raw_file_processor.colour, 'XYZ_to_RGB', lambda xyz, **kwargs: xyz)

    result = raw_file_processor.load_and_process_raw_file(
        'example.nef',
        white_balance=white_balance,
        temperature=temperature,
        tint=tint,
    )

    expected_linear = raw_image.astype(np.float32) / 65535.0
    expected = expected_linear if expected_source_white is None else expected_linear + 0.25
    expected = expected * expected_result_scale
    np.testing.assert_allclose(result, expected)
    assert all('user_wb' not in call for call in postprocess_calls)
    assert all('use_camera_wb' not in call for call in postprocess_calls)
    if expected_source_white is None:
        assert adaptation_calls == []
    else:
        assert len(adaptation_calls) == 1
        np.testing.assert_allclose(adaptation_calls[0]['source'], expected_source_white)
        np.testing.assert_allclose(adaptation_calls[0]['target'], [6.504, 1.0, 3.252])
        assert adaptation_calls[0]['kwargs']['method'] == 'Von Kries'


@pytest.mark.parametrize(
    ('lens_model', 'correction_summary', 'expect_database_call', 'expected_lens_info'),
    [
        ('', None, False, {}),
        ('Canon EF 50mm f/1.8 STM', '', True, {}),
        (
            'Canon EF 50mm f/1.8 STM',
            'Canon EF 50mm f/1.8 STM @ 50.0mm f/2.8',
            True,
            {'summary': 'Canon EF 50mm f/1.8 STM @ 50.0mm f/2.8'},
        ),
    ],
    ids=['missing-lens-model', 'no-correction-summary', 'correction-summary'],
)
def test_process_raw_file_lens_info_reporting(
    monkeypatch,
    lens_model: str,
    correction_summary: str | None,
    expect_database_call: bool,
    expected_lens_info: dict[str, str],
):
    raw_image = np.full((1, 1, 3), 16384, dtype=np.uint16)
    lens_info_out: dict[str, str] = {}

    _stub_raw_reader(monkeypatch, raw_image)
    _stub_exif(monkeypatch, lens_model=lens_model)

    if not expect_database_call:
        monkeypatch.setattr(
            raw_file_processor.lensfunpy,
            'Database',
            lambda: (_ for _ in ()).throw(AssertionError('lensfun database should not be queried without a lens model')),
        )
    else:
        monkeypatch.setattr(
            raw_file_processor,
            '_apply_lens_correction',
            lambda rgb, exif_metadata: (rgb, '' if correction_summary is None else correction_summary),
        )

    result = raw_file_processor.load_and_process_raw_file(
        'example.nef',
        lens_correction=True,
        lens_info_out=lens_info_out,
    )

    np.testing.assert_allclose(result, raw_image.astype(np.float32) / 65535.0)
    assert lens_info_out == expected_lens_info


def test_process_raw_file_reports_exif_read_failure_for_lens_correction(monkeypatch):
    raw_image = np.full((1, 1, 3), 16384, dtype=np.uint16)
    lens_info_out: dict[str, str] = {}

    _stub_raw_reader(monkeypatch, raw_image)
    monkeypatch.setattr(
        raw_file_processor,
        '_read_exif_metadata',
        lambda path: raw_file_processor.ExifData(
            make='',
            model='',
            lens_make='',
            lens_model='',
            focal_length=0.0,
            f_number=0.0,
            metadata_error='RuntimeError: damaged EXIF',
        ),
    )
    monkeypatch.setattr(
        raw_file_processor.lensfunpy,
        'Database',
        lambda: (_ for _ in ()).throw(AssertionError('lensfun database should not be queried without EXIF lens metadata')),
    )

    result = raw_file_processor.load_and_process_raw_file(
        'example.nef',
        lens_correction=True,
        lens_info_out=lens_info_out,
    )

    np.testing.assert_allclose(result, raw_image.astype(np.float32) / 65535.0)
    assert lens_info_out == {
        'warning': 'EXIF metadata unavailable; lens correction skipped: RuntimeError: damaged EXIF',
    }
