# AI Agent Swarm Specification (v3)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 AI Agent Swarm Specification (v3)

> **Status**: Draft
> **Version**: 1.0

### 1. Overview
A swarm of specialized AI Agents collaborating to generate investment strategies. v3 introduces **Passive/Active** modes and **Model Tiering** (Flash vs Deep).

### 2. Roles & Prompts

#### 2.1 Momentum Agent
*   **Role**: Technical Analyst.
*   **Input**: Price, Volume, RSI, MACD.
*   **Output**: Trend (Bull/Bear), Support/Resistance.

#### 2.2 Fundamental Agent
*   **Role**: Fundamental Analyst (Value Investor).
*   **Input**: Financials (10-K), Transcripts.
*   **Output**: Valuation, Growth Drivers, Risks.

#### 2.3 Macro Agent
*   **Role**: Global Macro Strategist.
*   **Input**: FRED Data (GDP, CPI, Yields).
*   **Output**: Economic Cycle, Sector Rotation.

#### 2.4 CIO Agent (Chief Investment Officer)
*   **Role**: Portfolio Manager & Decision Maker.
*   **Input**: Reports from above agents + Portfolio State.
*   **Output**: Buy/Sell/Hold decisions, Allocation.

### 3. Tool Utilization
*   **MarketDatum**: Alpha Vantage + FRED.
*   **Browser**: Headless Chrome for news/transcripts.

### 4. Interaction Flow (v3 Event-Driven)
1.  **Trigger**: Market Close or News.
2.  **Flash Scan**: Agents run in low-cost mode.
3.  **Filter**: `LightCIO` decides if a full report is needed.
4.  **Deep Dive**: `DeepCIO` assigns tasks.
5.  **Synthesis**: Final Report.

---

<a id="traditional-chinese"></a>

## 🇹🇼 AI Agent Swarm Specification (v3)

> **狀態**: 草稿 (Draft)
> **版本**: 1.0

### 1. 概觀 (Overview)
Agent Swarm (代理人集群) 由協作的多個專門 AI Agent 組成，負責生成投資策略。v3 版本引入了「被動/主動 (Passive/Active)」模式以及「模型分級 (Model Tiering)」(Flash vs Deep)。

### 2. 代理人角色與提示詞 (Agent Roles & Prompts)

#### 2.1 動能分析師 (Momentum Agent)
*   **角色**: 技術分析師 (Technical Analyst)。
*   **輸入**: 價格歷史, 成交量, RSI, MACD。
*   **輸出**: 趨勢分析 (看多/看空), 支撐/壓力位。
*   **系統提示詞**: `prompts/momentum_agent.txt`

#### 2.2 基本面分析師 (Fundamental Agent)
*   **角色**: 基本面分析師 (Fundamental Analyst, 巴菲特風格)。
*   **輸入**: 財務報表 (10-K, 10-Q), 財報會議逐字稿。
*   **輸出**: 估值分析 (低估/高估), 成長驅動因子, 風險評估。

#### 2.3 總體經濟分析師 (Macro Agent)
*   **角色**: 全球宏觀策略師 (Global Macro Strategist)。
*   **輸入**: FRED 數據 (GDP, CPI, 失業率, 殖利率曲線)。
*   **輸出**: 經濟週期階段, 類股輪動建議。

#### 2.4 投資長 (CIO Agent - Chief Investment Officer)
*   **角色**: 投資組合經理與最終決策者 (Portfolio Manager & Decision Maker)。
*   **輸入**: 上述所有 Agent 的報告 + 使用者投資組合狀態。
*   **輸出**: 最終買/賣/持有決策, 資產配置調整建議。

### 3. 工具運用 (Tool Utilization)

#### 3.1 市場數據服務 (MarketDataService)
*   整合 `Alpha Vantage` 與 `FRED`。

#### 3.2 瀏覽器服務 (BrowserService)
*   **目的**: 獲取最新新聞或財報逐字稿 (Headless Chrome)。

### 4. 互動流程 (Interaction Flow v3 Event-Driven)
1.  **觸發 (Trigger)**: 每日收盤或重大新聞事件。
2.  **快速掃描 (Flash Scan)**: Agents 以 `Flash Mode` (低成本) 運行。
3.  **過濾 (Filter)**: `LightCIO` 判斷是否需要完整報告。
4.  **深度研究 (Deep Dive)**: 若需要，`DeepCIO` 指派特定的「深度研究」任務給 Agent。
5.  **整合 (Synthesis)**: 生成最終策略報告。
