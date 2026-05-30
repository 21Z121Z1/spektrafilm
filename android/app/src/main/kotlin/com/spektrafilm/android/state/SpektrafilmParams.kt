package com.spektrafilm.android.state

import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

private val paramsJson = Json {
    encodeDefaults = true
    explicitNulls = false
}

@Serializable
data class SpektrafilmParams(
    val schemaVersion: Int = 1,
    val filmStock: String = "kodak_portra_400",
    val printPaper: String = "kodak_portra_endura",
    val camera: CameraParams = CameraParams(),
    val enlarger: EnlargerParams = EnlargerParams(),
    val scanner: ScannerParams = ScannerParams(),
    val io: IoParams = IoParams(),
    val render: RenderParams = RenderParams(),
    val settings: SettingsParams = SettingsParams(),
) {
    fun withExposureCompensation(value: Float): SpektrafilmParams {
        return copy(camera = camera.copy(exposureCompensationEv = value))
    }

    fun withPrintExposure(value: Float): SpektrafilmParams {
        return copy(enlarger = enlarger.copy(printExposure = value))
    }

    fun toJson(): String = paramsJson.encodeToString(this)

    fun toNativePayload(): ByteArray = toJson().toByteArray(Charsets.UTF_8)

    companion object {
        fun fromJson(json: String): SpektrafilmParams = paramsJson.decodeFromString(json)
    }
}

@Serializable
data class CameraParams(
    val exposureCompensationEv: Float = 0.0f,
    val autoExposure: Boolean = true,
    val autoExposureMethod: String = "scene_linear",
    val lensBlurUm: Float = 0.0f,
    val filmFormatMm: Float = 35.0f,
)

@Serializable
data class EnlargerParams(
    val illuminant: String = "TH-KG3",
    val printExposure: Float = 1.0f,
    val printExposureCompensation: Boolean = true,
    val normalizePrintExposure: Boolean = true,
    val yFilterShift: Float = 0.0f,
    val mFilterShift: Float = 0.0f,
    val yFilterNeutral: Float = 55.0f,
    val mFilterNeutral: Float = 65.0f,
    val cFilterNeutral: Float = 0.0f,
)

@Serializable
data class ScannerParams(
    val lensBlur: Float = 0.0f,
    val whiteCorrection: Boolean = false,
    val blackCorrection: Boolean = false,
    val whiteLevel: Float = 0.98f,
    val blackLevel: Float = 0.01f,
    val unsharpMaskAmount: Float = 0.7f,
    val unsharpMaskRadius: Float = 0.7f,
)

@Serializable
data class IoParams(
    val inputColorSpace: String = "ProPhoto RGB",
    val inputCctfDecoding: Boolean = false,
    val outputColorSpace: String = "sRGB",
    val outputCctfEncoding: Boolean = true,
    val outputClipMin: Boolean = true,
    val outputClipMax: Boolean = true,
    val crop: Boolean = false,
    val upscaleFactor: Float = 1.0f,
    val scanFilm: Boolean = false,
)

@Serializable
data class RenderParams(
    val grainActive: Boolean = true,
    val halationActive: Boolean = true,
    val dirCouplersActive: Boolean = true,
    val glareActive: Boolean = true,
)

@Serializable
data class SettingsParams(
    val computeBackend: String = "auto",
    val floatPrecision: String = "float32",
    val gpuPrecision: String = "float32",
    val rgbToRawMethod: String = "hanatos2025",
    val useEnlargerLut: Boolean = false,
    val useScannerLut: Boolean = false,
    val lutResolution: Int = 17,
    val useFastStats: Boolean = false,
    val previewMaxSize: Int = 640,
)
