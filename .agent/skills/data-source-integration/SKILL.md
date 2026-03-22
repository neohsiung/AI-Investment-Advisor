---
name: data-source-integration
description: 建立與串接新數據源的標準化流程 (Standardized workflow for adding new data sources)
---

# Data Source Integration Skill

此技能定義了在 AI Investment Advisor 中新增數據源的標準步驟。

## 1. 配置註冊 (Configuration Registration)

- **檔案**: `src/config/data_source_matrix_config.py`
- **操作**: 將新數據源加入 `DATA_SOURCE_GROUPS`。
- **必要欄位**:
  - `id`: 唯一識別碼 (snake_case)
  - `name`: 顯示名稱
  - `url`: **官方設置/文檔連結** (必須提供)
  - `desc`: 繁體中文功能描述
  - `trigger_type`: `polling`, `live`, 或 `webhook`
  - `fields`: API Key 或連線參數定義（系統自動生成 `source_{id}_{field_key}` 儲存鍵名）。

## 2. 實作 Data Provider

- **路徑**: `src/data/providers/[provider_name]_provider.py`
- **操作**: 繼承 `BaseDataProvider` 並實作必要方法。
- **金鑰讀取**: 必須透過 `SettingsService.get("source_[id]_[field]")` 讀取（嚴禁 Hardcode）。

## 3. 整合與驗證

1. **核心服務**: 在 `MarketDataService` 註冊 Provider 的工廠方法。
2. **UI 確認**: 檢查「系統設定 -> 數據源」分頁渲染是否正常。
3. **測試要求**: 撰寫 Mock 測試，Provider 模組覆蓋率必須 **> 70%**。

---
*完成後請執行 `trunk-based-commit` 中的 Wiki Sync 流程同步架構變動。*
