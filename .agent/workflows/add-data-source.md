---
description: 建立與串接新數據源的標準化流程 (Standardized workflow for adding new data sources)
---

# /add-data-source 工作流

此工作流定義了在 AI Investment Advisor 中新增數據源的標準步驟，確保代碼品質、UI 一致性與測試覆蓋率。

## 執行步驟 (Workflow Steps)

### 1. 配置註冊 (Configuration Registration)

- **檔案路徑**: `src/config/data_source_matrix_config.py`
- **操作**: 將新數據源加入 `DATA_SOURCE_GROUPS`。
- **必要欄位**:
  - `id`: 唯一識別碼 (snake_case)
  - `name`: 顯示名稱
  - `url`: **官方設置/文檔連結** (必須提供)
  - `desc`: 繁體中文功能描述，說明此數據用於系統何處
  - `trigger_type`: `polling` (哨兵主動抓取), `live` (實盤流), 或 `webhook`
  - `fields`: API Key 或連線參數定義。**注意：系統會自動生成 `source_{id}_{field_key}` 格式的儲存鍵名。**

### 2. 實作 Data Provider

- **檔案路徑**: `src/data/providers/[provider_name]_provider.py`
- **操作**: 繼承 `BaseDataProvider` 並實作必要方法。
- **規範**:
  - **金鑰讀取**: 必須透過 `SettingsService.get("source_[id]_[field]")` 讀取。
  - **嚴禁**: 嚴禁在代碼中寫死大寫金鑰名 (如 `POLYGON_API_KEY`)，除非是作為本地開發的極少數 Fallback。
  - 實作錯誤處理與 Rate Limit 緩衝邏輯。

### 3. 整合至核心服務

- **操作**: 在 `MarketDataService` 或相關 Service 註冊此 Provider 的工廠方法。
- **檢查點**: 確保哨兵 (Sentinel) 能識別並輪詢此來源。

### 4. 儀表板 UI 確認 (Frontend Verification)

- **操作**: 檢查「系統設定 -> 數據源」頁面是否正確渲染。
- **提示**: `data_sources_tab.py` 會自動讀取配置，通常無需額外修改代碼，但須確認 UI 排版是否正常。

### 5. 自動化測試要求 (Mandatory Testing)

- **操作**: 撰寫對應的 Mock 測試。
- **指標**: 該 Provider 模組的測試覆蓋率必須 **> 70%**。

## 注意事項

- 嚴禁寫死 (Hardcode) 任何 API 密鑰。
- 必須遵循「動態指標原則」，若涉及閾值設定需可經由 `SettingsService` 調整。
- 提交前請執行 `/walkthrough-wiki-sync` 同步架構變動。
