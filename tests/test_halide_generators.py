from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _halide_cmake_dir() -> Path:
    halide = pytest.importorskip("halide")
    install_dir = getattr(halide, "install_dir", None)
    if install_dir is None:
        pytest.skip("installed halide module does not expose install_dir()")
    cmake_dir = Path(install_dir()) / "lib/cmake/Halide"
    if not cmake_dir.exists():
        pytest.skip(f"Halide CMake package not found at {cmake_dir}")
    return cmake_dir


def _cmake_executable() -> str:
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("cmake executable is unavailable")
    return cmake


def _configure_generators(tmp_path: Path) -> tuple[str, Path]:
    cmake = _cmake_executable()
    repo_root = Path(__file__).resolve().parents[1]
    build_dir = tmp_path / "halide-generators-build"
    result = subprocess.run(
        [
            cmake,
            "-S",
            str(repo_root / "src/spektrafilm/generators"),
            "-B",
            str(build_dir),
            f"-DHalide_DIR={_halide_cmake_dir()}",
            "-DTARGET=host",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    return cmake, build_dir


def test_halide_generator_cmake_project_configures_and_builds_host_aot_targets(tmp_path: Path) -> None:
    cmake, build_dir = _configure_generators(tmp_path)
    result = subprocess.run(
        [cmake, "--build", str(build_dir)],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Built target lut_2d_cubic" in result.stdout + result.stderr


def test_spectral_density_to_light_generator_uses_wavelength_coordinate() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "src/spektrafilm/generators/spectral_generator.cpp").read_text()

    assert "density(c, y, w)" in source
    assert "density(c, y, 0)" not in source


def test_halide_generator_cmake_project_builds_host_targets(tmp_path: Path) -> None:
    cmake = shutil.which("cmake")
    if cmake is None:
        pytest.skip("cmake executable is unavailable")
    if shutil.which("c++") is None and shutil.which("g++") is None and shutil.which("clang++") is None:
        pytest.skip("C++ compiler is unavailable")

    repo_root = Path(__file__).resolve().parents[1]
    build_dir = tmp_path / "halide-generators-build"
    configure = subprocess.run(
        [
            cmake,
            "-S",
            str(repo_root / "src/spektrafilm/generators"),
            "-B",
            str(build_dir),
            f"-DHalide_DIR={_halide_cmake_dir()}",
            "-DTARGET=host",
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    assert configure.returncode == 0, configure.stdout + configure.stderr

    build = subprocess.run(
        [cmake, "--build", str(build_dir)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert build.returncode == 0, build.stdout + build.stderr
