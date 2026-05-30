#!/bin/bash
set -euo pipefail

HALIDE_DIR=${HALIDE_DIR:-$HOME/halide}
BUILD_DIR=build/halide-aot-arm64-android
OUTPUT_DIR=android/app/src/main/cpp/halide-aot

echo "Halide dir: $HALIDE_DIR"
echo "Build dir:  $BUILD_DIR"
echo "Output dir: $OUTPUT_DIR"

# Verify prerequisites
if [ ! -f "$HALIDE_DIR/lib/cmake/Halide/HalideConfig.cmake" ]; then
    echo "ERROR: Halide not found at $HALIDE_DIR"
    echo "Download from: https://github.com/halide/Halide/releases"
    exit 1
fi

# Configure
# IMPORTANT: Do NOT use the Android toolchain file. Halide AOT generators
# produce machine code directly via LLVM, so they run on the HOST and emit
# code for the TARGET (arm-64-android). No NDK C++ compiler needed.
cmake -S src/spektrafilm/generators -B "$BUILD_DIR" \
    -DHalide_DIR="$HALIDE_DIR/lib/cmake/Halide" \
    -DHalideHelpers_DIR="$HALIDE_DIR/lib/cmake/HalideHelpers" \
    -DTARGET=arm-64-android \
    -DCMAKE_BUILD_TYPE=Release

# Build generator executables (host)
cmake --build "$BUILD_DIR" --target spektrafilm_halide_generators-halide_generators \
    -j"$(sysctl -n hw.ncpu)"

# Build each AOT library (.update targets run the generators)
LIBS="density_to_light light_to_raw compute_density_spectral
      gaussian_blur_fir gaussian_blur_iir cctf_encode cctf_decode
      highlight_boost interp_1d lut_2d_cubic"

for lib in $LIBS; do
    echo "Building $lib..."
    cmake --build "$BUILD_DIR" --target "${lib}.update" -j"$(sysctl -n hw.ncpu)"
done

# Build runtime (one is enough - all share the same target)
cmake --build "$BUILD_DIR" --target density_to_light.runtime.update -j"$(sysctl -n hw.ncpu)"

# Copy outputs
mkdir -p "$OUTPUT_DIR"
for lib in $LIBS; do
    cp "$BUILD_DIR/$lib.a" "$OUTPUT_DIR/"
    cp "$BUILD_DIR/$lib.h" "$OUTPUT_DIR/"
done

# Copy runtime as HalideRuntime.a
cp "$BUILD_DIR/density_to_light.runtime.a" "$OUTPUT_DIR/HalideRuntime.a"

echo ""
echo "Done! Built $(ls "$OUTPUT_DIR"/*.a 2>/dev/null | wc -l | tr -d ' ') AOT libraries."
ls -la "$OUTPUT_DIR"/*.a
