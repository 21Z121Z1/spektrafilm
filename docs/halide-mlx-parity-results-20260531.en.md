> This is an English translation of the Chinese original. For the authoritative version, see the Chinese original.

# Halide / MLX Parity Results - 2026-05-31

## Scope

This result document covers the direct spectral runtime path, not the LUT shortcut path. The main validation uses the local 12.58MP DNG and a separate 2048x1536 resize with grain OFF, halation ON, `use_lut=False`, CPU float64 as the primary reference, and MLX float32 as the secondary reference.

Implemented changes in this working tree:

- Added fused Halide CMY-to-logXYZ and CMY-to-logRaw spectral pipelines.
- Routed `cmy_to_log_xyz_backend()` and print exposure to backend-specialized fused Halide methods when present.
- Preserved profile NaN semantics by zeroing NaN light inside fused Halide spectral kernels.
- Added a benchmark script that reports warm-up/JIT time, wall-clock time, synced stage time, final materialization, shape/dtype/backend metadata, conversion counts, and precision metrics.
- Relaxed spectral profile validation to allow profile-authored `NaN` spectral gaps while still rejecting infinities.

## Main Results

Input: `/Users/retriedstormtrooper/Documents/OPPO 互联/IMG20260530191638.dng`

Main config: `kodak_portra_400` / `kodak_portra_endura`, grain OFF, halation ON, direct spectral mode (`use_lut=False`).

| Size | CPU float64 best | MLX float32 best | Halide float32 best | Halide vs CPU | Halide vs MLX |
|---|---:|---:|---:|---:|---:|
| 2048x1536 | 11.181s | 1.150s | 1.546s | 7.23x faster | 1.34x slower |
| 3072x4096 full | 305.897s | 53.381s | 9.231s | 33.14x faster | 5.78x faster |

Precision against CPU float64:

| Size | MLX mean_diff / PSNR | Halide mean_diff / PSNR | Halide max_diff |
|---|---:|---:|---:|
| 2048x1536 | 1.2508e-03 / 54.10 dB | 1.2523e-03 / 54.09 dB | 4.5587e-02 |
| 3072x4096 full | 1.2524e-03 / 54.09 dB | 1.2527e-03 / 54.09 dB | 5.4178e-02 |

Halide meets the requested gates for the main configuration:

- Faster than CPU on both 2048x1536 and full 12.58MP.
- More than 2x faster than CPU at full resolution.
- At full resolution, faster than MLX in this measured direct spectral run.
- PSNR stays above 52 dB.
- Halide mean_diff is effectively the same as MLX mean_diff and below the 1.5x allowance.
- Halide max_diff stays below 6e-2, so no exception is needed.

## Artifacts

- Full 3072x4096 direct spectral grain OFF: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-124449.md`
- Full 3072x4096 direct spectral grain OFF JSON: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-124449.json`
- 2048x1536 direct spectral grain OFF: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-131211.md`
- 2048x1536 direct spectral grain OFF JSON: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-131211.json`
- 512x384 direct spectral grain ON smoke: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-131348.md`
- 512x384 direct spectral grain ON smoke JSON: `docs/dev/benchmark-artifacts/halide_mlx_parity_20260531/benchmark-20260531-131348.json`

Older LUT-mode artifacts remain in the artifact directory as secondary context, but they are not the verdict for this request.

## Bottlenecks

The 12.58MP direct spectral synced stage breakdown shows the main win came from fused Halide print and scan spectral reductions:

| Stage | CPU | MLX | Halide |
|---|---:|---:|---:|
| film.expose | 5.7032s | 8.4035s | 3.1653s |
| film.develop | 1.6627s | 1.3856s | 1.4345s |
| print.expose | 144.6863s | 30.0314s | 1.0758s |
| scan | 151.6026s | 20.3281s | 1.6150s |

Remaining Halide costs are still visible in conversion counters:

- Full direct wall run: 26 `backend.asarray`, 18 `backend.to_numpy`, and 30 `halide.Buffer` constructions.
- Full direct wall run moved about 2.81GB through `backend.asarray`, 2.91GB through `backend.to_numpy`, and 576MB through Halide buffers.

Halide should remain experimental because the Python JIT host-target boundary is still explicit and there are still avoidable NumPy crossings.

## Grain ON Smoke

512x384 direct spectral grain ON + halation ON completed without backend failures:

- CPU float64: 0.561s.
- MLX float32: 0.211s.
- Halide float32: 0.768s.

This is a compatibility smoke, not the primary precision gate. Grain changes the numerical envelope; the main acceptance metrics above use grain OFF as requested.

## Self-Audit

- Halide executed Halide paths: the artifacts record `selected_backend=halide`, Halide target data, `halide.Buffer` construction, and fused spectral stage timings.
- Timed runs exclude JIT/warm-up: artifacts report `warmup_seconds` separately.
- Stage timings are synchronized and final materialization appears as `final.asarray_float64`.
- Speed was not obtained by changing main semantics: grain OFF, halation ON, direct spectral mode, same DNG, same profiles, and full scan path were used.
- Halide output is finite and numerically comparable to CPU and MLX in the main config.
- Both 2048x1536 and full 3072x4096 inputs were tested.
- Grain ON smoke was tested and saved as an artifact.

## Next Work

- Reduce Halide `to_numpy`/`asarray` crossings in film and scan setup.
- Investigate persistent compiled Halide generators or AOT targets to reduce Python JIT and buffer boundary cost.
- Add visual diff artifacts if Halide moves beyond experimental status.
