package com.spektrafilm.android.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.spektrafilm.android.processing.DirectFloatImage
import com.spektrafilm.android.processing.ProcessingMode
import com.spektrafilm.android.processing.ProcessingRequest
import com.spektrafilm.android.processing.ProcessorSelfTest
import com.spektrafilm.android.processing.SpektrafilmProcessor
import com.spektrafilm.android.state.EditHistory
import com.spektrafilm.android.state.SpektrafilmParams
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineDispatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.flatMapLatest
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@OptIn(FlowPreview::class, ExperimentalCoroutinesApi::class)
class SpektrafilmViewModel(
    private val processor: SpektrafilmProcessor,
    private val processingDispatcher: CoroutineDispatcher = Dispatchers.Default,
    private val previewDebounceMillis: Long = 150,
) : ViewModel() {
    private val history = EditHistory(SpektrafilmParams())
    private val inputImage = MutableStateFlow<DirectFloatImage?>(null)
    private val params = MutableStateFlow(history.current)
    private val _uiState = MutableStateFlow(SpektrafilmUiState())

    val uiState: StateFlow<SpektrafilmUiState> = _uiState.asStateFlow()

    init {
        viewModelScope.launch {
            val result = try {
                withContext(processingDispatcher) {
                    processor.selfTest()
                }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Throwable) {
                ProcessorSelfTest(
                    ok = false,
                    processor = "spektrafilm_android",
                    version = "unavailable",
                    details = listOf(
                        "native self-test failed: ${error.javaClass.simpleName}: ${error.message}",
                    ),
                )
            }
            _uiState.update { it.copy(selfTest = result) }
        }
        viewModelScope.launch {
            combine(inputImage, params) { image, currentParams -> image to currentParams }
                .debounce(previewDebounceMillis)
                .distinctUntilChanged()
                .flatMapLatest { (image, currentParams) ->
                    flow {
                        if (image == null) {
                            emit(PreviewState.Idle)
                            return@flow
                        }
                        emit(PreviewState.Processing)
                        val result = withContext(processingDispatcher) {
                            processor.process(
                                ProcessingRequest(image, currentParams, ProcessingMode.Preview),
                            )
                        }
                        emit(PreviewState.Ready(result.image, result.diagnostics))
                    }.catch { error ->
                        if (error is CancellationException) {
                            throw error
                        }
                        emit(PreviewState.Error(error.message ?: error.javaClass.simpleName))
                    }
                }
                .collect { preview ->
                    _uiState.update { it.copy(preview = preview) }
                }
        }
    }

    fun setInputImage(image: DirectFloatImage) {
        inputImage.value = image
        _uiState.update { it.copy(hasInput = true, preview = PreviewState.Processing) }
    }

    fun setExposureCompensation(value: Float) {
        replaceParams(history.current.withExposureCompensation(value))
    }

    fun setPrintExposure(value: Float) {
        replaceParams(history.current.withPrintExposure(value))
    }

    fun updateParams(transform: (SpektrafilmParams) -> SpektrafilmParams) {
        replaceParams(transform(history.current))
    }

    fun undo() {
        history.undo()
        publishParams()
    }

    fun redo() {
        history.redo()
        publishParams()
    }

    fun exportCurrent() {
        val image = inputImage.value
        if (image == null) {
            _uiState.update {
                it.copy(export = ExportState.Error("No input image selected"))
            }
            return
        }
        viewModelScope.launch {
            _uiState.update { it.copy(export = ExportState.Processing(progress = null)) }
            try {
                val result = withContext(processingDispatcher) {
                    processor.process(
                        ProcessingRequest(image, history.current, ProcessingMode.FullResolution),
                    ) { progress ->
                        _uiState.update {
                            it.copy(export = ExportState.Processing(progress = progress))
                        }
                    }
                }
                _uiState.update { it.copy(export = ExportState.Done(result.diagnostics)) }
            } catch (error: CancellationException) {
                throw error
            } catch (error: Throwable) {
                _uiState.update {
                    it.copy(export = ExportState.Error(error.message ?: error.javaClass.simpleName))
                }
            }
        }
    }

    private fun replaceParams(next: SpektrafilmParams) {
        history.push(next)
        publishParams()
    }

    private fun publishParams() {
        params.value = history.current
        _uiState.update {
            it.copy(
                params = history.current,
                canUndo = history.canUndo,
                canRedo = history.canRedo,
            )
        }
    }
}
