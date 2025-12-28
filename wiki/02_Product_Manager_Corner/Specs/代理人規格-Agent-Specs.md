# AI Agent Swarm Specification (v3)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 AI Agent Swarm Specification (v3)

> **狀態**: 草稿 (Draft)
> **版本**: 1.1

### 1. 概觀 (Overview)
Agent Swarm (代理人集群) 由協作的多個專門 AI Agent 組成，負責生成投資策略。v3 版本引入了「被動/主動」模式；v4 版本引入了「板塊導向多階段工作流」。

### 2. 代理人角色與提示詞 (Agent Roles & Prompts)

#### 2.1 動能分析師 (Momentum Agent)
*   **角色**: 技術分析師 (Technical Analyst)。
*   **輸入**: 價格歷史, 成交量 (當日/均量), RSI, MACD, 均線 (SMA 20/50/200)。
*   **輸出**: 趨勢分析 (看多/看空), 支撐/壓力位, 量價分析。
*   **系統提示詞**: `prompts/momentum_agent.txt`

#### 2.2 基本面分析師 (Fundamental Agent)
*   **角色**: 基本面分析師 (Fundamental Analyst, 巴菲特風格)。
*   **輸入**: 財務報表 (10-K, 10-Q), 財報會議逐字稿。
*   **輸出**: 估值分析 (低估/高估), 成長驅動因子, 風險評估。

#### 2.3 總體經濟分析師 (Macro Agent)
*   **角色**: 全球宏觀策略師 (Global Macro Strategist)。
*   **輸入**: FRED 數據 (GDP, CPI, 失業率, 殖利率曲線)。
*   **輸出**: 經濟週期階段, 類股輪動建議。

#### 2.4 市場情緒分析師 (Sentiment Agent)
*   **角色**: 市場情緒分析師 (Market Sentiment Analyst)。
*   **輸入**: 新聞標題, 恐懼貪婪指數 (Fear & Greed), VIX 指數。
*   **輸出**: 市場情緒狀態 (恐慌/貪婪), 情緒分數 (0-100)。

#### 2.5 投資長 (CIO Agent - Chief Investment Officer)
*   **角色**: 投資組合經理與最終決策者 (Portfolio Manager & Decision Maker)。
*   **模式**:
    *   **戰略模式 (Strategy Mode)**: 分析板塊並篩選候選股。
    *   **報告模式 (Report Mode)**: 最終選股與報告撰寫。
*   **輸入**: 上述所有 Agent 的報告 + 使用者投資組合狀態。
*   **輸出**: 最終買/賣/持有決策, 資產配置調整建議。

### 3. 工具運用 (Tool Utilization)

#### 3.1 市場數據服務 (MarketDataService)
*   整合 `Alpha Vantage` 與 `FRED`。

#### 3.2 瀏覽器服務 (BrowserService)
*   **目的**: 獲取最新新聞或財報逐字稿 (Headless Chrome)。

### 4. 互動流程 (Interaction Flow v4 Sector-Driven)
1.  **全局戰略 (Step 1)**: `CIO Agent` (戰略模式) + `Macro Agent`。
    -   分析持倉板塊分佈 vs 總經環境。
    -   輸出: 目標進攻板塊 (Target Sectors)。
2.  **候選篩選 (Step 2)**: `CIO Agent` 篩選 15 檔候選股。
    -   **嚴格規則**: 不選 ETF。
    -   輸出: 15 檔股票代碼清單。
3.  **深度研究 (Step 3)**:
    -   系統針對 (現有持倉 + 候選股) 進行迴圈。
    -   平行執行 `Momentum Agent`, `Fundamental Agent` 與 `Sentiment Agent`。
4.  **最終報告 (Step 4)**: `CIO Agent` (報告模式)。
    -   綜合所有研究筆記。
    -   挑選 Top 3-5 精選標的。
    -   生成 HTML 報告。

### 5. 系統特性
*   **強制觸發**: 支援 `--force-report` 跳過新鮮度檢查。
*   **DSPy 優化 (v3)**:
    -   **Signatures**: 所有 Agent 使用強型別 DSPy Signatures 定義輸入/輸出。
    -   **BootstrapFewShot**: Momentum Agent 透過「預測誤差」(價格變動 vs 訊號) 指標進行自動優化。
    -   **Feedback Loop**: 每週驗證結果將反饋至 Optimizer，自動微調 Prompt。

## 🔗 相關連結 (See Also)
- [設計模式_工廠 (Factory Pattern)](wiki/05_Engineering_Handbook/設計模式_工廠-Factory-Pattern.md)
- [系統概觀 (System Overview)](wiki/04_Architect_View/系統概觀-System-Overview.md)

---

<a id="en"></a>

## 🇺🇸 AI Agent Swarm Specification (v3)

> **Status**: Draft
> **Version**: 1.0

### 1. Overview
A swarm of specialized AI Agents collaborating to generate investment strategies. v3 introduces **Passive/Active** modes and **Model Tiering** (Flash vs Deep).

### 2. Roles & Prompts

#### 2.1 Momentum Agent
*   **Role**: Technical Analyst.
*   **Input**: Price, Volume (Current/Avg), RSI, MACD, SMA (20/50/200).
*   **Output**: Trend (Bull/Bear), Support/Resistance, Volume Analysis.

#### 2.2 Fundamental Agent
*   **Role**: Fundamental Analyst (Value Investor).
*   **Input**: Financials (10-K), Transcripts.
*   **Output**: Valuation, Growth Drivers, Risks.

#### 2.3 Macro Agent
*   **Role**: Global Macro Strategist.
*   **Input**: FRED Data (GDP, CPI, Yields).
*   **Output**: Economic Cycle, Sector Rotation.

#### 2.4 Sentiment Agent (New)
*   **Role**: Market Sentiment Analyst.
*   **Input**: News Headlines, Fear & Greed Index, VIX.
*   **Output**: Market Mood (Panic/Euphoria), Sentiment Score (0-100).

#### 2.5 CIO Agent (Chief Investment Officer)
*   **Role**: Portfolio Manager & Decision Maker.
*   **Input**: Reports from above agents + Portfolio State.
*   **Output**: Buy/Sell/Hold decisions, Allocation.

### 3. Tool Utilization
*   **MarketDatum**: Alpha Vantage + FRED.
*   **Browser**: Headless Chrome for news/transcripts.

### 4. Interaction Flow (v4 Sector-Driven Workflow)
1.  **Global Strategy (Step 1)**: `CIO Agent` (Strategy Mode) + `Macro Agent`.
    -   Analyzes portfolio sector allocation vs macro environment.
    -   Output: Target Sectors (e.g., Financials, Energy).
2.  **Candidate Screening (Step 2)**: `CIO Agent` screens 15 candidates.
    -   **Strict Rule**: No ETFs.
    -   Output: List of 15 Ticker Symbols.
3.  **Deep Research (Step 3)**:
    -   System loops through (Holdings + Candidates).
    -   Executes `Momentum Agent`, `Fundamental Agent`, and `Sentiment Agent` in parallel.
4.  **Final Report (Step 4)**: `CIO Agent` (Report Mode).
    -   Synthesizes all research notes.
    -   Selects Top 3-5 Picks.
    -   Generates HTML Report.

### 5. Features
*   **Force Trigger**: `--force-report` to bypass freshness checks.
*   **Smart Freshness**: Hashes inputs to avoid re-running agents on same data.
*   **DSPy Optimization (v3)**:
    -   **Signatures**: All agents use typed DSPy signatures for structured input/output.
    -   **BootstrapFewShot**: Momentum Agent is auto-optimized using a "Prediction Error" metric (Price Change vs Signal).
    -   **Feedback Loop**: Weekly results are fed back into the Optimizer to refine prompts automatically.
