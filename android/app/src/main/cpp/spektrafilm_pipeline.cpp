#include "spektrafilm_pipeline.h"

#include <cmath>
#include <cstring>
#include <algorithm>
#include <random>
#include <android/log.h>

// Halide AOT headers
#include "density_to_light.h"
#include "light_to_raw.h"
#include "compute_density_spectral.h"
#include "gaussian_blur_fir.h"
#include "gaussian_blur_iir.h"
#include "cctf_encode.h"
#include "cctf_decode.h"
#include "highlight_boost.h"
#include "interp_1d.h"
#include "lut_2d_cubic.h"

#define LOG_TAG "SpektrafilmPipeline"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace spektrafilm {

// ============================================================================
// HalideBuffer implementation
// ============================================================================

HalideBuffer HalideBuffer::make_chw(float* host, int C, int H, int W) {
    HalideBuffer hb;
    hb.buf.dimensions = 3;
    hb.buf.type = halide_type_of<float>();
    hb.buf.host = reinterpret_cast<uint8_t*>(host);
    // dim[0] = C, dim[1] = H, dim[2] = W
    hb.dims[0] = {0, C, 1};        // stride=1 for channel
    hb.dims[1] = {0, H, C};        // stride=C for row
    hb.dims[2] = {0, W, C * H};    // stride=C*H for col
    hb.dims[3] = {0, 0, 0};        // unused
    hb.buf.dim = hb.dims;
    return hb;
}

HalideBuffer HalideBuffer::make_hw(float* host, int H, int W) {
    HalideBuffer hb;
    hb.buf.dimensions = 2;
    hb.buf.type = halide_type_of<float>();
    hb.buf.host = reinterpret_cast<uint8_t*>(host);
    hb.dims[0] = {0, H, 1};
    hb.dims[1] = {0, W, H};
    hb.dims[2] = {0, 0, 0};
    hb.dims[3] = {0, 0, 0};
    hb.buf.dim = hb.dims;
    return hb;
}

HalideBuffer HalideBuffer::make_1d(float* host, int N) {
    HalideBuffer hb;
    hb.buf.dimensions = 1;
    hb.buf.type = halide_type_of<float>();
    hb.buf.host = reinterpret_cast<uint8_t*>(host);
    hb.dims[0] = {0, N, 1};
    hb.dims[1] = {0, 0, 0};
    hb.dims[2] = {0, 0, 0};
    hb.dims[3] = {0, 0, 0};
    hb.buf.dim = hb.dims;
    return hb;
}

HalideBuffer HalideBuffer::make_2d(float* host, int N, int M) {
    HalideBuffer hb;
    hb.buf.dimensions = 2;
    hb.buf.type = halide_type_of<float>();
    hb.buf.host = reinterpret_cast<uint8_t*>(host);
    hb.dims[0] = {0, N, 1};
    hb.dims[1] = {0, M, N};
    hb.dims[2] = {0, 0, 0};
    hb.dims[3] = {0, 0, 0};
    hb.buf.dim = hb.dims;
    return hb;
}

HalideBuffer HalideBuffer::make_hwc(float* host, int H, int W, int C) {
    HalideBuffer hb;
    hb.buf.dimensions = 3;
    hb.buf.type = halide_type_of<float>();
    hb.buf.host = reinterpret_cast<uint8_t*>(host);
    hb.dims[0] = {0, H, 1};
    hb.dims[1] = {0, W, H};
    hb.dims[2] = {0, C, H * W};
    hb.dims[3] = {0, 0, 0};
    hb.buf.dim = hb.dims;
    return hb;
}

void HalideBuffer::free_host() {
    // We don't own the host memory (managed by vectors)
}

// ============================================================================
// PipelineBuffers
// ============================================================================

void PipelineBuffers::allocate(int w, int h) {
    width = w;
    height = h;
    capacity_pixels = w * h;
    size_t pix = static_cast<size_t>(w) * h;
    chw_a.resize(3 * pix);
    chw_b.resize(3 * pix);
    query_2d.resize(pix);
    query_hwc2.resize(pix * 2);
    grain_tmp.resize(3 * pix);
}

bool PipelineBuffers::needs_reallocation(int w, int h) const {
    return w != width || h != height;
}

// ============================================================================
// Pipeline
// ============================================================================

Pipeline::Pipeline() = default;
Pipeline::~Pipeline() = default;

int Pipeline::configure(const PipelineConfig& config) {
    config_ = config;
    if (!config_.initialized) {
        init_pipeline_config(config_);
    }
    config_hash_ = hash_config(config_);
    return kPipelineOk;
}

int Pipeline::process(const float* input, float* output, int width, int height) {
    if (!config_.initialized) return kPipelineNotInitialized;
    if (!input || !output) return kPipelineNullBuffer;
    if (width <= 0 || height <= 0) return kPipelineInvalidDimensions;

    if (buffers_.needs_reallocation(width, height)) {
        buffers_.allocate(width, height);
    }

    if (config_.render.scan_film) {
        return process_scan_film(input, output, width, height);
    } else {
        return process_print(input, output, width, height);
    }
}

// ============================================================================
// Utility functions
// ============================================================================

void Pipeline::hwc_to_chw(const float* hwc, float* chw, int H, int W) {
    for (int c = 0; c < 3; c++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                chw[c * H * W + y * W + x] = hwc[(y * W + x) * 3 + c];
            }
        }
    }
}

void Pipeline::chw_to_hwc(const float* chw, float* hwc, int H, int W) {
    for (int c = 0; c < 3; c++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                hwc[(y * W + x) * 3 + c] = chw[c * H * W + y * W + x];
            }
        }
    }
}

void Pipeline::apply_exposure_comp(float* raw, int H, int W, float ev) {
    if (ev == 0.0f) return;
    float factor = std::pow(2.0f, ev);
    size_t total = 3 * H * W;
    for (size_t i = 0; i < total; i++) {
        raw[i] *= factor;
    }
}

void Pipeline::apply_log_transform(const float* in, float* out, int total) {
    for (int i = 0; i < total; i++) {
        out[i] = std::log10(std::max(in[i], 0.0f) + 1e-10f);
    }
}

void Pipeline::apply_exp_transform(const float* in, float* out, int total) {
    for (int i = 0; i < total; i++) {
        out[i] = std::pow(10.0f, in[i]);
    }
}

void Pipeline::clamp_01(float* data, int total) {
    for (int i = 0; i < total; i++) {
        data[i] = std::max(0.0f, std::min(1.0f, data[i]));
    }
}

// ============================================================================
// Halide AOT kernel wrappers
// ============================================================================

void Pipeline::apply_gaussian_blur(float* data, int H, int W, float sigma_pixels) {
    if (sigma_pixels <= 0.0f) return;

    // Pure C++ separable Gaussian blur (Halide kernels have boundary bugs)
    int radius = static_cast<int>(std::ceil(sigma_pixels * 3.0f));
    if (radius < 1) radius = 1;
    int k_size = 2 * radius + 1;
    std::vector<float> kernel(k_size);
    float sum = 0.0f;
    for (int i = 0; i < k_size; i++) {
        float x = static_cast<float>(i - radius);
        kernel[i] = std::exp(-0.5f * x * x / (sigma_pixels * sigma_pixels));
        sum += kernel[i];
    }
    for (int i = 0; i < k_size; i++) kernel[i] /= sum;

    size_t pix = H * W;
    std::vector<float> tmp(3 * pix);

    // Horizontal pass
    for (int c = 0; c < 3; c++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float val = 0.0f;
                for (int k = -radius; k <= radius; k++) {
                    int sx = std::max(0, std::min(W - 1, x + k));
                    val += data[c * pix + y * W + sx] * kernel[k + radius];
                }
                tmp[c * pix + y * W + x] = val;
            }
        }
    }

    // Vertical pass
    for (int c = 0; c < 3; c++) {
        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float val = 0.0f;
                for (int k = -radius; k <= radius; k++) {
                    int sy = std::max(0, std::min(H - 1, y + k));
                    val += tmp[c * pix + sy * W + x] * kernel[k + radius];
                }
                data[c * pix + y * W + x] = val;
            }
        }
    }
}

void Pipeline::apply_gaussian_blur_fir(float* data, int H, int W, float sigma_pixels) {
    if (sigma_pixels <= 0.0f) return;
    int radius = static_cast<int>(std::ceil(sigma_pixels * 3.0f));
    int k_size = 2 * radius + 1;
    std::vector<float> kernel(k_size);
    float sum = 0.0f;
    for (int i = 0; i < k_size; i++) {
        float x = static_cast<float>(i - radius);
        kernel[i] = std::exp(-0.5f * x * x / (sigma_pixels * sigma_pixels));
        sum += kernel[i];
    }
    for (int i = 0; i < k_size; i++) kernel[i] /= sum;

    auto in_buf = HalideBuffer::make_chw(data, 3, H, W);
    auto kern_buf = HalideBuffer::make_1d(kernel.data(), k_size);
    auto out_buf = HalideBuffer::make_chw(buffers_.chw_b.data(), 3, H, W);
    int err = gaussian_blur_fir(&in_buf.buf, &kern_buf.buf, &out_buf.buf);
    if (err == 0) {
        std::memcpy(data, buffers_.chw_b.data(), 3 * H * W * sizeof(float));
    }
}

void Pipeline::apply_cctf_encode(float* data, int H, int W) {
    auto in_buf = HalideBuffer::make_chw(data, 3, H, W);
    auto out_buf = HalideBuffer::make_chw(buffers_.chw_b.data(), 3, H, W);
    int err = cctf_encode(&in_buf.buf,
                           config_.film.cctf_gamma,
                           config_.film.cctf_threshold,
                           config_.film.cctf_linear_slope,
                           config_.film.cctf_alpha,
                           &out_buf.buf);
    if (err == 0) {
        std::memcpy(data, buffers_.chw_b.data(), 3 * H * W * sizeof(float));
    }
}

void Pipeline::apply_cctf_decode(float* data, int H, int W) {
    auto in_buf = HalideBuffer::make_chw(data, 3, H, W);
    auto out_buf = HalideBuffer::make_chw(buffers_.chw_b.data(), 3, H, W);
    int err = cctf_decode(&in_buf.buf,
                           config_.film.cctf_gamma,
                           config_.film.cctf_threshold,
                           config_.film.cctf_linear_slope,
                           config_.film.cctf_alpha,
                           &out_buf.buf);
    if (err == 0) {
        std::memcpy(data, buffers_.chw_b.data(), 3 * H * W * sizeof(float));
    }
}

void Pipeline::apply_highlight_boost(float* data, int H, int W) {
    const auto& h = config_.render.halation;
    if (h.boost_ev == 0.0f) return;
    auto in_buf = HalideBuffer::make_chw(data, 3, H, W);
    auto out_buf = HalideBuffer::make_chw(buffers_.chw_b.data(), 3, H, W);
    int err = highlight_boost(&in_buf.buf, h.boost_ev, h.boost_range, h.protect_ev, &out_buf.buf);
    if (err == 0) {
        std::memcpy(data, buffers_.chw_b.data(), 3 * H * W * sizeof(float));
    }
}

// ============================================================================
// Spectral operations
// ============================================================================

namespace {
    // Bicubic interpolation (Mitchell-Netravali B=1/3, C=1/3) on a 2D LUT
    inline float mitchell_cubic(float t) {
        float at = std::abs(t);
        if (at < 1.0f) {
            return (12.0f - 9.0f * 1.0f/3.0f - 6.0f * 1.0f/3.0f) * at * at * at +
                   (-18.0f + 12.0f * 1.0f/3.0f + 6.0f * 1.0f/3.0f) * at * at +
                   (6.0f - 2.0f * 1.0f/3.0f);
        }
        if (at < 2.0f) {
            return (-1.0f * 1.0f/3.0f - 6.0f * 1.0f/3.0f) * at * at * at +
                   (6.0f * 1.0f/3.0f + 30.0f * 1.0f/3.0f) * at * at +
                   (-12.0f * 1.0f/3.0f - 48.0f * 1.0f/3.0f) * at +
                   (8.0f * 1.0f/3.0f + 24.0f * 1.0f/3.0f);
        }
        return 0.0f;
    }

    // Lookup a 2D LUT [size][size][81] at coordinates (u, v) in [0,1]
    // Returns spectrum[81]
    void lut_2d_lookup(const float* lut, int size, float u, float v, float* out_spectrum) {
        // Map to grid coordinates
        float gx = u * (size - 1);
        float gy = v * (size - 1);
        int ix = static_cast<int>(gx);
        int iy = static_cast<int>(gy);
        float fx = gx - ix;
        float fy = gy - iy;

        // Clamp to valid range
        ix = std::max(0, std::min(size - 1, ix));
        iy = std::max(0, std::min(size - 1, iy));

        // Bicubic: sample 4x4 neighborhood
        for (int w = 0; w < 81; w++) {
            float sum = 0;
            for (int dy = -1; dy <= 2; dy++) {
                float wy = mitchell_cubic(fy - dy);
                int sy = std::max(0, std::min(size - 1, iy + dy));
                for (int dx = -1; dx <= 2; dx++) {
                    float wx = mitchell_cubic(fx - dx);
                    int sx = std::max(0, std::min(size - 1, ix + dx));
                    float val = lut[(sy * size + sx) * 81 + w];
                    sum += val * wx * wy;
                }
            }
            out_spectrum[w] = sum;
        }
    }

    // Tri2quad: convert xy chromaticity to LUT grid coordinates
    inline void tri2quad(float x, float y, float& u, float& v) {
        // x, y are CIE xy chromaticity
        // tc = tri2quad: y_coord = y / (1 - x), x_coord = (1-x)^2
        float denom = std::max(1.0f - x, 1e-10f);
        float ty = y / denom;
        float tx = (1.0f - x) * (1.0f - x);
        u = std::max(0.0f, std::min(1.0f, tx));
        v = std::max(0.0f, std::min(1.0f, ty));
    }
}

void Pipeline::rgb_to_film_raw(const float* rgb_chw, float* raw_chw, int H, int W) {
    // Hanatos2025 spectral upsampling:
    // 1. RGB -> XYZ (with rgb_to_xyz matrix)
    // 2. Per pixel: b = sum(XYZ), xy = X/b, Y/b
    // 3. tri2quad(xy) -> (u, v) in [0,1]
    // 4. LUT lookup at (u,v) -> spectrum[81]
    // 5. raw[c] = sum_w(spectrum[w] * sensitivity[w][c])
    // 6. raw *= b

    const auto& film = config_.film;
    size_t pix = H * W;

    // Step 1: RGB -> XYZ
    float* xyz = buffers_.chw_b.data();
    matrix_multiply_chw(rgb_chw, xyz, H, W, film.rgb_to_xyz);

    // Check if Hanatos LUT is available
    bool has_lut = (config_.hanatos_lut.data != nullptr && config_.hanatos_lut.size > 0);

    if (has_lut) {
        // Hanatos2025 path using Halide lut_2d_cubic kernel
        const float* lut_data = config_.hanatos_lut.data;
        int lut_size = config_.hanatos_lut.size;

        // Step 2: Compute tri2quad (u,v) coordinates for all pixels
        // Store as [W, H, 2] layout (matching Halide dim order: x, y, ch)
        size_t uv_count = pix * 2;
        std::vector<float> uv_buf(uv_count);
        for (size_t i = 0; i < pix; i++) {
            float X = xyz[0 * pix + i];
            float Y = xyz[1 * pix + i];
            float Z = xyz[2 * pix + i];
            float b = X + Y + Z;
            float b_inv = (b > 1e-10f) ? 1.0f / b : 0.0f;
            float cx = X * b_inv;
            float cy = Y * b_inv;
            float u, v;
            tri2quad(cx, cy, u, v);
            // Store in [x, y, 2] layout: uv_buf[x + y*W + ch*W*H]
            // But our loop iterates as i = y*W + x, so:
            size_t x_idx = i % W;
            size_t y_idx = i / W;
            uv_buf[x_idx + y_idx * W + 0 * pix] = u; // ch=0
            uv_buf[x_idx + y_idx * W + 1 * pix] = v; // ch=1
        }

        // Step 3: Set up Halide buffers and call lut_2d_cubic
        // LUT: [size, size, 81] — dim[0]=x, dim[1]=y, dim[2]=wavelength
        HalideBuffer lut_hb;
        lut_hb.buf.dimensions = 3;
        lut_hb.buf.type = halide_type_of<float>();
        lut_hb.buf.host = reinterpret_cast<uint8_t*>(const_cast<float*>(lut_data));
        lut_hb.dims[0] = {0, lut_size, 1};
        lut_hb.dims[1] = {0, lut_size, lut_size};
        lut_hb.dims[2] = {0, kNumWavelengths, lut_size * lut_size};
        lut_hb.buf.dim = lut_hb.dims;

        // Image: [W, H, 2] — dim[0]=x, dim[1]=y, dim[2]=uv
        HalideBuffer img_hb;
        img_hb.buf.dimensions = 3;
        img_hb.buf.type = halide_type_of<float>();
        img_hb.buf.host = reinterpret_cast<uint8_t*>(uv_buf.data());
        img_hb.dims[0] = {0, W, 1};
        img_hb.dims[1] = {0, H, W};
        img_hb.dims[2] = {0, 2, W * H};
        img_hb.buf.dim = img_hb.dims;

        // Output: [W, H, 81] — dim[0]=x, dim[1]=y, dim[2]=wavelength
        // Use grain_tmp as temporary storage (large enough for H*W*81 floats)
        size_t spectra_count = pix * kNumWavelengths;
        if (buffers_.grain_tmp.size() < spectra_count) {
            buffers_.grain_tmp.resize(spectra_count);
        }
        float* spectra = buffers_.grain_tmp.data();

        HalideBuffer out_hb;
        out_hb.buf.dimensions = 3;
        out_hb.buf.type = halide_type_of<float>();
        out_hb.buf.host = reinterpret_cast<uint8_t*>(spectra);
        out_hb.dims[0] = {0, W, 1};
        out_hb.dims[1] = {0, H, W};
        out_hb.dims[2] = {0, kNumWavelengths, W * H};
        out_hb.buf.dim = out_hb.dims;

        int err = lut_2d_cubic(&lut_hb.buf, &img_hb.buf, &out_hb.buf);

        if (err == 0) {
            // Step 4: raw[c] = sum_w(spectra[x,y,w] * sensitivity[w][c]) * b
            // spectra layout: [W, H, 81] = spectra[x + y*W + w*W*H]
            for (size_t i = 0; i < pix; i++) {
                float X = xyz[0 * pix + i];
                float Y = xyz[1 * pix + i];
                float Z = xyz[2 * pix + i];
                float b = X + Y + Z;

                size_t x_idx = i % W;
                size_t y_idx = i / W;

                for (int c = 0; c < 3; c++) {
                    float s = 0;
                    for (int w = 0; w < kNumWavelengths; w++) {
                        s += spectra[x_idx + y_idx * W + w * pix] * config_.sensitivity[w][c];
                    }
                    raw_chw[c * pix + i] = s * b;
                }
            }
        } else {
            // Fallback to per-pixel C++ if kernel fails
            for (size_t i = 0; i < pix; i++) {
                float X = xyz[0 * pix + i];
                float Y = xyz[1 * pix + i];
                float Z = xyz[2 * pix + i];
                float b = X + Y + Z;
                float b_inv = (b > 1e-10f) ? 1.0f / b : 0.0f;
                float cx = X * b_inv;
                float cy = Y * b_inv;
                float u, v;
                tri2quad(cx, cy, u, v);
                float spectrum[81];
                lut_2d_lookup(lut_data, lut_size, u, v, spectrum);
                for (int c = 0; c < 3; c++) {
                    float s = 0;
                    for (int w = 0; w < 81; w++) {
                        s += spectrum[w] * config_.sensitivity[w][c];
                    }
                    raw_chw[c * pix + i] = s * b;
                }
            }
        }
    } else {
        // Fallback: simple matrix path (no LUT)
        float sens_weighted[3] = {0};
        for (int k = 0; k < 81; k++) {
            for (int c = 0; c < 3; c++) {
                sens_weighted[c] += film.illuminant[k] * config_.sensitivity[k][c];
            }
        }
        float max_sens = std::max({sens_weighted[0], sens_weighted[1], sens_weighted[2]});
        if (max_sens > 0) {
            for (int c = 0; c < 3; c++) sens_weighted[c] /= max_sens;
        }
        for (int c = 0; c < 3; c++) {
            for (size_t i = 0; i < pix; i++) {
                raw_chw[c * pix + i] = xyz[c * pix + i] * sens_weighted[c];
            }
        }
    }
}

void Pipeline::matrix_multiply_chw(const float* in, float* out, int H, int W,
                                     const float M[3][3]) {
    size_t pix = H * W;
    for (size_t i = 0; i < pix; i++) {
        float r = in[0 * pix + i];
        float g = in[1 * pix + i];
        float b = in[2 * pix + i];
        out[0 * pix + i] = M[0][0] * r + M[0][1] * g + M[0][2] * b;
        out[1 * pix + i] = M[1][0] * r + M[1][1] * g + M[1][2] * b;
        out[2 * pix + i] = M[2][0] * r + M[2][1] * g + M[2][2] * b;
    }
}

void Pipeline::xyz_to_rgb_transform(const float* xyz, float* rgb, int H, int W,
                                      const float M[3][3]) {
    matrix_multiply_chw(xyz, rgb, H, W, M);
}

void Pipeline::interpolate_exposure_to_density(const float* log_raw, float* density,
                                                 int H, int W,
                                                 const float* log_exposure,
                                                 const float* density_curves,
                                                 int curve_len, float gamma_factor) {
    // For each channel, interpolate log_raw values against log_exposure/density_curves
    size_t pix = H * W;

    // Prepare positions buffer (log_exposure is the x-axis)
    auto pos_buf = HalideBuffer::make_1d(const_cast<float*>(log_exposure), curve_len);

    for (int c = 0; c < 3; c++) {
        // Extract density curve for this channel
        // density_curves is [curve_len][3], we need [curve_len] for channel c
        std::vector<float> values(curve_len);
        for (int i = 0; i < curve_len; i++) {
            values[i] = density_curves[i * 3 + c]; // assuming row-major [curve_len][3]
        }
        auto val_buf = HalideBuffer::make_1d(values.data(), curve_len);

        // Query buffer: log_raw for this channel [H, W]
        auto query_buf = HalideBuffer::make_hw(
            const_cast<float*>(log_raw + c * pix), H, W);
        auto out_buf = HalideBuffer::make_hw(density + c * pix, H, W);

        int err = interp_1d(&val_buf.buf, &pos_buf.buf, &query_buf.buf, &out_buf.buf);
        if (err != 0) {
            // Fallback: linear interpolation in C++
            float dx = log_exposure[1] - log_exposure[0];
            for (size_t i = 0; i < pix; i++) {
                float q = log_raw[c * pix + i];
                float idx_f = (q - log_exposure[0]) / dx;
                int idx = std::max(0, std::min(curve_len - 2, static_cast<int>(idx_f)));
                float frac = idx_f - idx;
                density[c * pix + i] = values[idx] * (1 - frac) + values[idx + 1] * frac;
            }
        }

        // Apply gamma factor
        if (gamma_factor != 1.0f) {
            for (size_t i = 0; i < pix; i++) {
                density[c * pix + i] = std::pow(density[c * pix + i], gamma_factor);
            }
        }
    }
}

void Pipeline::compute_density_spectral(const float* density_cmy_3ch, float* density_spectral,
                                          int H, int W_spectral,
                                          const float channel_density[81][3],
                                          const float base_density[3]) {
    // einsum('ijk, lk->ijl', density_cmy_3ch[3,H,W_spectral], channel_density[81,3])
    // density_cmy_3ch is [3, H, 3] for 3-channel CMY
    // Actually for the spectral path, we need [3, H, 81]
    // This is the compute_density_spectral Halide kernel

    // The Halide kernel expects:
    // density_cmy [3, H, 81] and channel_density [3, 81]
    // But our density_cmy is [3, H, 3] (3 CMY channels)
    // We need to expand: for each CMY channel c, for each wavelength w:
    //   density_spectral[c,y,w] = sum_k(density_cmy[c,y,k] * channel_density[w,k])

    // Actually this is the compute_density_spectral kernel which does exactly this einsum
    // density_cmy: [3, H, 3] (3 CMY channels, H rows, 3 cols)
    // channel_density: [3, 81] -> transposed to [81, 3]
    // output: [3, H, 81]

    // For the kernel call, we need density_cmy as [3, H, K] where K=3 (CMY)
    // and channel_density as [K, 81] where K=3

    // Transpose channel_density from [81][3] to [3][81] for the kernel
    float cd_transposed[3][81];
    for (int w = 0; w < 81; w++) {
        for (int k = 0; k < 3; k++) {
            cd_transposed[k][w] = channel_density[w][k];
        }
    }

    // density_cmy: [3, H, 3] -> kernel expects [3, H, K]
    // channel_density: [3, 81] -> kernel expects [K, 81]
    // output: [3, H, 81]

    auto density_buf = HalideBuffer::make_chw(const_cast<float*>(density_cmy_3ch), 3, H, 3);
    // Actually for the Halide kernel compute_density_spectral:
    // Input: density_cmy [3, H, K] where K is the number of CMY channels (3)
    // Input: channel_density [3, 81] -> but the kernel signature says [3, 81]
    // Output: [3, H, 81]

    // The kernel from the header:
    // int compute_density_spectral(halide_buffer_t* density_cmy, halide_buffer_t* channel_density, halide_buffer_t* output)
    // Generator: density_cmy(c, y, k), channel_density(w, k) -> output(c, y, w)
    // So density_cmy is [3, H, 3] and channel_density is [81, 3]

    auto cd_buf = HalideBuffer::make_2d(cd_transposed[0], 3, 81);
    // Wait, the kernel expects channel_density as [3, 81] but the generator code uses:
    // channel_density(w, k) which means dim[0]=w (81), dim[1]=k (3)
    // So it's [81, 3] in memory

    auto out_buf = HalideBuffer::make_chw(density_spectral, 3, H, 81);
    // Wait, output is [3, H, 81] but make_chw creates [C, H, W] with C=3, H=H, W=81

    // Actually the density_cmy input for the spectral computation is the 3-channel CMY density
    // But we're computing spectral density from 3 CMY channels, so:
    // density_cmy: [3, H, 3] means C=3 channels, H rows, 3 CMY values per pixel
    // This doesn't match the standard [3, H, W] layout

    // Let me re-think. The compute_density_spectral kernel from the generator:
    // density_cmy(c, y, k) where c=3 channels, y=H spatial, k=3 CMY
    // channel_density(w, k) where w=81 wavelengths, k=3 CMY
    // output(c, y, w) where c=3, y=H, w=81

    // So density_cmy is [3, H, 3] in CHW-like layout
    // And channel_density is [81, 3] (w-major)

    // For the Halide buffer:
    // density_cmy: dimensions = 3, extents = [3, H, 3], strides = [1, 3, 3*H]
    HalideBuffer density_hb;
    density_hb.buf.dimensions = 3;
    density_hb.buf.type = halide_type_of<float>();
    density_hb.buf.host = reinterpret_cast<uint8_t*>(const_cast<float*>(density_cmy_3ch));
    density_hb.dims[0] = {0, 3, 1};
    density_hb.dims[1] = {0, H, 3};
    density_hb.dims[2] = {0, 3, 3 * H};
    density_hb.dims[3] = {0, 0, 0};
    density_hb.buf.dim = density_hb.dims;

    // channel_density: [81, 3]
    HalideBuffer cd_hb;
    cd_hb.buf.dimensions = 2;
    cd_hb.buf.type = halide_type_of<float>();
    cd_hb.buf.host = reinterpret_cast<uint8_t*>(cd_transposed[0]);
    cd_hb.dims[0] = {0, 81, 1};
    cd_hb.dims[1] = {0, 3, 81};
    cd_hb.dims[2] = {0, 0, 0};
    cd_hb.dims[3] = {0, 0, 0};
    cd_hb.buf.dim = cd_hb.dims;

    // output: [3, H, 81]
    HalideBuffer out_hb;
    out_hb.buf.dimensions = 3;
    out_hb.buf.type = halide_type_of<float>();
    out_hb.buf.host = reinterpret_cast<uint8_t*>(density_spectral);
    out_hb.dims[0] = {0, 3, 1};
    out_hb.dims[1] = {0, H, 3};
    out_hb.dims[2] = {0, 81, 3 * H};
    out_hb.dims[3] = {0, 0, 0};
    out_hb.buf.dim = out_hb.dims;

    int err = ::compute_density_spectral(&density_hb.buf, &cd_hb.buf, &out_hb.buf);
    if (err != 0) {
        // Fallback: manual einsum
        for (int c = 0; c < 3; c++) {
            for (int y = 0; y < H; y++) {
                for (int w = 0; w < 81; w++) {
                    float sum = 0;
                    for (int k = 0; k < 3; k++) {
                        sum += density_cmy_3ch[c * H * 3 + y * 3 + k] * cd_transposed[k][w];
                    }
                    density_spectral[c * H * 81 + y * 81 + w] = sum;
                }
            }
        }
    }

    // Add base density
    if (base_density) {
        for (int c = 0; c < 3; c++) {
            for (int y = 0; y < H; y++) {
                for (int w = 0; w < 81; w++) {
                    density_spectral[c * H * 81 + y * 81 + w] += base_density[c];
                }
            }
        }
    }
}

void Pipeline::density_to_light(const float* density_spectral, float* light,
                                  int H, int W_spectral,
                                  const float illuminant[81]) {
    // light = 10^(-density_spectral) * illuminant
    // density_spectral: [3, H, 81]
    // illuminant: [81]
    // light: [3, H, 81]

    auto dens_buf = HalideBuffer::make_chw(const_cast<float*>(density_spectral), 3, H, 81);
    // illuminant: [81, 3] in the generator, but we have [81]
    // The generator: density[3,H,81], illuminant[81,3] -> output[3,H,81]
    // illuminant[w, c] means for each wavelength w, 3 channel values
    // But our illuminant is just [81] (single value per wavelength)
    // We need to expand to [81, 3] with the same value for all channels

    float illum_expanded[81 * 3];
    for (int w = 0; w < 81; w++) {
        for (int c = 0; c < 3; c++) {
            illum_expanded[w * 3 + c] = illuminant[w];
        }
    }
    auto illum_buf = HalideBuffer::make_2d(illum_expanded, 81, 3);
    auto out_buf = HalideBuffer::make_chw(light, 3, H, 81);

    int err = ::density_to_light(&dens_buf.buf, &illum_buf.buf, &out_buf.buf);
    if (err != 0) {
        // Fallback
        for (int c = 0; c < 3; c++) {
            for (int y = 0; y < H; y++) {
                for (int w = 0; w < 81; w++) {
                    float d = density_spectral[c * H * 81 + y * 81 + w];
                    light[c * H * 81 + y * 81 + w] = std::pow(10.0f, -d) * illuminant[w];
                }
            }
        }
    }
}

void Pipeline::light_to_raw(const float* light, float* raw,
                              int H, int W_spectral,
                              const float sensitivity[81][3]) {
    // einsum('ijk, kl->ijl', light[3,H,81], sensitivity[81,3])
    // -> raw[3, H, 3]

    auto light_buf = HalideBuffer::make_chw(const_cast<float*>(light), 3, H, 81);
    auto sens_buf = HalideBuffer::make_2d(const_cast<float*>(sensitivity[0]), 81, 3);
    auto out_buf = HalideBuffer::make_chw(raw, 3, H, 3);

    int err = ::light_to_raw(&light_buf.buf, &sens_buf.buf, &out_buf.buf);
    if (err != 0) {
        // Fallback
        for (int c = 0; c < 3; c++) {
            for (int y = 0; y < H; y++) {
                for (int s = 0; s < 3; s++) {
                    float sum = 0;
                    for (int k = 0; k < 81; k++) {
                        sum += light[c * H * 81 + y * 81 + k] * sensitivity[k][s];
                    }
                    raw[c * H * 3 + y * 3 + s] = sum;
                }
            }
        }
    }
}

// ============================================================================
// Complex effects
// ============================================================================

void Pipeline::apply_halation(float* raw, int H, int W, float pixel_size_um) {
    const auto& hal = config_.render.halation;
    if (!hal.active) return;

    size_t pix = H * W;
    float* tmp_a = buffers_.chw_a.data();
    float* tmp_b = buffers_.chw_b.data();

    // --- Pass 1: Scatter ---
    if (hal.scatter_amount > 0) {
        float s_scale = hal.scatter_spatial_scale;
        float s_amount = hal.scatter_amount;

        for (int c = 0; c < 3; c++) {
            float sigma_c = hal.scatter_core_um * s_scale / pixel_size_um;
            float lambda_t = hal.scatter_tail_um * s_scale / pixel_size_um;
            float w_s = hal.scatter_tail_weight[c];

            // Extract channel c
            float* ch_data = raw + c * pix;
            std::memcpy(tmp_a, ch_data, pix * sizeof(float));

            // Gaussian core
            if (sigma_c > 0.01f) {
                // Use IIR blur on single channel
                auto in_buf = HalideBuffer::make_hw(tmp_a, H, W);
                auto out_buf = HalideBuffer::make_hw(tmp_b, H, W);
                // gaussian_blur_iir expects [3,H,W], so we use a 3-channel buffer
                // and just blur channel c. For simplicity, blur all 3 at once.
                // Actually, let's just blur the full 3-channel buffer
            }

            // For simplicity, apply scatter as a weighted blend with blurred version
            // Using the full 3-channel blur
        }

        // Copy raw to tmp_a for blending
        std::memcpy(tmp_a, raw, 3 * pix * sizeof(float));

        // Blur for core
        float sigma_c_max = hal.scatter_core_um * hal.scatter_spatial_scale / pixel_size_um;
        if (sigma_c_max > 0.01f) {
            std::memcpy(tmp_b, raw, 3 * pix * sizeof(float));
            apply_gaussian_blur(tmp_b, H, W, sigma_c_max);
        } else {
            std::memcpy(tmp_b, raw, 3 * pix * sizeof(float));
        }

        // Blur for tail (approximate exponential with Gaussian)
        float lambda_t_max = hal.scatter_tail_um * hal.scatter_spatial_scale / pixel_size_um;
        float* tail_buf = buffers_.grain_tmp.data();
        if (lambda_t_max > 0.01f) {
            std::memcpy(tail_buf, raw, 3 * pix * sizeof(float));
            // Exponential filter approx: Gaussian with sigma = lambda * sqrt(2)
            apply_gaussian_blur(tail_buf, H, W, lambda_t_max * 1.414f);
        } else {
            std::memcpy(tail_buf, raw, 3 * pix * sizeof(float));
        }

        // Blend: scattered = (1-w_s)*core + w_s*tail per channel
        // Then: raw = (1-s)*raw + s*scattered
        for (int c = 0; c < 3; c++) {
            float w_s = hal.scatter_tail_weight[c];
            for (size_t i = 0; i < pix; i++) {
                size_t idx = c * pix + i;
                float core = tmp_b[idx];
                float tail = tail_buf[idx];
                float scattered = (1.0f - w_s) * core + w_s * tail;
                raw[idx] = (1.0f - s_amount) * raw[idx] + s_amount * scattered;
            }
        }
    }

    // --- Pass 2: Halation (multi-bounce) ---
    if (hal.halation_n_bounces >= 1) {
        int N = hal.halation_n_bounces;
        float rho = hal.halation_bounce_decay;
        float sigma_h = hal.halation_first_sigma_um * hal.halation_spatial_scale / pixel_size_um;

        if (sigma_h > 0.01f) {
            // Compute decay weights
            std::vector<float> decay(N);
            float decay_sum = 0;
            for (int k = 0; k < N; k++) {
                decay[k] = std::pow(rho, static_cast<float>(k));
                decay_sum += decay[k];
            }
            for (int k = 0; k < N; k++) decay[k] /= decay_sum;

            // Accumulate weighted Gaussian blurs
            std::fill(tmp_a, tmp_a + 3 * pix, 0.0f);
            for (int k = 0; k < N; k++) {
                float sigma_k = sigma_h * std::sqrt(static_cast<float>(k + 1));
                std::memcpy(tmp_b, raw, 3 * pix * sizeof(float));
                apply_gaussian_blur(tmp_b, H, W, sigma_k);
                for (size_t i = 0; i < 3 * pix; i++) {
                    tmp_a[i] += decay[k] * tmp_b[i];
                }
            }

            // Apply halation: raw += a_tot * halation_blur
            for (int c = 0; c < 3; c++) {
                float a_tot = hal.halation_strength[c] * hal.halation_amount;
                for (size_t i = 0; i < pix; i++) {
                    raw[c * pix + i] += a_tot * tmp_a[c * pix + i];
                }
            }

            // Renormalize
            if (hal.halation_renormalize) {
                for (int c = 0; c < 3; c++) {
                    float a_tot = hal.halation_strength[c] * hal.halation_amount;
                    float factor = 1.0f / (1.0f + a_tot);
                    for (size_t i = 0; i < pix; i++) {
                        raw[c * pix + i] *= factor;
                    }
                }
            }
        }
    }
}

void Pipeline::apply_grain(float* density_cmy, int H, int W, float pixel_size_um) {
    const auto& gr = config_.render.grain;
    if (!gr.active) return;

    size_t pix = H * W;
    float pixel_area = pixel_size_um * pixel_size_um;

    // Compute density_max from curves
    float density_max_val[3];
    for (int c = 0; c < 3; c++) {
        density_max_val[c] = config_.density_max[c] + gr.density_min[c];
    }

    // Compute n_particles_per_pixel per channel
    float n_particles[3];
    for (int c = 0; c < 3; c++) {
        float area_c = gr.agx_particle_area_um2 * gr.agx_particle_scale[c];
        n_particles[c] = (area_c > 0) ? pixel_area / area_c : 0;
        if (gr.n_sub_layers > 1) n_particles[c] /= gr.n_sub_layers;
    }

    // Add base fog
    for (int c = 0; c < 3; c++) {
        for (size_t i = 0; i < pix; i++) {
            density_cmy[c * pix + i] += gr.density_min[c];
        }
    }

    // Grain simulation per channel
    std::vector<float> grain_out(3 * pix, 0.0f);
    std::mt19937 rng(42); // fixed seed for determinism

    for (int c = 0; c < 3; c++) {
        float od_particle = density_max_val[c] / std::max(n_particles[c], 1.0f);

        for (int sl = 0; sl < gr.n_sub_layers; sl++) {
            for (size_t i = 0; i < pix; i++) {
                float density = density_cmy[c * pix + i];
                float p_dev = density / density_max_val[c];
                p_dev = std::max(1e-6f, std::min(1.0f - 1e-6f, p_dev));

                float saturation = 1.0f - p_dev * gr.grain_uniformity[c] * (1.0f - 1e-6f);
                float lambda = n_particles[c] / std::max(saturation, 1e-6f);

                // Poisson sample
                std::poisson_distribution<int> poisson_dist(std::max(0.0, static_cast<double>(lambda)));
                int seeds = poisson_dist(rng);

                // Binomial sample
                std::binomial_distribution<int> binom_dist(seeds, static_cast<double>(p_dev));
                int developed = binom_dist(rng);

                float grain_val = static_cast<float>(developed) * od_particle * saturation;
                grain_out[c * pix + i] += grain_val;
            }
        }
    }

    // Average sublayers
    if (gr.n_sub_layers > 1) {
        float inv_layers = 1.0f / gr.n_sub_layers;
        for (size_t i = 0; i < 3 * pix; i++) {
            grain_out[i] *= inv_layers;
        }
    }

    // Copy result and remove base fog
    for (int c = 0; c < 3; c++) {
        for (size_t i = 0; i < pix; i++) {
            density_cmy[c * pix + i] = grain_out[c * pix + i] - gr.density_min[c];
        }
    }

    // Optional blur
    if (gr.grain_blur > 0.4f) {
        apply_gaussian_blur(density_cmy, H, W, gr.grain_blur);
    }
}

void Pipeline::apply_dir_couplers(float* density_cmy, const float* log_raw, int H, int W,
                                    float pixel_size_um) {
    const auto& dc = config_.render.dir_couplers;
    if (!dc.active) return;

    size_t pix = H * W;
    float* tmp = buffers_.grain_tmp.data();

    // Build coupler inhibition matrix (3x3)
    float couplers_matrix[3][3] = {};
    for (int i = 0; i < 3; i++) {
        couplers_matrix[i][i] = dc.gamma_samelayer[i] * dc.amount;
        for (int j = 0; j < 3; j++) {
            if (i != j) {
                couplers_matrix[i][j] = dc.gamma_interlayer[i][j] * dc.amount;
            }
        }
    }

    // Compute log_raw_correction = density_silver @ couplers_matrix
    // For negative film: density_silver = density_cmy
    for (int c = 0; c < 3; c++) {
        for (size_t i = 0; i < pix; i++) {
            float correction = 0;
            for (int k = 0; k < 3; k++) {
                correction += density_cmy[k * pix + i] * couplers_matrix[c][k];
            }
            tmp[c * pix + i] = correction;
        }
    }

    // Apply spatial diffusion (Gaussian + optional exponential tail)
    float diff_sigma = dc.diffusion_size_um / pixel_size_um;
    if (diff_sigma > 0.01f) {
        apply_gaussian_blur(tmp, H, W, diff_sigma);
    }

    // Apply correction: log_raw_corrected = log_raw - correction
    for (size_t i = 0; i < 3 * pix; i++) {
        tmp[i] = log_raw[i] - tmp[i];
    }

    // Re-interpolate corrected exposure through density curves
    interpolate_exposure_to_density(tmp, density_cmy, H, W,
                                     config_.film.log_exposure,
                                     &config_.film.density_curves[0][0],
                                     kDensityCurveLen,
                                     config_.render.density_curve_gamma);
}

void Pipeline::apply_diffusion_filter(float* data, int H, int W, float pixel_size_um) {
    const auto& df = config_.render.diffusion_filter;
    if (!df.active || df.strength <= 0) return;

    // Simplified: single Gaussian blur with energy-conserving blend
    // Full implementation would build per-channel PSF from core/halo/bloom groups
    float sigma_um = df.spatial_scale * 10.0f; // rough approximation
    float sigma_px = sigma_um / pixel_size_um;
    if (sigma_px < 0.5f) return;

    // Compute scatter fraction from strength (log2 interpolation)
    float breakpoints[] = {0.125f, 0.25f, 0.5f, 1.0f, 2.0f};
    float values[] = {0.10f, 0.20f, 0.35f, 0.55f, 0.75f};
    float p_s = 0.10f;
    for (int i = 0; i < 4; i++) {
        if (df.strength >= breakpoints[i] && df.strength < breakpoints[i + 1]) {
            float t = (df.strength - breakpoints[i]) / (breakpoints[i + 1] - breakpoints[i]);
            p_s = values[i] * (1 - t) + values[i + 1] * t;
        }
    }
    if (df.strength >= breakpoints[4]) p_s = values[4];
    p_s = std::min(0.99f, std::max(0.0f, p_s));

    // Blur
    size_t total = 3 * H * W;
    std::vector<float> blurred(total);
    std::memcpy(blurred.data(), data, total * sizeof(float));
    apply_gaussian_blur(blurred.data(), H, W, sigma_px);

    // Energy-conserving blend
    for (size_t i = 0; i < total; i++) {
        data[i] = (1.0f - p_s) * data[i] + p_s * blurred[i];
    }
}

void Pipeline::apply_unsharp_mask(float* data, int H, int W, float sigma, float amount) {
    if (sigma <= 0 || amount <= 0) return;
    size_t total = 3 * H * W;
    std::vector<float> blurred(total);
    std::memcpy(blurred.data(), data, total * sizeof(float));
    apply_gaussian_blur(blurred.data(), H, W, sigma);
    for (size_t i = 0; i < total; i++) {
        data[i] += amount * (data[i] - blurred[i]);
    }
}

void Pipeline::apply_glare(float* xyz, int H, int W) {
    const auto& gl = config_.render.glare;
    if (!gl.active || gl.amount <= 0) return;

    // Simplified: add blurred noise
    size_t pix = H * W;
    std::mt19937 rng(12345);
    std::normal_distribution<float> noise_dist(0.0f, gl.amount * 0.01f);

    std::vector<float> noise(3 * pix);
    for (size_t i = 0; i < 3 * pix; i++) {
        noise[i] = noise_dist(rng);
    }

    if (gl.sigma > 0) {
        apply_gaussian_blur(noise.data(), H, W, gl.sigma);
    }

    for (size_t i = 0; i < 3 * pix; i++) {
        xyz[i] = std::max(0.0f, xyz[i] + noise[i]);
    }
}

// ============================================================================
// Print path spectral computation
// ============================================================================

void Pipeline::film_cmy_to_print_log_raw(const float* cmy_density, float* log_raw_print,
                                           int H, int W) {
    // Per-pixel spectral: density_cmy[3] -> light[81] -> raw[3] -> log
    // Uses fused enlarger_illum_sens = enlarger_illuminant * print_sensitivity
    size_t pix = H * W;
    const float base_f = config_.base_factor;
    const auto& cd = config_.film.channel_density;
    const auto& eis = config_.enlarger_illum_sens;
    const float kL2I = PipelineConfig::kLog2_10;

    for (int y = 0; y < H; y++) {
        for (int x = 0; x < W; x++) {
            float d_cmy[3];
            for (int c = 0; c < 3; c++) d_cmy[c] = cmy_density[c * pix + y * W + x];

            // Fused: raw[s] = sum_w(exp2f(-sum_k(d_cmy[k]*cd[w][k]) * log2_10) * base_factor * enlarger_illum_sens[w][s])
            float raw[3] = {0, 0, 0};
            for (int w = 0; w < 81; w++) {
                float d = d_cmy[0] * cd[w][0] + d_cmy[1] * cd[w][1] + d_cmy[2] * cd[w][2];
                float l = exp2f(-d * kL2I) * base_f;
                raw[0] += l * eis[w][0];
                raw[1] += l * eis[w][1];
                raw[2] += l * eis[w][2];
            }

            for (int c = 0; c < 3; c++) {
                log_raw_print[c * pix + y * W + x] = log10f(std::max(raw[c], 0.0f) + 1e-10f);
            }
        }
    }
}

// ============================================================================
// Pipeline routes
// ============================================================================

int Pipeline::process_scan_film(const float* input, float* output, int W, int H) {
    size_t pix = H * W;
    size_t total = 3 * pix;

    // Debug: log input range
    float in_min = 1e30f, in_max = -1e30f;
    for (size_t i = 0; i < total; i++) {
        if (input[i] < in_min) in_min = input[i];
        if (input[i] > in_max) in_max = input[i];
    }
    LOGI("process_scan_film: input range [%f, %f], W=%d, H=%d", in_min, in_max, W, H);

    // Transpose input [H,W,3] -> [3,H,W]
    float* chw = buffers_.chw_a.data();
    hwc_to_chw(input, chw, H, W);

    // --- Filming Stage: expose ---

    // 1. Spectral upsampling (simplified: RGB -> raw)
    float* raw = buffers_.chw_b.data();
    rgb_to_film_raw(chw, raw, H, W);

    // 2. Exposure compensation
    apply_exposure_comp(raw, H, W, config_.render.exposure_comp_ev);

    // 3. Highlight boost
    apply_highlight_boost(raw, H, W);

    // 4. Diffusion filter
    float pixel_size_um = config_.render.film_format_mm * 1000.0f /
                           std::max(W, H);
    apply_diffusion_filter(raw, H, W, pixel_size_um);

    // 5. Camera lens blur
    if (config_.render.lens_blur_um > 0) {
        float sigma = config_.render.lens_blur_um / pixel_size_um;
        apply_gaussian_blur(raw, H, W, sigma);
    }

    // 6. Halation
    apply_halation(raw, H, W, pixel_size_um);

    // 7. Log transform
    float* log_raw = buffers_.chw_a.data();
    apply_log_transform(raw, log_raw, total);

    // --- Filming Stage: develop ---

    // 8. Interpolate exposure to density
    float* density = buffers_.chw_b.data();
    interpolate_exposure_to_density(log_raw, density, H, W,
                                     config_.film.log_exposure,
                                     &config_.density_curves_normalized[0][0],
                                     kDensityCurveLen,
                                     config_.render.density_curve_gamma);

    // 9. DIR couplers
    apply_dir_couplers(density, log_raw, H, W, pixel_size_um);

    // 10. Grain
    apply_grain(density, H, W, pixel_size_um);

    // --- Scanning Stage: scan (per-pixel spectral, fused tables) ---
    float* rgb_out = buffers_.chw_a.data();
    {
        const float norm = config_.xyz_normalization;
        const float base_f = config_.base_factor;
        const auto& cd = config_.film.channel_density;
        const auto& illum_cmfs = config_.illum_cmfs;
        const auto& xyz2rgb = config_.film.xyz_to_rgb;
        const float kL2I = PipelineConfig::kLog2_10;

        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float d_cmy[3];
                for (int c = 0; c < 3; c++) d_cmy[c] = density[c * pix + y * W + x];

                // Fused: xyz[s] = sum_w(exp2f(-sum_k(d_cmy[k]*cd[w][k]) * log2_10) * base_factor * illum_cmfs[w][s])
                float xyz[3] = {0, 0, 0};
                for (int w = 0; w < 81; w++) {
                    float d = d_cmy[0] * cd[w][0] + d_cmy[1] * cd[w][1] + d_cmy[2] * cd[w][2];
                    float l = exp2f(-d * kL2I) * base_f;
                    xyz[0] += l * illum_cmfs[w][0];
                    xyz[1] += l * illum_cmfs[w][1];
                    xyz[2] += l * illum_cmfs[w][2];
                }
                if (norm > 0) { xyz[0] /= norm; xyz[1] /= norm; xyz[2] /= norm; }

                // XYZ to RGB
                for (int c = 0; c < 3; c++) {
                    float val = xyz2rgb[c][0] * xyz[0] + xyz2rgb[c][1] * xyz[1] + xyz2rgb[c][2] * xyz[2];
                    rgb_out[c * pix + y * W + x] = val;
                }
            }
        }
    }

    // 13. Scanner blur + unsharp mask
    if (config_.render.scanner_blur > 0) {
        apply_gaussian_blur(rgb_out, H, W, config_.render.scanner_blur);
    }
    apply_unsharp_mask(rgb_out, H, W,
                        config_.render.unsharp_mask_radius,
                        config_.render.unsharp_mask_amount);

    // 14. CCTF encode
    if (config_.render.output_cctf_encoding) {
        apply_cctf_encode(rgb_out, H, W);
    }

    // 15. Clamp
    clamp_01(rgb_out, total);

    // Debug: log output range
    float out_min = 1e30f, out_max = -1e30f;
    for (size_t i = 0; i < total; i++) {
        if (rgb_out[i] < out_min) out_min = rgb_out[i];
        if (rgb_out[i] > out_max) out_max = rgb_out[i];
    }
    LOGI("process_scan_film: output range [%f, %f]", out_min, out_max);

    // Transpose back [3,H,W] -> [H,W,3]
    chw_to_hwc(rgb_out, output, H, W);

    return kPipelineOk;
}

int Pipeline::process_print(const float* input, float* output, int W, int H) {
    size_t pix = H * W;
    size_t total = 3 * pix;

    // Transpose input
    float* chw = buffers_.chw_a.data();
    hwc_to_chw(input, chw, H, W);

    float pixel_size_um = config_.render.film_format_mm * 1000.0f / std::max(W, H);

    // --- Filming Stage (same as scan_film) ---
    float* raw = buffers_.chw_b.data();
    rgb_to_film_raw(chw, raw, H, W);
    apply_exposure_comp(raw, H, W, config_.render.exposure_comp_ev);
    apply_highlight_boost(raw, H, W);
    apply_diffusion_filter(raw, H, W, pixel_size_um);
    if (config_.render.lens_blur_um > 0) {
        apply_gaussian_blur(raw, H, W, config_.render.lens_blur_um / pixel_size_um);
    }
    apply_halation(raw, H, W, pixel_size_um);

    float* log_raw = buffers_.chw_a.data();
    apply_log_transform(raw, log_raw, total);

    float* density = buffers_.chw_b.data();
    interpolate_exposure_to_density(log_raw, density, H, W,
                                     config_.film.log_exposure,
                                     &config_.density_curves_normalized[0][0],
                                     kDensityCurveLen,
                                     config_.render.density_curve_gamma);
    apply_dir_couplers(density, log_raw, H, W, pixel_size_um);
    apply_grain(density, H, W, pixel_size_um);

    // --- Printing Stage ---
    float* log_raw_print = buffers_.chw_a.data();
    film_cmy_to_print_log_raw(density, log_raw_print, H, W);

    // Convert to linear
    float* raw_print = buffers_.chw_b.data();
    apply_exp_transform(log_raw_print, raw_print, total);

    // Print exposure
    float print_exp = config_.render.print_exposure;
    for (size_t i = 0; i < total; i++) raw_print[i] *= print_exp;

    // Enlarger diffusion filter
    apply_diffusion_filter(raw_print, H, W, pixel_size_um);

    // Log transform
    apply_log_transform(raw_print, log_raw_print, total);

    // Print develop
    float* print_density = buffers_.chw_b.data();
    interpolate_exposure_to_density(log_raw_print, print_density, H, W,
                                     config_.print_profile.log_exposure,
                                     &config_.print_density_curves_normalized[0][0],
                                     kDensityCurveLen,
                                     config_.render.print_density_curve_gamma);

    // --- Scanning Stage (per-pixel spectral, fused tables, print profile) ---
    float* rgb_out = buffers_.chw_a.data();
    {
        const float norm = config_.print_xyz_normalization;
        const float base_f = config_.print_base_factor;
        const auto& cd = config_.print_profile.channel_density;
        const auto& illum_cmfs = config_.print_illum_cmfs;
        const auto& xyz2rgb = config_.print_profile.xyz_to_rgb;
        const float kL2I = PipelineConfig::kLog2_10;

        for (int y = 0; y < H; y++) {
            for (int x = 0; x < W; x++) {
                float d_cmy[3];
                for (int c = 0; c < 3; c++) d_cmy[c] = print_density[c * pix + y * W + x];

                float xyz[3] = {0, 0, 0};
                for (int w = 0; w < 81; w++) {
                    float d = d_cmy[0] * cd[w][0] + d_cmy[1] * cd[w][1] + d_cmy[2] * cd[w][2];
                    float l = exp2f(-d * kL2I) * base_f;
                    xyz[0] += l * illum_cmfs[w][0];
                    xyz[1] += l * illum_cmfs[w][1];
                    xyz[2] += l * illum_cmfs[w][2];
                }
                if (norm > 0) { xyz[0] /= norm; xyz[1] /= norm; xyz[2] /= norm; }

                for (int c = 0; c < 3; c++) {
                    float val = xyz2rgb[c][0] * xyz[0] + xyz2rgb[c][1] * xyz[1] + xyz2rgb[c][2] * xyz[2];
                    rgb_out[c * pix + y * W + x] = val;
                }
            }
        }
    }

    // Scanner blur + unsharp
    if (config_.render.scanner_blur > 0) {
        apply_gaussian_blur(rgb_out, H, W, config_.render.scanner_blur);
    }
    apply_unsharp_mask(rgb_out, H, W,
                        config_.render.unsharp_mask_radius,
                        config_.render.unsharp_mask_amount);

    // CCTF encode + clamp
    if (config_.render.output_cctf_encoding) {
        apply_cctf_encode(rgb_out, H, W);
    }
    clamp_01(rgb_out, total);

    chw_to_hwc(rgb_out, output, H, W);
    return kPipelineOk;
}

// ============================================================================
// Hash
// ============================================================================

uint32_t hash_config(const PipelineConfig& cfg) {
    uint32_t h = 0;
    const uint8_t* data = reinterpret_cast<const uint8_t*>(&cfg);
    // Hash just the key fields to detect changes
    for (size_t i = 0; i < sizeof(PipelineConfig); i++) {
        h = h * 31 + data[i];
    }
    return h;
}

} // namespace spektrafilm
