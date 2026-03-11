# 數據源矩陣管理 (Data Source Matrix) 架構指南

本作旨在釐清系統中 15+ 種異質數據源，如何從前端 **UI 配置** 貫串到 **Sentinel 哨兵架構**，最終落實至 **系統程式設計** 介面的全自動化數據處理生命週期。

> **設計哲學**: 將分散的外部世界數據，透過統一的配置介面與雙軌聚合（輪詢 Polling + 事件驱动 Webhooks）收斂至 Sentinel，形成具備高度擴充性的環境感知雷達。

---

## 🏗️ 1. 雙軌數據流架構 (Dual-Track Data Flow architecture)

為解決 API 呼叫成本與即時性的矛盾，Sentinel 採用雙軌模式攝取大數據：

```mermaid
graph TD
    classDef ui fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef polling fill:#dcf8c6,stroke:#2b4c7e,stroke-width:2px;
    classDef webhook fill:#fff3cd,stroke:#ff8f00,stroke-width:2px;
    classDef sentinel fill:#e1bee7,stroke:#5e35b1,stroke-width:2px;

    UI[🖥️ Dashboard:"Settings > Data Sources]:::ui"
    
    subgraph "Track 1:"Active Polling (Scheduled)""
        P_FRED[FRED]:::polling
        P_FD[FinancialData.Net]:::polling
        P_AV[Alpha Vantage]:::polling
        P_Readwise[Readwise]:::polling
        P_Crypto[Crypto Metrics]:::polling
        
        P_FRED & P_FD & P_AV & P_Readwise & P_Crypto -->"|Interval Tick| CS[SentinelService._check_active_sources]"
    end
    
    subgraph "Track 2:"Event-Driven Webhooks (Real-time)""
        W_TV[TradingView]:::webhook
        W_Zapier[Zapier / SEC]:::webhook
        W_Github[GitHub Ops]:::webhook
        W_IFTTT[IFTTT Broker]:::webhook
        
        W_TV & W_Zapier & W_Github & W_IFTTT -->"|FastAPI Endpoint| MCP[MCP Server / webhook]"
    end
    
    UI -.->|Saves Enabled State & Keys| DB["(Settings Storage")]
    CS -.->|Reads Keys| DB
    
    CS -->"SENTINEL((🦅 Sentinel Core Engine)):::sentinel"
    MCP -->"|process_event()| SENTINEL"
    
    SENTINEL -->"|Aggregate & Escalate| COUNCIL_ATS[Council Or ATS Auto-Hedge]"
```

---

## 🧭 2. 矩陣群組映射 (Matrix Domain Mapping)

以下整理不同層級的數據源，從 UI 上的分類一路對應到 Python 的負責模組。所有開關皆透由前台 `Settings` 控制，底層鍵值規則為 `source_{id}_enabled` 與 `source_{id}_api_key`。

### 📊 總體經濟 (Macro - P0)

用於捕捉市場體制切換 (Regime Shift) 的基石。

| Data Source | UI ID | Trigger Type | Implementation Logic | Target Module |
| :--- | :--- | :--- | :--- | :--- |
| **FRED** | `fred` | Polling | `_check_macro_shifts()` 抓取 10年公債、通膨數據。 | `FredProvider` |
| **Alpha Vantage** | `alpha_vantage` | Polling | `_poll_single_source()` 驗證聯通與新聞。 | `MarketDataService` |

### 📈 市場行情與實盤傳輸 (Market & Execution - P1)

高頻、低延遲的報價與下單通道。

| Data Source | UI ID | Trigger Type | Implementation Logic | Target Module |
| :--- | :--- | :--- | :--- | :--- |
| **Futu (富途)** | `futu` | Legacy | [DEPRECATED] v5.0 移除 `futu-api` 依賴。 | N/A |
| **Polygon.io** | `polygon` | Live | [官網](https://polygon.io/) | `MarketDataService` |
| **FinancialData.Net** | `financialdata` | Polling | [官網](https://financialdata.net/) | `FinancialDataProvider` |
| **Alpaca** | `alpaca` | Live | [官網](https://app.alpaca.markets/) | BrokerFactory / ATS |

### 🏢 財報與個股基本面 (Fundamental - P0)

Council Agent 進行估值與護城河辯論的彈藥存儲。

| Data Source | UI ID | Trigger Type | Implementation Logic | Target Module |
| :--- | :--- | :--- | :--- | :--- |
| **FMP** | `fmp` | Polling | Fundamental 提問深掘，獲取 DCF 模型。 | `FmpProvider` |
| **Yahoo Finance** | `yahoo_finance` | Polling | 無密鑰快速歷史資料回測 | `MarketDataService` |

### 📰 情感與即時新聞 (Sentiment & News - P2)

用於加權關鍵字異常偵測與輿論壓力測試。

| Data Source | UI ID | Trigger Type | Implementation Logic | Target Module |
| :--- | :--- | :--- | :--- | :--- |
| **Finnhub** | `finnhub` | Polling | 抓取 AI 情緒聚合分數。 | `MarketDataService` |
| **Tiingo** | `tiingo` | Polling | 提取標籤化 (Tagged) 新聞。 | `MarketDataService` |
| **NewsAPI / Tavily** | `news_api` / `tavily` | Polling | 執行 `_check_breaking_news()` 並對照資料庫加權字典。 | `TavilySearchService` |
| **Readwise** | `readwise` | Polling | `_poll_single_source("readwise")`，非同步調用 LLM 過濾畫線，產生 Insight。 | `ReadwiseService` |

### ⛓️ 加密與鏈上監控 (Crypto & On-chain)

早期預警市場資金板塊輪動。

| Data Source | UI ID | Trigger Type | Implementation Logic | Target Module |
| :--- | :--- | :--- | :--- | :--- |
| **CryptoPanic** | `cryptopanic` | Polling | 抓取幣圈恐慌指數。 | `SentinelService/_poll_single_source` |
| **Fear & Greed** | `alternative_me` | Polling | 值 < 25 或 > 75 觸發 `fng_extreme` 警報。 | `SentinelService/_poll_single_source` |
| **Whale Alert** | `whale_alert` | Polling | 捕獲鏈上異動。 | `SentinelService/_poll_single_source` |

### ⚡ 事件驅動 Webhooks (Event-Driven Triggers)

低成本、被動攔截外部推播的擴充槽。此類別不在 UI 中填寫 API Key，而是填寫接收用的 `Webhook Secret`。

| Trigger Event | UI ID | Trigger Type | Handling Method | Escalation |
| :--- | :--- | :--- | :--- | :--- |
| **TradingView Alert** | `webhook_tradingview` | Webhook | 由 MCP 接收，注入 `process_event(source='tv')` | 直接拉起 ATS，或交回 Council 辯論 |
| **Make.com / Reddit**| `webhook_make_social` | Webhook | 由 MCP 接收，注入 `process_event(source='make')` | 總結為突發新聞維度 |
| **Zapier (SEC 報告)**| `webhook_zapier_sec` | Webhook | `process_event(source='earnings_call')` 引發供應鏈檢驗 | 生成 `earnings_sc_impact` 報告 |
| **GitHub Ops** | `webhook_github` | Webhook | `process_event(source='github')` | 通知 Vibe Coding Agent |

---

## 🛠️ 3. 程式碼組件深潛 (Code Implementation Walkthrough)

若要新增或除錯一個新的數據源，需理解以下三個代碼斷點：

### 1️⃣ 統一設定註冊 (Central Registry `data_source_matrix_config.py`)

**This is the Single Source of Truth**. 新增任何數據源，只需在 `src/config/data_source_matrix_config.py` 的 `DATA_SOURCE_GROUPS` 中定義：
這是不二法門 (Single Source of Truth)。新增任何數據源，只需在此處定義：

```python
{
    "id": "new_source_id",
    "name": "Display Name",
    "desc": "Short description shown in UI",
    "fields": {"api_key": {"label": "API Key", "type": "password"}},
    "type": "polling" # 'polling' or 'webhook'
}
```

UI (`data_sources_tab.py`) 會自動讀取並生成 Switch 元件，開啟時寫入 `source_{new_source_id}_enabled = "true"` 到 Settings Storage。

### 2️⃣ Sentinel 自動輪詢綁定 (`sentinel_service.py`)

`SentinelService._check_active_sources()` 採用動態載入。開發者需確保 API 金鑰遵循系統統一命名規範：`source_{id}_{field}`。

```python
async def _poll_single_source(self, sid: str, settings: Dict[str, str]):
    # 統一使用小寫 snake_case 鍵名讀取
    api_key = settings.get(f"source_{sid}_api_key") 
    
    if sid == "financialdata":
        # 呼叫 FinancialDataProvider...
        pass
```

### 3️⃣ Webhook 被動攔截 (`mcp_service/` & `sentinel_service.py`)

不透過 Polling，而是由外部打入 `/webhook/{source}` 端點。MCP Server 驗證 Secret 後，將 JSON payload 直接塞進 `SentinelService.process_event(event)`。Sentinel 會強制中斷睡眠，提煉警語 (`msg`, `ticker`) 並執行 `_escalate()`。
