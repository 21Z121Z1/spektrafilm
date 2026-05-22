from __future__ import annotations

import json
from dataclasses import asdict, fields, is_dataclass
from pathlib import Path
from typing import Any

from qtpy.QtCore import QSettings, QStandardPaths

from spektrafilm_gui.state import GuiState, PROJECT_DEFAULT_GUI_STATE, clone_gui_state


DEFAULT_GUI_STATE_FILENAME = "gui_default_state.json"


def gui_state_to_dict(state: GuiState) -> dict[str, Any]:
    return asdict(state)


def gui_state_from_dict(data: dict[str, Any]) -> GuiState:
    if not isinstance(data, dict):
        raise ValueError("GUI state data must be a JSON object.")
    return _merge_into_dataclass(clone_gui_state(PROJECT_DEFAULT_GUI_STATE), data)


def load_default_gui_state() -> GuiState:
    default_path = default_gui_state_path()
    if not default_path.exists():
        return clone_gui_state(PROJECT_DEFAULT_GUI_STATE)
    return load_gui_state_from_path(default_path)


def save_default_gui_state(state: GuiState) -> Path:
    default_path = default_gui_state_path()
    save_gui_state_to_path(state, default_path)
    return default_path


def clear_saved_default_gui_state() -> None:
    default_path = default_gui_state_path()
    if default_path.exists():
        default_path.unlink()


def save_gui_state_to_path(state: GuiState, path: str | Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8") as file:
        json.dump(gui_state_to_dict(state), file, indent=2)


def load_gui_state_from_path(path: str | Path) -> GuiState:
    source = Path(path)
    with source.open("r", encoding="utf-8") as file:
        return gui_state_from_dict(json.load(file))


def default_gui_state_path() -> Path:
    app_config_location = QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation)
    if app_config_location:
        return Path(app_config_location) / DEFAULT_GUI_STATE_FILENAME
    return Path.home() / ".spektrafilm" / DEFAULT_GUI_STATE_FILENAME


def _merge_into_dataclass(target: Any, data: Any) -> Any:
    if not isinstance(data, dict):
        return target
    for field_info in fields(target):
        name = field_info.name
        if name not in data:
            continue
        current = getattr(target, name)
        value = data[name]
        if is_dataclass(current):
            _merge_into_dataclass(current, value)
        elif isinstance(current, tuple) and isinstance(value, (list, tuple)):
            setattr(target, name, tuple(value))
        elif not is_dataclass(current) and not isinstance(current, tuple):
            setattr(target, name, value)
    return target


def load_dialog_dir(key: str) -> str:
    return QSettings('spektrafilm', 'spektrafilm').value(f'dialog_dirs/{key}', '')


def save_dialog_dir(key: str, directory: str) -> None:
    QSettings('spektrafilm', 'spektrafilm').setValue(f'dialog_dirs/{key}', directory)