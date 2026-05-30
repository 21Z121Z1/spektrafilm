package com.spektrafilm.android.ui.components

import android.content.Context
import android.graphics.BitmapFactory
import android.net.Uri
import com.spektrafilm.android.processing.DirectFloatImage
import kotlin.math.min

fun loadUriToFloatImage(
    context: Context,
    uri: Uri,
    maxDim: Int = 1280,
): DirectFloatImage? {
    return try {
        // First pass: decode bounds only
        val opts = BitmapFactory.Options().apply { inJustDecodeBounds = true }
        context.contentResolver.openInputStream(uri)?.use { BitmapFactory.decodeStream(it, null, opts) }
        val origW = opts.outWidth
        val origH = opts.outHeight
        if (origW <= 0 || origH <= 0) return null

        // Calculate inSampleSize (power of 2)
        var sampleSize = 1
        while (origW / (sampleSize * 2) >= maxDim || origH / (sampleSize * 2) >= maxDim) {
            sampleSize *= 2
        }

        // Second pass: decode at reduced resolution
        val decodeOpts = BitmapFactory.Options().apply {
            if (sampleSize > 1) inSampleSize = sampleSize
        }
        val bitmap = context.contentResolver.openInputStream(uri)?.use {
            BitmapFactory.decodeStream(it, null, decodeOpts)
        } ?: return null

        val w = bitmap.width
        val h = bitmap.height
        val image = DirectFloatImage.allocate(w, h, 3)
        val floats = image.buffer.asFloatBuffer()
        val pixels = IntArray(w * h)
        bitmap.getPixels(pixels, 0, w, 0, 0, w, h)

        for (y in 0 until h) {
            for (x in 0 until w) {
                val pixel = pixels[y * w + x]
                val idx = (y * w + x) * 3
                floats.put(idx, ((pixel shr 16) and 0xFF) / 255.0f)
                floats.put(idx + 1, ((pixel shr 8) and 0xFF) / 255.0f)
                floats.put(idx + 2, (pixel and 0xFF) / 255.0f)
            }
        }
        bitmap.recycle()
        image
    } catch (e: Exception) {
        null
    }
}
