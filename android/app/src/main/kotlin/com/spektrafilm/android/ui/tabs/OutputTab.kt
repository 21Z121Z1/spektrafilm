package com.spektrafilm.android.ui.tabs

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.spektrafilm.android.ui.components.CollapsibleSection
import com.spektrafilm.android.ui.components.ParamDropdown
import com.spektrafilm.android.ui.components.ParamSlider
import com.spektrafilm.android.ui.components.ParamToggle
import com.spektrafilm.android.viewmodel.ExportState
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel

private val colorSpaces = listOf("sRGB", "ProPhoto RGB", "Adobe RGB", "Display P3")

@Composable
fun OutputTab(viewModel: SpektrafilmViewModel) {
    val state by viewModel.uiState.collectAsState()
    val params = state.params

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(0.dp),
    ) {
        // IO Settings
        CollapsibleSection(title = "Input / Output", initiallyExpanded = true) {
            ParamDropdown(
                label = "Input Color Space",
                selectedValue = params.io.inputColorSpace,
                options = colorSpaces,
                onValueChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(inputColorSpace = it)) } },
            )
            ParamToggle(
                label = "Input CCTF Decoding",
                checked = params.io.inputCctfDecoding,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(inputCctfDecoding = it)) } },
            )
            ParamDropdown(
                label = "Output Color Space",
                selectedValue = params.io.outputColorSpace,
                options = colorSpaces,
                onValueChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(outputColorSpace = it)) } },
            )
            ParamToggle(
                label = "Output CCTF Encoding",
                checked = params.io.outputCctfEncoding,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(outputCctfEncoding = it)) } },
            )
            ParamToggle(
                label = "Clip Negatives",
                checked = params.io.outputClipMin,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(outputClipMin = it)) } },
            )
            ParamToggle(
                label = "Clip Highlights",
                checked = params.io.outputClipMax,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(outputClipMax = it)) } },
            )
            ParamSlider(
                label = "Upscale Factor",
                value = params.io.upscaleFactor,
                onValueChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(upscaleFactor = it)) } },
                valueRange = 0.25f..4f,
                format = { "%.2fx".format(it) },
            )
        }

        // Render Effects Master Toggles
        CollapsibleSection(title = "Render Effects") {
            ParamToggle(
                label = "Grain",
                checked = params.render.grainActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(grainActive = it)) } },
            )
            ParamToggle(
                label = "Halation",
                checked = params.render.halationActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(halationActive = it)) } },
            )
            ParamToggle(
                label = "DIR Couplers",
                checked = params.render.dirCouplersActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(dirCouplersActive = it)) } },
            )
            ParamToggle(
                label = "Glare",
                checked = params.render.glareActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(glareActive = it)) } },
            )
        }

        // Settings
        CollapsibleSection(title = "Settings") {
            ParamDropdown(
                label = "RGB to Raw Method",
                selectedValue = params.settings.rgbToRawMethod,
                options = listOf("hanatos2025", "mallett2019"),
                onValueChange = { viewModel.updateParams { p -> p.copy(settings = p.settings.copy(rgbToRawMethod = it)) } },
            )
            ParamSlider(
                label = "Preview Max Size",
                value = params.settings.previewMaxSize.toFloat(),
                onValueChange = { viewModel.updateParams { p -> p.copy(settings = p.settings.copy(previewMaxSize = it.toInt())) } },
                valueRange = 320f..2048f,
                format = { "%.0f px".format(it) },
            )
            ParamSlider(
                label = "LUT Resolution",
                value = params.settings.lutResolution.toFloat(),
                onValueChange = { viewModel.updateParams { p -> p.copy(settings = p.settings.copy(lutResolution = it.toInt())) } },
                valueRange = 9f..33f,
                format = { "%.0f".format(it) },
            )
        }

        // Export
        CollapsibleSection(title = "Export", initiallyExpanded = true) {
            Button(
                onClick = viewModel::exportCurrent,
                enabled = state.hasInput,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text("Export Full Resolution")
            }
            val export = state.export
            when (export) {
                ExportState.Idle -> Text("Ready", style = MaterialTheme.typography.bodySmall)
                is ExportState.Processing -> {
                    val progress = export.progress
                    if (progress != null) {
                        LinearProgressIndicator(
                            progress = { progress.fraction },
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Text("${progress.stage} ${"%.0f".format(progress.fraction * 100)}%",
                            style = MaterialTheme.typography.bodySmall)
                    } else {
                        LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        Text("Processing...", style = MaterialTheme.typography.bodySmall)
                    }
                }
                is ExportState.Done -> {
                    Text("Export complete", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.tertiary)
                }
                is ExportState.Error -> {
                    Text("Error: ${export.message}", style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.error)
                }
            }
        }
    }
}
