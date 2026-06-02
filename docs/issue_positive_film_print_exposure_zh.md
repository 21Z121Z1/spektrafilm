> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 为正片胶片选择打印配置文件后，打印曝光不起作用

## 摘要

使用正片胶片（如 `fujifilm_provia_100f`）时，选择打印配置文件后，`Print exposure` 不会影响预览。GUI 似乎仍保持在直扫胶片路径（`scan_film=True`），因此即使已选择打印配置文件，打印阶段仍被跳过。

## 复现步骤

1. 打开 GUI。
2. 导入 RAW/图像。
3. 选择胶片配置文件：`fujifilm_provia_100f`。
4. 选择打印配置文件：`fujifilm_crystal_archive_typeii`。
5. 调整 `Print exposure`。
6. 运行预览，或使用自动预览。

## 预期行为

用户明确选择打印配置文件后，预览应运行打印流程。`Print exposure` 应改变输出预览效果。

## 实际行为

调整 `Print exposure` 没有可见效果。对于正片胶片，状态仍保持 `scan_film=True`，因此运行时走的是直扫胶片路径，绕过了打印流程：

```python
if self.io.scan_film:
    rgb_scan = self._pipeline_scan_film(image)
else:
    rgb_scan = self._pipeline_print(image)
```

## 可能的原因

两个配置文件选择器连接到了同一个处理函数：

```python
widgets.simulation.film_stock.textActivated.connect(controller.apply_profile_defaults)
widgets.simulation.print_paper.textActivated.connect(controller.apply_profile_defaults)
```

该处理函数执行 `digest_after_selection()`，其中设置了：

```python
params.io.scan_film = bool(params.film.is_positive)
```

对于正片胶片，这意味着即使选择了打印配置文件，`scan_film` 仍为 `True`。

## 建议的修复方案

为胶片和打印配置文件选择分别使用独立的处理函数：

- 胶片配置文件选择可以保持当前的默认路径：正片胶片 `scan_film=True`，负片胶片 `False`。
- 打印配置文件选择应强制设置 `scan_film=False`，因为选择打印配置文件是明确要求预览/扫描打印流程的意图。

这样既保留了正片胶片的实用默认行为，又能在选择打印配置文件后使打印控件按预期工作。

## 备注

此问题与已关闭的 DIR 耦合剂数量行为问题无关。当前 `main` 分支对 `fujifilm_provia_100f`/`fujifilm_velvia_100` 使用绝对 DIR 耦合剂 gamma 预设值，因此此问题专门针对 GUI 路径选择和打印阶段控件。
