# Files Read

本次研究没有读取本地既有 README、docs、reports、notes、markdown/rst/txt 叙述性文件。读取范围限于源码、测试代码、样片目录索引、以及本次新建的分析产物。

## Source Files

- `src/spektrafilm/color_management.py`
- `src/spektrafilm/gpu/backend.py`
- `src/spektrafilm/gpu/mlx_backend.py`
- `src/spektrafilm/gpu/numpy_backend.py`
- `src/spektrafilm/gpu/kernels/color.py`
- `src/spektrafilm/gpu/kernels/lut.py`
- `src/spektrafilm/gpu/kernels/density.py`
- `src/spektrafilm/runtime/params_schema.py`
- `src/spektrafilm/runtime/pipeline.py`
- `src/spektrafilm/runtime/services/spectral_lut_compute.py`
- `src/spektrafilm/runtime/stages/filming.py`
- `src/spektrafilm/runtime/stages/printing.py`
- `src/spektrafilm/runtime/stages/scanning.py`
- `src/spektrafilm/utils/raw_file_processor.py`
- `src/spektrafilm/utils/io.py`
- `src/spektrafilm/utils/hdr_photo.py`
- `src/spektrafilm/hdr/routemaster_export.py`
- `src/spektrafilm_gui/controller.py`
- `src/spektrafilm_gui/controller_runtime.py`
- `src/spektrafilm_gui/params_mapper.py`
- `src/spektrafilm_gui/options.py`
- `src/spektrafilm_gui/state.py`

## Test Files

- `tests/test_raw_file_processor.py`
- `tests/test_raw_smoke.py`
- `tests/test_gpu_color_chain.py`
- `tests/test_pipeline_smoke.py`
- `tests/test_spectral_lut_service.py`
- `tests/test_upstream_parity.py`
- `tests/test_tier3_fixes.py`
- `tests/gui/test_controller_runtime_module.py`
- `tests/gui/test_controller_output.py`

## Analysis Files Created And Read

- `analysis/metal_float32_precision/measure_precision.py`
- `analysis/metal_float32_precision/sample_inventory.csv`
- `analysis/metal_float32_precision/measurement_config.json`
- `analysis/metal_float32_precision/per_sample_metrics.json`
- `analysis/metal_float32_precision/metrics_summary.csv`
- `analysis/metal_float32_precision/results/inventory/environment.json`
- `analysis/metal_float32_precision/results/inventory/measurement_config.json`
- `analysis/metal_float32_precision/results/inventory/selected_sample_candidates.csv`
- `analysis/metal_float32_precision/results/synthetic_64/environment.json`
- `analysis/metal_float32_precision/results/synthetic_64/measurement_config.json`
- `analysis/metal_float32_precision/results/synthetic_64/per_sample_metrics.json`
- `analysis/metal_float32_precision/results/synthetic_64/metrics_summary.csv`
- `analysis/metal_float32_precision/results/synthetic_64/stage_stats.csv`
- `analysis/metal_float32_precision/results/synthetic_64/failures.json`
- `analysis/metal_float32_precision/results/raw_128/environment.json`
- `analysis/metal_float32_precision/results/raw_128/measurement_config.json`
- `analysis/metal_float32_precision/results/raw_128/per_sample_metrics.json`
- `analysis/metal_float32_precision/results/raw_128/metrics_summary.csv`
- `analysis/metal_float32_precision/results/raw_128/stage_stats.csv`
- `analysis/metal_float32_precision/results/raw_128/failures.json`

## Sample Inputs

样片根目录：

- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片`

实际测量的 8 张样片：

- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4557.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/04_批量导出_转换与预览/converted_DNG/IMG_0342_converted.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/01_散片原始DNG/IMG20260603204611..dng`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/08_小归档_Archive1_DNG/IMG_9333.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260531_IDG_131302_390/IMG_2972.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/02_转换DNG/IDG_20260410_140916_153_converted.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260528_IMG_4897/IMG_4897.DNG`
- `/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4536.DNG`
