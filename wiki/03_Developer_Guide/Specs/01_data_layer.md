# 資料層規格 (Data Layer Specification) v3

> **狀態**: 已核准 (Approved)
> **版本**: 3.0 (對齊 v3 架構)

## 1. 概觀 (Overview)
資料層負責攝取、標準化以及儲存來自各種來源的金融數據。v3 版本引入了 **事件日誌 (Event Logs)** 與 **手動輸入 (Manual Inputs)** 以支援事件驅動架構 (Event-Driven Architecture)。

## 2. 攝取架構 (Ingestion Architecture)

我們使用 **策略模式 (Strategy Pattern)** 進行數據攝取：
*   `TradeIngestor` (抽象基底類別): 定義合約介面 `ingest(file_path, user_id)`。
*   `RobinhoodIngestor`: 實作 Robinhood CSV 格式的解析邏輯。
*   `IBKRIngestor`: 實作 Interactive Brokers (盈透證券) CSV 格式的解析邏輯。
*   `CSVIngestor`: 實作簡易標準 CSV 格式的解析邏輯。

### 工廠模式 (Factory)
`IngestorFactory` 負責根據提供的字串 (provider string) 將請求路由至對應的 Ingestor。

## 3. CSV 格式 (CSV Formats)

### 簡易標準格式 (Simple Format)
```csv
ticker,quantity,cost
AAPL,10,150.0
TSLA,5,200.0
```

### Robinhood 格式 (標準匯出)
常見欄位包含：`state`, `symbol`, `date`, `side`, `quantity`, `price`, `fees`。

### IBKR 格式 (Flex Query)
常見欄位包含：`Type`, `Symbol`, `Date/Time`, `Quantity`, `T. Price`, `Comm/Fee`。

## 4. 資料庫模式 (Database Schema) v3

定義於 `src/data/database.py`。主要新增：
*   **event_logs**: 供 `LightCIO` 記錄被忽略的事件。
*   **manual_inputs**: 供使用者注入 PDF/文字報告以進行分析。
*   **agent_knowledge**: 用於持久化特定 Agent 的洞察 (Insights)。
