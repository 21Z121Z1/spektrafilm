package com.spektrafilm.android.ui.tabs

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.spektrafilm.android.ui.components.CollapsibleSection
import com.spektrafilm.android.ui.components.ParamSlider
import com.spektrafilm.android.ui.components.ParamToggle
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel

@Composable
fun PrintTab(viewModel: SpektrafilmViewModel) {
    val state by viewModel.uiState.collectAsState()
    val params = state.params

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(0.dp),
    ) {
        // Diffusion Filter
        CollapsibleSection(title = "Diffusion Filter") {
            ParamToggle(
                label = "Active",
                checked = params.render.halationActive, // reuse halation toggle for now
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(halationActive = it)) } },
            )
        }

        // Glare
        CollapsibleSection(title = "Glare") {
            ParamToggle(
                label = "Active",
                checked = params.render.glareActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(glareActive = it)) } },
            )
        }

        // Scanner
        CollapsibleSection(title = "Scanner") {
            ParamSlider(
                label = "Lens Blur",
                value = params.scanner.lensBlur,
                onValueChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(lensBlur = it)) } },
                valueRange = 0f..50f,
                format = { "%.1f".format(it) },
            )
            ParamToggle(
                label = "White Correction",
                checked = params.scanner.whiteCorrection,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(whiteCorrection = it)) } },
            )
            ParamToggle(
                label = "Black Correction",
                checked = params.scanner.blackCorrection,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(blackCorrection = it)) } },
            )
            ParamSlider(
                label = "White Level",
                value = params.scanner.whiteLevel,
                onValueChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(whiteLevel = it)) } },
                valueRange = 0.5f..1.0f,
            )
            ParamSlider(
                label = "Black Level",
                value = params.scanner.blackLevel,
                onValueChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(blackLevel = it)) } },
                valueRange = 0f..0.1f,
            )
            ParamSlider(
                label = "Unsharp Mask Amount",
                value = params.scanner.unsharpMaskAmount,
                onValueChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(unsharpMaskAmount = it)) } },
                valueRange = 0f..2f,
            )
            ParamSlider(
                label = "Unsharp Mask Radius",
                value = params.scanner.unsharpMaskRadius,
                onValueChange = { viewModel.updateParams { p -> p.copy(scanner = p.scanner.copy(unsharpMaskRadius = it)) } },
                valueRange = 0.1f..5f,
            )
        }
    }
}
