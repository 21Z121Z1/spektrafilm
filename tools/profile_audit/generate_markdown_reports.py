#!/usr/bin/env python3
"""Generate Markdown reports from the profile_sources.json database."""

import json
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_JSON_PATH = os.path.join(PROJECT_ROOT, "tools", "profile_audit", "profile_sources.json")
REGISTRY_MD_PATH = os.path.join(PROJECT_ROOT, "docs", "reports", "profile-source-registry-20260704.md")
MATRIX_MD_PATH = os.path.join(PROJECT_ROOT, "docs", "reports", "profile-field-provenance-matrix-20260704.md")

# Residual data manually integrated from audit_residuals.py run
RESIDUALS = {
    "kodak_portra_400": {"sens_mae": 0.834, "dens_mae": 0.249, "dens_rmse": 0.287},
    "kodak_portra_800": {"sens_mae": 0.943, "dens_mae": 0.295, "dens_rmse": 0.342},
    "fujifilm_pro_400h": {"sens_mae": 0.633, "dens_mae": 0.303, "dens_rmse": 0.345},
    "kodak_verita_200d": {"sens_mae": 0.808, "dens_mae": 0.311, "dens_rmse": 0.364},
    "kodak_vision3_500t": {"sens_mae": 0.471, "dens_mae": 0.417, "dens_rmse": 0.481},
    "kodak_2383": {"sens_mae": 1.449, "dens_mae": 1.278, "dens_rmse": 1.597}
}


def load_registry():
    with open(REGISTRY_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def build_registry_md(data):
    sources = data["sources"]
    profiles = data["profiles"]

    md = []
    md.append("# Spektrafilm Profile 官方技术来源注册表")
    md.append("\n**报告日期**: 2026-07-04  ")
    md.append("**审计版本**: v1.0.0-registry  \n")
    md.append("本注册表记录了 Spektrafilm 内置的 28 个胶卷与相纸 profile 的官方/近官方文献来源列表，用于为后续物理模型的可复现性提供技术支持。")
    
    md.append("\n## 官方技术文献数据库")
    md.append("\n| Source ID | 文献标题 | 厂商 | 文献代码 / 标识 | 年份 / 版本 | 官方/归档链接 | 级别 |")
    md.append("| --- | --- | --- | --- | --- | --- | --- |")
    
    for sid, info in sorted(sources.items()):
        url = info.get("url", "")
        url_link = f"[Link]({url})" if url else "N/A"
        md.append(
            f"| `{sid}` | {info['title']} | {info['manufacturer']} | `{info.get('publication_code', 'N/A')}` | {info.get('revision_date', info.get('year'))} | {url_link} | `{info['source_class']}` |"
        )

    md.append("\n## Profile 文献关联与支持摘要")
    for slug, prof in sorted(profiles.items()):
        md.append(f"\n### `{slug}` ({prof['info']['name']})")
        md.append(f"- **类型**: `{prof['info']['type']}`, **介质**: `{prof['info']['support']}`")
        
        # Gather unique sources for this profile
        p_sources = set()
        for f_name, f_info in prof["fields"].items():
            ev = f_info.get("evidence", {})
            if ev.get("source_id"):
                p_sources.add(ev["source_id"])
        
        if p_sources:
            md.append("- **关联数据源**:")
            for ps in sorted(p_sources):
                s_info = sources[ps]
                md.append(f"  - `{ps}`: *{s_info['title']}* (代码: `{s_info.get('publication_code', 'N/A')}`)")
        else:
            md.append("- **关联数据源**: 无直接官方文献 (全部继承自关联 profile 或为通用占位)")

    return "\n".join(md) + "\n"


def build_matrix_md(data):
    profiles = data["profiles"]
    
    md = []
    md.append("# Spektrafilm Profile 字段级来源追溯矩阵 (Provenance Matrix)")
    md.append("\n**报告日期**: 2026-07-04  \n")
    md.append("本矩阵对 Spektrafilm 全套 28 个内置 profile 的 9 个核心物理字段逐一核查，建立可追溯的分类（Classification）与证据链。")
    md.append("\n### 修复层级定义 (Repair Tiers)")
    md.append("- **`Tier 0`**: 仅需文档/元数据修复。")
    md.append("- **`Tier 1`**: 可使用公开资料与物理先验进行受约束拟合（Constrained Refit），不需实物测量。")
    md.append("- **`Tier 2`**: 必须依赖物理实体胶片、标准冲洗及分光密度计进行重新测量（Physical Measurement）。")

    md.append("\n## 字段级追溯矩阵")
    md.append("\n| Profile | Field | Source support | Classification | Evidence | Notes | Repair tier |")
    md.append("| ------- | ----- | -------------- | -------------- | -------- | ----- | ----------- |")

    for slug, prof in sorted(profiles.items()):
        name = prof["info"]["name"]
        refit_cand = prof["refit_spec"]["refit_candidate"]
        
        for f_name, f_info in prof["fields"].items():
            cls = f_info["classification"]
            ev = f_info.get("evidence", {})
            
            # Determine Tier
            if cls in ["reconstructed", "source-composite"]:
                tier = "`Tier 1`" if refit_cand else "`Tier 0`"
            elif cls == "derived-from-related-profile":
                tier = "`Tier 1`"
            elif cls == "unknown":
                tier = "`Tier 2`"
            else:
                tier = "`Tier 0`"
                
            # Evidence text
            ev_text = ""
            src_id = ev.get("source_id", "")
            if src_id:
                ev_text = f"`{src_id}` (p. {ev.get('page', 'N/A')})"
            elif ev.get("derived_from"):
                ev_text = f"Inherited from `{ev['derived_from']}`"
            elif f_info.get("search_history"):
                ev_text = f"Search history: {f_info['search_history']}"
            else:
                ev_text = "N/A"
                
            # Support text
            support = src_id if src_id else "None"
            
            # Notes text (include residuals if core audit group)
            notes = ""
            if slug in RESIDUALS:
                res = RESIDUALS[slug]
                if f_name == "log_sensitivity":
                    notes = f"Audit comparison R/G/B peaks. MAE = {res['sens_mae']:.3f} log10."
                elif f_name == "density_curves":
                    notes = f"Sensitometric curves RMSE = {res['dens_rmse']:.3f}D against Status M/A datasheet."
            
            if cls == "channel_density" and prof["info"]["type"] == "negative":
                notes = "Negative separate CMY curves are reconstructed/unmixed (Datasheet only has neutral/min composite)."
            if slug == "fujifilm_pro_400h" and f_name == "log_sensitivity":
                notes = "Schema limit: discarded 4th color layer (cyan-green). 3-ch dimension reduction."
            if not notes:
                notes = "-"
                
            md.append(
                f"| `{slug}` | `{f_name}` | {support} | `{cls}` | {ev_text} | {notes} | {tier} |"
            )

    return "\n".join(md) + "\n"


def main():
    data = load_registry()
    
    # 1. Registry MD
    reg_content = build_registry_md(data)
    with open(REGISTRY_MD_PATH, "w", encoding="utf-8") as f:
        f.write(reg_content)
    print(f"Generated: {REGISTRY_MD_PATH}")
    
    # 2. Matrix MD
    matrix_content = build_matrix_md(data)
    with open(MATRIX_MD_PATH, "w", encoding="utf-8") as f:
        f.write(matrix_content)
    print(f"Generated: {MATRIX_MD_PATH}")


if __name__ == "__main__":
    main()
