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
import com.spektrafilm.android.ui.components.ParamDropdown
import com.spektrafilm.android.ui.components.ParamSlider
import com.spektrafilm.android.ui.components.ParamToggle
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel

private val filmStocks = listOf(
    "kodak_portra_400",
    "kodak_portra_160",
    "kodak_gold_200",
    "fuji_pro_400h",
    "kodak_trix_400",
    "ilford_hp5",
)

private val printPapers = listOf(
    "kodak_portra_endura",
    "kodak_supra_endura",
    "fuji_crystal_archive",
)

@Composable
fun FilmTab(viewModel: SpektrafilmViewModel) {
    val state by viewModel.uiState.collectAsState()
    val params = state.params

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 12.dp),
        verticalArrangement = Arrangement.spacedBy(0.dp),
    ) {
        // Film Stock
        CollapsibleSection(title = "Film Stock", initiallyExpanded = true) {
            ParamDropdown(
                label = "Film Stock",
                selectedValue = params.filmStock,
                options = filmStocks,
                onValueChange = { viewModel.updateParams { p -> p.copy(filmStock = it) } },
            )
            ParamDropdown(
                label = "Print Paper",
                selectedValue = params.printPaper,
                options = printPapers,
                onValueChange = { viewModel.updateParams { p -> p.copy(printPaper = it) } },
            )
        }

        // Camera
        CollapsibleSection(title = "Camera") {
            ParamSlider(
                label = "Exposure Compensation",
                value = params.camera.exposureCompensationEv,
                onValueChange = viewModel::setExposureCompensation,
                valueRange = -3f..3f,
                format = { "%.2f EV".format(it) },
            )
            ParamToggle(
                label = "Auto Exposure",
                checked = params.camera.autoExposure,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(camera = p.camera.copy(autoExposure = it)) } },
            )
            ParamSlider(
                label = "Lens Blur",
                value = params.camera.lensBlurUm,
                onValueChange = { viewModel.updateParams { p -> p.copy(camera = p.camera.copy(lensBlurUm = it)) } },
                valueRange = 0f..100f,
                format = { "%.0f um".format(it) },
            )
            ParamSlider(
                label = "Film Format",
                value = params.camera.filmFormatMm,
                onValueChange = { viewModel.updateParams { p -> p.copy(camera = p.camera.copy(filmFormatMm = it)) } },
                valueRange = 8f..90f,
                format = { "%.1f mm".format(it) },
            )
        }

        // Halation
        CollapsibleSection(title = "Halation") {
            ParamToggle(
                label = "Active",
                checked = params.render.halationActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(halationActive = it)) } },
            )
        }

        // Grain
        CollapsibleSection(title = "Grain") {
            ParamToggle(
                label = "Active",
                checked = params.render.grainActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(grainActive = it)) } },
            )
        }

        // DIR Couplers
        CollapsibleSection(title = "DIR Couplers") {
            ParamToggle(
                label = "Active",
                checked = params.render.dirCouplersActive,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(render = p.render.copy(dirCouplersActive = it)) } },
            )
        }

        // Enlarger
        CollapsibleSection(title = "Enlarger") {
            ParamSlider(
                label = "Print Exposure",
                value = params.enlarger.printExposure,
                onValueChange = viewModel::setPrintExposure,
                valueRange = 0.25f..2.5f,
            )
            ParamDropdown(
                label = "Illuminant",
                selectedValue = params.enlarger.illuminant,
                options = listOf("TH-KG3", "D50", "D65", "A", "F11"),
                onValueChange = { viewModel.updateParams { p -> p.copy(enlarger = p.enlarger.copy(illuminant = it)) } },
            )
            ParamToggle(
                label = "Print Exposure Compensation",
                checked = params.enlarger.printExposureCompensation,
                onCheckedChange = { viewModel.updateParams { p -> p.copy(enlarger = p.enlarger.copy(printExposureCompensation = it)) } },
            )
            ParamSlider(
                label = "Y Filter Shift",
                value = params.enlarger.yFilterShift,
                onValueChange = { viewModel.updateParams { p -> p.copy(enlarger = p.enlarger.copy(yFilterShift = it)) } },
                valueRange = -50f..50f,
            )
            ParamSlider(
                label = "M Filter Shift",
                value = params.enlarger.mFilterShift,
                onValueChange = { viewModel.updateParams { p -> p.copy(enlarger = p.enlarger.copy(mFilterShift = it)) } },
                valueRange = -50f..50f,
            )
        }
    }
}
