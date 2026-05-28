"""Test that the Halide AOT generator CMake project configures and builds on host."""

import shutil
import subprocess

import pytest

halide = pytest.importorskip("halide")

HALIDE_CMAKE_DIR = halide.install_dir() + "/lib/cmake/Halide"
GENERATORS_SRC = "src/spektrafilm/generators"
BUILD_DIR = "/tmp/spektrafilm-halide-test"


@pytest.fixture()
def cmake_build():
    """Configure and build the Halide generators, then clean up."""
    shutil.rmtree(BUILD_DIR, ignore_errors=True)
    yield BUILD_DIR
    shutil.rmtree(BUILD_DIR, ignore_errors=True)


@pytest.mark.skipif(
    shutil.which("cmake") is None, reason="cmake not found on PATH"
)
@pytest.mark.skipif(
    shutil.which("c++") is None and shutil.which("g++") is None and shutil.which("clang++") is None,
    reason="no C++ compiler found",
)
class TestHalideGenerators:
    def test_cmake_configure(self, cmake_build):
        result = subprocess.run(
            [
                "cmake",
                "-S", GENERATORS_SRC,
                "-B", cmake_build,
                f"-DHalide_DIR={HALIDE_CMAKE_DIR}",
                "-DTARGET=host",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"cmake configure failed:\n{result.stderr}"
        assert "Configuring done" in result.stdout or "Configuring done" in result.stderr

    def test_cmake_build(self, cmake_build):
        # Configure first
        subprocess.run(
            [
                "cmake",
                "-S", GENERATORS_SRC,
                "-B", cmake_build,
                f"-DHalide_DIR={HALIDE_CMAKE_DIR}",
                "-DTARGET=host",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        # Build
        result = subprocess.run(
            ["cmake", "--build", cmake_build],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"cmake build failed:\n{result.stderr}"
        combined = result.stdout + result.stderr
        assert "[100%] Built target" in combined
