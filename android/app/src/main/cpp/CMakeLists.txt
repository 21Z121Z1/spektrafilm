cmake_minimum_required(VERSION 3.22.1)
project(spektrafilm_android LANGUAGES CXX)

add_library(spektrafilm_android SHARED
    spektrafilm_android_jni.cpp
    spektrafilm_pipeline.cpp
)

target_compile_features(spektrafilm_android PRIVATE cxx_std_17)
target_compile_options(spektrafilm_android PRIVATE
    -Wall
    -Wextra
    -Wno-unused-parameter
    -Wno-unused-variable
)

find_library(log-lib log)
target_link_libraries(spektrafilm_android PRIVATE ${log-lib})

# Include project headers (HalideRuntime.h, spektrafilm_params.h, etc.)
target_include_directories(spektrafilm_android PRIVATE ${CMAKE_CURRENT_SOURCE_DIR})

# Halide AOT libraries
set(SPEKTRAFILM_HALIDE_AOT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/halide-aot"
    CACHE PATH "Directory containing Spektrafilm Android Halide AOT libraries")

if(SPEKTRAFILM_HALIDE_AOT_DIR AND EXISTS "${SPEKTRAFILM_HALIDE_AOT_DIR}")
    # Include generated AOT headers
    target_include_directories(spektrafilm_android PRIVATE ${SPEKTRAFILM_HALIDE_AOT_DIR})

    # Link each Halide AOT library
    foreach(lib density_to_light light_to_raw compute_density_spectral
                gaussian_blur_fir gaussian_blur_iir cctf_encode cctf_decode
                highlight_boost interp_1d lut_2d_cubic)
        add_library(${lib} STATIC IMPORTED)
        set_target_properties(${lib} PROPERTIES
            IMPORTED_LOCATION "${SPEKTRAFILM_HALIDE_AOT_DIR}/${lib}.a")
        target_link_libraries(spektrafilm_android PRIVATE ${lib})
    endforeach()

    # Halide runtime
    add_library(HalideRuntime STATIC IMPORTED)
    set_target_properties(HalideRuntime PROPERTIES
        IMPORTED_LOCATION "${SPEKTRAFILM_HALIDE_AOT_DIR}/HalideRuntime.a")
    target_link_libraries(spektrafilm_android PRIVATE HalideRuntime)

    target_compile_definitions(spektrafilm_android PRIVATE SPEKTRAFILM_HAS_HALIDE_AOT=1)
    message(STATUS "Spektrafilm Halide AOT libraries found at: ${SPEKTRAFILM_HALIDE_AOT_DIR}")
else()
    message(STATUS "Spektrafilm Halide AOT directory not configured; building diagnostic bridge only")
endif()
