package com.spektrafilm.android.viewmodel

import com.spektrafilm.android.processing.DirectFloatImage
import com.spektrafilm.android.processing.ProcessingProgress
import com.spektrafilm.android.processing.ProcessorSelfTest
import com.spektrafilm.android.state.SpektrafilmParams

data class SpektrafilmUiState(
    val params: SpektrafilmParams = SpektrafilmParams(),
    val preview: PreviewState = PreviewState.Idle,
    val export: ExportState = ExportState.Idle,
    val selfTest: ProcessorSelfTest? = null,
    val errorMessage: String? = null,
    val hasInput: Boolean = false,
    val canUndo: Boolean = false,
    val canRedo: Boolean = false,
)

sealed interface PreviewState {
    data object Idle : PreviewState
    data object Processing : PreviewState
    data class Ready(
        val image: DirectFloatImage,
        val diagnostics: List<String>,
    ) : PreviewState
    data class Error(val message: String) : PreviewState
}

sealed interface ExportState {
    data object Idle : ExportState
    data class Processing(val progress: ProcessingProgress?) : ExportState
    data class Done(val diagnostics: List<String>) : ExportState
    data class Error(val message: String) : ExportState
}
