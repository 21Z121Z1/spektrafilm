package com.spektrafilm.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.lifecycle.viewmodel.compose.viewModel
import com.spektrafilm.android.processing.NativeSpektrafilmProcessor
import com.spektrafilm.android.ui.SpektrafilmApp
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            val appContext = applicationContext
            val viewModel: SpektrafilmViewModel = viewModel {
                SpektrafilmViewModel(NativeSpektrafilmProcessor(appContext))
            }
            SpektrafilmApp(viewModel)
        }
    }
}
