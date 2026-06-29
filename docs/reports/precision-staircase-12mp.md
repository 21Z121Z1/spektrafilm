# Precision Staircase Report

## Environment

- python: `3.13.1`
- platform: `macOS-26.5.1-arm64-arm-64bit-Mach-O`
- numpy: `2.4.4`
- height: `3000`
- width: `4000`
- runs: `3`
- seed: `20260629`
- scenario: `smooth_ramp`
- selected_scenarios: `['smooth_ramp']`
- tile_rows: `375`
- MLX: `{'available': True, 'backend': 'mlx', 'precision': 'float32'}`

## Scope

This benchmark uses focused numeric probes for the named pipeline stages. It does not alter production defaults and does not claim complete production-stage coverage.

## Conclusion

- near_theoretical_limit_proven: `False`
- reason: The harness provides staircase evidence, but complete proof also requires production-stage hook coverage and review of any measured MLX tails.

## Scenario: smooth_ramp

- shape: `[3000, 4000, 3]`
- seed: `20260629`

### Timing Summary

- `cpu_float32_legacy.total`: median 6.073000s (min 5.867707s, max 6.586447s)
- `cpu_float32_same_order.total`: median 3.781036s (min 3.685301s, max 5.796778s)
- `cpu_float64.total`: median 8.096979s (min 6.316191s, max 8.728262s)
- `lut.mlx_fused_metal`: median 0.001669s (min 0.001134s, max 0.004214s)
- `lut.mlx_unfused_ops`: median 0.157404s (min 0.059848s, max 0.176200s)
- `lut.same_order`: median 0.068292s (min 0.058706s, max 0.083131s)
- `mlx_fused.printing_expose`: median 0.003490s (min 0.003120s, max 0.003952s)
- `mlx_fused.scanning_scan_film`: median 0.003228s (min 0.002656s, max 0.004388s)

### Representative Metrics

#### preprocess_input_conversion
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=2.98023e-08, mean_abs=1.01689e-08, rmse=1.31133e-08, psnr=157.646
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=2.98023e-08, mean_abs=1.01689e-08, rmse=1.31133e-08, psnr=157.646
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=0, mean_abs=0, rmse=0, psnr=inf

#### filming.expose
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=1.05312e-07, mean_abs=1.66696e-08, rmse=2.15306e-08, psnr=153.339
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=1.05312e-07, mean_abs=1.66696e-08, rmse=2.15306e-08, psnr=153.339
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=0, mean_abs=0, rmse=0, psnr=inf

#### filming.develop
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=7.99657e-08, mean_abs=1.63048e-08, rmse=2.06814e-08, psnr=153.688
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=7.99657e-08, mean_abs=1.63048e-08, rmse=2.06814e-08, psnr=153.688
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=0, mean_abs=0, rmse=0, psnr=inf

#### printing.expose
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=2.12034e-07, mean_abs=3.21694e-08, rmse=4.03086e-08, psnr=147.892
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=2.13592e-07, mean_abs=3.25903e-08, rmse=4.08327e-08, psnr=147.78
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=1.78814e-07, mean_abs=1.0962e-08, rmse=2.35189e-08, psnr=152.572

#### printing.develop
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=8.6057e-08, mean_abs=2.03782e-08, rmse=2.49751e-08, psnr=152.05
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=8.63466e-08, mean_abs=2.04094e-08, rmse=2.50146e-08, psnr=152.036
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=5.96046e-08, mean_abs=2.41217e-09, rmse=1.19907e-08, psnr=158.423

#### scanning.scan_film
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=2.76965e-07, mean_abs=6.08263e-08, rmse=7.28808e-08, psnr=142.748
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=2.6923e-07, mean_abs=6.10771e-08, rmse=7.32544e-08, psnr=142.703
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=2.38419e-07, mean_abs=1.30642e-08, rmse=3.94843e-08, psnr=148.072

#### scanning.scan_print
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=1.6306e-07, mean_abs=2.83803e-08, rmse=3.49692e-08, psnr=149.126
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=2.03317e-07, mean_abs=3.38966e-08, rmse=4.16038e-08, psnr=147.617
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=2.08616e-07, mean_abs=1.95691e-08, rmse=2.91832e-08, psnr=150.697

#### RouteMaster projection light_table
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=3.12412e-07, mean_abs=7.18075e-08, rmse=8.37697e-08, psnr=141.538
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=3.89346e-07, mean_abs=8.38647e-08, rmse=9.75998e-08, psnr=140.211
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=3.8743e-07, mean_abs=3.86817e-08, rmse=5.51321e-08, psnr=145.172

#### RouteMaster projection paper generic
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=3.45989e-07, mean_abs=7.44127e-08, rmse=8.71352e-08, psnr=141.196
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=3.99221e-07, mean_abs=8.66473e-08, rmse=1.01074e-07, psnr=139.907
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=3.8743e-07, mean_abs=3.97122e-08, rmse=5.65863e-08, psnr=144.946

#### paper chemical fallback
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=3.45989e-07, mean_abs=7.44127e-08, rmse=8.71352e-08, psnr=141.196
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=3.99221e-07, mean_abs=8.66473e-08, rmse=1.01074e-07, psnr=139.907
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=3.8743e-07, mean_abs=3.97122e-08, rmse=5.65863e-08, psnr=144.946

#### gain_map encode
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=5.37636e-07, mean_abs=1.31975e-07, rmse=1.54392e-07, psnr=136.228
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=6.4044e-07, mean_abs=1.48806e-07, rmse=1.73855e-07, psnr=135.196
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=6.55651e-07, mean_abs=8.46987e-08, rmse=1.11164e-07, psnr=139.081

#### final materialize
- `cpu_float32_legacy_vs_cpu_float64`: max_abs=3.45989e-07, mean_abs=7.44127e-08, rmse=8.71352e-08, psnr=141.196
- `cpu_float32_same_order_vs_cpu_float64`: max_abs=3.99221e-07, mean_abs=8.66473e-08, rmse=1.01074e-07, psnr=139.907
- `cpu_float32_same_order_vs_cpu_float32_legacy`: max_abs=3.8743e-07, mean_abs=3.97122e-08, rmse=5.65863e-08, psnr=144.946

### MLX Layers

- MLX fused spectral stage metrics are present in JSON.
