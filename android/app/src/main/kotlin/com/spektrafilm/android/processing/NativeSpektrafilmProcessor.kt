package com.spektrafilm.android.processing

import android.content.Context
import kotlinx.coroutines.ensureActive
import kotlin.coroutines.coroutineContext

class NativeSpektrafilmProcessor(private val context: Context) : SpektrafilmProcessor {
    override suspend fun selfTest(): ProcessorSelfTest {
        return NativeBridge.selfTest()
    }

    override suspend fun process(
        request: ProcessingRequest,
        onProgress: (ProcessingProgress) -> Unit,
    ): ProcessingResult {
        coroutineContext.ensureActive()
        NativeBridge.requireAvailable()
        require(request.image.channels == 3) {
            "native processor currently accepts RGB float32 images only"
        }

        onProgress(ProcessingProgress(stage = "native-processing", fraction = 0.1f))

        val output = DirectFloatImage.allocate(
            width = request.image.width,
            height = request.image.height,
            channels = request.image.channels,
        )

        // Load profile data
        val filmProfile = ProfileLoader.loadProfile(context, request.params.filmStock)
        val printProfile = ProfileLoader.loadProfile(context, request.params.printPaper)
        val hanatosLut = ProfileLoader.loadHanatosLut(context)

        val paramsJson = request.params.toNativePayload()
        val status = NativeBridge.processImage(
            input = request.image.buffer,
            output = output.buffer,
            width = request.image.width,
            height = request.image.height,
            paramsJson = paramsJson,
            filmProfileBytes = filmProfile,
            printProfileBytes = printProfile,
            hanatosLutBytes = hanatosLut,
        )

        if (status != 0) {
            // Fall back to diagnostic mode if pipeline not available
            if (status == 4) { // kNotInitialized
                val diagStatus = NativeBridge.scaleRgbDirect(
                    input = request.image.buffer,
                    output = output.buffer,
                    floatCount = request.image.floatCount,
                    scale = 1.0f,
                )
                if (diagStatus != 0) {
                    throw ProcessorUnavailableException(
                        "native diagnostic processor returned status $diagStatus"
                    )
                }
                coroutineContext.ensureActive()
                onProgress(ProcessingProgress(stage = "done", fraction = 1.0f))
                return ProcessingResult(
                    image = output,
                    diagnostics = listOf(
                        "native direct-buffer diagnostic completed",
                        "real Spektrafilm rendering is not available (Halide AOT not linked)",
                    ),
                )
            }
            throw ProcessorUnavailableException("native pipeline returned status $status")
        }

        coroutineContext.ensureActive()
        onProgress(ProcessingProgress(stage = "done", fraction = 1.0f))
        return ProcessingResult(
            image = output,
            diagnostics = listOf(
                "native Spektrafilm pipeline completed",
                "image: ${request.image.width}x${request.image.height}",
                "film: ${request.params.filmStock}",
                "mode: ${if (request.params.io.scanFilm) "scan_film" else "print"}",
            ),
        )
    }
}

internal object NativeBridge {
    private val loadFailure: Throwable? = runCatching {
        System.loadLibrary("spektrafilm_android")
    }.exceptionOrNull()

    fun requireAvailable() {
        val failure = loadFailure
        if (failure != null) {
            throw ProcessorUnavailableException(
                "libspektrafilm_android is unavailable; install the Android NDK and build native code",
                failure,
            )
        }
    }

    fun selfTest(): ProcessorSelfTest {
        val failure = loadFailure
        if (failure != null) {
            return ProcessorSelfTest(
                ok = false,
                processor = "spektrafilm_android_jni",
                version = "unavailable",
                details = listOf(
                    "native library load failed: ${failure.javaClass.simpleName}: ${failure.message}",
                    "this is a diagnostic native bridge, not a full Spektrafilm renderer",
                ),
            )
        }
        val status = nativeSelfTest()
        return ProcessorSelfTest(
            ok = status == 0,
            processor = "spektrafilm_android_jni",
            version = nativeVersion(),
            details = listOf(
                "native self-test status=$status",
            ),
        )
    }

    fun scaleRgbDirect(input: java.nio.ByteBuffer, output: java.nio.ByteBuffer, floatCount: Int, scale: Float): Int {
        requireAvailable()
        return nativeScaleRgbDirect(input, output, floatCount, scale)
    }

    fun processImage(
        input: java.nio.ByteBuffer,
        output: java.nio.ByteBuffer,
        width: Int,
        height: Int,
        paramsJson: ByteArray,
        filmProfileBytes: ByteArray?,
        printProfileBytes: ByteArray?,
        hanatosLutBytes: ByteArray?,
    ): Int {
        requireAvailable()
        return nativeProcessImage(
            input, output, width, height, paramsJson,
            filmProfileBytes ?: ByteArray(0),
            printProfileBytes ?: ByteArray(0),
            hanatosLutBytes ?: ByteArray(0),
        )
    }

    private external fun nativeVersion(): String
    private external fun nativeSelfTest(): Int
    private external fun nativeScaleRgbDirect(
        input: java.nio.ByteBuffer,
        output: java.nio.ByteBuffer,
        floatCount: Int,
        scale: Float,
    ): Int

    private external fun nativeProcessImage(
        input: java.nio.ByteBuffer,
        output: java.nio.ByteBuffer,
        width: Int,
        height: Int,
        paramsJson: ByteArray,
        filmProfileBytes: ByteArray,
        printProfileBytes: ByteArray,
        hanatosLutBytes: ByteArray,
    ): Int
}
