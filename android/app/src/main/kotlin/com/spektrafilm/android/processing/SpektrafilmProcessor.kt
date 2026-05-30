package com.spektrafilm.android.processing

import com.spektrafilm.android.state.SpektrafilmParams
import java.nio.ByteBuffer
import java.nio.ByteOrder

data class DirectFloatImage(
    val width: Int,
    val height: Int,
    val channels: Int = 3,
    val buffer: ByteBuffer,
) {
    val floatCount: Int
    val byteCount: Int

    init {
        require(width > 0) { "width must be positive" }
        require(height > 0) { "height must be positive" }
        require(channels in 1..4) { "channels must be between 1 and 4" }
        floatCount = checkedFloatCount(width, height, channels)
        byteCount = checkedByteCount(floatCount)
        require(buffer.isDirect) { "image buffer must be a direct ByteBuffer" }
        require(buffer.order() == ByteOrder.nativeOrder()) {
            "image buffer byte order must be native order"
        }
        require(buffer.capacity() >= byteCount) {
            "image buffer capacity is smaller than width * height * channels * sizeof(float)"
        }
    }

    companion object {
        fun allocate(width: Int, height: Int, channels: Int = 3): DirectFloatImage {
            val floatCount = checkedFloatCount(width, height, channels)
            val byteCount = checkedByteCount(floatCount)
            val buffer = ByteBuffer
                .allocateDirect(byteCount)
                .order(ByteOrder.nativeOrder())
            return DirectFloatImage(width, height, channels, buffer)
        }

        private fun checkedFloatCount(width: Int, height: Int, channels: Int): Int {
            require(width > 0) { "width must be positive" }
            require(height > 0) { "height must be positive" }
            require(channels in 1..4) { "channels must be between 1 and 4" }

            val maxFloatCount = Int.MAX_VALUE / Float.SIZE_BYTES
            val maxPixels = maxFloatCount / channels
            val pixelCount = width.toLong() * height.toLong()
            require(pixelCount <= maxPixels.toLong()) {
                "image dimensions exceed supported direct ByteBuffer capacity"
            }
            return (pixelCount * channels.toLong()).toInt()
        }

        private fun checkedByteCount(floatCount: Int): Int {
            return Math.multiplyExact(floatCount, Float.SIZE_BYTES)
        }
    }
}

enum class ProcessingMode {
    Preview,
    FullResolution,
}

data class ProcessingRequest(
    val image: DirectFloatImage,
    val params: SpektrafilmParams,
    val mode: ProcessingMode,
)

data class ProcessingProgress(
    val stage: String,
    val fraction: Float,
) {
    init {
        require(fraction in 0.0f..1.0f) { "fraction must be in [0, 1]" }
    }
}

data class ProcessingResult(
    val image: DirectFloatImage,
    val diagnostics: List<String>,
)

data class ProcessorSelfTest(
    val ok: Boolean,
    val processor: String,
    val version: String,
    val details: List<String> = emptyList(),
)

class ProcessorUnavailableException(message: String, cause: Throwable? = null) :
    RuntimeException(message, cause)

interface SpektrafilmProcessor {
    suspend fun selfTest(): ProcessorSelfTest

    suspend fun process(
        request: ProcessingRequest,
        onProgress: (ProcessingProgress) -> Unit = {},
    ): ProcessingResult
}
