package com.spektrafilm.android.ui.components

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import com.spektrafilm.android.processing.DirectFloatImage
import com.spektrafilm.android.viewmodel.PreviewState

@Composable
fun ImagePreview(
    preview: PreviewState,
    modifier: Modifier = Modifier,
) {
    Box(
        modifier = modifier
            .fillMaxWidth()
            .aspectRatio(4f / 3f)
            .background(MaterialTheme.colorScheme.surfaceVariant),
        contentAlignment = Alignment.Center,
    ) {
        when (preview) {
            PreviewState.Idle -> {
                Text(
                    text = "Pick a photo to start",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            PreviewState.Processing -> {
                Text(
                    text = "Processing...",
                    style = MaterialTheme.typography.bodyLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
            is PreviewState.Ready -> {
                val bitmap = remember(preview.image) { floatImageToBitmap(preview.image) }
                Image(
                    bitmap = bitmap.asImageBitmap(),
                    contentDescription = "Preview",
                    modifier = Modifier.matchParentSize(),
                    contentScale = ContentScale.Fit,
                )
            }
            is PreviewState.Error -> {
                Text(
                    text = "Error: ${preview.message}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }
}

fun floatImageToBitmap(image: DirectFloatImage): Bitmap {
    val w = image.width
    val h = image.height
    val bitmap = Bitmap.createBitmap(w, h, Bitmap.Config.ARGB_8888)
    val floats = image.buffer.asFloatBuffer()
    val pixels = IntArray(w * h)
    for (y in 0 until h) {
        for (x in 0 until w) {
            val idx = (y * w + x) * 3
            val r = (floats.get(idx).coerceIn(0f, 1f) * 255).toInt()
            val g = (floats.get(idx + 1).coerceIn(0f, 1f) * 255).toInt()
            val b = (floats.get(idx + 2).coerceIn(0f, 1f) * 255).toInt()
            pixels[y * w + x] = (0xFF shl 24) or (r shl 16) or (g shl 8) or b
        }
    }
    bitmap.setPixels(pixels, 0, w, 0, 0, w, h)
    return bitmap
}
