# Android Port Status - 2026-05-28

## Summary

This run adds a real Android port foundation under `android/`. It is a native
Android/Kotlin project with Compose UI, ViewModel/StateFlow state, deterministic
parameter serialization aligned with current `RuntimePhotoParams` defaults,
unit coverage, and JNI/C++ diagnostic bridge source.

It does not implement full Spektrafilm film/print/scan rendering on Android.
The native processor is explicitly diagnostic: it validates Direct `ByteBuffer`
and JNI plumbing for float32 RGB buffers.

## Evidence-Based Decisions

- Chaquopy was not integrated. Official Chaquopy 17.0 supports Python 3.10-3.14
  and AGP 7.3-9.2, but the Python 3.13 package index does not provide the
  Spektrafilm dependency graph: NumPy is available as `1.26.2`, not the
  repository's `numpy~=2.4`, and SciPy does not have a Python 3.13 wheel in the
  checked Chaquopy index. See:
  - https://chaquo.com/chaquopy/doc/current/versions.html
  - https://chaquo.com/pypi-13.1/numpy/
  - https://chaquo.com/pypi-13.1/scipy/
- AGP 9.2 is used with Gradle 9.4.1. AGP 9 rejects the legacy
  `org.jetbrains.kotlin.android` plugin because Kotlin support is built in.
  The build therefore applies AGP plus Kotlin Compose and serialization plugins
  only.
- JDK 21 was used for Android validation. The machine also has JDK 24/25, but
  the validation command pins JDK 21 to avoid testing a newer JVM combination as
  an Android app defect.
- Android native packaging is gated by a precise NDK preflight. The local SDK
  has only an incomplete `ndk/28.2.13676358/.installer` directory from an
  attempted AGP auto-provision, not a complete NDK with
  `build/cmake/android.toolchain.cmake`.
- Existing Halide host AOT generator build remains the strongest local Halide
  proof. Android cross-compilation still requires a complete NDK and future
  Halide AOT integration.

## Implemented Components

- `android/settings.gradle.kts`, root/app Gradle files, Android manifest, and
  app resources.
- Compose screen for sample preview/export flow and parameter controls.
- `SpektrafilmViewModel` using immutable UI state, `StateFlow`, debounced
  `flatMapLatest` preview processing, export state, errors, self-test state,
  and undo/redo-backed parameter edits.
- `SpektrafilmParams` and nested serializable parameter classes with defaults
  matching current runtime defaults where the Android model has fields.
- `SpektrafilmProcessor` contract with preview/full-resolution modes,
  progress, self-test, result diagnostics, and direct float image boundary.
- Direct float image allocation validates dimensions with overflow-safe bounds
  before calculating byte counts, so invalid large dimensions fail before any
  allocation attempt.
- `SpektrafilmViewModel` reports native self-test exceptions as explicit
  unavailable self-test state instead of crashing the coroutine scope.
- JNI/C++ diagnostic bridge source:
  - `nativeVersion()`
  - `nativeSelfTest()`
  - direct-buffer float32 copy/scale entrypoint with null/capacity checks
- Unit tests for params serialization, edit history, direct-buffer contract,
  processor modes, and ViewModel cancellation/state behavior.

## Build And Validation Commands

Use JDK 21 for repeatable local validation:

```bash
export JAVA_HOME="$(/usr/libexec/java_home -v 21)"
export ANDROID_HOME="$HOME/Library/Android/sdk"
```

Kotlin/JVM unit validation:

```bash
gradle -p android testDebugUnitTest --no-daemon --max-workers=1 --stacktrace --console=plain
```

Native packaging validation:

```bash
gradle -p android assembleDebug --no-daemon --max-workers=1 --stacktrace --console=plain
```

Expected local result today: `assembleDebug` fails before packaging with:

```text
Android NDK 28.2.13676358 with build/cmake/android.toolchain.cmake is required
for Spektrafilm native builds. Install it with: sdkmanager "ndk;28.2.13676358"
```

After installing the NDK, rerun `assembleDebug`. If Halide AOT libraries are
available later, pass their directory through the CMake cache variable
`SPEKTRAFILM_HALIDE_AOT_DIR` and add explicit link targets before claiming real
Halide processing.

## 2026-05-28 Verification Snapshot

Latest verification in this workspace used:

```bash
JAVA_HOME=/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home
```

Results:

- `gradle -p android clean testDebugUnitTest --no-daemon --max-workers=1 --stacktrace --console=plain`:
  `BUILD SUCCESSFUL in 24s` with 25 executed tasks.
- `gradle -p android assembleDebug --no-daemon --max-workers=1 --stacktrace --console=plain`:
  expected failure at `:app:spektrafilmNativePreflight` because the local SDK
  does not contain a complete `ndk/28.2.13676358` with
  `build/cmake/android.toolchain.cmake`; this was rechecked after `clean` and
  failed as designed in 18s.
- `.venv/bin/python -m pytest tests/test_halide_android.py tests/test_halide_generators.py -q`:
  `14 passed in 34.16s`.
- `.venv/bin/python -m pytest tests/test_halide_backend.py tests/test_halide_color.py tests/test_halide_lut.py tests/test_halide_spectral.py tests/test_halide_filters.py tests/test_halide_android.py tests/test_halide_generators.py -q`:
  `67 passed in 42.49s`.
- `.venv/bin/python -m pytest tests/test_photo_params.py tests/test_runtime_api.py -q`:
  `45 passed in 0.52s`; the run emitted the known headless Metal-device atexit
  warning after completion.
- `.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm/generators tests -q`:
  passed.
- `c++ -std=c++17 -Wall -Wextra -Werror -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include -I/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home/include/darwin -fsyntax-only android/app/src/main/cpp/spektrafilm_android_jni.cpp`:
  passed.
- `git diff --check`: passed.

## Known Limitations

- No Android device/emulator instrumentation run was completed in this pass.
- No Chaquopy bridge exists because current package evidence does not support
  the repository's Python 3.13 dependency set.
- No full Spektrafilm renderer exists on Android. UI copy, processor
  diagnostics, and docs all describe the native path as diagnostic only.
- No Android Halide cross-compilation was completed locally because a complete
  NDK is absent.
- AGP 9 built-in Kotlin did not put the app classes jar on the local
  `compileDebugUnitTestKotlin` classpath automatically. The build adds a narrow
  `testImplementation(files(...classes.jar))` dependency and task dependency so
  unit tests compile against the app classes jar produced by AGP.

## Next Steps

1. Install a complete NDK 28.2.13676358 and rerun `assembleDebug`.
2. Add a small Android instrumentation test for `NativeSpektrafilmProcessor`
   after native packaging succeeds.
3. Cross-compile one Halide AOT kernel for `arm-64-android`, link it into
   `libspektrafilm_android`, and add a direct-buffer parity test.
4. Define an Android-side tiled/full-resolution image boundary before wiring
   real export.
5. Revisit Python-on-Android only if Spektrafilm's dependency set changes or
   project-owned Android wheels are built for NumPy/SciPy and native I/O deps.
