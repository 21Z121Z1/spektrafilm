package com.spektrafilm.android.ui.tabs

import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.Undo
import androidx.compose.material.icons.filled.Redo
import androidx.compose.material3.Button
import androidx.compose.material3.FilledTonalButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import com.spektrafilm.android.ui.components.ImagePreview
import com.spektrafilm.android.ui.components.ParamSlider
import com.spektrafilm.android.ui.components.ParamToggle
import com.spektrafilm.android.ui.components.loadUriToFloatImage
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel

@Composable
fun PreviewTab(viewModel: SpektrafilmViewModel) {
    val state by viewModel.uiState.collectAsState()
    val context = LocalContext.current

    val photoPicker = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia(),
    ) { uri ->
        if (uri != null) {
            val image = loadUriToFloatImage(context, uri)
            if (image != null) {
                viewModel.setInputImage(image)
            }
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        // Image preview
        ImagePreview(
            preview = state.preview,
            modifier = Modifier.weight(1f),
        )

        // Pick photo button
        Button(
            onClick = {
                photoPicker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))
            },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Icon(Icons.Default.PhotoLibrary, contentDescription = null)
            Text("  Pick Photo")
        }

        // Basic controls
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "Controls",
                style = MaterialTheme.typography.titleSmall,
                color = MaterialTheme.colorScheme.primary,
            )
            Row {
                IconButton(
                    onClick = viewModel::undo,
                    enabled = state.canUndo,
                ) {
                    Icon(Icons.Default.Undo, contentDescription = "Undo")
                }
                IconButton(
                    onClick = viewModel::redo,
                    enabled = state.canRedo,
                ) {
                    Icon(Icons.Default.Redo, contentDescription = "Redo")
                }
            }
        }

        ParamSlider(
            label = "Exposure",
            value = state.params.camera.exposureCompensationEv,
            onValueChange = viewModel::setExposureCompensation,
            valueRange = -3f..3f,
            format = { "%.2f EV".format(it) },
        )

        ParamSlider(
            label = "Print Exposure",
            value = state.params.enlarger.printExposure,
            onValueChange = viewModel::setPrintExposure,
            valueRange = 0.25f..2.5f,
        )

        ParamToggle(
            label = "Scan Film (vs Print)",
            checked = state.params.io.scanFilm,
            onCheckedChange = { viewModel.updateParams { p -> p.copy(io = p.io.copy(scanFilm = it)) } },
        )

        Spacer(modifier = Modifier.height(4.dp))

        // Status
        val selfTest = state.selfTest
        if (selfTest != null) {
            Text(
                text = "${selfTest.processor} ${selfTest.version}: ${if (selfTest.ok) "ready" else "unavailable"}",
                style = MaterialTheme.typography.bodySmall,
                color = if (selfTest.ok) MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.error,
            )
        }
    }
}
