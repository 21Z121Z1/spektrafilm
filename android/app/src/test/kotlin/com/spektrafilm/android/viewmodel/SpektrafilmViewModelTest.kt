package com.spektrafilm.android.viewmodel

import com.spektrafilm.android.processing.DirectFloatImage
import com.spektrafilm.android.processing.ProcessingMode
import com.spektrafilm.android.processing.ProcessingProgress
import com.spektrafilm.android.processing.ProcessingRequest
import com.spektrafilm.android.processing.ProcessingResult
import com.spektrafilm.android.processing.ProcessorSelfTest
import com.spektrafilm.android.processing.SpektrafilmProcessor
import com.spektrafilm.android.state.SpektrafilmParams
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class SpektrafilmViewModelTest {
    private val dispatcher = StandardTestDispatcher()

    @get:Rule
    val mainDispatcherRule = MainDispatcherRule(dispatcher)

    @Test
    fun parameterEditsUpdateStateAndUndoRedo() = runTest(dispatcher) {
        val viewModel = SpektrafilmViewModel(
            processor = RecordingProcessor(),
            processingDispatcher = dispatcher,
            previewDebounceMillis = 25,
        )

        viewModel.setExposureCompensation(0.5f)
        viewModel.setPrintExposure(1.2f)

        assertEquals(0.5f, viewModel.uiState.value.params.camera.exposureCompensationEv)
        assertEquals(1.2f, viewModel.uiState.value.params.enlarger.printExposure)
        assertTrue(viewModel.uiState.value.canUndo)

        viewModel.undo()
        assertEquals(0.5f, viewModel.uiState.value.params.camera.exposureCompensationEv)
        assertEquals(1.0f, viewModel.uiState.value.params.enlarger.printExposure)

        viewModel.redo()
        assertEquals(1.2f, viewModel.uiState.value.params.enlarger.printExposure)
    }

    @Test
    fun previewProcessingIsDebouncedAndCancelsStaleWork() = runTest(dispatcher) {
        val processor = RecordingProcessor(delayMillis = 100)
        val viewModel = SpektrafilmViewModel(
            processor = processor,
            processingDispatcher = dispatcher,
            previewDebounceMillis = 50,
        )
        viewModel.setInputImage(DirectFloatImage.allocate(width = 2, height = 2, channels = 3))

        viewModel.setExposureCompensation(0.25f)
        advanceTimeBy(49)
        viewModel.setExposureCompensation(0.5f)
        advanceTimeBy(50)
        runCurrent()
        assertEquals(1, processor.started)

        viewModel.setExposureCompensation(0.75f)
        advanceTimeBy(50)
        runCurrent()
        assertEquals(2, processor.started)

        advanceTimeBy(100)
        runCurrent()
        assertEquals(1, processor.completed)
        assertEquals(0.75f, processor.lastParams.camera.exposureCompensationEv)
        assertTrue(viewModel.uiState.value.preview is PreviewState.Ready)
    }

    @Test
    fun selfTestFailureIsReportedInState() = runTest(dispatcher) {
        val viewModel = SpektrafilmViewModel(
            processor = FailingSelfTestProcessor(),
            processingDispatcher = dispatcher,
            previewDebounceMillis = 25,
        )

        runCurrent()

        val selfTest = viewModel.uiState.value.selfTest
        require(selfTest != null)
        assertFalse(selfTest.ok)
        assertEquals("spektrafilm_android", selfTest.processor)
        assertTrue(selfTest.details.single().contains("native self-test failed"))
    }

    private class RecordingProcessor(
        private val delayMillis: Long = 0,
    ) : SpektrafilmProcessor {
        var started = 0
        var completed = 0
        var lastParams = SpektrafilmParams()

        override suspend fun selfTest(): ProcessorSelfTest {
            return ProcessorSelfTest(ok = true, processor = "recording", version = "test")
        }

        override suspend fun process(
            request: ProcessingRequest,
            onProgress: (ProcessingProgress) -> Unit,
        ): ProcessingResult {
            require(request.mode == ProcessingMode.Preview)
            started += 1
            lastParams = request.params
            onProgress(ProcessingProgress(stage = "start", fraction = 0.1f))
            if (delayMillis > 0) {
                delay(delayMillis)
            }
            completed += 1
            onProgress(ProcessingProgress(stage = "done", fraction = 1.0f))
            return ProcessingResult(request.image, diagnostics = listOf("recording"))
        }
    }

    private class FailingSelfTestProcessor : SpektrafilmProcessor {
        override suspend fun selfTest(): ProcessorSelfTest {
            error("boom")
        }

        override suspend fun process(
            request: ProcessingRequest,
            onProgress: (ProcessingProgress) -> Unit,
        ): ProcessingResult {
            return ProcessingResult(request.image, diagnostics = emptyList())
        }
    }
}
