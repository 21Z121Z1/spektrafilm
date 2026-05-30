package com.spektrafilm.android.state

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SpektrafilmParamsTest {
    @Test
    fun defaultsMatchRuntimePhotoParamsDefaults() {
        val params = SpektrafilmParams()

        assertEquals("kodak_portra_400", params.filmStock)
        assertEquals("kodak_portra_endura", params.printPaper)
        assertEquals(0.0f, params.camera.exposureCompensationEv)
        assertEquals(true, params.camera.autoExposure)
        assertEquals("scene_linear", params.camera.autoExposureMethod)
        assertEquals("TH-KG3", params.enlarger.illuminant)
        assertEquals(1.0f, params.enlarger.printExposure)
        assertEquals("ProPhoto RGB", params.io.inputColorSpace)
        assertEquals("sRGB", params.io.outputColorSpace)
        assertEquals("auto", params.settings.computeBackend)
        assertEquals("float32", params.settings.floatPrecision)
        assertEquals(640, params.settings.previewMaxSize)
    }

    @Test
    fun jsonRoundTripPreservesAllFieldsAndUsesStableDefaults() {
        val params = SpektrafilmParams(
            filmStock = "fujifilm_provia_100f",
            printPaper = "kodak_2383",
            camera = CameraParams(exposureCompensationEv = 0.5f, autoExposure = false),
            settings = SettingsParams(computeBackend = "halide", previewMaxSize = 1024),
        )

        val json = params.toJson()
        val restored = SpektrafilmParams.fromJson(json)

        assertEquals(params, restored)
        assertEquals(json, restored.toJson())
        assertTrue(json.contains("\"schemaVersion\":1"))
        assertTrue(json.contains("\"filmStock\":\"fujifilm_provia_100f\""))
    }

    @Test
    fun nativePayloadIsUtf8Json() {
        val params = SpektrafilmParams(camera = CameraParams(exposureCompensationEv = -1.25f))

        assertArrayEquals(params.toJson().toByteArray(Charsets.UTF_8), params.toNativePayload())
    }
}
