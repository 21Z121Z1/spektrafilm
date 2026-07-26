# Spektrafilm Profile 字段级来源追溯矩阵 (Provenance Matrix)

**报告日期**: 2026-07-04  

本矩阵对 Spektrafilm 全套 28 个内置 profile 的 9 个核心物理字段逐一核查，建立可追溯的分类（Classification）与证据链。

### 修复层级定义 (Repair Tiers)
- **`Tier 0`**: 仅需文档/元数据修复。
- **`Tier 1`**: 可使用公开资料与物理先验进行受约束拟合（Constrained Refit），不需实物测量。
- **`Tier 2`**: 必须依赖物理实体胶片、标准冲洗及分光密度计进行重新测量（Physical Measurement）。

## 字段级追溯矩阵

| Profile | Field | Source support | Classification | Evidence | Notes | Repair tier |
| ------- | ----- | -------------- | -------------- | -------- | ----- | ----------- |
| `fujifilm_c200` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_c200` | `log_sensitivity` | FUJI_C200 | `direct-source` | `FUJI_C200` (p. 4) | - | `Tier 0` |
| `fujifilm_c200` | `channel_density` | FUJI_C200 | `reconstructed` | `FUJI_C200` (p. 4) | - | `Tier 1` |
| `fujifilm_c200` | `base_density` | FUJI_C200 | `source-composite` | `FUJI_C200` (p. 4) | - | `Tier 1` |
| `fujifilm_c200` | `midscale_neutral_density` | FUJI_C200 | `source-composite` | `FUJI_C200` (p. 4) | - | `Tier 1` |
| `fujifilm_c200` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_c200` | `density_curves` | FUJI_C200 | `optimized` | `FUJI_C200` (p. 3) | - | `Tier 0` |
| `fujifilm_c200` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_c200` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_crystal_archive_typeii` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_crystal_archive_typeii` | `log_sensitivity` | FUJI_CRYSTAL_ARCHIVE_II | `direct-source` | `FUJI_CRYSTAL_ARCHIVE_II` (p. 5) | - | `Tier 0` |
| `fujifilm_crystal_archive_typeii` | `channel_density` | FUJI_CRYSTAL_ARCHIVE_II | `direct-source` | `FUJI_CRYSTAL_ARCHIVE_II` (p. 5) | - | `Tier 0` |
| `fujifilm_crystal_archive_typeii` | `base_density` | None | `derived-from-related-profile` | Inherited from `fields.base_density of kodak_supra_endura` | - | `Tier 1` |
| `fujifilm_crystal_archive_typeii` | `midscale_neutral_density` | FUJI_CRYSTAL_ARCHIVE_II | `reconstructed` | `FUJI_CRYSTAL_ARCHIVE_II` (p. 5) | - | `Tier 1` |
| `fujifilm_crystal_archive_typeii` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_crystal_archive_typeii` | `density_curves` | FUJI_CRYSTAL_ARCHIVE_II | `optimized` | `FUJI_CRYSTAL_ARCHIVE_II` (p. 4) | - | `Tier 0` |
| `fujifilm_crystal_archive_typeii` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_crystal_archive_typeii` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_pro_400h` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_pro_400h` | `log_sensitivity` | FUJI_PRO_400H | `direct-source` | `FUJI_PRO_400H` (p. 4) | Schema limit: discarded 4th color layer (cyan-green). 3-ch dimension reduction. | `Tier 0` |
| `fujifilm_pro_400h` | `channel_density` | FUJI_PRO_400H | `reconstructed` | `FUJI_PRO_400H` (p. 4) | - | `Tier 1` |
| `fujifilm_pro_400h` | `base_density` | FUJI_PRO_400H | `source-composite` | `FUJI_PRO_400H` (p. 4) | - | `Tier 1` |
| `fujifilm_pro_400h` | `midscale_neutral_density` | FUJI_PRO_400H | `source-composite` | `FUJI_PRO_400H` (p. 4) | - | `Tier 1` |
| `fujifilm_pro_400h` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_pro_400h` | `density_curves` | FUJI_PRO_400H | `optimized` | `FUJI_PRO_400H` (p. 3) | Sensitometric curves RMSE = 0.345D against Status M/A datasheet. | `Tier 0` |
| `fujifilm_pro_400h` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_pro_400h` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_provia_100f` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_provia_100f` | `log_sensitivity` | FUJI_PROVIA_100F | `direct-source` | `FUJI_PROVIA_100F` (p. 4) | - | `Tier 0` |
| `fujifilm_provia_100f` | `channel_density` | FUJI_PROVIA_100F | `direct-source` | `FUJI_PROVIA_100F` (p. 4) | - | `Tier 0` |
| `fujifilm_provia_100f` | `base_density` | FUJI_PROVIA_100F | `direct-source` | `FUJI_PROVIA_100F` (p. 4) | - | `Tier 0` |
| `fujifilm_provia_100f` | `midscale_neutral_density` | FUJI_PROVIA_100F | `reconstructed` | `FUJI_PROVIA_100F` (p. 4) | - | `Tier 0` |
| `fujifilm_provia_100f` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_provia_100f` | `density_curves` | FUJI_PROVIA_100F | `optimized` | `FUJI_PROVIA_100F` (p. 3) | - | `Tier 0` |
| `fujifilm_provia_100f` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `fujifilm_provia_100f` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `fujifilm_velvia_100` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_velvia_100` | `log_sensitivity` | FUJI_VELVIA_100 | `direct-source` | `FUJI_VELVIA_100` (p. 4) | - | `Tier 0` |
| `fujifilm_velvia_100` | `channel_density` | FUJI_VELVIA_100 | `direct-source` | `FUJI_VELVIA_100` (p. 4) | - | `Tier 0` |
| `fujifilm_velvia_100` | `base_density` | FUJI_VELVIA_100 | `direct-source` | `FUJI_VELVIA_100` (p. 4) | - | `Tier 0` |
| `fujifilm_velvia_100` | `midscale_neutral_density` | FUJI_VELVIA_100 | `reconstructed` | `FUJI_VELVIA_100` (p. 4) | - | `Tier 0` |
| `fujifilm_velvia_100` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_velvia_100` | `density_curves` | FUJI_VELVIA_100 | `optimized` | `FUJI_VELVIA_100` (p. 3) | - | `Tier 0` |
| `fujifilm_velvia_100` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `fujifilm_velvia_100` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `fujifilm_xtra_400` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_xtra_400` | `log_sensitivity` | FUJI_XTRA_400 | `direct-source` | `FUJI_XTRA_400` (p. 4) | - | `Tier 0` |
| `fujifilm_xtra_400` | `channel_density` | FUJI_XTRA_400 | `reconstructed` | `FUJI_XTRA_400` (p. 4) | - | `Tier 1` |
| `fujifilm_xtra_400` | `base_density` | FUJI_XTRA_400 | `source-composite` | `FUJI_XTRA_400` (p. 4) | - | `Tier 1` |
| `fujifilm_xtra_400` | `midscale_neutral_density` | FUJI_XTRA_400 | `source-composite` | `FUJI_XTRA_400` (p. 4) | - | `Tier 1` |
| `fujifilm_xtra_400` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `fujifilm_xtra_400` | `density_curves` | FUJI_XTRA_400 | `optimized` | `FUJI_XTRA_400` (p. 3) | - | `Tier 0` |
| `fujifilm_xtra_400` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `fujifilm_xtra_400` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_2383` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_2383` | `log_sensitivity` | KODAK_2383 | `direct-source` | `KODAK_2383` (p. 4) | Audit comparison R/G/B peaks. MAE = 1.449 log10. | `Tier 0` |
| `kodak_2383` | `channel_density` | KODAK_2383 | `source-composite` | `KODAK_2383` (p. 4) | - | `Tier 1` |
| `kodak_2383` | `base_density` | KODAK_2383 | `reconstructed` | `KODAK_2383` (p. 4) | - | `Tier 1` |
| `kodak_2383` | `midscale_neutral_density` | KODAK_2383 | `reconstructed` | `KODAK_2383` (p. 4) | - | `Tier 1` |
| `kodak_2383` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_2383` | `density_curves` | KODAK_2383 | `optimized` | `KODAK_2383` (p. 3) | Sensitometric curves RMSE = 1.597D against Status M/A datasheet. | `Tier 0` |
| `kodak_2383` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_2383` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_2393` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_2393` | `log_sensitivity` | KODAK_2393 | `direct-source` | `KODAK_2393` (p. 4) | - | `Tier 0` |
| `kodak_2393` | `channel_density` | KODAK_2393 | `source-composite` | `KODAK_2393` (p. 4) | - | `Tier 1` |
| `kodak_2393` | `base_density` | KODAK_2393 | `reconstructed` | `KODAK_2393` (p. 4) | - | `Tier 1` |
| `kodak_2393` | `midscale_neutral_density` | KODAK_2393 | `reconstructed` | `KODAK_2393` (p. 4) | - | `Tier 1` |
| `kodak_2393` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_2393` | `density_curves` | KODAK_2393 | `optimized` | `KODAK_2393` (p. 3) | - | `Tier 0` |
| `kodak_2393` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_2393` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ektachrome_100` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektachrome_100` | `log_sensitivity` | KODAK_E100 | `direct-source` | `KODAK_E100` (p. 5) | - | `Tier 0` |
| `kodak_ektachrome_100` | `channel_density` | KODAK_E100 | `direct-source` | `KODAK_E100` (p. 5) | - | `Tier 0` |
| `kodak_ektachrome_100` | `base_density` | KODAK_E100 | `direct-source` | `KODAK_E100` (p. 5) | - | `Tier 0` |
| `kodak_ektachrome_100` | `midscale_neutral_density` | KODAK_E100 | `reconstructed` | `KODAK_E100` (p. 5) | - | `Tier 0` |
| `kodak_ektachrome_100` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektachrome_100` | `density_curves` | KODAK_E100 | `optimized` | `KODAK_E100` (p. 5) | - | `Tier 0` |
| `kodak_ektachrome_100` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_ektachrome_100` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_ektacolor_edge` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektacolor_edge` | `log_sensitivity` | KODAK_EKTACOLOR_EDGE | `direct-source` | `KODAK_EKTACOLOR_EDGE` (p. 5) | - | `Tier 0` |
| `kodak_ektacolor_edge` | `channel_density` | KODAK_EKTACOLOR_EDGE | `direct-source` | `KODAK_EKTACOLOR_EDGE` (p. 5) | - | `Tier 0` |
| `kodak_ektacolor_edge` | `base_density` | KODAK_EKTACOLOR_EDGE | `source-composite` | `KODAK_EKTACOLOR_EDGE` (p. 5) | - | `Tier 1` |
| `kodak_ektacolor_edge` | `midscale_neutral_density` | KODAK_EKTACOLOR_EDGE | `reconstructed` | `KODAK_EKTACOLOR_EDGE` (p. 5) | - | `Tier 1` |
| `kodak_ektacolor_edge` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektacolor_edge` | `density_curves` | KODAK_EKTACOLOR_EDGE | `optimized` | `KODAK_EKTACOLOR_EDGE` (p. 4) | - | `Tier 0` |
| `kodak_ektacolor_edge` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ektacolor_edge` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ektar_100` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektar_100` | `log_sensitivity` | KODAK_E4046 | `direct-source` | `KODAK_E4046` (p. 5) | - | `Tier 0` |
| `kodak_ektar_100` | `channel_density` | KODAK_E4046 | `reconstructed` | `KODAK_E4046` (p. 5) | - | `Tier 1` |
| `kodak_ektar_100` | `base_density` | KODAK_E4046 | `source-composite` | `KODAK_E4046` (p. 5) | - | `Tier 1` |
| `kodak_ektar_100` | `midscale_neutral_density` | KODAK_E4046 | `source-composite` | `KODAK_E4046` (p. 5) | - | `Tier 1` |
| `kodak_ektar_100` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ektar_100` | `density_curves` | KODAK_E4046 | `optimized` | `KODAK_E4046` (p. 5) | - | `Tier 0` |
| `kodak_ektar_100` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ektar_100` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_endura_premier` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_endura_premier` | `log_sensitivity` | KODAK_ENDURA_PREMIER | `direct-source` | `KODAK_ENDURA_PREMIER` (p. 5) | - | `Tier 0` |
| `kodak_endura_premier` | `channel_density` | KODAK_ENDURA_PREMIER | `direct-source` | `KODAK_ENDURA_PREMIER` (p. 5) | - | `Tier 0` |
| `kodak_endura_premier` | `base_density` | KODAK_ENDURA_PREMIER | `source-composite` | `KODAK_ENDURA_PREMIER` (p. 5) | - | `Tier 1` |
| `kodak_endura_premier` | `midscale_neutral_density` | KODAK_ENDURA_PREMIER | `reconstructed` | `KODAK_ENDURA_PREMIER` (p. 5) | - | `Tier 1` |
| `kodak_endura_premier` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_endura_premier` | `density_curves` | KODAK_ENDURA_PREMIER | `optimized` | `KODAK_ENDURA_PREMIER` (p. 4) | - | `Tier 0` |
| `kodak_endura_premier` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_endura_premier` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_gold_200` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_gold_200` | `log_sensitivity` | KODAK_E7022 | `direct-source` | `KODAK_E7022` (p. 4) | - | `Tier 0` |
| `kodak_gold_200` | `channel_density` | KODAK_E7022 | `reconstructed` | `KODAK_E7022` (p. 4) | - | `Tier 1` |
| `kodak_gold_200` | `base_density` | KODAK_E7022 | `source-composite` | `KODAK_E7022` (p. 4) | - | `Tier 1` |
| `kodak_gold_200` | `midscale_neutral_density` | KODAK_E7022 | `source-composite` | `KODAK_E7022` (p. 4) | - | `Tier 1` |
| `kodak_gold_200` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_gold_200` | `density_curves` | KODAK_E7022 | `optimized` | `KODAK_E7022` (p. 3) | - | `Tier 0` |
| `kodak_gold_200` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_gold_200` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_kodachrome_64` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_kodachrome_64` | `log_sensitivity` | KODAK_K64 | `direct-source` | `KODAK_K64` (p. 6) | - | `Tier 0` |
| `kodak_kodachrome_64` | `channel_density` | KODAK_K64 | `direct-source` | `KODAK_K64` (p. 6) | - | `Tier 0` |
| `kodak_kodachrome_64` | `base_density` | KODAK_K64 | `direct-source` | `KODAK_K64` (p. 6) | - | `Tier 0` |
| `kodak_kodachrome_64` | `midscale_neutral_density` | KODAK_K64 | `reconstructed` | `KODAK_K64` (p. 6) | - | `Tier 0` |
| `kodak_kodachrome_64` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_kodachrome_64` | `density_curves` | KODAK_K64 | `optimized` | `KODAK_K64` (p. 5) | - | `Tier 0` |
| `kodak_kodachrome_64` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_kodachrome_64` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_portra_160` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_160` | `log_sensitivity` | KODAK_E4051 | `direct-source` | `KODAK_E4051` (p. 6) | - | `Tier 0` |
| `kodak_portra_160` | `channel_density` | KODAK_E4051 | `reconstructed` | `KODAK_E4051` (p. 6) | - | `Tier 1` |
| `kodak_portra_160` | `base_density` | KODAK_E4051 | `source-composite` | `KODAK_E4051` (p. 6) | - | `Tier 1` |
| `kodak_portra_160` | `midscale_neutral_density` | KODAK_E4051 | `source-composite` | `KODAK_E4051` (p. 6) | - | `Tier 1` |
| `kodak_portra_160` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_160` | `density_curves` | KODAK_E4051 | `optimized` | `KODAK_E4051` (p. 5) | - | `Tier 0` |
| `kodak_portra_160` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_160` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_400` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_400` | `log_sensitivity` | KODAK_E4050 | `direct-source` | `KODAK_E4050` (p. 6) | Audit comparison R/G/B peaks. MAE = 0.834 log10. | `Tier 0` |
| `kodak_portra_400` | `channel_density` | KODAK_E4050 | `reconstructed` | `KODAK_E4050` (p. 6) | - | `Tier 1` |
| `kodak_portra_400` | `base_density` | KODAK_E4050 | `source-composite` | `KODAK_E4050` (p. 6) | - | `Tier 1` |
| `kodak_portra_400` | `midscale_neutral_density` | KODAK_E4050 | `source-composite` | `KODAK_E4050` (p. 6) | - | `Tier 1` |
| `kodak_portra_400` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_400` | `density_curves` | KODAK_E4050 | `optimized` | `KODAK_E4050` (p. 5) | Sensitometric curves RMSE = 0.287D against Status M/A datasheet. | `Tier 0` |
| `kodak_portra_400` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_400` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_800` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800` | `log_sensitivity` | KODAK_E4040 | `direct-source` | `KODAK_E4040` (p. 6) | Audit comparison R/G/B peaks. MAE = 0.943 log10. | `Tier 0` |
| `kodak_portra_800` | `channel_density` | KODAK_E4040 | `reconstructed` | `KODAK_E4040` (p. 6) | - | `Tier 1` |
| `kodak_portra_800` | `base_density` | KODAK_E4040 | `source-composite` | `KODAK_E4040` (p. 6) | - | `Tier 1` |
| `kodak_portra_800` | `midscale_neutral_density` | KODAK_E4040 | `source-composite` | `KODAK_E4040` (p. 6) | - | `Tier 1` |
| `kodak_portra_800` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800` | `density_curves` | KODAK_E4040 | `optimized` | `KODAK_E4040` (p. 5) | Sensitometric curves RMSE = 0.342D against Status M/A datasheet. | `Tier 0` |
| `kodak_portra_800` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_800` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_800_push1` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800_push1` | `log_sensitivity` | None | `derived-from-related-profile` | Inherited from `fields.log_sensitivity of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push1` | `channel_density` | None | `derived-from-related-profile` | Inherited from `fields.channel_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push1` | `base_density` | None | `derived-from-related-profile` | Inherited from `fields.base_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push1` | `midscale_neutral_density` | None | `derived-from-related-profile` | Inherited from `fields.midscale_neutral_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push1` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800_push1` | `density_curves` | KODAK_E4040 | `optimized` | `KODAK_E4040` (p. 5) | - | `Tier 0` |
| `kodak_portra_800_push1` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_portra_800_push1` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_portra_800_push2` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800_push2` | `log_sensitivity` | None | `derived-from-related-profile` | Inherited from `fields.log_sensitivity of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push2` | `channel_density` | None | `derived-from-related-profile` | Inherited from `fields.channel_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push2` | `base_density` | None | `derived-from-related-profile` | Inherited from `fields.base_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push2` | `midscale_neutral_density` | None | `derived-from-related-profile` | Inherited from `fields.midscale_neutral_density of kodak_portra_800` | - | `Tier 1` |
| `kodak_portra_800_push2` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_800_push2` | `density_curves` | KODAK_E4040 | `optimized` | `KODAK_E4040` (p. 5) | - | `Tier 0` |
| `kodak_portra_800_push2` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_portra_800_push2` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 0` |
| `kodak_portra_endura` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_endura` | `log_sensitivity` | KODAK_PORTRA_ENDURA | `direct-source` | `KODAK_PORTRA_ENDURA` (p. 6) | - | `Tier 0` |
| `kodak_portra_endura` | `channel_density` | KODAK_PORTRA_ENDURA | `direct-source` | `KODAK_PORTRA_ENDURA` (p. 6) | - | `Tier 0` |
| `kodak_portra_endura` | `base_density` | KODAK_PORTRA_ENDURA | `source-composite` | `KODAK_PORTRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_portra_endura` | `midscale_neutral_density` | KODAK_PORTRA_ENDURA | `reconstructed` | `KODAK_PORTRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_portra_endura` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_portra_endura` | `density_curves` | KODAK_PORTRA_ENDURA | `optimized` | `KODAK_PORTRA_ENDURA` (p. 5) | - | `Tier 0` |
| `kodak_portra_endura` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_portra_endura` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_supra_endura` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_supra_endura` | `log_sensitivity` | None | `derived-from-related-profile` | Inherited from `fields.log_sensitivity of kodak_portra_endura` | - | `Tier 1` |
| `kodak_supra_endura` | `channel_density` | KODAK_SUPRA_ENDURA | `direct-source` | `KODAK_SUPRA_ENDURA` (p. 6) | - | `Tier 0` |
| `kodak_supra_endura` | `base_density` | KODAK_SUPRA_ENDURA | `source-composite` | `KODAK_SUPRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_supra_endura` | `midscale_neutral_density` | KODAK_SUPRA_ENDURA | `reconstructed` | `KODAK_SUPRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_supra_endura` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_supra_endura` | `density_curves` | KODAK_SUPRA_ENDURA | `optimized` | `KODAK_SUPRA_ENDURA` (p. 5) | - | `Tier 0` |
| `kodak_supra_endura` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_supra_endura` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ultra_endura` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ultra_endura` | `log_sensitivity` | KODAK_ULTRA_ENDURA | `direct-source` | `KODAK_ULTRA_ENDURA` (p. 6) | - | `Tier 0` |
| `kodak_ultra_endura` | `channel_density` | KODAK_ULTRA_ENDURA | `direct-source` | `KODAK_ULTRA_ENDURA` (p. 6) | - | `Tier 0` |
| `kodak_ultra_endura` | `base_density` | KODAK_ULTRA_ENDURA | `source-composite` | `KODAK_ULTRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_ultra_endura` | `midscale_neutral_density` | KODAK_ULTRA_ENDURA | `reconstructed` | `KODAK_ULTRA_ENDURA` (p. 6) | - | `Tier 1` |
| `kodak_ultra_endura` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ultra_endura` | `density_curves` | KODAK_ULTRA_ENDURA | `optimized` | `KODAK_ULTRA_ENDURA` (p. 5) | - | `Tier 0` |
| `kodak_ultra_endura` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ultra_endura` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ultramax_400` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ultramax_400` | `log_sensitivity` | KODAK_UM400 | `direct-source` | `KODAK_UM400` (p. 4) | - | `Tier 0` |
| `kodak_ultramax_400` | `channel_density` | KODAK_UM400 | `reconstructed` | `KODAK_UM400` (p. 4) | - | `Tier 1` |
| `kodak_ultramax_400` | `base_density` | KODAK_UM400 | `source-composite` | `KODAK_UM400` (p. 4) | - | `Tier 1` |
| `kodak_ultramax_400` | `midscale_neutral_density` | KODAK_UM400 | `source-composite` | `KODAK_UM400` (p. 4) | - | `Tier 1` |
| `kodak_ultramax_400` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_ultramax_400` | `density_curves` | KODAK_UM400 | `optimized` | `KODAK_UM400` (p. 3) | - | `Tier 0` |
| `kodak_ultramax_400` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_ultramax_400` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_verita_200d` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_verita_200d` | `log_sensitivity` | KODAK_VERITA_LAUNCH | `direct-source` | `KODAK_VERITA_LAUNCH` (p. 1) | Audit comparison R/G/B peaks. MAE = 0.808 log10. | `Tier 0` |
| `kodak_verita_200d` | `channel_density` | KODAK_VERITA_LAUNCH | `reconstructed` | `KODAK_VERITA_LAUNCH` (p. 1) | - | `Tier 1` |
| `kodak_verita_200d` | `base_density` | KODAK_VERITA_LAUNCH | `source-composite` | `KODAK_VERITA_LAUNCH` (p. 1) | - | `Tier 1` |
| `kodak_verita_200d` | `midscale_neutral_density` | KODAK_VERITA_LAUNCH | `source-composite` | `KODAK_VERITA_LAUNCH` (p. 1) | - | `Tier 1` |
| `kodak_verita_200d` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_verita_200d` | `density_curves` | KODAK_VERITA_LAUNCH | `optimized` | `KODAK_VERITA_LAUNCH` (p. 1) | Sensitometric curves RMSE = 0.364D against Status M/A datasheet. | `Tier 0` |
| `kodak_verita_200d` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_verita_200d` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_200t` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_200t` | `log_sensitivity` | KODAK_VISION3_COMMON | `direct-source` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_200t` | `channel_density` | KODAK_VISION3_COMMON | `reconstructed` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_200t` | `base_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_200t` | `midscale_neutral_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_200t` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_200t` | `density_curves` | KODAK_VISION3_COMMON | `optimized` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_200t` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_200t` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_250d` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_250d` | `log_sensitivity` | KODAK_VISION3_COMMON | `direct-source` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_250d` | `channel_density` | KODAK_VISION3_COMMON | `reconstructed` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_250d` | `base_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_250d` | `midscale_neutral_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_250d` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_250d` | `density_curves` | KODAK_VISION3_COMMON | `optimized` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_250d` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_250d` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_500t` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_500t` | `log_sensitivity` | KODAK_VISION3_COMMON | `direct-source` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | Audit comparison R/G/B peaks. MAE = 0.471 log10. | `Tier 0` |
| `kodak_vision3_500t` | `channel_density` | KODAK_VISION3_COMMON | `reconstructed` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_500t` | `base_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_500t` | `midscale_neutral_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_500t` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_500t` | `density_curves` | KODAK_VISION3_COMMON | `optimized` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | Sensitometric curves RMSE = 0.481D against Status M/A datasheet. | `Tier 0` |
| `kodak_vision3_500t` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_500t` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_50d` | `wavelengths` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_50d` | `log_sensitivity` | KODAK_VISION3_COMMON | `direct-source` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_50d` | `channel_density` | KODAK_VISION3_COMMON | `reconstructed` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_50d` | `base_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_50d` | `midscale_neutral_density` | KODAK_VISION3_COMMON | `source-composite` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 1` |
| `kodak_vision3_50d` | `log_exposure` | None | `generic` | N/A | - | `Tier 0` |
| `kodak_vision3_50d` | `density_curves` | KODAK_VISION3_COMMON | `optimized` | `KODAK_VISION3_COMMON` (p. H-24 datasheet section) | - | `Tier 0` |
| `kodak_vision3_50d` | `density_curves_layers` | None | `reconstructed` | N/A | - | `Tier 1` |
| `kodak_vision3_50d` | `density_curves_model` | None | `reconstructed` | N/A | - | `Tier 1` |
