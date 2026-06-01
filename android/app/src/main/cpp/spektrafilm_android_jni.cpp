#include <jni.h>

#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <android/log.h>

#ifdef SPEKTRAFILM_HAS_HALIDE_AOT
#include "spektrafilm_pipeline.h"
#include "spektrafilm_params.h"
#include "HalideRuntime.h"
#endif

#define LOG_TAG "SpektrafilmJNI"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

namespace {
constexpr jint kOk = 0;
constexpr jint kNullBuffer = 1;
constexpr jint kInvalidCount = 2;
constexpr jint kCapacityTooSmall = 3;
constexpr jint kNotInitialized = 4;
constexpr jint kPipelineError = 5;
}  // namespace

extern "C" JNIEXPORT jstring JNICALL
Java_com_spektrafilm_android_processing_NativeBridge_nativeVersion(JNIEnv* env, jobject /* thiz */) {
#ifdef SPEKTRAFILM_HAS_HALIDE_AOT
    return env->NewStringUTF("spektrafilm-android-jni-0.3.0-profiles");
#else
    return env->NewStringUTF("spektrafilm-android-jni-0.1.0-diagnostic");
#endif
}

extern "C" JNIEXPORT jint JNICALL
Java_com_spektrafilm_android_processing_NativeBridge_nativeSelfTest(JNIEnv* /* env */, jobject /* thiz */) {
    static_assert(sizeof(float) == 4, "Spektrafilm Android bridge expects IEEE-754 float32");
    return kOk;
}

extern "C" JNIEXPORT jint JNICALL
Java_com_spektrafilm_android_processing_NativeBridge_nativeScaleRgbDirect(
    JNIEnv* env,
    jobject /* thiz */,
    jobject input,
    jobject output,
    jint float_count,
    jfloat scale
) {
    if (float_count <= 0) return kInvalidCount;
    if (input == nullptr || output == nullptr) return kNullBuffer;

    auto* input_data = static_cast<float*>(env->GetDirectBufferAddress(input));
    auto* output_data = static_cast<float*>(env->GetDirectBufferAddress(output));
    if (input_data == nullptr || output_data == nullptr) return kNullBuffer;

    const jlong required_bytes = static_cast<jlong>(float_count) * static_cast<jlong>(sizeof(float));
    if (env->GetDirectBufferCapacity(input) < required_bytes ||
        env->GetDirectBufferCapacity(output) < required_bytes) {
        return kCapacityTooSmall;
    }

    for (jint i = 0; i < float_count; ++i) {
        output_data[i] = input_data[i] * scale;
    }
    return kOk;
}

#ifdef SPEKTRAFILM_HAS_HALIDE_AOT

namespace {
    // Custom Halide error handler — log instead of abort()
    void halide_error_handler(void* /*user_context*/, const char* msg) {
        LOGE("Halide error: %s", msg);
        // Don't abort — let the kernel return error code, caller handles fallback
    }

    struct HalideErrorInit {
        HalideErrorInit() { halide_set_error_handler(halide_error_handler); }
    } g_halide_error_init;

    spektrafilm::Pipeline g_pipeline;
    uint32_t g_config_hash = 0;
    float* g_hanatos_lut_data = nullptr;
    size_t g_hanatos_lut_size = 0;

    // Extract a single float from JSON by flat key search
    float extract_json_float(const char* json, size_t len, const char* key, float def) {
        if (json == nullptr || key == nullptr) return def;
        size_t klen = strlen(key);
        if (klen == 0 || len < klen) return def;
        for (size_t i = 0; i + klen <= len; i++) {
            if (memcmp(json + i, key, klen) == 0) {
                const char* p = json + i + klen;
                const char* end = json + len;
                while (p < end && *p != ':') p++;
                if (p >= end) return def;
                p++;
                while (p < end && (*p == ' ' || *p == '\t')) p++;
                const char* start = p;
                while (p < end && *p != ',' && *p != '}' && *p != ']' && *p != '\n') p++;
                const size_t token_len = static_cast<size_t>(p - start);
                if (token_len == 0 || token_len >= 64) return def;
                char token[64];
                memcpy(token, start, token_len);
                token[token_len] = '\0';
                return static_cast<float>(atof(token));
            }
        }
        return def;
    }

    bool extract_json_bool(const char* json, size_t len, const char* key, bool def) {
        if (json == nullptr || key == nullptr) return def;
        size_t klen = strlen(key);
        if (klen == 0 || len < klen) return def;
        for (size_t i = 0; i + klen <= len; i++) {
            if (memcmp(json + i, key, klen) == 0) {
                const char* p = json + i + klen;
                const char* end = json + len;
                while (p < end && *p != ':') p++;
                if (p >= end) return def;
                p++;
                while (p < end && (*p == ' ' || *p == '\t')) p++;
                if (p + 4 <= end && memcmp(p, "true", 4) == 0) return true;
                if (p + 5 <= end && memcmp(p, "false", 5) == 0) return false;
                return def;
            }
        }
        return def;
    }

    // Parse render settings from JSON (profile data comes from binary)
    void parse_render_settings(const char* json, size_t len, spektrafilm::RenderSettings& r) {
        r.exposure_comp_ev = extract_json_float(json, len, "exposureCompensationEv", 0.0f);
        r.lens_blur_um = extract_json_float(json, len, "lensBlurUm", 0.0f);
        r.film_format_mm = extract_json_float(json, len, "filmFormatMm", 35.0f);
        r.print_exposure = extract_json_float(json, len, "printExposure", 1.0f);
        r.normalize_print_exposure = extract_json_bool(json, len, "normalizePrintExposure", true);
        r.scanner_blur = extract_json_float(json, len, "lensBlur", 0.0f);
        r.unsharp_mask_amount = extract_json_float(json, len, "unsharpMaskAmount", 0.7f);
        r.unsharp_mask_radius = extract_json_float(json, len, "unsharpMaskRadius", 0.7f);
        r.scan_film = extract_json_bool(json, len, "scanFilm", false);
        r.output_cctf_encoding = extract_json_bool(json, len, "outputCctfEncoding", true);
        r.grain.active = extract_json_bool(json, len, "grainActive", true);
        r.halation.active = extract_json_bool(json, len, "halationActive", true);
        r.dir_couplers.active = extract_json_bool(json, len, "dirCouplersActive", true);
        r.glare.active = extract_json_bool(json, len, "glareActive", true);
    }

    // Load a binary profile into FilmProfileData
    // The binary data starts after a 16-byte header and matches the struct layout
    bool load_profile_bytes(const jbyte* bytes, jsize len, spektrafilm::FilmProfileData& profile) {
        if (bytes == nullptr || len <= 16) return false;

        // Verify magic
        uint32_t magic;
        memcpy(&magic, bytes, 4);
        if (magic != spektrafilm::kProfileMagic) {
            LOGE("Invalid profile magic: 0x%08x", magic);
            return false;
        }

        // Get data offset
        uint32_t offset;
        memcpy(&offset, bytes + 8, 4);

        const size_t total_len = static_cast<size_t>(len);
        if (offset < 16 || static_cast<size_t>(offset) > total_len) {
            LOGE("Invalid profile data offset: %u", offset);
            return false;
        }

        const char* data = reinterpret_cast<const char*>(bytes) + offset;
        size_t data_len = total_len - static_cast<size_t>(offset);
        size_t expected = sizeof(spektrafilm::FilmProfileData);

        if (data_len < expected) {
            LOGE("Profile data too small: %zu < %zu", data_len, expected);
            return false;
        }

        // Direct memcpy - struct layout matches binary format
        memcpy(&profile, data, expected);
        return true;
    }
} // anonymous namespace

extern "C" JNIEXPORT jint JNICALL
Java_com_spektrafilm_android_processing_NativeBridge_nativeProcessImage(
    JNIEnv* env,
    jobject /* thiz */,
    jobject inputBuffer,
    jobject outputBuffer,
    jint width,
    jint height,
    jbyteArray paramsJson,
    jbyteArray filmProfileBytes,
    jbyteArray printProfileBytes,
    jbyteArray hanatosLutBytes
) {
    if (inputBuffer == nullptr || outputBuffer == nullptr) return kNullBuffer;
    if (paramsJson == nullptr) return kInvalidCount;
    if (width <= 0 || height <= 0) return kInvalidCount;

    auto* input_data = static_cast<float*>(env->GetDirectBufferAddress(inputBuffer));
    auto* output_data = static_cast<float*>(env->GetDirectBufferAddress(outputBuffer));
    if (input_data == nullptr || output_data == nullptr) return kNullBuffer;

    const jlong required = static_cast<jlong>(width) * height * 3 * sizeof(float);
    if (env->GetDirectBufferCapacity(inputBuffer) < required ||
        env->GetDirectBufferCapacity(outputBuffer) < required) {
        return kCapacityTooSmall;
    }

    // Build config
    spektrafilm::PipelineConfig config;

    // Load film profile from binary
    if (filmProfileBytes != nullptr) {
        jbyte* bytes = env->GetByteArrayElements(filmProfileBytes, nullptr);
        if (bytes == nullptr) return kNullBuffer;
        jsize len = env->GetArrayLength(filmProfileBytes);
        bool ok = load_profile_bytes(bytes, len, config.film);
        env->ReleaseByteArrayElements(filmProfileBytes, bytes, JNI_ABORT);
        if (!ok) {
            LOGE("Failed to load film profile");
            return kPipelineError;
        }
        // Film profile also serves as print profile defaults
        config.print_profile = config.film;
    }

    // Load print profile (overrides film profile for print data)
    if (printProfileBytes != nullptr) {
        jbyte* bytes = env->GetByteArrayElements(printProfileBytes, nullptr);
        if (bytes == nullptr) return kNullBuffer;
        jsize len = env->GetArrayLength(printProfileBytes);
        spektrafilm::FilmProfileData print_data;
        if (load_profile_bytes(bytes, len, print_data)) {
            // Copy print-specific arrays
            memcpy(config.print_profile.log_sensitivity, print_data.log_sensitivity, sizeof(print_data.log_sensitivity));
            memcpy(config.print_profile.channel_density, print_data.channel_density, sizeof(print_data.channel_density));
            memcpy(config.print_profile.base_density, print_data.base_density, sizeof(print_data.base_density));
            memcpy(config.print_profile.log_exposure, print_data.log_exposure, sizeof(print_data.log_exposure));
            memcpy(config.print_profile.density_curves, print_data.density_curves, sizeof(print_data.density_curves));
        }
        env->ReleaseByteArrayElements(printProfileBytes, bytes, JNI_ABORT);
    }

    // Load Hanatos2025 LUT
    if (hanatosLutBytes != nullptr) {
        jsize lut_len = env->GetArrayLength(hanatosLutBytes);
        size_t expected_lut = spektrafilm::kHanatosLutSize * spektrafilm::kHanatosLutSize * spektrafilm::kNumWavelengths * sizeof(float);
        if (static_cast<size_t>(lut_len) >= expected_lut) {
            // Cache the LUT data
            if (g_hanatos_lut_data == nullptr || g_hanatos_lut_size != static_cast<size_t>(lut_len)) {
                delete[] g_hanatos_lut_data;
                g_hanatos_lut_data = new float[lut_len / sizeof(float)];
                g_hanatos_lut_size = lut_len;
            }
            jbyte* bytes = env->GetByteArrayElements(hanatosLutBytes, nullptr);
            if (bytes == nullptr) return kNullBuffer;
            memcpy(g_hanatos_lut_data, bytes, lut_len);
            env->ReleaseByteArrayElements(hanatosLutBytes, bytes, JNI_ABORT);
            config.hanatos_lut.data = g_hanatos_lut_data;
            config.hanatos_lut.size = spektrafilm::kHanatosLutSize;
        } else {
            LOGE("Hanatos LUT too small: %d < %zu", lut_len, expected_lut);
        }
    }

    // Parse render settings from JSON
    jbyte* json_bytes = env->GetByteArrayElements(paramsJson, nullptr);
    if (json_bytes == nullptr) return kNullBuffer;
    jsize json_len = env->GetArrayLength(paramsJson);
    parse_render_settings(reinterpret_cast<const char*>(json_bytes), json_len, config.render);
    env->ReleaseByteArrayElements(paramsJson, json_bytes, JNI_ABORT);

    // Configure pipeline
    uint32_t new_hash = spektrafilm::hash_config(config);
    if (new_hash != g_config_hash) {
        spektrafilm::init_pipeline_config(config);
        g_pipeline.configure(config);
        g_config_hash = new_hash;
        LOGI("Pipeline configured (hash=%u)", new_hash);
    }

    // Process
    LOGI("Processing %dx%d image...", width, height);
    int err = g_pipeline.process(input_data, output_data, width, height);
    LOGI("Pipeline returned %d", err);
    if (err != spektrafilm::kPipelineOk) {
        LOGE("Pipeline error: %d", err);
        return kPipelineError;
    }

    return kOk;
}

#else // !SPEKTRAFILM_HAS_HALIDE_AOT

extern "C" JNIEXPORT jint JNICALL
Java_com_spektrafilm_android_processing_NativeBridge_nativeProcessImage(
    JNIEnv* /* env */, jobject /* thiz */,
    jobject /* inputBuffer */, jobject /* outputBuffer */,
    jint /* width */, jint /* height */,
    jbyteArray /* paramsJson */,
    jbyteArray /* filmProfileBytes */,
    jbyteArray /* printProfileBytes */,
    jbyteArray /* hanatosLutBytes */
) {
    LOGE("nativeProcessImage called but Halide AOT not available");
    return kNotInitialized;
}

#endif // SPEKTRAFILM_HAS_HALIDE_AOT
