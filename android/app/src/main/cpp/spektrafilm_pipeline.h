#pragma once

#include "spektrafilm_params.h"
#include "HalideRuntime.h"

#include <cstdint>
#include <memory>
#include <vector>

namespace spektrafilm {

// Error codes
enum PipelineError {
    kPipelineOk = 0,
    kPipelineNullBuffer = 1,
    kPipelineInvalidDimensions = 2,
    kPipelineNotInitialized = 3,
    kPipelineHalideError = 4,
    kPipelineAllocFailed = 5,
};

// Managed halide_buffer_t wrapper
struct HalideBuffer {
    halide_buffer_t buf = {};
    halide_dimension_t dims[4] = {};

    // Create a [C, H, W] float32 buffer backed by the given host pointer.
    // If host is null, allocates memory (caller must free via free_host).
    static HalideBuffer make_chw(float* host, int C, int H, int W);

    // Create a [H, W] float32 buffer (single channel, 2D)
    static HalideBuffer make_hw(float* host, int H, int W);

    // Create a [N] float32 buffer (1D)
    static HalideBuffer make_1d(float* host, int N);

    // Create a [N, M] float32 buffer (2D)
    static HalideBuffer make_2d(float* host, int N, int M);

    // Create a [H, W, 2] float32 buffer (3D, for lut_2d_cubic input)
    static HalideBuffer make_hwc(float* host, int H, int W, int C);

    void free_host();
};

// Temporary buffers for pipeline processing
struct PipelineBuffers {
    int width = 0;
    int height = 0;
    int capacity_pixels = 0; // width * height

    // CHW layout buffers [3, H, W]
    std::vector<float> chw_a; // primary
    std::vector<float> chw_b; // secondary (for ping-pong)
    // 1D query buffer for interp_1d [H, W]
    std::vector<float> query_2d;
    // LUT query buffer [H, W, 2]
    std::vector<float> query_hwc2;
    // Temporary for grain
    std::vector<float> grain_tmp;

    void allocate(int w, int h);
    bool needs_reallocation(int w, int h) const;
};

// Main pipeline class
class Pipeline {
public:
    Pipeline();
    ~Pipeline();

    // Set pipeline configuration (film profile + render settings).
    // Must be called before process().
    int configure(const PipelineConfig& config);

    // Process an image.
    // input/output are [H, W, 3] interleaved float32 buffers.
    // Returns PipelineError code.
    int process(const float* input, float* output, int width, int height);

    // Get the current config hash for change detection.
    uint32_t config_hash() const { return config_hash_; }

private:
    PipelineConfig config_;
    PipelineBuffers buffers_;
    uint32_t config_hash_ = 0;

    // Film-only path (scan_film = true)
    int process_scan_film(const float* input, float* output, int W, int H);

    // Full print path (scan_film = false)
    int process_print(const float* input, float* output, int W, int H);

    // --- Pipeline stages ---

    // Transpose [H,W,3] interleaved -> [3,H,W] planar
    void hwc_to_chw(const float* hwc, float* chw, int H, int W);

    // Transpose [3,H,W] planar -> [H,W,3] interleaved
    void chw_to_hwc(const float* chw, float* hwc, int H, int W);

    // Spectral upsampling: RGB [3,H,W] -> film raw [3,H,W]
    // Uses the Hanatos2025 method with LUT
    void rgb_to_film_raw(const float* rgb_chw, float* raw_chw, int H, int W);

    // Apply exposure compensation: raw *= 2^ev
    void apply_exposure_comp(float* raw, int H, int W, float ev);

    // Log transform: out = log10(max(raw, 0) + 1e-10) on total floats
    void apply_log_transform(const float* in, float* out, int total);

    // Exp transform: out = 10^in on total floats
    void apply_exp_transform(const float* in, float* out, int total);

    // Interpolate exposure to density via 1D LUT (interp_1d Halide kernel)
    // log_raw [3,H,W] -> density [3,H,W]
    void interpolate_exposure_to_density(const float* log_raw, float* density, int H, int W,
                                          const float* log_exposure, const float* density_curves,
                                          int curve_len, float gamma_factor);

    // Compute spectral density: density_cmy [3,H,81] from density [3,H,W]
    // einsum('ijk,lk->ijl', density_cmy_3, channel_density)
    // Actually for the printing/scanning path, W=81 (spectral dimension)
    void compute_density_spectral(const float* density_cmy_3ch, float* density_spectral,
                                   int H, int W_spectral,
                                   const float channel_density[81][3],
                                   const float base_density[3]);

    // Density to light: light = 10^(-density) * illuminant
    void density_to_light(const float* density_spectral, float* light,
                           int H, int W_spectral,
                           const float illuminant[81]);

    // Light to raw: einsum('ijk,kl->ijl', light, sensitivity)
    void light_to_raw(const float* light, float* raw,
                       int H, int W_spectral,
                       const float sensitivity[81][3]);

    // XYZ to RGB matrix multiply: rgb = xyz @ M.T
    void xyz_to_rgb_transform(const float* xyz, float* rgb, int H, int W,
                               const float matrix[3][3]);

    // 3x3 matrix multiply on CHW data: out[c] = sum_k M[c][k] * in[k]
    void matrix_multiply_chw(const float* in, float* out, int H, int W,
                              const float matrix[3][3]);

    // Gaussian blur using Halide AOT kernel (IIR for any sigma)
    void apply_gaussian_blur(float* data, int H, int W, float sigma_pixels);

    // Gaussian blur FIR (for small sigma)
    void apply_gaussian_blur_fir(float* data, int H, int W, float sigma_pixels);

    // Halation: scatter + multi-bounce
    void apply_halation(float* raw, int H, int W, float pixel_size_um);

    // Grain simulation on density
    void apply_grain(float* density_cmy, int H, int W, float pixel_size_um);

    // DIR couplers correction
    void apply_dir_couplers(float* density_cmy, const float* log_raw, int H, int W,
                             float pixel_size_um);

    // Diffusion filter (simplified Gaussian approximation)
    void apply_diffusion_filter(float* data, int H, int W, float pixel_size_um);

    // Unsharp mask
    void apply_unsharp_mask(float* data, int H, int W, float sigma, float amount);

    // CCTF encode using Halide AOT kernel
    void apply_cctf_encode(float* data, int H, int W);

    // CCTF decode using Halide AOT kernel
    void apply_cctf_decode(float* data, int H, int W);

    // Highlight boost using Halide AOT kernel
    void apply_highlight_boost(float* data, int H, int W);

    // Clamp values to [0, 1]
    void clamp_01(float* data, int total_floats);

    // Convert [3,H,W] interleaved RGB to XYZ using rgb_to_xyz matrix
    void rgb_to_xyz(const float* rgb, float* xyz, int H, int W);

    // Glare: add blurred lognormal noise
    void apply_glare(float* xyz, int H, int W);

    // Print path spectral computation
    void film_cmy_to_print_log_raw(const float* cmy_density, float* log_raw_print,
                                    int H, int W);
};

// Compute a simple hash of the config for change detection
uint32_t hash_config(const PipelineConfig& cfg);

} // namespace spektrafilm
