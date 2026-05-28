# Halide AOT generator CMake configuration.
#
# Usage (standalone build):
#   mkdir build && cd build
#   cmake .. -DHalide_DIR=/path/to/halide/lib/cmake/Halide
#   cmake --build .
#
# To integrate into a larger project, add this directory via add_subdirectory()
# and link the generated libraries with target_link_libraries().

cmake_minimum_required(VERSION 3.28)
project(spektrafilm_halide_generators LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(Halide REQUIRED)

# ---------------------------------------------------------------------------
# Target configuration
# ---------------------------------------------------------------------------
# Default to host; override with -DTARGET=arm-64-android on the command line.
if(NOT DEFINED TARGET)
    set(TARGET host)
endif()

# ---------------------------------------------------------------------------
# Generator executables — must be declared before add_halide_library() calls
# ---------------------------------------------------------------------------
add_halide_generator(spectral_generator SOURCES spectral_generator.cpp)
add_halide_generator(filter_generator SOURCES filter_generator.cpp)
add_halide_generator(color_generator SOURCES color_generator.cpp)
add_halide_generator(lut_generator SOURCES lut_generator.cpp)

# ---------------------------------------------------------------------------
# Generators — each add_halide_library() call:
#   1. Builds the Generator executable (compile-time)
#   2. Runs it to emit .a/.h for the target platform
# ---------------------------------------------------------------------------

# --- Spectral generators (3 functions) ---
add_halide_library(density_to_light FROM spectral_generator
                   GENERATOR DensityToLightGenerator
                   TARGETS ${TARGET}
                   REGISTRATION density_to_light_reg)

add_halide_library(light_to_raw FROM spectral_generator
                   GENERATOR LightToRawGenerator
                   TARGETS ${TARGET}
                   REGISTRATION light_to_raw_reg)

add_halide_library(compute_density_spectral FROM spectral_generator
                   GENERATOR ComputeDensitySpectralGenerator
                   TARGETS ${TARGET}
                   REGISTRATION compute_density_spectral_reg)

# --- Filter generators (2 functions) ---
add_halide_library(gaussian_blur_fir FROM filter_generator
                   GENERATOR GaussianBlurFIRGenerator
                   TARGETS ${TARGET}
                   REGISTRATION gaussian_blur_fir_reg)

add_halide_library(gaussian_blur_iir FROM filter_generator
                   GENERATOR GaussianBlurIIRGenerator
                   TARGETS ${TARGET}
                   REGISTRATION gaussian_blur_iir_reg)

# --- Colour generators (3 functions) ---
add_halide_library(cctf_encode FROM color_generator
                   GENERATOR CCTFEncodeGenerator
                   TARGETS ${TARGET}
                   REGISTRATION cctf_encode_reg)

add_halide_library(cctf_decode FROM color_generator
                   GENERATOR CCTFDecodeGenerator
                   TARGETS ${TARGET}
                   REGISTRATION cctf_decode_reg)

add_halide_library(highlight_boost FROM color_generator
                   GENERATOR HighlightBoostGenerator
                   TARGETS ${TARGET}
                   REGISTRATION highlight_boost_reg)

# --- LUT generators (2 functions) ---
add_halide_library(interp_1d FROM lut_generator
                   GENERATOR Interp1DGenerator
                   TARGETS ${TARGET}
                   REGISTRATION interp_1d_reg)

add_halide_library(lut_2d_cubic FROM lut_generator
                   GENERATOR Lut2DCubicGenerator
                   TARGETS ${TARGET}
                   REGISTRATION lut_2d_cubic_reg)

# ---------------------------------------------------------------------------
# Aggregate convenience target — links all generated libraries.
# ---------------------------------------------------------------------------
add_library(spektrafilm_halide_all INTERFACE)
target_link_libraries(spektrafilm_halide_all
    INTERFACE
        density_to_light
        light_to_raw
        compute_density_spectral
        gaussian_blur_fir
        gaussian_blur_iir
        cctf_encode
        cctf_decode
        highlight_boost
        interp_1d
        lut_2d_cubic
)
