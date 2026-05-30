package com.spektrafilm.android.processing

import android.content.Context
import java.io.IOException

/**
 * Loads binary profile data (.prof files) and the Hanatos2025 LUT from Android assets.
 * The binary layout matches the C++ FilmProfileData struct exactly.
 */
object ProfileLoader {

    private val profileCache = mutableMapOf<String, ByteArray>()
    private var hanatosLutCache: ByteArray? = null

    /**
     * Load a film profile binary from assets/profiles/<name>.prof
     * Returns raw bytes that can be passed directly to JNI.
     */
    fun loadProfile(context: Context, stockName: String): ByteArray? {
        profileCache[stockName]?.let { return it }

        return try {
            val bytes = context.assets.open("profiles/$stockName.prof").use { it.readBytes() }
            profileCache[stockName] = bytes
            bytes
        } catch (e: IOException) {
            android.util.Log.e("ProfileLoader", "Failed to load profile: $stockName", e)
            null
        }
    }

    /**
     * Load the Hanatos2025 spectral LUT from assets/profiles/hanatos2025_lut.bin
     * Returns raw bytes (192*192*81*4 = ~11.4MB).
     */
    fun loadHanatosLut(context: Context): ByteArray? {
        hanatosLutCache?.let { return it }

        return try {
            val bytes = context.assets.open("profiles/hanatos2025_lut.bin").use { it.readBytes() }
            hanatosLutCache = bytes
            bytes
        } catch (e: IOException) {
            android.util.Log.e("ProfileLoader", "Failed to load Hanatos2025 LUT", e)
            null
        }
    }

    fun clearCache() {
        profileCache.clear()
        hanatosLutCache = null
    }
}
