from __future__ import annotations

import sys

import pytest

from spektrafilm.runtime.api import init_params
from spektrafilm.runtime.params_schema import FilmBaseParams
from spektrafilm_gui.param_manifest import TUNE_PANEL_FIELDS
from spektrafilm_gui.params_mapper import build_params_from_state
from spektrafilm_gui.state import clone_gui_state, gui_state_from_params


FILM = "kodak_portra_400"
PRINT = "kodak_portra_endura"


def _custom_base() -> FilmBaseParams:
    return FilmBaseParams(
        active=True,
        scale=1.17,
        tilt=-0.08,
        cyan=1.12,
        magenta=0.93,
        yellow=1.06,
    )


def _gui_state_with_custom_base():
    params = init_params(film_profile=FILM, print_profile=PRINT)
    params.film_render.base = _custom_base()
    return gui_state_from_params(params, film_stock=FILM, print_paper=PRINT)


def _assert_custom_base(base: FilmBaseParams) -> None:
    expected = _custom_base()
    assert base.active == expected.active
    assert base.scale == expected.scale
    assert base.tilt == expected.tilt
    assert base.cyan == expected.cyan
    assert base.magenta == expected.magenta
    assert base.yellow == expected.yellow


def test_runtime_to_gui_to_runtime_preserves_film_base():
    state = _gui_state_with_custom_base()
    _assert_custom_base(state.special.film_render.base)

    rebuilt = build_params_from_state(state)
    _assert_custom_base(rebuilt.film_render.base)


def test_gui_clone_does_not_alias_nested_film_base():
    source = _gui_state_with_custom_base()
    clone = clone_gui_state(source)

    clone.special.film_render.base.scale = 2.0
    clone.special.film_render.base.cyan = 0.5

    assert source.special.film_render.base.scale == 1.17
    assert source.special.film_render.base.cyan == 1.12


@pytest.mark.skipif(sys.platform != "darwin", reason="Qt persistence import is validated on the macOS CI lane")
def test_gui_persistence_round_trip_preserves_film_base():
    from spektrafilm_gui.persistence import gui_state_from_dict, gui_state_to_dict

    source = _gui_state_with_custom_base()
    encoded = gui_state_to_dict(source)

    assert encoded["special"]["film_base_scale"] == 1.17
    assert encoded["special"]["film_base_tilt"] == -0.08

    restored = gui_state_from_dict(encoded)
    _assert_custom_base(restored.special.film_render.base)


def test_tune_manifest_exposes_all_film_base_controls():
    paths = {spec.path for spec in TUNE_PANEL_FIELDS}
    assert {
        "film_render.base.active",
        "film_render.base.scale",
        "film_render.base.cyan",
        "film_render.base.magenta",
        "film_render.base.yellow",
        "film_render.base.tilt",
    } <= paths
