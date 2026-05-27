from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_:.-]*$")


@dataclass(frozen=True, slots=True)
class AndroidHalideTarget:
    abi: str
    halide_target: str
    cmake_abi: str
    notes: tuple[str, ...] = ()


_ANDROID_TARGETS: dict[str, AndroidHalideTarget] = {
    "arm64-v8a": AndroidHalideTarget(
        abi="arm64-v8a",
        halide_target="arm-64-android",
        cmake_abi="arm64-v8a",
        notes=("Default production target for modern Android devices.",),
    ),
    "armeabi-v7a": AndroidHalideTarget(
        abi="armeabi-v7a",
        halide_target="arm-32-android",
        cmake_abi="armeabi-v7a",
        notes=("Legacy 32-bit ARM target; keep only if product support requires it.",),
    ),
    "x86_64": AndroidHalideTarget(
        abi="x86_64",
        halide_target="x86-64-android",
        cmake_abi="x86_64",
        notes=("Emulator and selected ChromeOS devices.",),
    ),
    "x86": AndroidHalideTarget(
        abi="x86",
        halide_target="x86-32-android",
        cmake_abi="x86",
        notes=("Legacy emulator target.",),
    ),
}


def android_halide_target(abi: str) -> AndroidHalideTarget:
    try:
        return _ANDROID_TARGETS[abi]
    except KeyError as exc:
        supported = ", ".join(_ANDROID_TARGETS)
        raise ValueError(f"Unsupported Android ABI {abi!r}; supported ABIs: {supported}") from exc


def android_halide_targets(abis: Iterable[str] | None = None) -> tuple[AndroidHalideTarget, ...]:
    selected_abis = ("arm64-v8a",) if abis is None else tuple(abis)
    return tuple(android_halide_target(abi) for abi in selected_abis)


def _validate_identifier(value: str, label: str) -> str:
    if not value or not _IDENTIFIER_RE.match(value):
        raise ValueError(f"{label} must be a safe CMake identifier, got {value!r}")
    return value


def render_add_halide_library(
    *,
    library_name: str,
    generator_target: str,
    generator_name: str,
    abis: Iterable[str] = ("arm64-v8a",),
    autoscheduler: str | None = "Halide::Adams2019",
) -> str:
    """Render the tested CMake AOT contract for Android Halide generators."""

    library_name = _validate_identifier(library_name, "library_name")
    generator_target = _validate_identifier(generator_target, "generator_target")
    generator_name = _validate_identifier(generator_name, "generator_name")
    if autoscheduler is not None:
        autoscheduler = _validate_identifier(autoscheduler, "autoscheduler")

    targets = " ".join(target.halide_target for target in android_halide_targets(abis))
    lines = [
        f"add_halide_library({library_name}",
        f"    FROM {generator_target}",
        f"    GENERATOR {generator_name}",
        f"    TARGETS {targets}",
    ]
    if autoscheduler:
        lines.append(f"    AUTOSCHEDULER {autoscheduler}")
    lines.append(")")
    return "\n".join(lines)
