package com.spektrafilm.android.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColorScheme = darkColorScheme(
    primary = Color(0xFFFFB74D),       // Amber 300
    onPrimary = Color(0xFF1A1A1A),
    primaryContainer = Color(0xFF4E3A00),
    onPrimaryContainer = Color(0xFFFFDDB3),
    secondary = Color(0xFF90CAF9),     // Blue 200
    onSecondary = Color(0xFF1A1A1A),
    secondaryContainer = Color(0xFF1A3A5C),
    onSecondaryContainer = Color(0xFFBBDEFB),
    tertiary = Color(0xFFA5D6A7),      // Green 200
    onTertiary = Color(0xFF1A1A1A),
    tertiaryContainer = Color(0xFF1B3D1B),
    onTertiaryContainer = Color(0xFFC8E6C9),
    background = Color(0xFF121212),
    onBackground = Color(0xFFE0E0E0),
    surface = Color(0xFF1E1E1E),
    onSurface = Color(0xFFE0E0E0),
    surfaceVariant = Color(0xFF2A2A2A),
    onSurfaceVariant = Color(0xFFBDBDBD),
    error = Color(0xFFEF9A9A),
    onError = Color(0xFF1A1A1A),
    outline = Color(0xFF424242),
)

private val LightColorScheme = lightColorScheme(
    primary = Color(0xFFE65100),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFFFCC80),
    onPrimaryContainer = Color(0xFF3E1A00),
    secondary = Color(0xFF1565C0),
    onSecondary = Color.White,
    secondaryContainer = Color(0xFFBBDEFB),
    onSecondaryContainer = Color(0xFF003C8F),
    background = Color(0xFFFAFAFA),
    onBackground = Color(0xFF1A1A1A),
    surface = Color.White,
    onSurface = Color(0xFF1A1A1A),
    surfaceVariant = Color(0xFFF5F5F5),
    onSurfaceVariant = Color(0xFF616161),
)

@Composable
fun SpektrafilmTheme(
    darkTheme: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colorScheme = if (darkTheme) DarkColorScheme else LightColorScheme
    MaterialTheme(
        colorScheme = colorScheme,
        content = content,
    )
}
