> 这是英文原文的中文翻译。权威版本请参考英文原文。

# 曲线分析语料库

本目录主要是胶片+相纸 HDR 曲线行为的生成文档。核心结论在摘要报告中：HDR 映射应依赖于胶片型号与打印相纸的联合响应，而非仅依赖胶片或相纸单独的特性。

## 入口

| 路径 | 用途 |
| --- | --- |
| [`film_print_hdr_analysis.md`](film_print_hdr_analysis.md) | 人工摘要与工程解读。请从这里开始阅读。 |
| [`curve_analysis.json`](curve_analysis.json) | 机器可读的分析数据。 |
| [`analyze_curves.py`](analyze_curves.py) | 将胶片/相纸组合通过模拟器运行并拟合曲线的脚本。 |
| [`generate_all_md.py`](generate_all_md.py) | 从 `curve_analysis.json` 生成各组合 Markdown 报告的脚本。 |

## 生成的报告

共有 160 份各组合的 Markdown 报告，命名格式为：

```text
<film>_on_<paper>.md
```

语料库涵盖 20 种胶片变体和 8 种打印相纸配置文件。调查特定配置文件对时请使用各组合文件；否则请优先参考摘要报告。

## 维护说明

- 除非有意修正生成器输出，否则不要手动编辑生成的各组合报告。
- 如果 `curve_analysis.json` 发生变化，请使用 `generate_all_md.py` 重新生成各组合的 Markdown 文件，以保持语料库的一致性。
- 更改 HDR 曲线配置逻辑时，请确保摘要报告与生成数据保持一致。
