# Native prepared execution

Experimental extension of [the spatial foundation](native-metal-spatial.md).
Production CPU/MLX selection, profiles, defaults, locks and tolerances do not change.
No speed claim follows from another project's hardware or benchmark.

## Authority and boundary

Python prepares immutable constants from this repository's CPU implementation.
`program.py` compiles named mathematical operations into last-use buffer slots.
`executor.py` manages opaque C handles. `execution.mm` owns one Metal queue.
The shipped `.metallib` performs the arithmetic; MLX is not imported or required.
There is no second C++ implementation of profile fitting, filter coefficients,
DIR inversion, color science or photographic policy.

This is independent source, not a claim of an isolated clean room. The authoring
context previously included SpektraLab source. No SpektraLab source or assets are
imported. The numerical authorities are our CPU model and the published algorithms.

## Implemented contracts

- Programs are immutable, acyclic, channel-checked and content-fingerprinted.
  Dead nodes are pruned. Constants are interned. A slot is reused only after
  its last reader. Slot zero and external images remain immutable.
- All buffers use shared, tracked storage. Separate serial compute encoders
  order reuse without a CPU wait between nodes. One submission and one wait
  finish a program. Four status bytes return to the host, not each image.
- The pool holds only completed work. A live image pins its allocation, so a
  new render cannot overwrite an old result. The budget includes pooled and
  pinned buffers, constants, scratch and texture backing. It is buffer-byte
  accounting, not an RSS claim. Free pool entries can be trimmed explicitly.
- Gaussian FIR and IIR retain the original numerical contract. IIR uses a
  padded 32x32 threadgroup transpose and compensated recurrence. Weighted
  Gaussian accumulation can be fused into the final pass without removing
  its float32 rounding boundary.
- Prepared operators include affine, matrix, interpolation, spectral reduction,
  log/exp, multiplication, Gaussian, weighted Gaussian, layered grain and
  lognormal microstructure. Wavelengths stay in the register loop, not an HxWx81
  allocation. Missing density bands are neutralized as whole bands, not dyes.
- `prepare_spatial` implements serial CPU lens/scatter/bounce semantics.
  `prepare_development` implements real film log-exposure -> negative CMY,
  including canonical DIR setup and optional grain. Invalid inverse axes fail.
- `NativeSession` retains one source and one negative at any admitted resolution.
  Print-only program changes reuse the negative. Film constants, seed or source
  changes invalidate it. A failed film/print transaction cannot publish a new
  cache entry. There is no automatic unbounded LRU or 4 MP cutoff.
- `ResidentImage.texture()` packs RGB on the GPU into a leased RGBA32Float buffer
  texture, alpha one. No host image roundtrip occurs. This is not zero work and
  not a view of packed RGB. No color space is inferred or tagged. The consumer
  must finish external GPU reads before releasing the lease. Product UI wiring
  is not included. `TextureLease.numpy()` is explicit diagnostic readback only.

## Two distinct parity questions

Serial CPU spatial filtering is **not** the existing MLX fused-FFT algorithm.
For example, the CPU exponential-fit amplitudes sum to 0.9999. The MLX FFT path
renormalizes them. Replacing that path cannot be called a bit-identical change.
Keep the old path until a separately reviewed compatibility decision is made.

The new RNG contract is `philox4x32-10-thinned-poisson-v1`. Its key is the
64-bit seed; its counter is `(pixel-low, pixel-high, stream, block)`. Streams
0..8 identify dye sublayers/channels. Streams 9..11 identify independent
microstructure channels. The simple-grain mode uses streams 3*layer+channel.
Pixel origins must be supplied when partitioning independent draws. Spatial
blurs are full-frame: this does not make a tiled blur seam-free.

Poisson thinning replaces Poisson -> binomial with Poisson(lambda*p), an
identity of distributions, not random realizations. Knuth/PTRS samples are
not Gaussian approximations. The current MLX particle path does use normal
approximations; its bits are not this sampler's target. Float32 RNG acceptance
and 23-bit open-interval uniforms remain finite-precision arithmetic. Rates
outside [0, 2^20], a 256-attempt exhaustion, or non-finite results fail the
whole operation; none silently falls back to a different distribution.

## Use

```python
from spektrafilm.gpu.native_metal.executor import NativeExecutor
from spektrafilm.gpu.native_metal.program import Builder

b = Builder(3)
b.gaussian(0, (0.75, 3.0, 130.0))
with NativeExecutor("build/native") as executor:
    with executor.prepare(b.finish()) as program, executor.upload(rgb_float32) as source:
        output, stats = executor.run(program, source)
        with output:
            result = output.numpy()  # explicit terminal readback
```

Build explicitly; no import or render compiles code:

```sh
uv run --frozen python -m spektrafilm.gpu.native_metal.build --output build/native
uv run --frozen python -m pytest tests/native_metal -q
uv run --frozen python tests/native_metal/benchmark_execution.py \
  --bundle build/native --width 4000 --height 3000 --output /tmp/native-12mp.json
```

The existing CI native matrix picks up these tests. macOS must compile and run
Metal; missing tools/devices fail. Linux proves only host arithmetic and plans.
Checks include published Philox vectors, CPU float32/64 Gaussian parity,
transposed/untransposed and fused/unfused bit equality, real-profile DIR stages,
Poisson moments/PSD/correlations, global-pixel determinism, budget recovery,
cache failure transactions, handle concurrency and texture content/lifetime.
Numerical gates remain `atol=rtol=1e-6`; stochastic bars are fixed independently.

The benchmark measures **post-upsampling film stages**, not RAW-to-RGB or a full
print. It alternates CPU/native order, materializes both outputs, records the
input/program hashes and hardware, and asserts parity before reporting time.
A 50 MP run requires sufficient memory and is not implied by smaller tests.

## Not promoted

No backend-factory registration or default switch. Arbitrary camera/enlarger
diffusion PSFs are not replaced by Gaussian approximations. Spectral upsampling,
full print/scan/color/HDR output integration and the product UI still need their
own contracts. The native candidate is not yet a row in the existing full
precision staircase. Passing this operator/stage suite is not that missing gate.

## Algorithm references

- Apple, Metal Best Practices, Command Buffers: minimize submissions without
  starving the GPU. Resource tracking and ownership are still required.
  https://developer.apple.com/library/archive/documentation/3DDrawing/Conceptual/MTLBestPracticesGuide/CommandBuffers.html
- Salmon et al., *Parallel Random Numbers: As Easy as 1, 2, 3*, SC11.
  https://www.thesalmons.org/john/random123/papers/random123sc11.pdf
- The original author's Philox known-answer vectors:
  https://github.com/DEShawResearch/random123/blob/main/tests/kat_vectors
- Gaussian/halation/DIR/grain formulas: this repository's
  `utils/fast_gaussian_filter.py`, `model/diffusion.py`, `model/couplers.py`,
  `model/develop.py` and `model/grain.py`.
