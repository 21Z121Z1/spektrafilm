# Commands Run

本文件只记录本次 `analysis/metal_float32_precision/` 研究相关命令。未读取本地既有 README/docs/reports/notes/markdown/rst/txt 叙述性文件。

```bash
git status --short --branch
mkdir -p analysis/metal_float32_precision/results
.venv/bin/python -m py_compile analysis/metal_float32_precision/measure_precision.py
.venv/bin/python analysis/metal_float32_precision/measure_precision.py --inventory-only --results-dir analysis/metal_float32_precision/results/inventory
.venv/bin/python analysis/metal_float32_precision/measure_precision.py --synthetic-only --synthetic-size 64 --deterministic --results-dir analysis/metal_float32_precision/results/synthetic_64
.venv/bin/python analysis/metal_float32_precision/measure_precision.py --deterministic --max-working-size 128 --results-dir analysis/metal_float32_precision/results/raw_128 --samples \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4557.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/04_批量导出_转换与预览/converted_DNG/IMG_0342_converted.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/01_散片原始DNG/IMG20260603204611..dng' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/08_小归档_Archive1_DNG/IMG_9333.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260531_IDG_131302_390/IMG_2972.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/02_转换DNG/IDG_20260410_140916_153_converted.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/03_成组拍摄/20260528_IMG_4897/IMG_4897.DNG' \
  '/Users/retriedstormtrooper/Downloads/03_图片素材/RAW_DNG照片/07_历史批量归档_DNG/IMG_4536.DNG'
.venv/bin/python -m pytest --ignore=tests/gui -q
rm -rf analysis/metal_float32_precision/__pycache__
find analysis/metal_float32_precision/results -maxdepth 1 -type f -delete
```

辅助只读检查命令使用过 `rg`、`nl -ba ... | sed -n ...`、`cat`、`wc -l`、`find` 和短 Python 片段汇总 CSV/JSON 指标；这些命令只读取源码、测试、配置、样片清单和本次新建的分析结果。

验证结果：

- `measure_precision.py --inventory-only`: 成功，`sample_inventory.csv` 记录 754 个 RAW/DNG 文件。
- `measure_precision.py --synthetic-only --synthetic-size 64 --deterministic`: 成功，5 个合成样例全部完成，PNG16 roundtrip 成功。
- `measure_precision.py --deterministic --max-working-size 128 --samples ...`: 成功，8 张 RAW/DNG 样片全部完成，PNG16 roundtrip 成功。
- `.venv/bin/python -m pytest --ignore=tests/gui -q`: `1486 passed, 7 skipped, 4 warnings in 108.10s`。
