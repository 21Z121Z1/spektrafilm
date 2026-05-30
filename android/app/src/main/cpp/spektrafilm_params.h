#pragma once

#include <cstring>
#include <cmath>
#include <vector>
#include <string>

namespace spektrafilm {

constexpr int kNumChannels = 3;
constexpr int kNumWavelengths = 81;
constexpr int kDensityCurveLen = 256;
constexpr int kHanatosLutSize = 192;

// Binary profile format version
constexpr uint32_t kProfileMagic = 0x53504631; // "SPF1"
constexpr uint32_t kProfileVersion = 1;

// Profile header for the binary .prof file
struct ProfileHeader {
    uint32_t magic;       // kProfileMagic
    uint32_t version;     // kProfileVersion
    uint32_t data_offset; // offset to data arrays from start of file
    uint32_t reserved;
};

// Film profile data - layout must match the binary .prof file (after header)
// All arrays are float32. The binary file stores them in this exact order.
struct FilmProfileData {
    // [81][3] - log10 sensitivity per wavelength per channel (Python shape [81,3])
    float log_sensitivity[kNumWavelengths][kNumChannels] = {};
    // [81][3] - spectral channel density per wavelength per channel
    float channel_density[kNumWavelengths][kNumChannels] = {};
    // [81] - base density per wavelength (spectral)
    float base_density[kNumWavelengths] = {};
    // [256] - log exposure axis for characteristic curves
    float log_exposure[kDensityCurveLen] = {};
    // [256][3] - density curves per exposure per channel
    float density_curves[kDensityCurveLen][kNumChannels] = {};
    // [81][3] - CIE 1931 2° CMFS
    float cmfs[kNumWavelengths][kNumChannels] = {};
    // [81] - scene illuminant spectrum
    float illuminant[kNumWavelengths] = {};
    // [81] - scanner illuminant spectrum
    float scan_illuminant[kNumWavelengths] = {};
    // [81] - enlarger illuminant spectrum
    float enlarger_illuminant[kNumWavelengths] = {};
    // [81][3] - Mallett2019 basis functions (for spectral upsampling)
    float basis_functions[kNumWavelengths][kNumChannels] = {};
    // [81] - basis illuminant (illuminant * basis, pre-multiplied)
    float basis_illuminant[kNumWavelengths][kNumChannels] = {};
    // [3][3] - RGB to XYZ matrix
    float rgb_to_xyz[3][3] = {};
    // [3][3] - XYZ to RGB matrix
    float xyz_to_rgb[3][3] = {};
    // [3][3] - ProPhoto RGB to XYZ matrix
    float prophoto_to_xyz[3][3] = {};
    // sRGB CCTF parameters
    float cctf_gamma = 2.4f;
    float cctf_threshold = 0.0031308f;
    float cctf_linear_slope = 12.92f;
    float cctf_alpha = 1.055f;

    // Total size: ~12KB (without Hanatos LUT)
};

// The Hanatos2025 LUT is stored separately (192*192*81*4 = ~11.4MB)
// It's loaded once and shared across all profiles
struct HanatosLut {
    const float* data = nullptr; // [192][192][81] float32
    int size = 0;                // 192
    bool owned = false;          // true if we allocated the memory

    void free() {
        if (owned && data) {
            delete[] data;
            data = nullptr;
        }
    }
};

struct RenderSettings {
    float exposure_comp_ev = 0.0f;
    float lens_blur_um = 0.0f;
    float film_format_mm = 35.0f;
    float print_exposure = 1.0f;
    bool normalize_print_exposure = true;
    float scanner_blur = 0.0f;
    float unsharp_mask_amount = 0.7f;
    float unsharp_mask_radius = 0.7f;
    bool scan_film = false;
    bool output_cctf_encoding = true;
    float density_curve_gamma = 1.0f;

    struct Halation {
        bool active = false;
        float scatter_amount = 0.0f;
        float scatter_spatial_scale = 1.0f;
        float scatter_core_um = 0.0f;
        float scatter_tail_um = 0.0f;
        float scatter_tail_weight[3] = {};
        float halation_amount = 0.0f;
        float halation_spatial_scale = 1.0f;
        float halation_strength[3] = {};
        float halation_first_sigma_um = 0.0f;
        int halation_n_bounces = 0;
        float halation_bounce_decay = 0.0f;
        bool halation_renormalize = false;
        float boost_ev = 0.0f;
        float boost_range = 0.0f;
        float protect_ev = 0.0f;
    } halation;

    struct Grain {
        bool active = false;
        float agx_particle_area_um2 = 0.0f;
        float agx_particle_scale[3] = {1.0f, 0.8f, 3.0f};
        float density_min[3] = {0.03f, 0.06f, 0.04f};
        float grain_uniformity[3] = {0.98f, 0.98f, 0.98f};
        float grain_blur = 1.0f;
        int n_sub_layers = 1;
    } grain;

    struct DirCouplers {
        bool active = false;
        float amount = 0.0f;
        float gamma_samelayer[3] = {};
        float gamma_interlayer[3][3] = {};
        float diffusion_size_um = 0.0f;
        float diffusion_tail_um = 0.0f;
        float tail_weight = 0.0f;
    } dir_couplers;

    struct DiffusionFilter {
        bool active = false;
        float strength = 0.0f;
        float spatial_scale = 1.0f;
        float halo_warmth = 0.0f;
    } diffusion_filter;

    float print_density_curve_gamma = 1.0f;

    struct Glare {
        bool active = false;
        float amount = 0.0f;
        float sigma = 0.0f;
    } glare;
};

struct PipelineConfig {
    FilmProfileData film;
    FilmProfileData print_profile; // print paper profile data
    HanatosLut hanatos_lut;
    RenderSettings render;

    // Computed at init
    float sensitivity[81][3] = {};
    float print_sensitivity[81][3] = {};
    float density_curves_normalized[256][3] = {};
    float print_density_curves_normalized[256][3] = {};
    float density_max[3] = {};
    float print_density_max[3] = {};
    float xyz_normalization = 1.0f;
    float print_xyz_normalization = 1.0f;

    // Fused spectral tables (precomputed for scanning hot path)
    // illum_cmfs[w][s] = scan_illuminant[w] * cmfs[w][s]
    float illum_cmfs[81][3] = {};
    // print_illum_cmfs[w][s] = print_profile.scan_illuminant[w] * print_profile.cmfs[w][s]
    float print_illum_cmfs[81][3] = {};
    // enlarger_illum_sens[w][s] = enlarger_illuminant[w] * print_sensitivity[w][s]
    float enlarger_illum_sens[81][3] = {};
    // base_factor = 10^(-base_density[0]) for film
    float base_factor = 1.0f;
    // print_base_factor = 10^(-print_profile.base_density[0])
    float print_base_factor = 1.0f;
    // log2(10) for fast exp conversion
    static constexpr float kLog2_10 = 3.32192809489f;

    bool initialized = false;
};

// Compute normalization factor: sum(illuminant * cmfs[:, 1])
inline float compute_xyz_normalization(const float illuminant[81], const float cmfs[81][3]) {
    float sum = 0.0f;
    for (int k = 0; k < 81; k++) {
        sum += illuminant[k] * cmfs[k][1]; // Y channel
    }
    return sum;
}

// Pre-compute sensitivity from log sensitivity
inline void compute_sensitivity(const float log_sens[81][3], float out[81][3]) {
    for (int k = 0; k < 81; k++) {
        for (int c = 0; c < 3; c++) {
            float val = log_sens[k][c];
            if (std::isnan(val) || val < -20.0f) {
                out[k][c] = 0.0f;
            } else {
                out[k][c] = std::pow(10.0f, val);
            }
        }
    }
}

// Normalize density curves (subtract column minimum)
inline void normalize_density_curves(const float curves[256][3], float out[256][3], float max_out[3]) {
    float col_min[3] = {1e30f, 1e30f, 1e30f};
    for (int i = 0; i < 256; i++) {
        for (int c = 0; c < 3; c++) {
            if (!std::isnan(curves[i][c]) && curves[i][c] < col_min[c]) {
                col_min[c] = curves[i][c];
            }
        }
    }
    for (int c = 0; c < 3; c++) {
        max_out[c] = -1e30f;
    }
    for (int i = 0; i < 256; i++) {
        for (int c = 0; c < 3; c++) {
            out[i][c] = std::isnan(curves[i][c]) ? 0.0f : curves[i][c] - col_min[c];
            if (out[i][c] > max_out[c]) max_out[c] = out[i][c];
        }
    }
}

inline void init_pipeline_config(PipelineConfig& cfg) {
    compute_sensitivity(cfg.film.log_sensitivity, cfg.sensitivity);
    compute_sensitivity(cfg.print_profile.log_sensitivity, cfg.print_sensitivity);
    normalize_density_curves(cfg.film.density_curves, cfg.density_curves_normalized, cfg.density_max);
    normalize_density_curves(cfg.print_profile.density_curves, cfg.print_density_curves_normalized, cfg.print_density_max);
    cfg.xyz_normalization = compute_xyz_normalization(cfg.film.scan_illuminant, cfg.film.cmfs);
    cfg.print_xyz_normalization = compute_xyz_normalization(cfg.print_profile.scan_illuminant, cfg.print_profile.cmfs);

    // Precompute fused spectral tables for scanning hot path
    for (int w = 0; w < 81; w++) {
        for (int s = 0; s < 3; s++) {
            cfg.illum_cmfs[w][s] = cfg.film.scan_illuminant[w] * cfg.film.cmfs[w][s];
            cfg.print_illum_cmfs[w][s] = cfg.print_profile.scan_illuminant[w] * cfg.print_profile.cmfs[w][s];
            cfg.enlarger_illum_sens[w][s] = cfg.film.enlarger_illuminant[w] * cfg.print_sensitivity[w][s];
        }
    }
    cfg.base_factor = std::pow(10.0f, -cfg.film.base_density[0]);
    cfg.print_base_factor = std::pow(10.0f, -cfg.print_profile.base_density[0]);

    cfg.initialized = true;
}

} // namespace spektrafilm
