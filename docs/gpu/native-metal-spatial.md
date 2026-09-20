# Native Metal spatial experiment

Status: experimental. Base: `develop` at `5d14af4`. This is a standalone
Gaussian executor, not a replacement for the film pipeline or MLX backend.
[中文](native-metal-spatial_zh.md)

## Authority and scope

Python remains the model authority. `prepare_gaussian` reads
`SMALL_SIGMA_MAX`, `_gaussian_kernel_1d`, and `_yvv_coeffs` from
`utils/fast_gaussian_filter.py`. It creates immutable execution data.
C++/Metal neither derives those coefficients nor loads film profiles.
No production call site, backend default, RNG, profile, or FFT path changes.

The architectural motivation came from reviewing SpektraLab. This code is
independently written against this repository's CPU implementation. Prior
access to SpektraLab source prevents a claim of personnel-isolated clean-room
development. No SpektraLab source, assets, or vendored dependencies are imported.
The code retains the repository's GPL-3.0-or-later terms.

## Contract

Input is a finite, contiguous, native-endian float32 `HxW` or `HxWxC` array.
There are 1-4 channels, each side is 1-16384 pixels, and sigma is at most
256 pixels. Nonpositive sigma is identity. The FIR radius is at most 64.
Unsupported requests fail; the executor does not silently cast, clip, build,
select MLX, or fall back to CPU.

| Operation | Order | Boundary |
| --- | --- | --- |
| FIR, sigma below the CPU threshold | vertical, then horizontal | half-sample reflect, including single-pixel axes |
| YvV IIR, sigma at/above the threshold | horizontal, then vertical; forward and backward sweeps | replicated endpoint state |

FIR weights and IIR coefficients arrive as two float32 words per float64
constant. Recurrence state uses two-word arithmetic. Stored intermediate
images remain float32. The IIR is the CPU model's discrete recurrence, not
an assertion that an IIR equals an analytic Gaussian or the MLX FFT response.

Tests compare against BOTH CPU float32 storage and CPU float64, with fixed
`atol=1e-6, rtol=1e-6`. Repeated native runs and identity channels have separate
bitwise tests. This numerical contract is not whole-pipeline bitwise parity,
physical film validation, or permission to change existing production gates.
Metal subnormal behavior is not certified as CPU bitwise behavior.

## Execution and ownership

`native_metal/spatial.h` is the C ABI. `spatial.mm` is a narrow Apple adapter;
`spatial_math.h` contains arithmetic shared with a host-only test driver.
The host test driver is never linked into the Metal library. There is no MLX
or third-party native runtime dependency.

One context serializes calls and retains exactly one input, scratch, and output
buffer plus constants. Separate tracked-buffer encoders order the two passes.
The CPU waits once, after submission, not between passes. Buffers remain owned
until the command completes. The caller receives an independent NumPy copy only
after successful completion and a finite-result check.

The explicit allocation bound is `3 * input.nbytes + constant_bytes`, checked
before allocation. It excludes driver allocations and Python/NumPy memory;
it is not an RSS or physical-footprint bound. Resizing releases old buffers
before allocating replacements. `release_memory()` drops retained buffers;
`close()` releases the context and is idempotent. The Python wrapper serializes
close and execution. A C caller must not race destroy with another call.

This slice has one image upload and readback. It does NOT implement zero-copy
texture output, asynchronous rendering, negative caching, or a full graph.
Horizontal IIR access is not yet transpose-optimized. No speedup is claimed.

## Build and verify

From the repository root, with macOS 15+ and the Xcode Metal toolchain:

```sh
uv sync --frozen --extra dev
uv run --frozen python -m spektrafilm.gpu.native_metal.build --output /tmp/sfm-native
uv run --frozen python -m pytest tests/native_metal -q
uv run --frozen python tests/native_metal/benchmark.py \
  --bundle /tmp/sfm-native --width 1280 --height 800 --sigma 20 \
  --runs 3 --output /tmp/sfm-gaussian.json
```

The build uses safe/precise Metal math and disables implicit contraction.
A runtime probe checks the low word of `TwoSum(2^24, 1)`. It must retain 1;
unsafe reassociation can erase the compensation. Checking the recombined
`(a + b) - a` was insufficient: both compensated arithmetic and reassociated
real algebra returned `b` on Xcode 26.6. The macOS tests compile a deliberately
unsafe library and require refusal. The host test carries the same negative
control. This is a targeted arithmetic check, not universal compiler certification.
Native sources, the build script, and artifact hashes reject stale or
partially replaced bundles.
Compilation is explicit, never a first-render side effect.

The existing SDR workflow adds a change-gated Linux/macOS native lane. Linux
runs host arithmetic, contract and wheel-content checks. macOS first compiles
and executes Metal without MLX installed, then runs the complete non-GUI suite
with MLX installed: that existing suite includes unguarded MLX/CoreImage tests
and is not Linux-portable. A missing native compiler/device is an error, not a
successful skip. Both lanes use frozen dependencies and upload JUnit evidence.
Existing conformance lanes remain in place, now frozen too. Their candidate
fingerprint records the unchanged committed `uv.lock`; the old fingerprint
did not match those bytes and failed under the first frozen CI run.
The benchmark is a synchronized Gaussian microbenchmark, not
RAW-to-film time. Its allocated-byte count is not process peak memory.

## Promotion gates and next work

Before connecting any production node, compare the full spatial chain against
its intended CPU oracle AND the existing MLX FFT path. Report their differences;
do not relabel a model change as an optimization. Check borders, impulses,
large sigma, mixed channels, HDR values, and 12/50 MP workloads on the same
machine with matched settings. Run the existing precision staircase and the
complete non-GUI suite. Keep the current backend as default until these pass.

Then add grain under a separate, versioned sampling contract. A Philox stream
cannot promise the existing MLX realization bit for bit. Test distribution,
spatial/channel correlation and PSD without weakening current gates. Full
negative caching and texture interop follow only after lifecycle tests pass.
Do not duplicate profile or colour setup in C++ merely to remove Python.
