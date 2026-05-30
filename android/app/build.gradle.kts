plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}

val spektrafilmNdkVersion = "28.2.13676358"
val spektrafilmSdkDir = providers.environmentVariable("ANDROID_HOME")
    .orElse(providers.environmentVariable("ANDROID_SDK_ROOT"))
    .orElse(providers.provider { "${System.getProperty("user.home")}/Library/Android/sdk" })
val spektrafilmNdkDir = file("${spektrafilmSdkDir.get()}/ndk/$spektrafilmNdkVersion")
val spektrafilmNdkToolchain = spektrafilmNdkDir.resolve("build/cmake/android.toolchain.cmake")
val spektrafilmHasCompleteNdk = spektrafilmNdkToolchain.isFile

android {
    namespace = "com.spektrafilm.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.spektrafilm.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        if (spektrafilmHasCompleteNdk) {
            ndk {
                abiFilters += listOf("arm64-v8a")
            }
        }
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlin {
        compilerOptions {
            jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
        }
    }

    if (spektrafilmHasCompleteNdk) {
        ndkVersion = spektrafilmNdkVersion
        externalNativeBuild {
            cmake {
                path = file("src/main/cpp/CMakeLists.txt")
                version = "3.22.1+"
            }
        }
    }
}

tasks.register("spektrafilmNativePreflight") {
    group = "verification"
    description = "Checks that local Android native toolchain inputs are available."

    doLast {
        if (!spektrafilmNdkToolchain.isFile) {
            throw GradleException(
                "Android NDK $spektrafilmNdkVersion with build/cmake/android.toolchain.cmake " +
                    "is required for Spektrafilm native builds. Install it with: " +
                    "sdkmanager \"ndk;$spektrafilmNdkVersion\""
            )
        }
    }
}

tasks.matching {
    it.name == "assembleDebug" ||
        it.name == "assembleRelease" ||
        it.name == "bundleDebug" ||
        it.name == "bundleRelease" ||
        it.name == "packageDebug" ||
        it.name == "packageRelease" ||
        it.name == "mergeDebugNativeLibs" ||
        it.name == "mergeReleaseNativeLibs" ||
        it.name == "stripDebugDebugSymbols" ||
        it.name == "stripReleaseDebugSymbols" ||
        it.name.startsWith("externalNativeBuild")
}.configureEach {
    dependsOn("spektrafilmNativePreflight")
}

tasks.matching { it.name == "compileDebugUnitTestKotlin" }.configureEach {
    dependsOn("bundleDebugClassesToCompileJar")
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2026.05.00")
    implementation(composeBom)
    androidTestImplementation(composeBom)

    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.material:material-icons-extended")
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.9.3")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.9.3")
    implementation("androidx.navigation:navigation-compose:2.9.0")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")
    implementation("org.jetbrains.kotlinx:kotlinx-serialization-json:1.9.0")

    debugImplementation("androidx.compose.ui:ui-tooling")

    testImplementation(files(layout.buildDirectory.file("intermediates/compile_app_classes_jar/debug/bundleDebugClassesToCompileJar/classes.jar")))
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
