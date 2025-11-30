# 數據層規格 (Data Layer Specification)

本文件定義了投資平台如何處理異質交易數據的攝取、標準化與儲存。

## 1. 資料庫架構 (Database Schema)

資料庫採用 SQLite，檔案位於 `data/portfolio.db`。

### 1.1 Transactions Table (交易紀錄)
儲存所有原始交易紀錄。

| 欄位名稱 | 數據類型 | 說明 |
| :--- | :--- | :--- |
| `id` | TEXT (UUID) | Primary Key, 唯一識別碼 |
| `ticker` | TEXT | 標準化代碼 (e.g., AAPL, BTC-USD) |
| `trade_date` | TEXT (ISO8601) | 交易執行時間 (UTC) |
| `action` | TEXT | BUY, SELL, SHORT, COVER, OPTION_OPEN, OPTION_CLOSE |
| `quantity` | REAL | 交易數量 |
| `price` | REAL | 單位成交價格 |
| `fees` | REAL | 手續費與稅金 |
| `amount` | REAL | 總金額 (Quantity * Price + Fees) |
| `currency` | TEXT | 幣別 (USD, TWD) |
| `source_file` | TEXT | 來源 CSV 檔名 |
| `raw_data` | TEXT (JSON) | 原始 CSV 行數據備份 |

### 1.2 Positions Table (持倉)
儲存當前持倉狀態，由 Transactions 計算得出。

| 欄位名稱 | 數據類型 | 說明 |
| :--- | :--- | :--- |
| `ticker` | TEXT | Primary Key |
| `quantity` | REAL | 剩餘持股數 |
| `avg_cost` | REAL | 平均成本 |
| `current_price` | REAL | 最新市價 (由 Market Data Agent 更新) |
| `market_value` | REAL | 市值 |
| `unrealized_pl` | REAL | 未實現損益 |

### 1.3 CashFlow Table (現金流)
記錄非交易性的資金變動。

| 欄位名稱 | 數據類型 | 說明 |
| :--- | :--- | :--- |
| `id` | TEXT (UUID) | Primary Key |
| `date` | TEXT (ISO8601) | 發生時間 |
| `amount` | REAL | 金額 (+ 為入金/股息, - 為出金) |
| `type` | TEXT | DEPOSIT, WITHDRAWAL, DIVIDEND, INTEREST |
| `description` | TEXT | 備註 |

## 2. 數據攝取 (Data Ingestion)

### 2.1 支援格式
系統必須支援以下券商的匯出格式：

#### Robinhood
- **特徵**: 混合股票與選擇權，欄位包含 `chain_symbol`, `expiration_date`, `side`, `order_created_at`。
- **處理邏輯**:
    - 過濾 `state` 為 `filled` 的訂單。
    - 區分 `Equity` 與 `Option`。
    - 選擇權需計算 Delta 等風險參數 (Phase 2)。

#### Interactive Brokers (IBKR)
- **特徵**: 包含 `Symbol`, `Date/Time`, `Quantity`, `T. Price`, `Comm/Fee`。
- **處理邏輯**:
    - 識別 `Asset Class` (Stock, Future, Option)。
    - 分離 `Dividends` 至 CashFlow 表。
    - 處理 `Split` (股票分割) 紀錄。

### 2.2 攝取流程
1. 掃描 `data/raw_csv/` 目錄下的新檔案。
2. 根據檔名或檔頭 (Header) 自動識別券商格式。
3. 解析每一行，轉換為 `Transaction` 或 `CashFlow` 物件。
### 2.3 簡易股票代碼清單 (Simple Ticker List)
- **特徵**: 僅包含 `ticker` 欄位，或 `ticker, quantity, cost`。
- **處理邏輯**:
    - 若僅有 `ticker`，視為關注清單 (Watchlist) 或持倉數量未知的資產。
    - 預設 `quantity=0`, `price=0`，僅用於讓 Agent 進行分析建議，不計入 ROI 計算。
    - 支援格式:
        ```csv
        ticker
        AAPL
        NVDA
        ```
