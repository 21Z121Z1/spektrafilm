from __future__ import annotations

from pathlib import Path

import pytest

from spektrafilm.halide.android import (
    android_halide_target,
    android_halide_targets,
    render_add_halide_library,
)


pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[1]
JNI_SOURCE = REPO_ROOT / "android" / "app" / "src" / "main" / "cpp" / "spektrafilm_android_jni.cpp"


def _jni_source() -> str:
    return JNI_SOURCE.read_text()


@pytest.mark.parametrize(
    ("abi", "target"),
    [
        ("arm64-v8a", "arm-64-android"),
        ("armeabi-v7a", "arm-32-android"),
        ("x86_64", "x86-64-android"),
        ("x86", "x86-32-android"),
    ],
)
def test_android_halide_target_maps_ndk_abi_to_halide_target(abi: str, target: str) -> None:
    assert android_halide_target(abi).halide_target == target


def test_android_halide_targets_defaults_to_arm64_first() -> None:
    targets = android_halide_targets()

    assert [target.abi for target in targets] == ["arm64-v8a"]
    assert targets[0].halide_target == "arm-64-android"


def test_android_halide_target_rejects_unknown_abi() -> None:
    with pytest.raises(ValueError, match="Unsupported Android ABI"):
        android_halide_target("mips")


def test_render_add_halide_library_contains_aot_contract() -> None:
    cmake = render_add_halide_library(
        library_name="spektrafilm_rgb_to_xyz_halide",
        generator_target="spektrafilm_generators",
        generator_name="spektrafilm_rgb_to_xyz",
        abis=("arm64-v8a", "x86_64"),
        autoscheduler="Halide::Adams2019",
    )

    assert "add_halide_library(spektrafilm_rgb_to_xyz_halide" in cmake
    assert "FROM spektrafilm_generators" in cmake
    assert "GENERATOR spektrafilm_rgb_to_xyz" in cmake
    assert "TARGETS arm-64-android x86-64-android" in cmake
    assert "AUTOSCHEDULER Halide::Adams2019" in cmake


@pytest.mark.parametrize("unsafe", ["../x", "x;y", "x y", ""])
def test_render_add_halide_library_rejects_unsafe_identifiers(unsafe: str) -> None:
    with pytest.raises(ValueError, match="identifier"):
        render_add_halide_library(
            library_name=unsafe,
            generator_target="spektrafilm_generators",
            generator_name="spektrafilm_rgb_to_xyz",
        )


def test_android_jni_json_helpers_guard_short_payloads() -> None:
    source = _jni_source()

    assert "json == nullptr" in source
    assert "key == nullptr" in source
    assert "len < klen" in source
    assert "i + klen <= len" in source
    assert "char token[64]" in source


def test_android_jni_profile_loader_rejects_out_of_bounds_offset() -> None:
    source = _jni_source()

    assert "offset < 16" in source
    assert "static_cast<size_t>(offset) > total_len" in source


def test_android_jni_process_image_rejects_null_params_json() -> None:
    source = _jni_source()

    assert "paramsJson == nullptr" in source
    assert "json_bytes == nullptr" in source
