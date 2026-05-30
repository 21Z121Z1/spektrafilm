# Android Port Implementation Plan - 2026-05-28

## Goal

Build a validated Spektrafilm Android port foundation which is honest about what
works today: a native Android project with Kotlin/Compose state architecture,
typed parameter serialization aligned with `RuntimePhotoParams`, a stable
processing bridge contract, JNI/native proof-of-concept source, tests, and
documentation. This run will not claim full Spektrafilm rendering on Android.

## Current Repository Facts

- There is no existing `android/` project, Gradle wrapper, Android manifest,
  Kotlin source, Compose UI, JNI wrapper, or APK build output in the repo.
- `pyproject.toml` requires Python `~=3.13` and dependencies including
  `numpy~=2.4`, `scipy~=1.17`, `colour-science~=0.4.6`, `scikit-image~=0.26`,
  `numba~=0.64`, `OpenImageIO~=3.1.11`, `rawpy~=0.26.1`, `exiv2~=0.18.1`, and
  `lensfunpy~=1.18.0`.
- `RuntimePhotoParams` lives in `src/spektrafilm/runtime/params_schema.py`.
  It is a dataclass tree with required `Profile` instances for `film` and
  `print`; profile names are not currently a first-class serializable runtime
  field.
- `digest_params()` mutates and returns the same `RuntimePhotoParams` object.
  Existing tests assert runtime defaults, film/print profile defaults, and
  digest idempotence.
- The runtime is split into stage modules under
  `src/spektrafilm/runtime/stages/`: filming, printing, and scanning. The
  desktop pipeline must remain untouched in this run.
- Existing Android/Halide support is Python-side only:
  `src/spektrafilm/halide/android.py` maps Android ABIs to Halide target
  strings and has unit coverage in `tests/test_halide_android.py`.
- `src/spektrafilm/generators/` contains four C++ Halide generator files and a
  CMake project with 10 `add_halide_library()` targets.
- Host Halide generator configure and build was verified locally with the
  installed Python Halide CMake package. The build produced all host AOT
  libraries under `/tmp/spektrafilm-halide-generators-host`.
- Local Android SDK exists at `$HOME/Library/Android/sdk` with API 34, 35, and
  36 platforms and build-tools 30.0.3, 34.0.0, 35.0.0, 35.0.1, and 36.0.0.
- No Android NDK is installed locally. There is no
  `$ANDROID_NDK/build/cmake/android.toolchain.cmake` path to use for Android
  cross-compilation.
- Local Gradle is 9.4.1. Official Android documentation states AGP 9.2 requires
  Gradle 9.4.1, SDK build-tools 36.0.0, and JDK 17 minimum.
- Current local Java commands report JDK 24/25 depending on launcher context.
  AGP requires at least JDK 17; validation must report the actual JDK used.

## Research Document Validity

### Still Valid

- `research-android-app-architecture.md` is directionally correct that the app
  should use Kotlin, Jetpack Compose, ViewModel, StateFlow, coroutine
  cancellation, preview/export separation, and direct/native buffer discipline.
- Its memory warning is valid: full-resolution float32 buffers are too large to
  duplicate casually on Android, so the bridge contract must expose preview
  and full-resolution paths separately.
- Its preferred processing boundary, Direct `ByteBuffer` plus JNI/native
  processing, fits the current repo better than trying to run the entire
  desktop stack inside Android Python.
- `halide-android-port-plan.md` is accurate that there is no JNI, Android NDK
  project, Kotlin UI, APK, or device-side Android implementation today.
- The Halide AOT direction remains valid. The host generator project currently
  configures and builds when `Halide_DIR` points to the installed Halide CMake
  package.
- The `arm64-v8a -> arm-64-android` default remains the right production target
  when NDK tooling exists.

### Stale, Speculative, Contradictory, Or Unverified

- The Chaquopy recommendation in `research-android-porting-strategies.md` is
  stale for Spektrafilm as currently declared. Chaquopy 17.0 supports Python
  3.10-3.14 and AGP 7.3-9.2, but its native Android package index does not
  provide the required Spektrafilm stack for Python 3.13:
  - Chaquopy has `numpy-1.26.2` wheels for `cp313`, not Spektrafilm's
    `numpy~=2.4`.
  - Chaquopy's `scipy` index stops at `cp310` wheels and does not provide a
    `cp313` SciPy wheel, let alone `scipy~=1.17`.
  - `colour-science` is pure Python, but it depends on compatible NumPy/SciPy;
    pure Python status alone does not make the Spektrafilm dependency graph
    viable.
- The older `research-android-port.md` dependency table incorrectly says
  NumPy/SciPy/colour are easy through Chaquopy for the current dependency set.
- Claims about prebuilt scikit-image, Pillow, rawpy, OpenImageIO, exiv2, and
  lensfunpy being usable via Chaquopy are not proven for the current Python
  version and must not be used as an implementation foundation.
- Vulkan and AGSL notes are useful future research, but this run will not add a
  GPU compute backend. The current local validation target is native CPU/JNI
  contract plus existing Halide AOT generator evidence.
- Android cross-compilation is unverified locally because the NDK is absent.
  The implementation must fail clearly or document exact setup commands rather
  than pretending Android `.so` output was built.

## Concrete Implementation Scope

1. Add an `android/` Gradle project using:
   - AGP `9.2.0`
   - Kotlin Android plugin `2.3.21`
   - Compose BOM `2026.05.00`
   - `compileSdk = 36`
   - `minSdk = 26`
   - `targetSdk = 36`
   - `arm64-v8a` as the primary native ABI
2. Add a Kotlin application structure:
   - `MainActivity`
   - Compose edit screen suitable for import/preview/export flow
   - immutable `SpektrafilmUiState`
   - `SpektrafilmViewModel` using `StateFlow`
   - debounced and cancellable preview processing
   - export state and error reporting
   - bounded undo/redo history for parameter edits
3. Add Android parameter model and serialization:
   - `SpektrafilmParams`
   - nested camera/enlarger/scanner/render/settings parameter data classes
   - defaults aligned with current `RuntimePhotoParams` defaults
   - deterministic JSON serialization/deserialization
   - unit tests for defaults, serialization, edit reducer, and undo/redo
4. Add processing bridge contract:
   - `SpektrafilmProcessor`
   - `ProcessingRequest`, `ProcessingResult`, `ProcessingProgress`,
     `ProcessorSelfTest`
   - preview/full-resolution separation
   - direct `ByteBuffer` image boundary for future native code
   - no fake claim that diagnostic processing equals Spektrafilm rendering
5. Add native/JNI proof-of-concept source:
   - `libspektrafilm_android`
   - `nativeVersion()`
   - `nativeSelfTest()`
   - a minimal direct-buffer float32 RGB operation that validates native byte
     order, direct-buffer address handling, dimensions, and error returns
   - CMake that can link standalone native code now and optionally link Halide
     artifacts later when `SPEKTRAFILM_HALIDE_AOT_DIR` is provided
6. Add Gradle/native preflight behavior:
   - a documented NDK requirement
   - a clear Gradle task or build message for missing NDK/Halide AOT path
   - no silent native stub substitution
7. Add docs:
   - keep this pre-implementation plan
   - add `docs/dev/android-port-status-20260528.md`
   - amend the three Android research documents with a dated implementation
     note about Chaquopy viability and the implemented foundation
   - add a concise README pointer only if needed

## Non-Goals And Deferred Work

- No full C++ port of `SimulationPipeline`.
- No Chaquopy integration in this run.
- No claim that Android preview/export performs real Spektrafilm film/print/scan
  rendering.
- No Android device or emulator instrumentation test unless a runnable device is
  already available after the project builds.
- No Vulkan, AGSL, CameraX, MediaStore export, RAW/DNG import, HDR display
  pipeline, or Play Store packaging implementation.
- No changes to desktop Python runtime behavior, SDR rendering, profile
  behavior, HDR export, or existing GUI semantics.
- No local NDK installation as part of this run.

## Validation Commands

Pre-edit and discovery validation already run:

```bash
git status --short --branch
.venv/bin/python - <<'PY'
import halide, numpy, scipy, colour
print("halide", halide.install_dir())
print("numpy", numpy.__version__)
print("scipy", scipy.__version__)
print("colour", colour.__version__)
PY
cmake -S src/spektrafilm/generators -B /tmp/spektrafilm-halide-generators-host \
  -DHalide_DIR=$(.venv/bin/python - <<'PY'
from pathlib import Path
import halide
print(Path(halide.install_dir()) / "lib/cmake/Halide")
PY
) -DTARGET=host
cmake --build /tmp/spektrafilm-halide-generators-host -j2
```

Planned validation after implementation:

```bash
git status --short
git diff --check
gradle -p android testDebugUnitTest
ANDROID_HOME="$HOME/Library/Android/sdk" gradle -p android testDebugUnitTest
ANDROID_HOME="$HOME/Library/Android/sdk" gradle -p android assembleDebug
.venv/bin/python -m pytest tests/test_halide_android.py tests/test_halide_generators.py -q
.venv/bin/python -m pytest tests/test_photo_params.py tests/test_runtime_api.py -q
.venv/bin/python -m compileall src/spektrafilm/gpu src/spektrafilm/halide src/spektrafilm/runtime -q
```

Expected classification:

- `testDebugUnitTest` should pass if Gradle can resolve Android dependencies.
- `assembleDebug` is expected to fail locally if AGP requires an installed NDK
  before native build and no NDK exists. That failure must be classified as a
  missing local toolchain failure, not a code success.
- Android cross-compilation of Halide generators is skipped locally because no
  Android NDK is installed.

## Risks And Mitigations

- **False Chaquopy assumptions:** Do not add Chaquopy. Document the exact wheel
  mismatch and leave a future path only if the dependency set changes or native
  wheels are built.
- **AGP/Kotlin/Compose mismatch:** Use official AGP 9.2 / Gradle 9.4.1 guidance,
  Kotlin 2.3.21 from official AGP example, and Compose BOM 2026.05.00 from
  official Compose docs.
- **Missing NDK:** Keep native code real, but classify Android native build
  validation as blocked by missing NDK if it cannot run. Provide exact install
  and build commands.
- **Fake processing:** Name any non-native fallback diagnostic path as
  diagnostic only. UI copy and docs must state native Spektrafilm rendering is
  not yet implemented.
- **DirectByteBuffer misuse:** Native code must validate direct buffers, byte
  capacity, dimensions, and operation bounds. Kotlin must allocate buffers with
  `ByteOrder.nativeOrder()`.
- **Uncancellable preview:** ViewModel preview must use debounced `StateFlow` and
  `flatMapLatest`/job cancellation so rapid slider edits cancel stale work.
- **Full-resolution memory copies:** Bridge models must distinguish preview and
  full-resolution requests and keep float32 buffer allocation explicit.
- **Desktop regressions:** Do not edit desktop runtime modules except docs/tests
  unrelated to behavior. Run targeted Python tests.
- **Docs overclaiming:** Status docs and research amendments must distinguish
  "foundation exists" from "Android Spektrafilm renderer exists."
- **Dirty worktree:** Keep changes scoped to `android/`, directly related docs,
  and tests. Do not remove or rewrite unrelated untracked files.

## 100% Confidence Exit Check

Before final response, re-check:

- Chaquopy claims are consistent with official Chaquopy docs and package index.
- Android Gradle/Kotlin/Compose versions match official guidance.
- Native build status is reported with exact local toolchain facts.
- No unsupported code path is described as real Spektrafilm processing.
- Unit tests exercise parameter serialization, ViewModel cancellation/state,
  undo/redo, and processor contract.
- Docs and code agree about current capabilities and missing pieces.
- Existing desktop behavior remains untouched except for documentation and
  validation.
