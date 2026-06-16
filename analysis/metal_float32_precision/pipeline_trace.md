# Pipeline Trace: GUI RAW/DNG to Export

本文件只基于当前源码/测试代码追踪，未读取本地既有叙述性文档。

## Text Flow

`GUI file open/load RAW -> load_and_process_raw_file -> float32 scene RGB -> GuiState/build_params_from_state -> _prepare_simulation_input_image -> SimulationRequest/SimulationPipeline -> backend selection -> topology taps -> GUI preview display uint8/transform -> output layer float metadata -> SDR save_image_oiio OR HDR HEIC rerender via process_master/export_hdr_heic_from_simulator -> file encoder`

## Stage-by-Stage Trace

| Node | Code Evidence | Input / Output | CPU Path | MLX/Metal Path | Precision / Difference Risks |
|---|---|---|---|---|---|
| GUI RAW entry | `src/spektrafilm_gui/controller.py:244-258` `GuiController.load_raw_image` | path -> `image` | same loader | same loader | GUI raw controls pass white balance, temperature, tint, lens correction, input color space, input CCTF flag. |
| Lazy RAW loader wrapper | `src/spektrafilm_gui/controller.py:136-137` | function dispatch | same | same | Only dispatch wrapper; no precision change here. |
| RAW postprocess params | `src/spektrafilm/utils/raw_file_processor.py:83-130` | rawpy params | same | same | rawpy output is ACES, 16-bit, `no_auto_bright=True`, `gamma=(1,1)`; `as_shot` uses camera WB, other WB modes add colour-science adaptation. |
| RAW decode / linearize | `src/spektrafilm/utils/raw_file_processor.py:418-420` | rawpy 16-bit RGB -> float32/65535 | same | same | First hard precision boundary: RAW decode result becomes `np.float32`; CPU float64 reference begins after this point, not before demosaic. |
| RAW WB/tint/colorspace | `src/spektrafilm/utils/raw_file_processor.py:429-443`; tests `tests/test_raw_file_processor.py:96-109`, `tests/test_raw_smoke.py:10-15` | float32 linear ACES -> requested RGB, may remain float32 or colour-science return dtype | same | same | chromatic adaptation casts to float32; `colour.RGB_to_RGB` may compute internally with higher precision but loader return contract/test says float32 valid RGB. |
| GUI state -> params | `src/spektrafilm_gui/params_mapper.py:10-27`, `56-63`, `102-108` | `GuiState` -> `RuntimePhotoParams` | `compute_backend=cpu`, `materialize_policy` can be float64 | `compute_backend=mlx`, `gpu_precision=float32` | GUI forces output CCTF encoding true in params mapper and enables LUTs/resolution 17/fast stats. |
| GUI backend options | `src/spektrafilm_gui/options.py:80-96`; defaults `src/spektrafilm/runtime/params_schema.py:228-248` | enums/settings | CPU, auto, MLX, CuPy, Halide | MLX selected explicitly or auto if available | `GpuPrecision` exposes float64/float32, but GPU float64 is rejected by backend selector. |
| GUI input preparation | `src/spektrafilm_gui/controller.py:144-181`; called in `controller.py:896-908` and `976-984` | loaded image -> request image | non-MLX path `np.double(image_data)` | MLX float32 path `np.asarray(..., dtype=np.float32)` | The same decoded RAW source is promoted to float64 for CPU and kept/cast float32 for MLX. |
| Runtime construction | `src/spektrafilm/runtime/pipeline.py:73-123` | params -> backend, LUT/color services/stages | `select_backend(cpu)` -> `NumpyBackend` | `select_backend(mlx,float32)` -> `MlxBackend` | backend object is shared by LUT service and stage objects; cache/backend conversion can affect residency. |
| Backend selection | `src/spektrafilm/gpu/backend.py:72-122` | name/precision -> backend | explicit CPU returns NumPy; auto+float64 falls back CPU | float64 GPU rejected; auto prefers MLX then CuPy | There is no independent `metal_backend.py`; current Metal route is MLX through Apple Metal. |
| MLX dtype semantics | `src/spektrafilm/gpu/mlx_backend.py:12-40`, `56-75`, `167-172` | Python/NumPy -> MLX array -> NumPy | n/a | default dtype float32 for precision float32; only float32/float16 supported; `to_numpy` evals first | MLX path can be asynchronous until `eval`/`to_numpy`; `nan_to_num` uses float32 finite limits. |
| CPU dtype semantics | `src/spektrafilm/gpu/numpy_backend.py:20-79`; preprocess `pipeline.py:556-563` | arrays in NumPy | `_preprocess_base` uses `np.double` | n/a | CPU backend operations often inherit float64 because GUI/preprocess supplies double. |
| Topology taps | `src/spektrafilm/runtime/pipeline.py:871-886`; process hooks `228-239` | `rgb_in -> rgb_pre -> log_e_film -> cmy_film -> log_e_print -> cmy_print -> rgb_out` | same tap graph | same tap graph unless `scan_film` skips print taps | Existing topology taps are sufficient for non-invasive stage dumps. |
| Preprocess | CPU `pipeline.py:556-563`; MLX `602-663` | image -> RGB preprocessed | `np.double`, auto exposure, crop/rescale | `_backend_rgb_input` casts to backend dtype; crop can stay backend; resize falls back through CPU if upscale | crop/resize/auto exposure may cause backend differences; deterministic run disabled auto exposure and spatial stochastic effects. |
| Film expose | `src/spektrafilm/runtime/stages/filming.py:73-114` | RGB -> log exposure | NumPy/colour path, `np.log10(np.fmax(raw,0)+1e-10)` | backend kernels for RGB->raw, highlight boost, diffusion/blur/halation, `safe_log10_backend` | log/pow/fmax, spectral upsampling, blur/halation and backend kernels are major potential difference sources. |
| RGB -> tc / spectral mapping | `filming.py:163-191`; `gpu/kernels/color.py:219-251`; `gpu/kernels/lut.py:32-221`, `225-232` | RGB -> tc,b -> raw | `rgb_to_raw_hanatos2025`, CPU cubic LUT reference float64 | MLX float32 `rgb_to_tc_b_backend`, Metal 2D cubic LUT with `float`, output `mx.float32` | Algorithm intended to mirror CPU, but kernel arithmetic/interpolation is float32 and can differ from CPU float64 reference. |
| Film develop | `filming.py:116-129`; density kernels `gpu/kernels/density.py:68-117`, `126-181` | log exposure -> CMY density | CPU develop path | backend density interpolation kernels | endpoint clamp and interpolation in Metal `float`; precision and interpolation implementation are risk points. |
| Print expose | `src/spektrafilm/runtime/stages/printing.py:77-115`, `116-139` | CMY film -> log raw print | CPU spectral/LUT path | backend direct spectral calculation when LUT would diverge | Code intentionally avoids backend 3D LUT trilinear divergence for print/enlarger by direct GPU spectral fallback. |
| Print develop | `printing.py:189-211` | log print exposure -> CMY print | `develop_print_morph` | `interpolate_exposure_to_density_backend` | Interpolation and morphed curves are backend-specific implementation points. |
| Scanner spectral transform | `src/spektrafilm/runtime/stages/scanning.py:72-124`, `158-204`; `runtime/services/spectral_lut_compute.py:130-168` | density -> XYZ/RGB master | CPU direct/LUT spectral compute; direct CPU coerces float64 | GPU direct spectral fallback when LUT would be trilinear; backend `cmy_to_log_xyz_backend` | Measured error grows mainly around print/scan. Differences include float32 spectral sums, `pow(10)`, `log10`, matrix path. |
| Output gamut / CCTF / clip | `scanning.py:126-151`, `213-240`; `gpu/kernels/color.py:445-479` | route linear RGB -> display/output RGB | colour-science CCTF and NumPy clip | backend CCTF formulas and backend clip | Transfer functions, gamut compression, clip boundaries and unsupported color spaces can cause backend differences. |
| Materialization | `pipeline.py:898-917`; GUI export materialize `controller_runtime.py:434-451` | runtime value -> NumPy or backend | default `numpy_float64`; GUI export defaults to `np.float32` | `backend` policy can keep MLX until GUI materialize/export | Preview/export do not necessarily use the same dtype. |
| GUI preview | `src/spektrafilm_gui/controller_runtime.py:378-416` | scan -> display image | source materialized to NumPy, normalized, uint8; optional display transform | same, after materialization | Preview is uint8/display-transform oriented; it is not the same buffer as float export. |
| Output layer metadata | `controller_runtime.py:511-519`; `controller.py:921-938`, `963-1000`, `625-646` | display image + float image | stores float simulation output | stores float/MLX-backed output object until materialized | Output layer metadata carries float image and HDR sidecar. |
| SDR export | `controller.py:488-532`, `_save_output_kwargs` `556-568`; `utils/io.py:529-663`, `688-758` | output layer float or display -> encoder | `materialize_export_image(dtype=float32)`, optional colour conversion, `save_image_oiio` | same GUI layer, but source may originate from MLX path | PNG/JPEG clip to [0,1] and quantize; TIFF 16 clips; TIFF/EXR 32 casts float32; ICC/profile metadata can be embedded. |
| HDR HEIC export | `controller.py:403-451`; `hdr/routemaster_export.py:66-89`; `utils/io.py:643-663`; `utils/hdr_photo.py` float32/clip sites | current input + runtime simulator -> rerendered HDR pair -> HEIC/gain map | simulator rerender with current backend params | simulator rerender with current backend params | HEIC branch rerenders via `process_master`, not simply saving preview/output layer. HDR helpers cast/clip heavily to float32 and build gain map. This study did not decode HEIC roundtrip. |
| Metadata | `controller.py:460-485`, `519-544`; `utils/io.py:56-161` | source metadata -> output file | same | same | Metadata/ICC does not change measured numeric pipeline buffer, but can change downstream color interpretation. |

## Confirmed Measurement Hooks

`measure_precision.py` uses existing topology taps only:

- `rgb_in`
- `rgb_pre`
- `log_e_film`
- `cmy_film`
- `log_e_print`
- `cmy_print`
- `rgb_out`
- `materialized_rgb_out`
- `export_png16_roundtrip`

No production hook was added. Stages not exposed by existing topology, such as exact internal density spectral arrays, individual LUT samples, HDR gain-map internals, and encoder sidecar internals, are marked as not directly dumped.
