# AI Agent Swarm Specification (v3)

> **狀態**: 草稿 (Draft)
> **版本**: 1.0

## 1. 概觀 (Overview)
Agent Swarm (代理人集群) 由協作的多個專門 AI Agent 組成，負責生成投資策略。v3 版本引入了「被動/主動 (Passive/Active)」模式以及「模型分級 (Model Tiering)」(Flash vs Deep)。

## 2. 代理人角色與提示詞 (Agent Roles & Prompts)

### 2.1 動能分析師 (Momentum Agent)
*   **角色**: 技術分析師 (Technical Analyst)。
*   **輸入**: 價格歷史, 成交量, RSI, MACD。
*   **輸出**: 趨勢分析 (看多/看空), 支撐/壓力位。
*   **系統提示詞**: `prompts/momentum_agent.txt`
    *   *Persona*: "你是一位資深的技術交易員..."
    *   *限制*: 必須引用具體的技術指標數值。

### 2.2 基本面分析師 (Fundamental Agent)
*   **角色**: 基本面分析師 (Fundamental Analyst)。
*   **輸入**: 財務報表 (10-K, 10-Q), 財報會議逐字稿 (透過 Browser 獲取)。
*   **輸出**: 估值分析 (低估/高估), 成長驅動因子, 風險評估。
*   **系統提示詞**: `prompts/fundamental_agent.txt`
    *   *Persona*: "你是一位紀律嚴明的價值投資者 (巴菲特/蒙格風格)..."

### 2.3 總體經濟分析師 (Macro Agent)
*   **角色**: 全球宏觀策略師 (Global Macro Strategist)。
*   **輸入**: FRED 數據 (GDP, CPI, 失業率, 殖利率曲線)。
*   **輸出**: 經濟週期階段, 類股輪動建議。
*   **系統提示詞**: `prompts/macro_agent.txt`
    *   *Persona*: "你是一位觀察聯準會動向的全球宏觀策略師..."

### 2.4 投資長 (CIO Agent - Chief Investment Officer)
*   **角色**: 投資組合經理與最終決策者 (Portfolio Manager & Decision Maker)。
*   **輸入**: 上述所有 Agent 的報告 + 使用者投資組合狀態。
*   **輸出**: 最終買/賣/持有決策, 資產配置調整建議。
*   **系統提示詞**: `prompts/cio_agent.txt`
    *   *邏輯*: 權衡反對意見。優先考慮資本保全 (Capital Preservation)。

## 3. 工具運用 (Tool Utilization)

### 3.1 市場數據服務 (MarketDataService - 增強版)
*   若有需要，整合 `Alpha Vantage` 以獲取更細粒度的數據。
*   新增 `FRED` 客戶端供 Macro Agent 使用。

### 3.2 瀏覽器服務 (BrowserService - 新增)
*   **目的**: 當 `yfinance` 資訊不足時，獲取最新新聞或財報逐字稿。
*   **實作**: Headless Chrome (初期使用簡單的 `requests` + `BeautifulSoup`，必要時升級至 `playwright`)。

## 4. 互動流程 (Interaction Flow v3 Event-Driven)

1.  **觸發 (Trigger)**: 每日收盤或重大新聞事件。
2.  **快速掃描 (Flash Scan)**: Agents 以 `Flash Mode` (低成本) 運行。
3.  **過濾 (Filter)**: `LightCIO` 判斷是否需要完整報告。
4.  **深度研究 (Deep Dive)**: 若需要，`DeepCIO` 指派特定的「深度研究」任務給 Agent。
5.  **整合 (Synthesis)**: 生成最終策略報告。
