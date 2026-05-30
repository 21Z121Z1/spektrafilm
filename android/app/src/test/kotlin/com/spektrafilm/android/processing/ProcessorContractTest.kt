package com.spektrafilm.android.processing

import com.spektrafilm.android.state.SpektrafilmParams
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ProcessorContractTest {
    @Test
    fun directFloatImageAllocatesNativeOrderDirectBuffer() {
        val image = DirectFloatImage.allocate(width = 4, height = 3, channels = 3)

        assertTrue(image.buffer.isDirect)
        assertEquals(ByteOrder.nativeOrder(), image.buffer.order())
        assertEquals(4 * 3 * 3 * 4, image.buffer.capacity())
        assertEquals(36, image.floatCount)
        assertEquals(144, image.byteCount)
    }

    @Test(expected = IllegalArgumentException::class)
    fun directFloatImageRejectsHeapBuffers() {
        DirectFloatImage(
            width = 1,
            height = 1,
            channels = 3,
            buffer = ByteBuffer.allocate(12).order(ByteOrder.nativeOrder()),
        )
    }

    @Test(expected = IllegalArgumentException::class)
    fun directFloatImageRejectsDimensionsLargerThanByteBufferCanRepresent() {
        DirectFloatImage.allocate(width = Int.MAX_VALUE, height = 2, channels = 3)
    }

    @Test
    fun processorInterfaceSeparatesPreviewAndFullResolutionRequests() = runTest {
        val image = DirectFloatImage.allocate(width = 2, height = 2, channels = 3)
        val processor = RecordingProcessor()

        processor.process(
            ProcessingRequest(image, SpektrafilmParams(), ProcessingMode.Preview),
        )
        processor.process(
            ProcessingRequest(image, SpektrafilmParams(), ProcessingMode.FullResolution),
        )

        assertEquals(listOf(ProcessingMode.Preview, ProcessingMode.FullResolution), processor.modes)
    }

    private class RecordingProcessor : SpektrafilmProcessor {
        val modes = mutableListOf<ProcessingMode>()

        override suspend fun selfTest(): ProcessorSelfTest {
            return ProcessorSelfTest(ok = true, processor = "recording", version = "test")
        }

        override suspend fun process(
            request: ProcessingRequest,
            onProgress: (ProcessingProgress) -> Unit,
        ): ProcessingResult {
            modes += request.mode
            onProgress(ProcessingProgress(stage = "recording", fraction = 1.0f))
            return ProcessingResult(request.image, diagnostics = emptyList())
        }
    }
}
