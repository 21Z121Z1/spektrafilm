package com.spektrafilm.android.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Camera
import androidx.compose.material.icons.filled.Image
import androidx.compose.material.icons.filled.Print
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavDestination.Companion.hasRoute
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import com.spektrafilm.android.ui.tabs.FilmTab
import com.spektrafilm.android.ui.tabs.OutputTab
import com.spektrafilm.android.ui.tabs.PreviewTab
import com.spektrafilm.android.ui.tabs.PrintTab
import com.spektrafilm.android.viewmodel.SpektrafilmViewModel
import kotlinx.serialization.Serializable

@Serializable data object PreviewRoute
@Serializable data object FilmRoute
@Serializable data object PrintRoute
@Serializable data object OutputRoute

data class TabItem(
    val label: String,
    val icon: ImageVector,
    val route: Any,
)

private val tabs = listOf(
    TabItem("Preview", Icons.Default.Image, PreviewRoute),
    TabItem("Film", Icons.Default.Camera, FilmRoute),
    TabItem("Print", Icons.Default.Print, PrintRoute),
    TabItem("Output", Icons.Default.Settings, OutputRoute),
)

@Composable
fun SpektrafilmApp(viewModel: SpektrafilmViewModel) {
    SpektrafilmTheme {
        val navController = rememberNavController()
        val navBackStackEntry by navController.currentBackStackEntryAsState()
        val currentDestination = navBackStackEntry?.destination

        Scaffold(
            bottomBar = {
                NavigationBar {
                    tabs.forEach { tab ->
                        val selected = currentDestination?.hasRoute(tab.route::class) == true
                        NavigationBarItem(
                            selected = selected,
                            onClick = {
                                navController.navigate(tab.route) {
                                    popUpTo(navController.graph.findStartDestination().id) {
                                        saveState = true
                                    }
                                    launchSingleTop = true
                                    restoreState = true
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            },
        ) { padding ->
            NavHost(
                navController = navController,
                startDestination = PreviewRoute,
                modifier = Modifier.padding(padding),
            ) {
                composable<PreviewRoute> { PreviewTab(viewModel) }
                composable<FilmRoute> { FilmTab(viewModel) }
                composable<PrintRoute> { PrintTab(viewModel) }
                composable<OutputRoute> { OutputTab(viewModel) }
            }
        }
    }
}
